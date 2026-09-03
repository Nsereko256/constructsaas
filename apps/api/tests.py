from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.core import mail
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.finance.models import BudgetApproval, FinanceAuditEvent
from apps.materials.models import Category, Material
from apps.notifications.models import Notification
from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, PurchaseOrderItem, PurchaseRequest, PurchaseRequestItem, SupplierClaim
from apps.projects.models import Project
from apps.suppliers.models import Supplier
from apps.warehouse.models import StockMovement


class ApiFoundationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='API Demo')
        self.other_company = Company.objects.create(name='Other API Demo')
        self.user = User.objects.create_user(
            username='api_admin',
            password='password',
            company=self.company,
            role=User.ROLE_ADMIN,
        )
        self.site_engineer = User.objects.create_user(
            username='api_engineer',
            password='password',
            company=self.company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.second_site_engineer = User.objects.create_user(
            username='api_engineer_two',
            password='password',
            company=self.company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.storekeeper = User.objects.create_user(
            username='api_storekeeper',
            password='password',
            company=self.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.project_manager = User.objects.create_user(
            username='api_manager',
            password='password',
            company=self.company,
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.procurement_officer = User.objects.create_user(
            username='api_procurement',
            password='password',
            company=self.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.finance_viewer = User.objects.create_user(
            username='api_finance_viewer',
            password='password',
            company=self.company,
            role=User.ROLE_FINANCE_VIEWER,
        )
        self.no_company_user = User.objects.create_user(
            username='api_no_company',
            password='password',
            role=User.ROLE_ADMIN,
        )
        self.category = Category.objects.create(company=self.company, name='Cement')
        self.material = Material.objects.create(
            company=self.company,
            category=self.category,
            name='Hima Cement',
            code='HC-001',
            unit=Material.UNIT_BAG,
            unit_price=35000,
            min_stock_level=10,
        )
        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project if hasattr(self, 'project') else None,
            movement_type=StockMovement.MOVEMENT_IN,
            source=StockMovement.SOURCE_SUPPLIER,
            quantity=8,
            unit_price=35000,
            created_by=self.storekeeper,
        )
        self.other_category = Category.objects.create(company=self.other_company, name='Steel')
        self.other_manager = User.objects.create_user(
            username='api_other_manager',
            password='password',
            company=self.other_company,
            role=User.ROLE_PROJECT_MANAGER,
        )
        self.other_site_engineer = User.objects.create_user(
            username='api_other_engineer',
            password='password',
            company=self.other_company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.other_material = Material.objects.create(
            company=self.other_company,
            category=self.other_category,
            name='Other Steel',
            code='OS-001',
            unit=Material.UNIT_PIECE,
            unit_price=25000,
            min_stock_level=5,
        )
        self.project = Project.objects.create(company=self.company, name='Office Block', code='OB-001')
        self.other_project = Project.objects.create(
            company=self.other_company,
            name='Other Office Block',
            code='OOB-001',
            manager=self.other_manager,
        )
        self.purchase_request = PurchaseRequest.objects.create(
            company=self.company,
            project=self.project,
            number='PR-API-001',
            title='Cement request',
            requested_by=self.site_engineer,
        )
        PurchaseOrder.objects.create(
            company=self.company,
            purchase_request=self.purchase_request,
            project=self.project,
            number='PO-API-001',
            supplier_name='API Supplier',
        )
        self.supplier = Supplier.objects.create(
            company=self.company,
            name='Uganda Supplies',
            contact_person='David Buyer',
            phone='0700000000',
            email='sales@uganda-supplies.test',
        )
        self.other_supplier = Supplier.objects.create(company=self.other_company, name='Other Supplies')
        self.client = APIClient()

    def finance_clear(self, purchase_request):
        approval, _ = BudgetApproval.objects.update_or_create(
            company=self.company,
            purchase_request=purchase_request,
            defaults={
                'requested_amount': sum(
                    (
                        item.quantity * item.material.unit_price
                        for item in purchase_request.items.select_related('material')
                    ),
                    Decimal('0.00'),
                ).quantize(Decimal('0.01')),
                'status': BudgetApproval.STATUS_APPROVED,
                'created_by': self.user,
                'reviewed_by': self.user,
                'submitted_at': timezone.now(),
                'reviewed_at': timezone.now(),
            },
        )
        return approval

    def test_api_requires_login(self):
        response = self.client.get('/api/')
        self.assertIn(response.status_code, [403, 302])

    def test_api_root_is_available_for_logged_in_users(self):
        self.client.force_login(self.user)
        response = self.client.get('/api/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertIn('materials', response.data)
        self.assertIn('purchase-orders', response.data)

    def test_jwt_token_login_refresh_and_bearer_access_work(self):
        token_response = self.client.post(
            '/api/token/',
            {'username': 'api_admin', 'password': 'password'},
            format='json',
        )

        self.assertEqual(token_response.status_code, 200)
        self.assertIn('access', token_response.data)
        self.assertIn('refresh', token_response.data)

        jwt_client = APIClient()
        jwt_client.credentials(HTTP_AUTHORIZATION=f'Bearer {token_response.data["access"]}')
        dashboard_response = jwt_client.get('/api/dashboard/')

        self.assertEqual(dashboard_response.status_code, 200)
        self.assertEqual(dashboard_response.data['total_active_materials'], 1)

        refresh_response = self.client.post(
            '/api/token/refresh/',
            {'refresh': token_response.data['refresh']},
            format='json',
        )

        self.assertEqual(refresh_response.status_code, 200)
        self.assertIn('access', refresh_response.data)

    def test_jwt_rejects_users_from_inactive_companies(self):
        self.company.is_active = False
        self.company.save(update_fields=['is_active'])

        response = self.client.post(
            '/api/token/',
            {'username': 'api_admin', 'password': 'password'},
            format='json',
        )

        self.assertEqual(response.status_code, 401)

    def test_password_reset_sends_link_and_accepts_valid_confirmation(self):
        self.user.email = 'api-admin@example.test'
        self.user.save(update_fields=['email'])

        request_response = self.client.post('/api/password-reset/', {'email': self.user.email}, format='json')

        self.assertEqual(request_response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/reset-password?uid=', mail.outbox[0].body)

        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_response = self.client.post(
            '/api/password-reset/confirm/',
            {'uid': uid, 'token': token, 'password': 'A-strong-new-password-2026'},
            format='json',
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('A-strong-new-password-2026'))

    def test_materials_are_company_scoped_and_paginated(self):
        self.client.force_login(self.user)
        response = self.client.get('/api/materials/')

        self.assertEqual(response.status_code, 200)
        self.assertIn('results', response.data)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['name'], 'Hima Cement')
        self.assertEqual(response.data['results'][0]['current_stock'], 8)
        self.assertEqual(response.data['results'][0]['stock_value'], 280000)

    def test_only_admin_can_deactivate_a_material_and_the_record_is_retained(self):
        self.client.force_login(self.storekeeper)
        blocked = self.client.delete(f'/api/materials/{self.material.pk}/')
        self.assertEqual(blocked.status_code, 403)
        self.material.refresh_from_db()
        self.assertTrue(self.material.is_active)

        self.client.force_login(self.user)
        response = self.client.delete(f'/api/materials/{self.material.pk}/')
        self.assertEqual(response.status_code, 204)
        self.material.refresh_from_db()
        self.assertFalse(self.material.is_active)
        self.assertTrue(Material.objects.filter(pk=self.material.pk).exists())

    def test_user_without_company_cannot_access_api_data(self):
        self.client.force_login(self.no_company_user)
        response = self.client.get('/api/materials/')

        self.assertEqual(response.status_code, 403)

    def test_storekeeper_can_manage_inventory_api_and_view_project_api(self):
        self.client.force_login(self.storekeeper)

        materials_response = self.client.get('/api/materials/')
        projects_response = self.client.get('/api/projects/')
        project_patch_response = self.client.patch(
            f'/api/projects/{self.project.pk}/',
            {'name': 'Blocked project update'},
            format='json',
        )

        self.assertEqual(materials_response.status_code, 200)
        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual(project_patch_response.status_code, 403)

    def test_project_manager_can_view_materials_and_access_project_and_pr_api(self):
        self.client.force_login(self.project_manager)

        materials_response = self.client.get('/api/materials/')
        stock_movements_response = self.client.get('/api/stock-movements/')
        projects_response = self.client.get('/api/projects/')
        purchase_requests_response = self.client.get('/api/purchase-requests/')
        purchase_orders_response = self.client.get('/api/purchase-orders/')

        self.assertEqual(materials_response.status_code, 200)
        self.assertEqual(stock_movements_response.status_code, 200)
        self.assertEqual(projects_response.status_code, 200)
        self.assertEqual(purchase_requests_response.status_code, 200)
        self.assertEqual(purchase_orders_response.status_code, 200)
        self.assertEqual(purchase_orders_response.data['count'], 0)

    def test_procurement_officer_can_view_materials_and_access_procurement_api(self):
        self.client.force_login(self.procurement_officer)

        purchase_orders_response = self.client.get('/api/purchase-orders/')
        suppliers_response = self.client.get('/api/suppliers/')
        materials_response = self.client.get('/api/materials/')
        stock_movements_response = self.client.get('/api/stock-movements/')

        self.assertEqual(purchase_orders_response.status_code, 200)
        self.assertEqual(suppliers_response.status_code, 200)
        self.assertEqual(materials_response.status_code, 200)
        self.assertEqual(stock_movements_response.status_code, 200)

    def test_procurement_can_maintain_materials_but_cannot_post_direct_stock_movements(self):
        self.client.force_login(self.procurement_officer)

        material_response = self.client.patch(
            f'/api/materials/{self.material.pk}/',
            {'description': 'Procurement-maintained catalogue description.'},
            format='json',
        )
        movement_response = self.client.post('/api/stock-movements/', {}, format='json')

        self.assertEqual(material_response.status_code, 200)
        self.assertEqual(movement_response.status_code, 403)

    def test_finance_viewer_can_read_suppliers_without_supplier_maintenance_rights(self):
        self.client.force_login(self.finance_viewer)

        suppliers_response = self.client.get('/api/suppliers/')
        create_response = self.client.post('/api/suppliers/', {}, format='json')

        self.assertEqual(suppliers_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)

    def test_purchase_order_lists_are_destination_and_assignment_scoped(self):
        self.client.force_login(self.storekeeper)
        store_response = self.client.get('/api/purchase-orders/')
        self.assertEqual(store_response.status_code, 200)
        self.assertEqual(store_response.data['count'], 1)
        self.assertEqual(
            store_response.data['results'][0]['delivery_destination'],
            PurchaseOrder.DELIVERY_WAREHOUSE,
        )

        self.project.site_engineers.add(self.site_engineer)
        site_order = PurchaseOrder.objects.create(
            company=self.company,
            project=self.project,
            number='PO-SITE-LIST-001',
            supplier=self.supplier,
            supplier_name=self.supplier.name,
            delivery_destination=PurchaseOrder.DELIVERY_SITE,
        )
        self.client.force_login(self.site_engineer)
        engineer_response = self.client.get('/api/purchase-orders/')
        self.assertEqual(engineer_response.status_code, 200)
        self.assertEqual(engineer_response.data['count'], 1)
        self.assertEqual(engineer_response.data['results'][0]['id'], site_order.id)

    def test_site_engineer_can_view_materials_but_cannot_write_them(self):
        self.client.force_login(self.site_engineer)

        list_response = self.client.get('/api/materials/')
        patch_response = self.client.patch(
            f'/api/materials/{self.material.pk}/',
            {'name': 'Blocked update'},
            format='json',
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(patch_response.status_code, 403)

    def test_users_cannot_retrieve_another_company_records(self):
        self.client.force_login(self.user)

        material_response = self.client.get(f'/api/materials/{self.other_material.pk}/')
        project_response = self.client.get(f'/api/projects/{self.other_project.pk}/')

        self.assertEqual(material_response.status_code, 404)
        self.assertEqual(project_response.status_code, 404)

    def test_dashboard_api_returns_company_scoped_metrics(self):
        self.project.budget = 1000000
        self.project.save(update_fields=['budget', 'updated_at'])
        self.project.site_engineers.add(self.site_engineer)
        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project,
            movement_type=StockMovement.MOVEMENT_OUT,
            source=StockMovement.SOURCE_SITE,
            quantity=2,
            unit_price=35000,
            date=timezone.localdate(),
            created_by=self.storekeeper,
        )
        PurchaseRequest.objects.create(
            company=self.other_company,
            project=self.other_project,
            number='PR-OTHER-DASH',
            title='Other company pending request',
            requested_by=self.other_manager,
        )
        self.client.force_login(self.site_engineer)

        response = self.client.get('/api/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_active_materials'], 1)
        self.assertEqual(response.data['active_projects'], 1)
        self.assertEqual(response.data['low_stock_count'], 1)
        self.assertEqual(response.data['pending_purchase_requests'], 1)
        self.assertEqual(response.data['stock_in_today'], 8)
        self.assertEqual(response.data['inventory_value'], 210000)
        self.assertEqual(len(response.data['recent_stock_movements']), 2)
        self.assertEqual(response.data['low_stock_materials'][0]['code'], 'HC-001')
        self.assertEqual(response.data['low_stock_materials'][0]['current_stock'], 6)
        self.assertEqual(response.data['pending_purchase_requests_list'][0]['number'], 'PR-API-001')
        self.assertEqual(response.data['project_budget_vs_actual'], [])

    def test_dashboard_api_requires_company_user(self):
        self.client.force_login(self.no_company_user)

        response = self.client.get('/api/dashboard/')

        self.assertEqual(response.status_code, 403)

    def test_notifications_api_lists_only_logged_in_users_notifications(self):
        own_notification = Notification.objects.create(
            company=self.company,
            recipient=self.site_engineer,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Your notification',
            message='Visible to the logged-in user.',
        )
        Notification.objects.create(
            company=self.company,
            recipient=self.project_manager,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Manager notification',
            message='Should not be visible.',
        )
        Notification.objects.create(
            company=self.other_company,
            recipient=self.other_manager,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Other company notification',
            message='Should not be visible.',
        )
        self.client.force_login(self.site_engineer)

        response = self.client.get('/api/notifications/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], own_notification.pk)

    def test_notifications_unread_count_is_scoped_to_user_and_company(self):
        Notification.objects.create(
            company=self.company,
            recipient=self.site_engineer,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Unread',
            message='Count this.',
        )
        Notification.objects.create(
            company=self.company,
            recipient=self.site_engineer,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Read',
            message='Do not count this.',
            is_read=True,
        )
        Notification.objects.create(
            company=self.company,
            recipient=self.project_manager,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Other user unread',
            message='Do not count this.',
        )
        self.client.force_login(self.site_engineer)

        response = self.client.get('/api/notifications/unread-count/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['unread_count'], 1)

    def test_notification_mark_read_only_affects_logged_in_user_notification(self):
        own_notification = Notification.objects.create(
            company=self.company,
            recipient=self.site_engineer,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Own unread',
            message='Can mark this.',
        )
        other_user_notification = Notification.objects.create(
            company=self.company,
            recipient=self.project_manager,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Other unread',
            message='Cannot mark this.',
        )
        self.client.force_login(self.site_engineer)

        own_response = self.client.post(f'/api/notifications/{own_notification.pk}/mark-read/')
        other_response = self.client.post(f'/api/notifications/{other_user_notification.pk}/mark-read/')

        self.assertEqual(own_response.status_code, 200)
        own_notification.refresh_from_db()
        other_user_notification.refresh_from_db()
        self.assertTrue(own_notification.is_read)
        self.assertFalse(other_user_notification.is_read)
        self.assertEqual(other_response.status_code, 404)

    def test_notification_mark_all_read_only_affects_logged_in_user_notifications(self):
        own_unread = Notification.objects.create(
            company=self.company,
            recipient=self.site_engineer,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Own unread',
            message='Can mark this.',
        )
        other_user_unread = Notification.objects.create(
            company=self.company,
            recipient=self.project_manager,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Other unread',
            message='Must remain unread.',
        )
        self.client.force_login(self.site_engineer)

        response = self.client.post('/api/notifications/mark-all-read/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['updated'], 1)
        self.assertEqual(response.data['unread_count'], 0)
        own_unread.refresh_from_db()
        other_user_unread.refresh_from_db()
        self.assertTrue(own_unread.is_read)
        self.assertFalse(other_user_unread.is_read)

    def test_storekeeper_can_create_patch_and_soft_delete_material(self):
        self.client.force_login(self.storekeeper)

        create_response = self.client.post(
            '/api/materials/',
            {
                'category': self.category.pk,
                'name': 'Tororo Cement',
                'code': 'TC-001',
                'unit': Material.UNIT_BAG,
                'unit_price': '34000.00',
                'min_stock_level': '12.00',
                'description': 'API-created material.',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        created_id = create_response.data['id']
        self.assertEqual(create_response.data['company'], self.company.pk)

        patch_response = self.client.patch(
            f'/api/materials/{created_id}/',
            {'unit_price': '36000.00'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data['unit_price'], '36000.00')

        delete_response = self.client.delete(f'/api/materials/{created_id}/')
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(Material.objects.filter(pk=created_id).exists())
        self.assertTrue(Material.objects.get(pk=created_id).is_active)

    def test_material_search_and_low_stock_filter_work(self):
        self.client.force_login(self.site_engineer)

        search_response = self.client.get('/api/materials/', {'search': 'HC-001'})
        low_stock_response = self.client.get('/api/materials/', {'low_stock': 'true'})

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.data['count'], 1)
        self.assertEqual(low_stock_response.status_code, 200)
        self.assertEqual(low_stock_response.data['count'], 1)

    def test_material_create_rejects_category_from_another_company(self):
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            '/api/materials/',
            {
                'category': self.other_category.pk,
                'name': 'Cross Company Material',
                'code': 'XCM-001',
                'unit': Material.UNIT_BAG,
                'unit_price': '1000.00',
                'min_stock_level': '1.00',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_projects_include_calculated_material_cost_and_remaining_budget(self):
        self.project.site_engineers.add(self.site_engineer)
        self.client.force_login(self.site_engineer)
        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project,
            movement_type=StockMovement.MOVEMENT_OUT,
            source=StockMovement.SOURCE_SITE,
            quantity=2,
            unit_price=35000,
            date=timezone.localdate(),
            created_by=self.storekeeper,
        )
        self.project.budget = 1000000
        self.project.save(update_fields=['budget', 'updated_at'])

        response = self.client.get(f'/api/projects/{self.project.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total_material_cost'], 70000)
        self.assertEqual(response.data['remaining_budget'], 930000)
        self.assertEqual(response.data['manager_name'], '')

    def test_project_manager_can_create_and_patch_project(self):
        self.client.force_login(self.project_manager)

        create_response = self.client.post(
            '/api/projects/',
            {
                'name': 'Warehouse Extension',
                'code': 'WE-001',
                'client': 'Nile Construct',
                'location': 'Jinja',
                'description': 'Extra storage wing.',
                'budget': '2500000.00',
                'status': Project.STATUS_ACTIVE,
                'start_date': '2026-01-10',
                'end_date': '2026-06-30',
                'is_active': True,
                'company': self.other_company.pk,
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        created_project = Project.objects.get(pk=create_response.data['id'])
        self.assertEqual(created_project.company, self.company)
        self.assertEqual(created_project.manager, self.project_manager)

        patch_response = self.client.patch(
            f'/api/projects/{created_project.pk}/',
            {'location': 'Entebbe'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data['location'], 'Entebbe')

    def test_admin_assigns_manager_and_project_manager_assigns_multiple_engineers(self):
        self.client.force_login(self.user)

        manager_response = self.client.patch(
            f'/api/projects/{self.project.pk}/',
            {'manager': self.project_manager.pk},
            format='json',
        )

        self.assertEqual(manager_response.status_code, 200)
        self.assertEqual(manager_response.data['manager'], self.project_manager.pk)

        self.client.force_login(self.project_manager)
        engineer_response = self.client.patch(
            f'/api/projects/{self.project.pk}/',
            {'site_engineers': [self.site_engineer.pk, self.second_site_engineer.pk]},
            format='json',
        )

        self.assertEqual(engineer_response.status_code, 200)
        self.assertCountEqual(
            engineer_response.data['site_engineers'],
            [self.site_engineer.pk, self.second_site_engineer.pk],
        )
        self.assertCountEqual(
            engineer_response.data['site_engineer_names'],
            ['api_engineer', 'api_engineer_two'],
        )

    def test_project_manager_cannot_assign_engineer_to_project_not_managed_by_them(self):
        self.client.force_login(self.project_manager)

        response = self.client.patch(
            f'/api/projects/{self.project.pk}/',
            {'site_engineers': [self.site_engineer.pk]},
            format='json',
        )

        self.assertEqual(response.status_code, 404)
        self.project.refresh_from_db()
        self.assertFalse(self.project.site_engineers.exists())

    def test_project_rejects_engineer_from_another_company(self):
        self.project.manager = self.project_manager
        self.project.save(update_fields=['manager', 'updated_at'])
        self.client.force_login(self.project_manager)

        response = self.client.patch(
            f'/api/projects/{self.project.pk}/',
            {'site_engineers': [self.other_site_engineer.pk]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.project.site_engineers.exists())

    def test_non_project_manager_cannot_create_project(self):
        self.client.force_login(self.site_engineer)

        response = self.client.post(
            '/api/projects/',
            {
                'name': 'Unauthorized Project',
                'code': 'UP-001',
                'budget': '1000.00',
                'status': Project.STATUS_PLANNING,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_project_search_and_status_filter_work(self):
        self.client.force_login(self.storekeeper)
        self.project.status = Project.STATUS_ACTIVE
        self.project.client = 'Acme Developers'
        self.project.save(update_fields=['status', 'client', 'updated_at'])

        search_response = self.client.get('/api/projects/', {'search': 'Acme'})
        status_response = self.client.get('/api/projects/', {'status': Project.STATUS_ACTIVE})

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.data['count'], 1)
        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.data['count'], 1)

    def test_project_create_rejects_manager_from_another_company(self):
        self.client.force_login(self.project_manager)

        response = self.client.post(
            '/api/projects/',
            {
                'name': 'Cross Manager Project',
                'code': 'CMP-001',
                'budget': '1000.00',
                'status': Project.STATUS_PLANNING,
                'manager': self.other_manager.pk,
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)

    def test_procurement_officer_can_create_patch_and_soft_delete_supplier(self):
        self.client.force_login(self.procurement_officer)

        create_response = self.client.post(
            '/api/suppliers/',
            {
                'company': self.other_company.pk,
                'name': 'Kampala Hardware',
                'contact_person': 'Amina',
                'phone': '0777000000',
                'email': 'amina@hardware.test',
                'address': 'Industrial Area, Kampala',
                'rating': 4,
                'notes': 'Reliable supplier.',
                'is_active': True,
            },
            format='json',
        )
        self.assertEqual(create_response.status_code, 201)
        created_id = create_response.data['id']
        created_supplier = Supplier.objects.get(pk=created_id)
        self.assertEqual(created_supplier.company, self.company)

        patch_response = self.client.patch(
            f'/api/suppliers/{created_id}/',
            {'rating': 5, 'phone': '0788000000'},
            format='json',
        )
        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(patch_response.data['rating'], 5)

        delete_response = self.client.delete(f'/api/suppliers/{created_id}/')
        self.assertEqual(delete_response.status_code, 204)
        self.assertTrue(Supplier.objects.filter(pk=created_id).exists())
        self.assertFalse(Supplier.objects.get(pk=created_id).is_active)

    def test_non_procurement_user_cannot_manage_suppliers(self):
        self.client.force_login(self.storekeeper)

        list_response = self.client.get('/api/suppliers/')
        create_response = self.client.post(
            '/api/suppliers/',
            {'name': 'Blocked Supplier', 'rating': 3},
            format='json',
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(create_response.status_code, 403)

    def test_admin_can_manage_suppliers(self):
        self.client.force_login(self.user)

        response = self.client.patch(
            f'/api/suppliers/{self.supplier.pk}/',
            {'contact_person': 'Updated Contact'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['contact_person'], 'Updated Contact')

    def test_supplier_search_and_company_isolation_work(self):
        self.client.force_login(self.procurement_officer)

        search_response = self.client.get('/api/suppliers/', {'search': 'David'})
        detail_response = self.client.get(f'/api/suppliers/{self.other_supplier.pk}/')

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(search_response.data['count'], 1)
        self.assertEqual(search_response.data['results'][0]['name'], 'Uganda Supplies')
        self.assertEqual(detail_response.status_code, 404)

    def test_storekeeper_can_create_stock_movement_with_company_and_creator_set(self):
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            '/api/stock-movements/',
            {
                'company': self.other_company.pk,
                'created_by': self.user.pk,
                'material': self.material.pk,
                'project': self.project.pk,
                'movement_type': StockMovement.MOVEMENT_IN,
                'source': StockMovement.SOURCE_INTERNAL,
                'quantity': '4.00',
                'unit_price': '35000.00',
                'date': str(timezone.localdate()),
                'notes': 'API stock in.',
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        movement = StockMovement.objects.get(pk=response.data['id'])
        self.assertEqual(movement.company, self.company)
        self.assertEqual(movement.created_by, self.storekeeper)

    def test_supplier_stock_entry_requires_approved_purchase_order_receipt(self):
        self.client.force_login(self.storekeeper)
        response = self.client.post(
            '/api/stock-movements/',
            {
                'material': self.material.pk,
                'movement_type': StockMovement.MOVEMENT_IN,
                'source': StockMovement.SOURCE_SUPPLIER,
                'quantity': '1.00',
                'unit_price': '35000.00',
                'date': str(timezone.localdate()),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('source', response.data)

    def test_non_storekeeper_cannot_create_stock_movement_but_can_view(self):
        self.client.force_login(self.site_engineer)

        list_response = self.client.get('/api/stock-movements/')
        create_response = self.client.post(
            '/api/stock-movements/',
            {
                'material': self.material.pk,
                'movement_type': StockMovement.MOVEMENT_IN,
                'source': StockMovement.SOURCE_SUPPLIER,
                'quantity': '1.00',
                'unit_price': '35000.00',
                'date': str(timezone.localdate()),
            },
            format='json',
        )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(create_response.status_code, 403)

    def test_stock_movement_create_cannot_bypass_controlled_stock_issue(self):
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            '/api/stock-movements/',
            {
                'material': self.material.pk,
                'project': self.project.pk,
                'movement_type': StockMovement.MOVEMENT_OUT,
                'source': StockMovement.SOURCE_SITE,
                'quantity': '99.00',
                'unit_price': '35000.00',
                'date': str(timezone.localdate()),
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('movement_type', response.data)

    def test_stock_movement_filters_work(self):
        self.client.force_login(self.project_manager)
        today = timezone.localdate()
        yesterday = today - timedelta(days=1)

        StockMovement.objects.create(
            company=self.company,
            material=self.material,
            project=self.project,
            movement_type=StockMovement.MOVEMENT_OUT,
            source=StockMovement.SOURCE_SITE,
            quantity=2,
            unit_price=35000,
            date=yesterday,
            created_by=self.storekeeper,
        )

        response = self.client.get(
            '/api/stock-movements/',
            {
                'material': self.material.pk,
                'movement_type': StockMovement.MOVEMENT_OUT,
                'project': self.project.pk,
                'date_from': str(yesterday),
                'date_to': str(yesterday),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['movement_type'], StockMovement.MOVEMENT_OUT)

    def test_site_engineer_can_create_purchase_request_with_multiple_items(self):
        self.project.site_engineers.add(self.site_engineer)
        self.client.force_login(self.site_engineer)
        steel = Material.objects.create(
            company=self.company,
            category=self.category,
            name='Y12 Steel Bar',
            code='Y12-001',
            unit=Material.UNIT_PIECE,
            unit_price=18000,
            min_stock_level=5,
        )

        response = self.client.post(
            '/api/purchase-requests/',
            {
                'company': self.other_company.pk,
                'requested_by': self.user.pk,
                'status': PurchaseRequest.STATUS_APPROVED,
                'project': self.project.pk,
                'title': 'Site materials request',
                'priority': PurchaseRequest.PRIORITY_HIGH,
                'justification': 'Needed for ground floor slab.',
                'items': [
                    {'material': self.material.pk, 'quantity': '3.00', 'notes': 'Cement bags'},
                    {'material': steel.pk, 'quantity': '10.00', 'notes': 'Rebar'},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase_request = PurchaseRequest.objects.get(pk=response.data['id'])
        self.assertEqual(purchase_request.company, self.company)
        self.assertEqual(purchase_request.requested_by, self.site_engineer)
        self.assertEqual(purchase_request.status, PurchaseRequest.STATUS_PENDING)
        self.assertEqual(purchase_request.items.count(), 2)
        self.assertEqual(response.data['items'][0]['current_stock'], 8)
        self.assertEqual(response.data['total_estimated_cost'], 285000)

    def test_site_engineer_cannot_create_a_projectless_purchase_request(self):
        self.client.force_login(self.site_engineer)

        response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': None,
                'title': 'Unassigned site demand',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'items': [{'material': self.material.pk, 'quantity': '1.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('project', response.data)

    def test_procurement_can_create_projectless_warehouse_replenishment_for_finance(self):
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': None,
                'title': 'Replenish warehouse cement stock',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'justification': 'Restore warehouse safety stock.',
                'items': [{'material': self.material.pk, 'quantity': '20.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        replenishment = PurchaseRequest.objects.get(pk=response.data['id'])
        self.assertIsNone(replenishment.project)
        self.assertEqual(replenishment.requested_by, self.procurement_officer)
        self.assertEqual(replenishment.status, PurchaseRequest.STATUS_APPROVED)

        finance_response = self.client.post(
            f'/api/purchase-requests/{replenishment.pk}/submit-finance/',
            {'budget_line': None, 'comments': 'Warehouse safety stock requires finance review.'},
            format='json',
        )
        self.assertEqual(finance_response.status_code, 200, finance_response.data)
        self.assertEqual(finance_response.data['status'], BudgetApproval.STATUS_SUBMITTED)
        self.client.force_login(self.user)
        approval_response = self.client.post(
            f'/api/purchase-requests/{replenishment.pk}/finance-approve/',
            {'override': True, 'comments': 'Approved warehouse safety stock replenishment.'},
            format='json',
        )
        self.assertEqual(approval_response.status_code, 200, approval_response.data)
        self.client.force_login(self.procurement_officer)
        issue_response = self.client.post(f'/api/purchase-requests/{replenishment.pk}/issue-stock/')
        self.assertEqual(issue_response.status_code, 400)
        self.assertIn('cannot request stock issue', str(issue_response.data).lower())

    def test_purchase_request_create_rejects_other_company_project_and_material(self):
        self.client.force_login(self.site_engineer)

        project_response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': self.other_project.pk,
                'title': 'Cross-company project request',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'items': [{'material': self.material.pk, 'quantity': '1.00'}],
            },
            format='json',
        )
        material_response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': self.project.pk,
                'title': 'Cross-company material request',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'items': [{'material': self.other_material.pk, 'quantity': '1.00'}],
            },
            format='json',
        )

        self.assertEqual(project_response.status_code, 400)
        self.assertEqual(material_response.status_code, 400)

    def test_purchase_request_create_requires_items(self):
        self.client.force_login(self.site_engineer)

        response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': self.project.pk,
                'title': 'Empty request',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'items': [],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('items', response.data)

    def test_only_site_engineer_and_admin_can_submit_purchase_requests(self):
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            '/api/purchase-requests/',
            {
                'project': self.project.pk,
                'title': 'Blocked request',
                'priority': PurchaseRequest.PRIORITY_NORMAL,
                'items': [{'material': self.material.pk, 'quantity': '1.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_project_manager_can_approve_purchase_request(self):
        self.project.manager = self.project_manager
        self.project.save(update_fields=['manager', 'updated_at'])
        self.client.force_login(self.project_manager)
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/approve/')

        self.assertEqual(response.status_code, 200)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_APPROVED)
        self.assertEqual(response.data['status'], PurchaseRequest.STATUS_APPROVED)
        self.assertEqual(response.data['total_estimated_cost'], 70000)

    def test_procurement_can_request_stock_issue_without_creating_stock_movement(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.technical_approved_by = self.user
        self.purchase_request.save(update_fields=['status', 'technical_approved_by', 'manager_approved_by', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
            notes='Issue directly from store.',
        )
        self.finance_clear(self.purchase_request)
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.procurement_officer)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/issue-stock/')

        self.assertEqual(response.status_code, 200)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED)

        # The Storekeeper must see the handoff even while Finance clearance is
        # still pending; the fulfil action remains blocked until approval.
        self.client.force_login(self.storekeeper)
        queue_response = self.client.get('/api/purchase-requests/?action_queue=my_requests')
        self.assertEqual(queue_response.status_code, 200)
        self.assertIn(self.purchase_request.pk, [row['id'] for row in queue_response.data['results']])
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_procurement_can_request_stock_issue_before_finance_approval(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.technical_approved_by = self.user
        self.purchase_request.save(update_fields=['status', 'technical_approved_by', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        finance_officer = User.objects.create_user(
            username='api_finance_officer', password='password',
            company=self.company, role=User.ROLE_FINANCE_OFFICER,
        )
        finance_manager = User.objects.create_user(
            username='api_finance_manager', password='password',
            company=self.company, role=User.ROLE_FINANCE_MANAGER,
        )
        self.client.force_login(self.procurement_officer)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/issue-stock/')

        self.assertEqual(response.status_code, 200, response.data)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED)
        self.assertTrue(Notification.objects.filter(recipient=finance_officer, title__contains='Stock issue requested').exists())
        self.assertTrue(Notification.objects.filter(recipient=finance_manager, title__contains='Stock issue requested').exists())

    def test_storekeeper_can_fulfill_stock_issue_and_create_out_movements(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
            notes='Issue directly from store.',
        )
        self.finance_clear(self.purchase_request)
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/fulfill-stock/')

        self.assertEqual(response.status_code, 200)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_STOCK_ISSUED)
        self.assertEqual(StockMovement.objects.count(), movement_count + 1)
        movement = StockMovement.objects.latest('created_at')
        self.assertEqual(movement.movement_type, StockMovement.MOVEMENT_OUT)
        self.assertEqual(movement.source, StockMovement.SOURCE_SITE)
        self.assertEqual(movement.project, self.project)
        self.assertEqual(movement.created_by, self.storekeeper)
        self.assertEqual(movement.purchase_request, self.purchase_request)
        self.assertEqual(movement.purchase_request_item, self.purchase_request.items.get())
        self.assertIn(self.purchase_request.number, movement.notes)

    def test_fulfill_stock_blocks_insufficient_warehouse_stock(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='99.00',
        )
        self.finance_clear(self.purchase_request)
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/fulfill-stock/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('items', response.data)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED)
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_storekeeper_can_partially_issue_available_stock_and_leave_purchase_balance(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        request_item = PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='20.00',
        )
        self.finance_clear(self.purchase_request)
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            f'/api/purchase-requests/{self.purchase_request.pk}/fulfill-stock/',
            {'items': [{'purchase_request_item': request_item.pk, 'quantity': '2.00'}]},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED)
        request_item.refresh_from_db()
        self.assertEqual(response.data['items'][0]['issued_quantity'], Decimal('2.00'))
        self.assertEqual(response.data['items'][0]['outstanding_quantity'], Decimal('18.00'))
        self.assertIn('warehouse_available', response.data['items'][0])
        self.assertGreaterEqual(response.data['items'][0]['warehouse_available'], Decimal('0.00'))
        self.assertTrue(response.data['can_create_purchase_order'])
        self.assertEqual(StockMovement.objects.filter(purchase_request_item=request_item).count(), 1)

    def test_fulfill_stock_does_not_require_finance_approval(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='1.00',
        )
        approval = self.finance_clear(self.purchase_request)
        BudgetApproval.objects.filter(pk=approval.pk).update(status=BudgetApproval.STATUS_HOLD)
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/fulfill-stock/')

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(StockMovement.objects.count(), movement_count + 1)

    def test_storekeeper_cannot_request_purchase_request_stock_issue(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.technical_approved_by = self.user
        self.purchase_request.manager_approved_by = self.project_manager
        self.purchase_request.save(update_fields=['status', 'technical_approved_by', 'manager_approved_by', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='1.00',
        )
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/issue-stock/')

        self.assertEqual(response.status_code, 403)

    def test_non_project_manager_cannot_approve_purchase_request(self):
        self.client.force_login(self.site_engineer)

        response = self.client.post(f'/api/purchase-requests/{self.purchase_request.pk}/approve/')

        self.assertEqual(response.status_code, 403)

    def test_reject_purchase_request_requires_rejection_reason(self):
        self.project.manager = self.project_manager
        self.project.save(update_fields=['manager', 'updated_at'])
        self.client.force_login(self.project_manager)

        response = self.client.post(
            f'/api/purchase-requests/{self.purchase_request.pk}/reject/',
            {'rejection_reason': ''},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('rejection_reason', response.data)

    def test_project_manager_can_reject_purchase_request_with_reason(self):
        self.project.manager = self.project_manager
        self.project.save(update_fields=['manager', 'updated_at'])
        self.client.force_login(self.project_manager)

        response = self.client.post(
            f'/api/purchase-requests/{self.purchase_request.pk}/reject/',
            {'rejection_reason': 'Budget approval is missing.'},
            format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_REJECTED)
        self.assertEqual(self.purchase_request.rejection_reason, 'Budget approval is missing.')

    def test_users_cannot_retrieve_another_company_purchase_request(self):
        other_pr = PurchaseRequest.objects.create(
            company=self.other_company,
            project=self.other_project,
            number='PR-OTHER-001',
            title='Other company request',
            requested_by=self.other_manager,
        )
        self.client.force_login(self.user)

        response = self.client.get(f'/api/purchase-requests/{other_pr.pk}/')

        self.assertEqual(response.status_code, 404)

    def test_purchase_request_exposes_stock_issue_availability(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.technical_approved_by = self.user
        self.purchase_request.manager_approved_by = self.project_manager
        self.purchase_request.save(update_fields=['status', 'technical_approved_by', 'manager_approved_by', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.finance_clear(self.purchase_request)
        self.client.force_login(self.storekeeper)

        response = self.client.get(f'/api/purchase-requests/{self.purchase_request.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data['has_purchase_order'])
        self.assertTrue(response.data['can_issue_from_stock'])
        self.assertEqual(response.data['stock_issue_blockers'], [])

    def test_purchase_request_explains_when_stock_issue_is_blocked_by_po(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.technical_approved_by = self.user
        self.purchase_request.manager_approved_by = self.project_manager
        self.purchase_request.save(update_fields=['status', 'technical_approved_by', 'manager_approved_by', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.client.force_login(self.storekeeper)

        response = self.client.get(f'/api/purchase-requests/{self.purchase_request.pk}/')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['has_purchase_order'])
        self.assertFalse(response.data['can_issue_from_stock'])
        self.assertIn('purchase order', response.data['stock_issue_blockers'][0])

    def test_procurement_officer_cannot_create_purchase_order_without_finance_cleared_request(self):
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            '/api/purchase-orders/',
            {
                'project': self.project.pk,
                'supplier': self.supplier.pk,
                'status': PurchaseOrder.STATUS_PENDING,
                'notes': 'Manual API order.',
                'items': [
                    {
                        'material': self.material.pk,
                        'quantity': '4.00',
                        'unit_price': '36000.00',
                        'notes': 'Confirmed price.',
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)

    def test_purchase_order_create_requires_supplier_and_items(self):
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            '/api/purchase-orders/',
            {
                'project': self.project.pk,
                'supplier': None,
                'status': PurchaseOrder.STATUS_PENDING,
                'items': [],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('items', response.data)

        missing_supplier_response = self.client.post(
            '/api/purchase-orders/',
            {
                'project': self.project.pk,
                'supplier': None,
                'items': [
                    {
                        'material': self.material.pk,
                        'quantity': '1.00',
                        'unit_price': '35000.00',
                    }
                ],
            },
            format='json',
        )
        self.assertEqual(missing_supplier_response.status_code, 400)
        self.assertIn('supplier', missing_supplier_response.data)

    def test_non_procurement_user_cannot_create_purchase_order(self):
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            '/api/purchase-orders/',
            {
                'project': self.project.pk,
                'supplier': self.supplier.pk,
                'items': [{'material': self.material.pk, 'quantity': '1.00', 'unit_price': '35000.00'}],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 403)

    def test_procurement_officer_can_create_purchase_order_from_approved_pr(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
            notes='Copy this line.',
        )
        self.finance_clear(self.purchase_request)
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            f'/api/purchase-orders/from-pr/{self.purchase_request.pk}/',
            {'supplier': self.supplier.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        purchase_order = PurchaseOrder.objects.get(pk=response.data['id'])
        self.assertEqual(purchase_order.purchase_request, self.purchase_request)
        self.assertEqual(purchase_order.project, self.project)
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_PENDING)
        self.assertEqual(purchase_order.items.count(), 1)
        item = purchase_order.items.first()
        self.assertEqual(item.quantity, PurchaseRequestItem.objects.get(purchase_request=self.purchase_request).quantity)
        self.assertEqual(item.unit_price, self.material.unit_price)

    def test_create_purchase_order_from_pr_requires_approved_pr(self):
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            f'/api/purchase-orders/from-pr/{self.purchase_request.pk}/',
            {'supplier': self.supplier.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)

    def test_create_purchase_order_from_pr_prevents_duplicate_po(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            f'/api/purchase-orders/from-pr/{self.purchase_request.pk}/',
            {'supplier': self.supplier.pk},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)

    def test_create_purchase_order_from_pr_allows_confirmed_items(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseOrder.objects.filter(purchase_request=self.purchase_request).delete()
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.finance_clear(self.purchase_request)
        self.client.force_login(self.procurement_officer)

        response = self.client.post(
            f'/api/purchase-orders/from-pr/{self.purchase_request.pk}/',
            {
                'supplier': self.supplier.pk,
                'items': [
                    {
                        'material': self.material.pk,
                        'quantity': '2.00',
                        'unit_price': '34000.00',
                        'notes': 'Confirmed after supplier quote.',
                    }
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, 201)
        item = PurchaseOrder.objects.get(pk=response.data['id']).items.first()
        self.assertEqual(item.quantity, 2)
        self.assertEqual(item.unit_price, 34000)

    def test_storekeeper_can_receive_purchase_order_and_create_stock_movements(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='5.00',
        )
        self.finance_clear(self.purchase_request)
        purchase_order = PurchaseOrder.objects.get(purchase_request=self.purchase_request)
        purchase_order.supplier_name = 'Uganda Supplies'
        purchase_order.status = PurchaseOrder.STATUS_ORDERED
        purchase_order.save(update_fields=['supplier_name', 'status', 'updated_at'])
        purchase_order.items.all().delete()
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='5.00',
            unit_price='33000.00',
        )
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(response.status_code, 200)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_RECEIVED)
        self.assertEqual(StockMovement.objects.count(), movement_count + 1)
        movement = StockMovement.objects.latest('created_at')
        self.assertEqual(movement.purchase_order, purchase_order)
        self.assertEqual(movement.purchase_order_item, purchase_order.items.get())
        self.assertEqual(movement.movement_type, StockMovement.MOVEMENT_IN)
        self.assertEqual(movement.created_by, self.storekeeper)

    def test_storekeeper_must_explain_rejected_or_damaged_goods(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.finance_clear(self.purchase_request)
        purchase_order = PurchaseOrder.objects.get(purchase_request=self.purchase_request)
        purchase_order.supplier_name = 'Uganda Supplies'
        purchase_order.status = PurchaseOrder.STATUS_ORDERED
        purchase_order.save(update_fields=['supplier_name', 'status', 'updated_at'])
        purchase_order.items.all().delete()
        item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='2.00',
            unit_price='35000.00',
        )
        movement_count = StockMovement.objects.count()
        self.client.force_login(self.storekeeper)

        response = self.client.post(
            f'/api/purchase-orders/{purchase_order.pk}/receive/',
            {'items': [{
                'purchase_order_item': item.pk,
                'accepted_quantity': '0.00',
                'rejected_quantity': '2.00',
                'damaged_quantity': '0.00',
                'notes': '',
            }]},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('line note is required', str(response.data).lower())
        self.assertEqual(StockMovement.objects.count(), movement_count)

    def test_storekeeper_cannot_receive_more_rejected_or_damaged_goods_than_ordered(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.finance_clear(self.purchase_request)
        purchase_order = PurchaseOrder.objects.get(purchase_request=self.purchase_request)
        purchase_order.supplier_name = 'Uganda Supplies'
        purchase_order.status = PurchaseOrder.STATUS_ORDERED
        purchase_order.save(update_fields=['supplier_name', 'status', 'updated_at'])
        purchase_order.items.all().delete()
        item = PurchaseOrderItem.objects.create(
            purchase_order=purchase_order, material=self.material,
            quantity='2.00', unit_price='35000.00',
        )
        self.client.force_login(self.storekeeper)

        first_response = self.client.post(
            f'/api/purchase-orders/{purchase_order.pk}/receive/',
            {'items': [{
                'purchase_order_item': item.pk,
                'accepted_quantity': '0.00',
                'rejected_quantity': '2.00',
                'damaged_quantity': '0.00',
                'notes': 'Two bags were wet on arrival.',
            }]},
            format='json',
        )
        second_response = self.client.post(
            f'/api/purchase-orders/{purchase_order.pk}/receive/',
            {'items': [{
                'purchase_order_item': item.pk,
                'accepted_quantity': '0.00',
                'rejected_quantity': '1.00',
                'damaged_quantity': '0.00',
                'notes': 'Attempted duplicate rejection.',
            }]},
            format='json',
        )

        self.assertEqual(first_response.status_code, 200)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_RECEIVED)
        self.assertEqual(second_response.status_code, 400)
        self.assertIn('already been received', str(second_response.data).lower())
        claim = SupplierClaim.objects.get(goods_received_note_item__purchase_order_item=item)
        self.assertEqual(claim.status, SupplierClaim.STATUS_OPEN)
        self.assertEqual(claim.reported_by, self.storekeeper)
        self.assertEqual(claim.purchase_order, purchase_order)

    def test_receiving_purchase_order_updates_linked_pr_status_and_blocks_second_receive(self):
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='2.00',
        )
        self.finance_clear(self.purchase_request)
        purchase_order = PurchaseOrder.objects.get(purchase_request=self.purchase_request)
        purchase_order.status = PurchaseOrder.STATUS_ORDERED
        purchase_order.save(update_fields=['status', 'updated_at'])
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='2.00',
            unit_price='35000.00',
        )
        self.client.force_login(self.storekeeper)

        first_response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')
        second_response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 400)
        self.purchase_request.refresh_from_db()
        self.assertEqual(self.purchase_request.status, PurchaseRequest.STATUS_PO_CREATED)

    def test_procurement_officer_cannot_receive_warehouse_purchase_order(self):
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            project=self.project,
            number='PO-BLOCK-PROC-001',
            supplier_name='Uganda Supplies',
            status=PurchaseOrder.STATUS_ORDERED,
            delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='1.00',
            unit_price='35000.00',
        )
        self.client.force_login(self.procurement_officer)

        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(response.status_code, 403)

    def test_site_engineer_cannot_receive_purchase_order(self):
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            project=self.project,
            number='PO-BLOCK-001',
            supplier_name='Uganda Supplies',
            status=PurchaseOrder.STATUS_ORDERED,
            delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='1.00',
            unit_price='35000.00',
        )
        self.client.force_login(self.site_engineer)

        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(response.status_code, 404)

    def test_direct_site_po_requires_procurement_dispatch_then_assigned_engineer_receipt(self):
        self.project.site_engineers.add(self.site_engineer, self.second_site_engineer)
        self.purchase_request.status = PurchaseRequest.STATUS_APPROVED
        self.purchase_request.save(update_fields=['status', 'updated_at'])
        PurchaseRequestItem.objects.create(
            purchase_request=self.purchase_request,
            material=self.material,
            quantity='1.00',
        )
        self.finance_clear(self.purchase_request)
        purchase_order = PurchaseOrder.objects.get(purchase_request=self.purchase_request)
        purchase_order.supplier_name = 'Uganda Supplies'
        purchase_order.status = PurchaseOrder.STATUS_ORDERED
        purchase_order.delivery_destination = PurchaseOrder.DELIVERY_SITE
        purchase_order.save(update_fields=['supplier_name', 'status', 'delivery_destination', 'updated_at'])
        purchase_order.items.all().delete()
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='1.00',
            unit_price='35000.00',
        )
        movement_count = StockMovement.objects.count()

        self.client.force_login(self.second_site_engineer)
        blocked_response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(blocked_response.status_code, 400)
        self.assertEqual(StockMovement.objects.count(), movement_count)

        self.client.force_login(self.procurement_officer)
        dispatch_response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/confirm-dispatch/')

        self.assertEqual(dispatch_response.status_code, 200)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_DISPATCH_CONFIRMED)
        self.assertEqual(purchase_order.dispatch_confirmed_by, self.procurement_officer)
        self.assertIsNotNone(purchase_order.dispatch_confirmed_at)
        self.assertEqual(StockMovement.objects.count(), movement_count)

        self.client.force_login(self.second_site_engineer)
        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(response.status_code, 200, response.data)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_RECEIVED)
        self.assertEqual(purchase_order.received_by, self.second_site_engineer)
        self.assertIsNotNone(purchase_order.received_at)
        self.assertEqual(StockMovement.objects.count(), movement_count + 1)
        grn = GoodsReceivedNote.objects.get(purchase_order=purchase_order)
        pdf_response = self.client.get(f'/api/goods-received-notes/{grn.pk}/download-pdf/')
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertTrue(pdf_response.content[:4] == b'%PDF')
        register_pdf_response = self.client.get('/api/goods-received-notes/download-register-pdf/')
        self.assertEqual(register_pdf_response.status_code, 200)
        self.assertEqual(register_pdf_response['Content-Type'], 'application/pdf')
        self.assertTrue(register_pdf_response.content[:4] == b'%PDF')
        project_response = self.client.get(f'/api/projects/{self.project.pk}/')
        self.assertEqual(project_response.status_code, 200)
        self.assertEqual(project_response.data['total_material_cost'], 35000)

    def test_legacy_manual_purchase_order_cannot_be_received_without_finance_clearance(self):
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            project=self.project,
            number='PO-LEGACY-BLOCK-001',
            supplier_name='Legacy Supplier',
            status=PurchaseOrder.STATUS_ORDERED,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='1.00',
            unit_price='35000.00',
        )
        self.client.force_login(self.storekeeper)

        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/receive/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)
        purchase_order.refresh_from_db()
        self.assertEqual(purchase_order.status, PurchaseOrder.STATUS_ORDERED)

    def test_legacy_manual_site_purchase_order_cannot_be_dispatched(self):
        purchase_order = PurchaseOrder.objects.create(
            company=self.company,
            project=self.project,
            number='PO-LEGACY-SITE-BLOCK-001',
            supplier_name='Legacy Supplier',
            status=PurchaseOrder.STATUS_ORDERED,
            delivery_destination=PurchaseOrder.DELIVERY_SITE,
        )
        PurchaseOrderItem.objects.create(
            purchase_order=purchase_order,
            material=self.material,
            quantity='1.00',
            unit_price='35000.00',
        )
        self.client.force_login(self.procurement_officer)

        response = self.client.post(f'/api/purchase-orders/{purchase_order.pk}/confirm-dispatch/')

        self.assertEqual(response.status_code, 400)
        self.assertIn('purchase_request', response.data)


class WorkflowBadgeApiTests(TestCase):
    def setUp(self):
        from apps.finance.factories import FinanceFixtureFactory
        from apps.finance.models import ProjectBudget

        self.fixture = FinanceFixtureFactory('BadgeA')
        self.other = FinanceFixtureFactory('BadgeB')
        PurchaseRequest.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            number='PR-BADGE-A',
            title='Pending technical review',
            requested_by=self.fixture.engineer,
        )
        PurchaseRequest.objects.create(
            company=self.other.company,
            project=self.other.project,
            number='PR-BADGE-B',
            title='Other company review',
            requested_by=self.other.engineer,
        )
        PurchaseOrder.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            number='PO-BADGE-A',
            supplier=self.fixture.supplier,
            supplier_name=self.fixture.supplier.name,
        )
        PurchaseOrder.objects.create(
            company=self.other.company,
            project=self.other.project,
            number='PO-BADGE-B',
            supplier=self.other.supplier,
            supplier_name=self.other.supplier.name,
        )
        ProjectBudget.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            name='Badge budget A',
            status=ProjectBudget.STATUS_SUBMITTED,
            created_by=self.fixture.finance_officer,
        )
        ProjectBudget.objects.create(
            company=self.other.company,
            project=self.other.project,
            name='Badge budget B',
            status=ProjectBudget.STATUS_SUBMITTED,
            created_by=self.other.finance_officer,
        )
        self.client = APIClient()

    def test_badges_are_company_isolated_and_role_aware(self):
        self.client.force_login(self.fixture.admin)
        response = self.client.get('/api/workflow-badges/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['requests'], 1)
        self.assertEqual(response.data['purchase_orders'], 1)
        self.assertEqual(response.data['inventory'], 1)
        self.assertEqual(response.data['budgets'], 1)

        self.client.force_login(self.fixture.finance_manager)
        finance_response = self.client.get('/api/workflow-badges/')
        self.assertEqual(finance_response.status_code, 200)
        self.assertEqual(finance_response.data['budgets'], 1)
        self.assertEqual(finance_response.data['purchase_orders'], 0)
        self.assertEqual(finance_response.data['inventory'], 0)

    def test_project_manager_only_sees_assigned_project_request_queue(self):
        self.fixture.project.manager = self.fixture.manager
        self.fixture.project.save(update_fields=['manager'])
        second_project = Project.objects.create(
            company=self.fixture.company,
            name='Unassigned project',
            code='UNASSIGNED-BADGE',
        )
        PurchaseRequest.objects.create(
            company=self.fixture.company,
            project=second_project,
            number='PR-BADGE-UNASSIGNED',
            title='Not this manager queue',
            requested_by=self.fixture.engineer,
        )

        self.client.force_login(self.fixture.manager)
        response = self.client.get('/api/workflow-badges/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['requests'], 1)

    def test_storekeeper_badge_counts_warehouse_receipts_only(self):
        PurchaseOrder.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            number='PO-BADGE-WAREHOUSE',
            supplier=self.fixture.supplier,
            supplier_name=self.fixture.supplier.name,
            status=PurchaseOrder.STATUS_ORDERED,
            delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE,
        )
        PurchaseOrder.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            number='PO-BADGE-SITE',
            supplier=self.fixture.supplier,
            supplier_name=self.fixture.supplier.name,
            status=PurchaseOrder.STATUS_DISPATCH_CONFIRMED,
            delivery_destination=PurchaseOrder.DELIVERY_SITE,
        )

        self.client.force_login(self.fixture.storekeeper)
        response = self.client.get('/api/workflow-badges/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['deliveries'], 1)

    def test_badges_require_authentication(self):
        response = self.client.get('/api/workflow-badges/')
        self.assertIn(response.status_code, [401, 403])


class DraftLifecycleActionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Lifecycle Demo')
        self.engineer = User.objects.create_user(
            username='lifecycle_engineer', password='password', company=self.company,
            role=User.ROLE_SITE_ENGINEER,
        )
        self.procurement = User.objects.create_user(
            username='lifecycle_procurement', password='password', company=self.company,
            role=User.ROLE_PROCUREMENT_OFFICER,
        )
        self.category = Category.objects.create(company=self.company, name='Lifecycle Materials')
        self.material = Material.objects.create(
            company=self.company, category=self.category, name='Lifecycle Cement', code='LIFE-CEM',
            unit=Material.UNIT_BAG, unit_price=1000, min_stock_level=1,
        )
        self.project = Project.objects.create(company=self.company, name='Lifecycle Project', code='LIFE-001')
        self.supplier = Supplier.objects.create(company=self.company, name='Lifecycle Supplier')
        self.client = APIClient()

    def test_requester_can_edit_and_delete_pending_purchase_request_with_audit(self):
        request = PurchaseRequest.objects.create(
            company=self.company, project=self.project, number='PR-LIFE-001', title='Initial request',
            requested_by=self.engineer, status=PurchaseRequest.STATUS_PENDING,
        )
        PurchaseRequestItem.objects.create(purchase_request=request, material=self.material, quantity=2)
        self.client.force_authenticate(self.engineer)

        update = self.client.patch(f'/api/purchase-requests/{request.pk}/', {'title': 'Updated request'}, format='json')
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data['title'], 'Updated request')

        delete = self.client.delete(f'/api/purchase-requests/{request.pk}/')
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(PurchaseRequest.objects.filter(pk=request.pk).exists())
        self.assertTrue(FinanceAuditEvent.objects.filter(action='purchase_request.deleted', object_id=str(request.pk)).exists())

    def test_procurement_can_edit_and_delete_draft_purchase_order_only(self):
        request = PurchaseRequest.objects.create(
            company=self.company, project=self.project, number='PR-LIFE-002', title='Approved request',
            requested_by=self.engineer, status=PurchaseRequest.STATUS_APPROVED,
        )
        PurchaseRequestItem.objects.create(purchase_request=request, material=self.material, quantity=2)
        order = PurchaseOrder.objects.create(
            company=self.company, purchase_request=request, project=self.project, number='PO-LIFE-001',
            supplier=self.supplier, supplier_name=self.supplier.name, status=PurchaseOrder.STATUS_DRAFT,
        )
        PurchaseOrderItem.objects.create(purchase_order=order, material=self.material, quantity=2, unit_price=1000)
        self.client.force_authenticate(self.procurement)

        update = self.client.patch(f'/api/purchase-orders/{order.pk}/', {'notes': 'Supplier quote received'}, format='json')
        self.assertEqual(update.status_code, 200)
        self.assertEqual(update.data['notes'], 'Supplier quote received')

        delete = self.client.delete(f'/api/purchase-orders/{order.pk}/')
        self.assertEqual(delete.status_code, 204)
        self.assertFalse(PurchaseOrder.objects.filter(pk=order.pk).exists())
        self.assertTrue(FinanceAuditEvent.objects.filter(action='purchase_order.deleted', object_id=str(order.pk)).exists())
