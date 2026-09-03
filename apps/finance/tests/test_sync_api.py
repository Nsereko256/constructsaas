from copy import deepcopy
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User

from ..configuration_services import ensure_finance_settings
from ..factories import FinanceFixtureFactory
from ..ledger_services import ensure_ledger_configuration
from ..models import Account, FinanceSyncReceipt, Payment


class FinanceOfflineSyncApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('SYNC')
        self.other = FinanceFixtureFactory('SYNC-OTHER')
        self.settings = ensure_finance_settings(self.fixture.company)
        ensure_ledger_configuration(self.fixture.company)
        self.cash = Account.objects.get(company=self.fixture.company, system_key=Account.SYSTEM_CASH)
        self.client = APIClient()
        self.client.force_authenticate(self.fixture.finance_officer)

    def payment_data(self, amount='100.00'):
        return {
            'supplier': self.fixture.supplier.pk,
            'source_account': self.cash.pk,
            'currency': self.settings.base_currency_id,
            'exchange_rate': '1.000000',
            'amount': amount,
            'payment_date': timezone.localdate().isoformat(),
            'method': Payment.METHOD_BANK,
            'reference': f'OFFLINE-{amount}',
            'notes': 'Prepared offline',
        }

    def envelope(self, *, key='sync-key', client_uuid=None, version=None, data=None):
        payload = {
            'record_type': 'payment',
            'client_uuid': str(client_uuid or uuid4()),
            'idempotency_key': key,
            'data': data or self.payment_data(),
        }
        if version is not None:
            payload['version'] = version
        return payload

    def test_exact_retry_returns_receipt_without_duplicate_submission(self):
        payload = self.envelope()
        created = self.client.post('/api/v1/finance/sync/drafts/', payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        self.assertFalse(created.data['replayed'])
        self.assertEqual(created.data['version'], 1)

        retried = self.client.post('/api/v1/finance/sync/drafts/', payload, format='json')
        self.assertEqual(retried.status_code, 200, retried.data)
        self.assertTrue(retried.data['replayed'])
        self.assertEqual(Payment.objects.filter(company=self.fixture.company).count(), 1)
        self.assertEqual(FinanceSyncReceipt.objects.filter(company=self.fixture.company).count(), 1)

    def test_changed_payload_with_reused_key_returns_structured_conflict(self):
        payload = self.envelope()
        self.assertEqual(self.client.post(
            '/api/v1/finance/sync/drafts/', payload, format='json',
        ).status_code, 201)
        changed = deepcopy(payload)
        changed['data']['amount'] = '101.00'
        response = self.client.post('/api/v1/finance/sync/drafts/', changed, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['type'], 'conflict')
        self.assertEqual(response.data['code'], 'idempotency_key_reused')

    def test_update_increments_version_and_stale_copy_is_never_last_write_wins(self):
        client_uuid = uuid4()
        created_payload = self.envelope(client_uuid=client_uuid, key='create-versioned')
        created = self.client.post('/api/v1/finance/sync/drafts/', created_payload, format='json')
        self.assertEqual(created.status_code, 201, created.data)

        updated_data = self.payment_data('125.00')
        updated = self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid,
            key='update-versioned',
            version=1,
            data=updated_data,
        ), format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertEqual(updated.data['version'], 2)

        stale = self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid,
            key='stale-versioned',
            version=1,
            data=self.payment_data('130.00'),
        ), format='json')
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(stale.data['code'], 'stale_version')
        self.assertEqual(stale.data['server']['version'], 2)
        self.assertEqual(Payment.objects.get(client_uuid=client_uuid).amount, 125)

    def test_duplicate_uuid_requires_explicit_current_version(self):
        client_uuid = uuid4()
        self.assertEqual(self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid, key='uuid-first',
        ), format='json').status_code, 201)
        duplicate = self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid, key='uuid-second', data=self.payment_data('150.00'),
        ), format='json')
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.data['code'], 'version_required')

    def test_non_draft_status_is_revalidated_during_sync(self):
        client_uuid = uuid4()
        self.assertEqual(self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid, key='status-first',
        ), format='json').status_code, 201)
        Payment.objects.filter(client_uuid=client_uuid).update(status=Payment.STATUS_SUBMITTED)
        response = self.client.post('/api/v1/finance/sync/drafts/', self.envelope(
            client_uuid=client_uuid,
            key='status-second',
            version=1,
            data=self.payment_data('155.00'),
        ), format='json')
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data['code'], 'status_changed')

    def test_revoked_role_is_rechecked_even_for_an_exact_retry(self):
        payload = self.envelope(key='permission-retry')
        self.assertEqual(self.client.post(
            '/api/v1/finance/sync/drafts/', payload, format='json',
        ).status_code, 201)
        User.objects.filter(pk=self.fixture.finance_officer.pk).update(role=User.ROLE_FINANCE_VIEWER)
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post('/api/v1/finance/sync/drafts/', payload, format='json')
        self.assertEqual(response.status_code, 403)

    def test_cross_company_relationship_attack_is_rejected(self):
        payload = self.envelope(key='cross-company')
        payload['data']['supplier'] = self.other.supplier.pk
        response = self.client.post('/api/v1/finance/sync/drafts/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('supplier', response.data)
        self.assertFalse(Payment.objects.filter(company=self.fixture.company).exists())

    def test_workflow_fields_cannot_be_smuggled_through_draft_sync(self):
        payload = self.envelope(key='workflow-field')
        payload['data']['status'] = Payment.STATUS_APPROVED
        response = self.client.post('/api/v1/finance/sync/drafts/', payload, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('data', response.data)
