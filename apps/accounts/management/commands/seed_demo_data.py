from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Company, User
from apps.finance.configuration_services import ensure_finance_settings
from apps.finance import budget_services, matching_services, payment_services, services as finance_services
from apps.finance.ledger_services import ensure_ledger_configuration
from apps.finance.models import Account, BudgetCategory, CostCentre, Currency, Payment, ProjectBudget, SupplierInvoice
from apps.materials.models import Category, Material
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem, PurchaseRequest, PurchaseRequestItem
from apps.procurement.services import record_goods_received_note
from apps.projects.models import Project
from apps.suppliers.models import Supplier
from apps.warehouse.models import StockMovement


class Command(BaseCommand):
    help = 'Seed repeatable multi-company demo data for ConstructSaaS.'

    PASSWORD = 'Demo123!'
    DEMO_COMPANIES = (
        {
            'name': 'Nile Construct Uganda Ltd',
            'slug': 'nile-construct-uganda-ltd',
            'username_prefix': 'demo',
            'email_domain': 'nileconstruct.ug',
        },
        {
            'name': 'Kampala Metro Builders Ltd',
            'slug': 'kampala-metro-builders-ltd',
            'username_prefix': 'metro',
            'email_domain': 'kampalametro.ug',
        },
    )

    def handle(self, *args, **options):
        with transaction.atomic():
            demo_accounts = []
            for company_data in self.DEMO_COMPANIES:
                company = self.create_company(company_data)
                users = self.create_users(company, company_data)
                self.create_finance_baseline(company)
                categories = self.create_categories(company)
                materials = self.create_materials(company, categories)
                projects = self.create_projects(company, users)
                suppliers = self.create_suppliers(company)
                self.create_stock_movements(company, users, materials, projects)
                self.create_procurement_data(company, users, materials, projects, suppliers)
                if company_data['username_prefix'] == 'demo':
                    self.create_finance_demo(company, users, projects)
                demo_accounts.extend((company.name, username, role) for username, role in self.demo_accounts(company_data))

        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))
        self.stdout.write('')
        self.stdout.write('Login credentials:')
        for company_name, username, role in demo_accounts:
            self.stdout.write(f'- {company_name} / {role}: {username} / {self.PASSWORD}')

    def demo_accounts(self, company_data):
        prefix = company_data['username_prefix']
        return [
            (f'{prefix}_admin', 'Admin'),
            (f'{prefix}_engineer', 'Site Engineer'),
            (f'{prefix}_store', 'Storekeeper'),
            (f'{prefix}_manager', 'Project Manager'),
            (f'{prefix}_procurement', 'Procurement Officer'),
            (f'{prefix}_finance_officer', 'Finance Officer'),
            (f'{prefix}_finance_manager', 'Finance Manager'),
            (f'{prefix}_finance_viewer', 'Finance Viewer'),
        ]

    def create_company(self, company_data):
        company, created = Company.objects.get_or_create(
            name=company_data['name'],
            defaults={'slug': company_data['slug']},
        )
        if not created:
            company.is_active = True
            company.save(update_fields=['is_active', 'updated_at'])
        return company

    def create_users(self, company, company_data):
        prefix = company_data['username_prefix']
        email_domain = company_data['email_domain']
        users_data = [
            (f'{prefix}_admin', 'Admin', User.ROLE_ADMIN, True, True, f'admin@{email_domain}'),
            (f'{prefix}_engineer', 'Peter', User.ROLE_SITE_ENGINEER, False, False, f'engineer@{email_domain}'),
            (f'{prefix}_store', 'Moses', User.ROLE_STOREKEEPER, False, False, f'store@{email_domain}'),
            (f'{prefix}_manager', 'Sarah', User.ROLE_PROJECT_MANAGER, False, False, f'manager@{email_domain}'),
            (f'{prefix}_procurement', 'David', User.ROLE_PROCUREMENT_OFFICER, False, False, f'procurement@{email_domain}'),
            (f'{prefix}_finance_officer', 'Amina', User.ROLE_FINANCE_OFFICER, False, False, f'finance.officer@{email_domain}'),
            (f'{prefix}_finance_manager', 'Grace', User.ROLE_FINANCE_MANAGER, False, False, f'finance.manager@{email_domain}'),
            (f'{prefix}_finance_viewer', 'Noah', User.ROLE_FINANCE_VIEWER, False, False, f'finance.viewer@{email_domain}'),
        ]
        users = {}
        for username, first_name, role, is_staff, is_superuser, email in users_data:
            user, _ = User.objects.get_or_create(username=username)
            user.company = company
            user.first_name = first_name
            user.last_name = 'Demo'
            user.email = email
            user.phone = '+256700000000'
            user.role = role
            user.is_staff = is_staff or role == User.ROLE_ADMIN
            user.is_superuser = is_superuser or role == User.ROLE_ADMIN
            user.is_active = True
            user.set_password(self.PASSWORD)
            user.save()
            users[role] = user
        return users

    def create_finance_baseline(self, company):
        ensure_finance_settings(company)
        Currency.objects.get_or_create(
            company=company,
            code='USD',
            defaults={'name': 'US Dollar', 'symbol': '$', 'decimal_places': 2, 'is_active': True},
        )
        ensure_ledger_configuration(company)

    def create_finance_demo(self, company, users, projects):
        """Create a complete, idempotent USD purchase-to-payment demonstration."""
        project = projects['PRJ-NTD-001']
        cost_centre, _ = CostCentre.objects.get_or_create(
            company=company, code='SITE-NTD',
            defaults={'name': 'Ntinda Apartment Block', 'project': project},
        )
        category, _ = BudgetCategory.objects.get_or_create(
            company=company, code='MATERIALS',
            defaults={'name': 'Construction materials', 'cost_centre': cost_centre},
        )
        budget = ProjectBudget.objects.filter(company=company, name='FY26 Ntinda materials budget').first()
        if not budget:
            budget = budget_services.create_project_budget(
                user=users[User.ROLE_FINANCE_OFFICER], project=project,
                name='FY26 Ntinda materials budget',
                lines=[{'category': category, 'description': 'Materials procurement', 'original_amount': Decimal('150000000.00')}],
            )
            budget_services.submit_project_budget(budget=budget, user=users[User.ROLE_FINANCE_OFFICER])
            budget_services.approve_project_budget(
                budget=budget, user=users[User.ROLE_FINANCE_MANAGER], comments='Approved demo project budget.',
            )
        line = budget.lines.get(category=category)
        purchase_request = PurchaseRequest.objects.get(company=company, number='PR-20260726-0003')
        if not hasattr(purchase_request, 'budget_approval'):
            budget_services.submit_purchase_request_to_finance(
                purchase_request=purchase_request, user=users[User.ROLE_PROJECT_MANAGER], budget_line=line,
                comments='Submit approved materials request for finance clearance.',
            )
            budget_services.review_purchase_request_finance(
                purchase_request=purchase_request, user=users[User.ROLE_FINANCE_MANAGER],
                decision='APPROVED', comments='Within the approved materials budget.',
            )
        purchase_order = PurchaseOrder.objects.get(company=company, number='PO-20260726-0002')
        if purchase_order.status == PurchaseOrder.STATUS_PENDING:
            purchase_order = budget_services.approve_purchase_order(
                purchase_order=purchase_order, user=users[User.ROLE_PROCUREMENT_OFFICER],
            )
        if purchase_order.status != PurchaseOrder.STATUS_RECEIVED:
            purchase_order, _ = record_goods_received_note(
                purchase_order=purchase_order, user=users[User.ROLE_STOREKEEPER],
                receipt_date=timezone.localdate(), notes='Demo warehouse receipt for USD supplier invoice.',
            )
        invoice = SupplierInvoice.objects.filter(company=company, invoice_number='USD-DEMO-001').first()
        if not invoice:
            item = purchase_order.items.select_related('material').first()
            invoice = finance_services.create_supplier_invoice(
                company=company, user=users[User.ROLE_FINANCE_OFFICER], purchase_order=purchase_order,
                supplier=purchase_order.supplier, invoice_number='USD-DEMO-001', invoice_date=timezone.localdate(),
                currency='USD', exchange_rate=Decimal('4000.000000'), idempotency_key='demo-usd-invoice-v1',
                items=[{'purchase_order_item': item, 'quantity': item.quantity, 'unit_price': Decimal('13.00'), 'taxes': []}],
            )
            invoice = finance_services.submit_invoice(invoice=invoice, user=users[User.ROLE_FINANCE_OFFICER])
            matching_services.run_invoice_match(invoice=invoice, user=users[User.ROLE_FINANCE_OFFICER], idempotency_key='demo-usd-match-v1')
            invoice = finance_services.approve_invoice(invoice=invoice, user=users[User.ROLE_FINANCE_MANAGER])
            finance_services.post_invoice(
                invoice=invoice, user=users[User.ROLE_FINANCE_MANAGER], idempotency_key='demo-usd-invoice-post-v1',
            )
            invoice = SupplierInvoice.objects.get(company=company, invoice_number='USD-DEMO-001')
        if not Payment.objects.filter(company=company, reference='DEMO-USD-PAY-001').exists():
            cash = ensure_ledger_configuration(company)[Account.SYSTEM_CASH]
            usd = Currency.objects.get(company=company, code='USD')
            payment = payment_services.create_payment(
                user=users[User.ROLE_FINANCE_OFFICER], supplier=invoice.supplier, source_account=cash,
                currency=usd, amount=invoice.total_amount, payment_date=timezone.localdate(), method=Payment.METHOD_BANK,
                exchange_rate=Decimal('4100.000000'), reference='DEMO-USD-PAY-001',
                voucher_reference='USD-DEMO-VOUCHER', notes='Demo USD payment with realized FX.',
                idempotency_key='demo-usd-payment-v1',
            )
            payment_services.allocate_payment(payment=payment, user=users[User.ROLE_FINANCE_OFFICER], invoice=invoice, amount=invoice.total_amount)
            payment = payment_services.submit_payment(payment=payment, user=users[User.ROLE_FINANCE_OFFICER])
            payment = payment_services.approve_payment(payment=payment, user=users[User.ROLE_FINANCE_MANAGER])
            payment_services.post_payment(payment=payment, user=users[User.ROLE_FINANCE_MANAGER], idempotency_key='demo-usd-payment-post-v1')

    def create_categories(self, company):
        category_data = {
            'Cement & Concrete': 'Cement, concrete, and binding materials.',
            'Steel & Reinforcement': 'Reinforcement bars and steel products.',
            'Aggregates': 'Murram, hardcore, river sand, and related fills.',
            'Timber & Roofing': 'Timber, iron sheets, and roofing products.',
            'Finishes': 'Tiles and other finishing materials.',
        }
        categories = {}
        for name, description in category_data.items():
            category, _ = Category.objects.update_or_create(
                company=company,
                name=name,
                defaults={'description': description},
            )
            categories[name] = category
        return categories

    def create_materials(self, company, categories):
        material_data = [
            ('Hima Cement (50kg)', 'CEM-001', 'Cement & Concrete', Material.UNIT_BAG, '38000.00', '120.00'),
            ('Tororo Cement (50kg)', 'CEM-002', 'Cement & Concrete', Material.UNIT_BAG, '36000.00', '100.00'),
            ('Y12 Reinforcement Bar', 'STL-012', 'Steel & Reinforcement', Material.UNIT_PIECE, '28500.00', '50.00'),
            ('Y16 Reinforcement Bar', 'STL-016', 'Steel & Reinforcement', Material.UNIT_PIECE, '42500.00', '40.00'),
            ('Murram', 'AGG-001', 'Aggregates', Material.UNIT_CBM, '45000.00', '30.00'),
            ('Hardcore', 'AGG-002', 'Aggregates', Material.UNIT_CBM, '60000.00', '25.00'),
            ('River Sand', 'AGG-003', 'Aggregates', Material.UNIT_CBM, '70000.00', '20.00'),
            ('Timber 4x2', 'TIM-001', 'Timber & Roofing', Material.UNIT_PIECE, '25000.00', '80.00'),
            ('Iron Sheets 3m', 'ROF-001', 'Timber & Roofing', Material.UNIT_PIECE, '52000.00', '60.00'),
            ('Floor Tiles 60x60', 'FIN-001', 'Finishes', Material.UNIT_SQM, '48000.00', '40.00'),
        ]
        materials = {}
        for name, code, category_name, unit, unit_price, min_stock in material_data:
            material, _ = Material.objects.update_or_create(
                company=company,
                code=code,
                defaults={
                    'category': categories[category_name],
                    'name': name,
                    'unit': unit,
                    'unit_price': Decimal(unit_price),
                    'min_stock_level': Decimal(min_stock),
                    'description': f'Demo stock item for {name}.',
                    'is_active': True,
                },
            )
            materials[code] = material
        return materials

    def create_projects(self, company, users):
        today = timezone.localdate()
        projects_data = [
            {
                'name': 'Ntinda Apartment Block',
                'code': 'PRJ-NTD-001',
                'client': 'Kampala Homes Ltd',
                'location': 'Ntinda, Kampala',
                'description': 'Mid-rise apartment construction project.',
                'budget': Decimal('850000000.00'),
                'status': Project.STATUS_ACTIVE,
                'manager': users[User.ROLE_PROJECT_MANAGER],
                'site_engineers': [users[User.ROLE_SITE_ENGINEER]],
                'start_date': today.replace(month=5, day=15),
                'end_date': today.replace(month=11, day=30),
                'is_active': True,
            },
            {
                'name': 'Jinja Road Commercial Plaza',
                'code': 'PRJ-JRD-002',
                'client': 'Eastern Trade Group',
                'location': 'Jinja Road, Kampala',
                'description': 'Commercial plaza and parking structure.',
                'budget': Decimal('1250000000.00'),
                'status': Project.STATUS_ACTIVE,
                'manager': users[User.ROLE_PROJECT_MANAGER],
                'site_engineers': [users[User.ROLE_SITE_ENGINEER]],
                'start_date': today.replace(month=4, day=1),
                'end_date': today.replace(month=12, day=20),
                'is_active': True,
            },
        ]
        projects = {}
        for data in projects_data:
            defaults = data.copy()
            site_engineers = defaults.pop('site_engineers')
            project, _ = Project.objects.update_or_create(
                company=company,
                code=data['code'],
                defaults=defaults,
            )
            project.site_engineers.set(site_engineers)
            projects[data['code']] = project
        return projects

    def create_suppliers(self, company):
        supplier_data = [
            ('Roofings Uganda', 'Grace N.', '+256701111111', 'sales@roofings.co.ug', 'Lugogo, Kampala', 5),
            ('Tororo Cement Depot', 'Isaac O.', '+256702222222', 'orders@tororocement.ug', 'Namanve, Mukono', 4),
            ('Nile Building Supplies', 'Ruth K.', '+256703333333', 'info@nilebuild.ug', 'Ndeeba, Kampala', 4),
        ]
        suppliers = {}
        for name, contact_person, phone, email, address, rating in supplier_data:
            supplier, _ = Supplier.objects.update_or_create(
                company=company,
                name=name,
                defaults={
                    'contact_person': contact_person,
                    'phone': phone,
                    'email': email,
                    'address': address,
                    'rating': rating,
                    'notes': f'Demo supplier record for {name}.',
                    'is_active': True,
                },
            )
            suppliers[name] = supplier
        return suppliers

    def create_stock_movements(self, company, users, materials, projects):
        if StockMovement.objects.filter(company=company, notes__startswith='Seed demo').exists():
            return

        today = timezone.localdate()
        in_records = [
            ('CEM-001', '300.00', '38000.00'),
            ('CEM-002', '220.00', '36000.00'),
            ('STL-012', '150.00', '28500.00'),
            ('STL-016', '120.00', '42500.00'),
            ('AGG-001', '80.00', '45000.00'),
            ('AGG-002', '70.00', '60000.00'),
            ('AGG-003', '60.00', '70000.00'),
            ('TIM-001', '140.00', '25000.00'),
            ('ROF-001', '95.00', '52000.00'),
            ('FIN-001', '110.00', '48000.00'),
        ]
        for code, quantity, unit_price in in_records:
            StockMovement.objects.create(
                company=company,
                material=materials[code],
                movement_type=StockMovement.MOVEMENT_IN,
                source=StockMovement.SOURCE_SUPPLIER,
                quantity=Decimal(quantity),
                unit_price=Decimal(unit_price),
                date=today.replace(day=20),
                notes=f'Seed demo initial stock for {materials[code].name}.',
                created_by=users[User.ROLE_STOREKEEPER],
            )

        out_records = [
            ('CEM-001', '45.00', '38000.00', 'PRJ-NTD-001'),
            ('STL-012', '24.00', '28500.00', 'PRJ-NTD-001'),
            ('AGG-003', '12.00', '70000.00', 'PRJ-JRD-002'),
            ('TIM-001', '18.00', '25000.00', 'PRJ-JRD-002'),
            ('ROF-001', '10.00', '52000.00', 'PRJ-NTD-001'),
        ]
        for code, quantity, unit_price, project_code in out_records:
            StockMovement.objects.create(
                company=company,
                material=materials[code],
                project=projects[project_code],
                movement_type=StockMovement.MOVEMENT_OUT,
                source=StockMovement.SOURCE_SITE,
                quantity=Decimal(quantity),
                unit_price=Decimal(unit_price),
                date=today.replace(day=23),
                notes=f'Seed demo issue to site for {projects[project_code].name}.',
                created_by=users[User.ROLE_STOREKEEPER],
            )

    def create_procurement_data(self, company, users, materials, projects, suppliers):
        pending_pr, _ = PurchaseRequest.objects.update_or_create(
            company=company,
            number='PR-20260726-0001',
            defaults={
                'project': projects['PRJ-NTD-001'],
                'title': 'Cement and tiles for finishing phase',
                'priority': PurchaseRequest.PRIORITY_HIGH,
                'status': PurchaseRequest.STATUS_PENDING,
                'justification': 'Need more cement and tiles for finishing works at Ntinda site.',
                'requested_by': users[User.ROLE_SITE_ENGINEER],
                'rejection_reason': '',
            },
        )
        self.sync_pr_items(
            pending_pr,
            [
                (materials['CEM-001'], Decimal('60.00'), 'Additional bags for slab corrections'),
                (materials['FIN-001'], Decimal('35.00'), 'Tiles for lobby and stairways'),
            ],
        )

        po_created_pr, _ = PurchaseRequest.objects.update_or_create(
            company=company,
            number='PR-20260726-0002',
            defaults={
                'project': projects['PRJ-JRD-002'],
                'title': 'Steel bars and hardcore for basement works',
                'priority': PurchaseRequest.PRIORITY_URGENT,
                'status': PurchaseRequest.STATUS_PO_CREATED,
                'justification': 'Urgent restock needed for basement reinforcement and fill.',
                'requested_by': users[User.ROLE_SITE_ENGINEER],
                'rejection_reason': '',
            },
        )
        self.sync_pr_items(
            po_created_pr,
            [
                (materials['STL-016'], Decimal('30.00'), 'Rebar for basement columns'),
                (materials['AGG-002'], Decimal('20.00'), 'Hardcore for sub-base'),
            ],
        )

        approved_pr, _ = PurchaseRequest.objects.update_or_create(
            company=company,
            number='PR-20260726-0003',
            defaults={
                'project': projects['PRJ-NTD-001'],
                'title': 'Iron sheets for roof extension',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'status': PurchaseRequest.STATUS_APPROVED,
                'justification': 'Approved request awaiting PO generation.',
                'requested_by': users[User.ROLE_SITE_ENGINEER],
                'rejection_reason': '',
            },
        )
        self.sync_pr_items(
            approved_pr,
            [
                (materials['ROF-001'], Decimal('25.00'), 'Roof extension materials'),
            ],
        )

        received_po, _ = PurchaseOrder.objects.update_or_create(
            company=company,
            number='PO-20260726-0001',
            defaults={
                'purchase_request': po_created_pr,
                'project': projects['PRJ-JRD-002'],
                'supplier': suppliers['Roofings Uganda'],
                'supplier_name': 'Roofings Uganda',
                'status': PurchaseOrder.STATUS_RECEIVED,
                'notes': 'Seed demo received PO for basement materials.',
            },
        )
        self.sync_po_items(
            received_po,
            [
                (materials['STL-016'], Decimal('30.00'), Decimal('42500.00'), 'Received in full'),
                (materials['AGG-002'], Decimal('20.00'), Decimal('60000.00'), 'Received in full'),
            ],
        )

        if not StockMovement.objects.filter(
            company=company,
            purchase_order=received_po,
            notes__startswith='Seed demo received PO',
        ).exists():
            for item in received_po.items.select_related('material'):
                StockMovement.objects.create(
                    company=company,
                    material=item.material,
                    project=received_po.project,
                    movement_type=StockMovement.MOVEMENT_IN,
                    source=StockMovement.SOURCE_SUPPLIER,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    date=timezone.localdate().replace(day=24),
                    notes=f'Seed demo received PO {received_po.number}.',
                    purchase_order=received_po,
                    purchase_order_item=item,
                    created_by=users[User.ROLE_STOREKEEPER],
                )

        pending_po, _ = PurchaseOrder.objects.update_or_create(
            company=company,
            number='PO-20260726-0002',
            defaults={
                'purchase_request': approved_pr,
                'project': projects['PRJ-NTD-001'],
                'supplier': suppliers['Nile Building Supplies'],
                'supplier_name': 'Nile Building Supplies',
                'status': PurchaseOrder.STATUS_PENDING,
                'notes': 'Seed demo pending PO awaiting supplier confirmation.',
            },
        )
        self.sync_po_items(
            pending_po,
            [
                (materials['ROF-001'], Decimal('25.00'), Decimal('52000.00'), 'Awaiting supplier confirmation'),
            ],
        )

    def sync_pr_items(self, purchase_request, items):
        for material, quantity, notes in items:
            PurchaseRequestItem.objects.update_or_create(
                purchase_request=purchase_request,
                material=material,
                defaults={
                    'quantity': quantity,
                    'notes': notes,
                },
            )

    def sync_po_items(self, purchase_order, items):
        for material, quantity, unit_price, notes in items:
            PurchaseOrderItem.objects.update_or_create(
                purchase_order=purchase_order,
                material=material,
                defaults={
                    'quantity': quantity,
                    'unit_price': unit_price,
                    'notes': notes,
                },
            )
