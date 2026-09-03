from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from apps.accounts.models import Company, User
from apps.materials.models import Category, Material
from apps.procurement.models import PurchaseOrder, PurchaseOrderItem, PurchaseRequest, PurchaseRequestItem
from apps.projects.models import Project
from apps.suppliers.models import Supplier
from apps.warehouse.models import StockMovement

from .models import BudgetApproval


class FinanceFixtureFactory:
    """Small dependency-free factory used by finance tests and local fixtures."""

    def __init__(self, suffix='A'):
        self.company = Company.objects.create(name=f'Finance Company {suffix}')
        self.admin = User.objects.create_user(
            username=f'finance_admin_{suffix.lower()}', password='password', company=self.company, role=User.ROLE_ADMIN,
        )
        self.procurement = User.objects.create_user(
            username=f'finance_proc_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.manager = User.objects.create_user(
            username=f'finance_manager_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.finance_officer = User.objects.create_user(
            username=f'finance_officer_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_FINANCE_OFFICER,
        )
        self.finance_manager = User.objects.create_user(
            username=f'finance_finance_manager_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_FINANCE_MANAGER,
        )
        self.finance_viewer = User.objects.create_user(
            username=f'finance_viewer_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_FINANCE_VIEWER,
        )
        self.engineer = User.objects.create_user(
            username=f'finance_engineer_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.storekeeper = User.objects.create_user(
            username=f'finance_store_{suffix.lower()}', password='password', company=self.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.project = Project.objects.create(
            company=self.company, name=f'Finance Project {suffix}', code=f'FP-{suffix}',
            budget=Decimal('10000000.00'), manager=self.manager,
        )
        self.category = Category.objects.create(company=self.company, name=f'Cement {suffix}')
        self.material = Material.objects.create(
            company=self.company, category=self.category, name=f'Cement {suffix}', code=f'CEM-{suffix}',
            unit=Material.UNIT_BAG, unit_price=Decimal('35000.00'), min_stock_level=Decimal('5.00'),
        )
        self.supplier = Supplier.objects.create(company=self.company, name=f'Supplier {suffix}')

    def purchase_request(self, status=PurchaseRequest.STATUS_APPROVED, quantity=Decimal('10.00')):
        purchase_request = PurchaseRequest.objects.create(
            company=self.company, project=self.project, number=f'PR-{self.company_id}-{PurchaseRequest.objects.count() + 1}',
            title='Site materials', status=status, requested_by=self.engineer,
        )
        PurchaseRequestItem.objects.create(
            purchase_request=purchase_request, material=self.material, quantity=quantity,
        )
        return purchase_request

    def finance_clear_purchase_request(self, purchase_request):
        requested_amount = sum(
            (
                item.quantity * item.material.unit_price
                for item in purchase_request.items.select_related('material')
            ),
            Decimal('0.00'),
        ).quantize(Decimal('0.01'))
        return BudgetApproval.objects.create(
            company=self.company,
            purchase_request=purchase_request,
            requested_amount=requested_amount,
            status=BudgetApproval.STATUS_OVERRIDDEN,
            review_reason='Authorized unbudgeted test purchase.',
            created_by=self.finance_officer,
            reviewed_by=self.finance_manager,
            submitted_at=timezone.now(),
            reviewed_at=timezone.now(),
        )

    @property
    def company_id(self):
        return self.company.id

    def received_purchase_order(self, purchase_request=None, quantity=Decimal('10.00'), unit_price=Decimal('35000.00')):
        po = PurchaseOrder.objects.create(
            company=self.company,
            purchase_request=purchase_request,
            project=self.project,
            number=f'PO-{self.company_id}-{PurchaseOrder.objects.count() + 1}',
            supplier=self.supplier,
            supplier_name=self.supplier.name,
            status=PurchaseOrder.STATUS_RECEIVED,
            received_by=self.admin,
            received_at=timezone.now(),
        )
        item = PurchaseOrderItem.objects.create(
            purchase_order=po, material=self.material, quantity=quantity, unit_price=unit_price,
        )
        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project,
            movement_type=StockMovement.MOVEMENT_IN,
            source=StockMovement.SOURCE_SUPPLIER,
            quantity=quantity,
            unit_price=unit_price,
            date=timezone.localdate(),
            purchase_order=po,
            purchase_order_item=item,
            created_by=self.admin,
        )
        return po, item

    def invoice_payload(self, po, po_item, idempotency_key='invoice-key'):
        return {
            'purchase_order': po,
            'supplier': self.supplier,
            'invoice_number': f'SUP-{po.number}',
            'invoice_date': timezone.localdate(),
            'due_date': timezone.localdate() + timedelta(days=30),
            'items': [{
                'purchase_order_item': po_item,
                'quantity': po_item.quantity,
                'unit_price': po_item.unit_price,
                'tax_amount': Decimal('0.00'),
            }],
            'idempotency_key': idempotency_key,
        }
