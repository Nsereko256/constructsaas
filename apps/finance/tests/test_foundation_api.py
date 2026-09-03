from decimal import Decimal
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.finance.models import Account, CashAccount

from ..factories import FinanceFixtureFactory
from ..models import Currency, FinanceAuditEvent, FinanceSettings, TaxCode


class FinanceFoundationApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('F')
        self.other = FinanceFixtureFactory('G')
        self.storekeeper = User.objects.create_user(
            username='foundation_storekeeper', password='password', company=self.fixture.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.client = APIClient()

    def test_company_gets_scoped_ugx_defaults(self):
        settings = FinanceSettings.objects.get(company=self.fixture.company)
        other_settings = FinanceSettings.objects.get(company=self.other.company)
        self.assertEqual(settings.base_currency.code, 'UGX')
        self.assertEqual(settings.negative_stock_policy, FinanceSettings.NEGATIVE_STOCK_PREVENT)
        self.assertNotEqual(settings.base_currency_id, other_settings.base_currency_id)
        self.assertEqual(Currency.objects.for_company(self.fixture.company).count(), 1)

    def test_finance_roles_and_admin_can_read_foundation(self):
        for user in (
            self.fixture.finance_officer,
            self.fixture.finance_manager,
            self.fixture.finance_viewer,
            self.fixture.admin,
        ):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.get('/api/v1/finance/currencies/').status_code, 200)
        self.client.force_authenticate(self.storekeeper)
        self.assertEqual(self.client.get('/api/v1/finance/currencies/').status_code, 403)

    def test_only_finance_manager_and_admin_can_change_configuration(self):
        payload = {'code': 'VAT18', 'name': 'Standard VAT', 'rate_percent': '18.0000'}
        for user in (self.fixture.finance_officer, self.fixture.finance_viewer):
            self.client.force_authenticate(user)
            self.assertEqual(self.client.post('/api/v1/finance/tax-codes/', payload, format='json').status_code, 403)

        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.post('/api/v1/finance/tax-codes/', payload, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        tax_code = TaxCode.objects.get(pk=response.data['id'])
        self.assertEqual(tax_code.rate_percent, Decimal('18.0000'))
        self.assertTrue(FinanceAuditEvent.objects.filter(
            company=self.fixture.company, object_type='TaxCode', object_id=str(tax_code.pk),
        ).exists())

    def test_client_company_value_is_ignored_and_authenticated_company_is_used(self):
        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.post(
            '/api/v1/finance/tax-codes/',
            {
                'company': self.other.company.id,
                'code': 'LEVY',
                'name': 'Local Levy',
                'rate_percent': '2.5000',
            },
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(TaxCode.objects.get(pk=response.data['id']).company_id, self.fixture.company.id)

    def test_cross_company_records_and_relationships_are_inaccessible(self):
        other_tax = TaxCode.objects.create(
            company=self.other.company, code='OTHER', name='Other Tax', rate_percent=Decimal('7.0000'),
        )
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.get(f'/api/v1/finance/tax-codes/{other_tax.pk}/').status_code, 404)
        list_response = self.client.get('/api/v1/finance/tax-codes/')
        self.assertEqual(list_response.data['count'], 0)
        relationship_response = self.client.post(
            '/api/v1/finance/cost-centres/',
            {'code': 'SITE', 'name': 'Site', 'project': self.other.project.id},
            format='json',
        )
        self.assertEqual(relationship_response.status_code, 400)
        self.assertIn('project', relationship_response.data)

    def test_bank_statement_csv_import_is_scoped_idempotent_and_reports_bad_rows(self):
        ledger = Account.objects.create(
            company=self.fixture.company, code='1015', name='Imported bank',
            account_type=Account.TYPE_ASSET,
        )
        cash = CashAccount.objects.create(
            company=self.fixture.company, code='BANK-IMPORT', name='Imported bank account',
            account=ledger, currency=FinanceSettings.objects.get(company=self.fixture.company).base_currency,
            is_petty_cash=False,
        )
        self.client.force_authenticate(self.fixture.finance_officer)
        csv = SimpleUploadedFile(
            'statement.csv',
            b'statement_date,reference,amount,description\n'
            b'2026-08-20,TX-001,125000.00,Customer receipt\n'
            b'2026-08-20,TX-001,125000.00,Duplicate receipt\n'
            b'not-a-date,TX-002,50.00,Bad date\n',
            content_type='text/csv',
        )
        response = self.client.post(
            '/api/v1/finance/bank-statement-lines/import-csv/',
            {'cash_account': cash.id, 'file': csv}, format='multipart',
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['created'], 1)
        self.assertEqual(response.data['skipped_duplicates'], 1)
        self.assertEqual(len(response.data['errors']), 1)
        self.assertEqual(cash.statement_lines.count(), 1)
        self.assertEqual(cash.statement_lines.first().imported_by_id, self.fixture.finance_officer.id)

    def test_base_currency_must_belong_to_authenticated_company(self):
        settings = FinanceSettings.objects.get(company=self.fixture.company)
        other_currency = Currency.objects.get(company=self.other.company, code='UGX')
        self.client.force_authenticate(self.fixture.finance_manager)
        response = self.client.patch(
            f'/api/v1/finance/settings/{settings.pk}/',
            {'base_currency': other_currency.pk},
            format='json',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('base_currency', response.data)

    def test_audit_events_are_read_only_and_append_only(self):
        event = FinanceAuditEvent.objects.create(
            company=self.fixture.company,
            actor=self.fixture.finance_manager,
            action='test.created',
            object_type='Test',
        )
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post('/api/v1/finance/audit-events/', {}, format='json').status_code, 405)
        self.assertEqual(
            self.client.patch(f'/api/v1/finance/audit-events/{event.pk}/', {'message': 'changed'}, format='json').status_code,
            405,
        )
        event.message = 'changed directly'
        with self.assertRaises(DjangoValidationError):
            event.save()
        with self.assertRaises(DjangoValidationError):
            FinanceAuditEvent.objects.filter(pk=event.pk).update(message='queryset change')
        with self.assertRaises(DjangoValidationError):
            FinanceAuditEvent.objects.filter(pk=event.pk).delete()

    def test_search_filter_and_ordering_follow_api_conventions(self):
        TaxCode.objects.create(
            company=self.fixture.company, code='VAT18', name='Standard VAT', rate_percent=Decimal('18.0000'),
        )
        TaxCode.objects.create(
            company=self.fixture.company, code='ZERO', name='Zero Rated', rate_percent=Decimal('0.0000'),
        )
        self.client.force_authenticate(self.fixture.finance_viewer)
        search = self.client.get('/api/v1/finance/tax-codes/?search=standard')
        self.assertEqual(search.data['count'], 1)
        filtered = self.client.get('/api/v1/finance/tax-codes/?rate_from=10&ordering=-rate_percent')
        self.assertEqual(filtered.data['count'], 1)
        self.assertEqual(filtered.data['results'][0]['code'], 'VAT18')
