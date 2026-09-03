from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User

from ..factories import FinanceFixtureFactory


class FinancePermissionTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('P')
        self.storekeeper = User.objects.create_user(
            username='finance_storekeeper_p', password='password', company=self.fixture.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.client = APIClient()

    def test_only_finance_read_roles_can_list_ledger(self):
        for user in (
            self.fixture.manager,
            self.fixture.procurement,
            self.fixture.finance_officer,
            self.fixture.finance_manager,
            self.fixture.finance_viewer,
            self.fixture.admin,
        ):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/v1/finance/journal-entries/').status_code, 200)
        for user in (self.fixture.engineer, self.storekeeper):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/v1/finance/journal-entries/').status_code, 403)

    def test_only_admin_can_create_chart_account(self):
        payload = {'code': '6100', 'name': 'Site Overheads', 'account_type': 'EXPENSE'}
        self.client.force_authenticate(self.fixture.procurement)
        self.assertEqual(self.client.post('/api/v1/finance/accounts/', payload, format='json').status_code, 403)
        self.client.force_authenticate(self.fixture.admin)
        response = self.client.post('/api/v1/finance/accounts/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)

    def test_new_finance_roles_enforce_maker_and_checker_capabilities(self):
        self.client.force_authenticate(self.fixture.finance_officer)
        prepared = self.client.post('/api/v1/finance/supplier-invoices/', {}, format='json')
        self.assertEqual(prepared.status_code, 400)

        self.client.force_authenticate(self.fixture.finance_viewer)
        self.assertEqual(
            self.client.post('/api/v1/finance/supplier-invoices/', {}, format='json').status_code,
            403,
        )

        self.client.force_authenticate(self.fixture.finance_manager)
        prepared_by_manager = self.client.post('/api/v1/finance/supplier-invoices/', {}, format='json')
        self.assertEqual(prepared_by_manager.status_code, 400)
        checked = self.client.post(
            '/api/v1/finance/accounts/',
            {'code': '6200', 'name': 'Finance Charges', 'account_type': 'EXPENSE'},
            format='json',
        )
        self.assertEqual(checked.status_code, 201, checked.data)
