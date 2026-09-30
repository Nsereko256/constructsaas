from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import Company, User
from apps.finance.models import FinanceSettings, WorkflowConfirmation
from apps.finance.configuration_services import ensure_finance_settings
from apps.procurement.models import PurchaseRequest
from apps.materials.models import Material
from apps.warehouse.models import Warehouse


class CompanyReadinessTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='Readiness QA')
        self.admin = User.objects.create_user(username='readiness-admin', company=self.company, role=User.ROLE_ADMIN)
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_new_company_get_does_not_create_settings_or_stock(self):
        before = (FinanceSettings.objects.count(), Material.objects.count(), Warehouse.objects.count())
        response = self.client.get('/api/company-readiness/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertGreater(response.data['attention_count'], 0)
        self.assertEqual(before, (FinanceSettings.objects.count(), Material.objects.count(), Warehouse.objects.count()))
        checks = {row['key']: row for row in response.data['checks']}
        self.assertEqual(checks['warehouse']['status'], 'attention')
        self.assertEqual(checks['legacy_stock']['status'], 'ready')

    def test_other_company_warehouse_does_not_satisfy_setup(self):
        other = Company.objects.create(name='Another company')
        Warehouse.objects.create(company=other, name='Other warehouse', code='MAIN', is_default=True)
        response = self.client.get('/api/company-readiness/')
        self.assertEqual(next(row for row in response.data['checks'] if row['key'] == 'warehouse')['status'], 'attention')

    def test_non_admin_cannot_read_company_readiness(self):
        for role in [User.ROLE_SITE_ENGINEER, User.ROLE_PROJECT_MANAGER, User.ROLE_STOREKEEPER, User.ROLE_FINANCE_OFFICER]:
            self.admin.role = role
            self.admin.save(update_fields=['role'])
            self.assertEqual(self.client.get('/api/company-readiness/').status_code, 403)

    def test_admin_self_return_and_rejection_keep_controlled_override(self):
        settings = ensure_finance_settings(self.company)
        settings.maker_checker_enforced = True
        settings.save(update_fields=['maker_checker_enforced'])
        for action, field, expected in [('return-for-correction', 'comments', 'RETURNED'), ('reject', 'rejection_reason', 'REJECTED')]:
            request = PurchaseRequest.objects.create(company=self.company, requested_by=self.admin, number=f'MR-{expected}', title='Controlled local decision')
            url = f'/api/purchase-requests/{request.pk}/{action}/'
            payload = {field: 'Confirm the quantities before this can proceed.'}
            self.assertEqual(self.client.post(url, payload, format='json').status_code, 400)
            payload['override_reason'] = 'Independent reviewer unavailable; controlled QA review.'
            response = self.client.post(url, payload, format='json')
            self.assertEqual(response.status_code, 200, response.data)
            self.assertEqual(response.data['status'], expected)
            task = WorkflowConfirmation.objects.get(company=self.company, object_id=str(request.pk), document_type='PURCHASE_REQUEST')
            self.assertEqual(task.override_reason, payload['override_reason'])
