from decimal import Decimal

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User

from ..factories import FinanceFixtureFactory
from ..models import (
    BudgetCategory,
    BudgetLine,
    BudgetTransaction,
    ProjectBudget,
    SupplierInvoice,
)
from ..report_services import REPORTS


class FinanceReportingApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('REPORT')
        self.other = FinanceFixtureFactory('REPORT-OTHER')
        self.client = APIClient()
        category = BudgetCategory.objects.create(
            company=self.fixture.company, code='REPORT-MAT', name='Reporting materials',
        )
        self.budget = ProjectBudget.objects.create(
            company=self.fixture.company,
            project=self.fixture.project,
            name='Approved reporting budget',
            created_by=self.fixture.finance_officer,
            approved_by=self.fixture.finance_manager,
        )
        line = BudgetLine.objects.create(
            company=self.fixture.company,
            budget=self.budget,
            category=category,
            original_amount=Decimal('1000.00'),
        )
        ProjectBudget.objects.filter(pk=self.budget.pk).update(status=ProjectBudget.STATUS_APPROVED)
        self.budget.refresh_from_db()
        BudgetTransaction.objects.create(
            company=self.fixture.company,
            budget=self.budget,
            budget_line=line,
            transaction_type=BudgetTransaction.TYPE_COMMITMENT,
            amount=Decimal('250.00'),
            description='Open test commitment',
            created_by=self.fixture.finance_manager,
        )
        BudgetTransaction.objects.create(
            company=self.fixture.company,
            budget=self.budget,
            budget_line=line,
            transaction_type=BudgetTransaction.TYPE_ACTUAL,
            amount=Decimal('100.00'),
            description='Test actual',
            created_by=self.fixture.finance_manager,
        )

    def authenticate(self, user=None):
        self.client.force_authenticate(user or self.fixture.finance_viewer)

    def test_dashboard_returns_authoritative_company_scoped_totals(self):
        self.authenticate()
        response = self.client.get('/api/v1/finance/dashboard/')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['approved_budgets'], Decimal('1000.00'))
        self.assertEqual(response.data['open_commitments'], Decimal('250.00'))
        self.assertEqual(response.data['actual_expenditure'], Decimal('100.00'))
        self.assertEqual(response.data['available_project_balances'], Decimal('650.00'))
        self.assertEqual(response.data['project_balances'][0]['project_id'], self.fixture.project.id)

    def test_all_detailed_reports_are_paginated_frontend_friendly_json(self):
        self.authenticate()
        for slug in REPORTS:
            with self.subTest(slug=slug):
                response = self.client.get(f'/api/v1/finance/reports/{slug}/?page_size=1')
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIn('totals', response.data)
                self.assertIn('results', response.data)
                self.assertIn('count', response.data)
                self.assertNotContains(response, '<html', status_code=200)

    def test_cross_company_filters_are_rejected_and_records_do_not_leak(self):
        self.authenticate()
        response = self.client.get(
            f'/api/v1/finance/reports/budget-vs-actual/?project={self.other.project.id}',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('project', response.data)

        listing = self.client.get('/api/v1/finance/reports/budget-vs-actual/')
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data['count'], 1)
        self.assertEqual(listing.data['results'][0]['id'], self.budget.id)

    def test_role_and_authentication_permissions_apply_to_json_and_downloads(self):
        engineer = User.objects.create_user(
            username='report_engineer', company=self.fixture.company, role=User.ROLE_SITE_ENGINEER,
        )
        self.authenticate(engineer)
        self.assertEqual(self.client.get('/api/v1/finance/dashboard/').status_code, 403)
        self.assertEqual(self.client.get(
            '/api/v1/finance/reports/budget-vs-actual/download/csv/',
        ).status_code, 403)

        self.client.force_authenticate(user=None)
        self.assertIn(self.client.get('/api/v1/finance/dashboard/').status_code, {401, 403})

    def test_csv_and_excel_exports_are_authenticated_real_file_downloads(self):
        self.authenticate()
        csv_response = self.client.get(
            '/api/v1/finance/reports/budget-vs-actual/download/csv/',
        )
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response['Content-Type'], 'text/csv; charset=utf-8')
        self.assertIn(b'Project code', csv_response.content)
        self.assertIn(b'FP-REPORT', csv_response.content)

        xlsx_response = self.client.get(
            '/api/v1/finance/reports/budget-vs-actual/download/xlsx/',
        )
        self.assertEqual(xlsx_response.status_code, 200)
        self.assertEqual(
            xlsx_response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertTrue(xlsx_response.content.startswith(b'PK'))

    def test_invalid_date_range_returns_field_level_error(self):
        self.authenticate()
        response = self.client.get(
            '/api/v1/finance/reports/payment-register/?date_from=2026-02-01&date_to=2026-01-01',
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn('date_to', response.data)

    def test_budget_report_query_count_is_bounded_as_rows_grow(self):
        self.authenticate()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v1/finance/reports/budget-vs-actual/')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 10, [query['sql'] for query in queries])

    def test_supplier_statement_uses_batched_balance_aggregates(self):
        purchase_order, purchase_order_item = self.fixture.received_purchase_order()
        for index in range(6):
            SupplierInvoice.objects.create(
                company=self.fixture.company,
                supplier=self.fixture.supplier,
                purchase_order=purchase_order,
                project=self.fixture.project,
                internal_number=f'REPORT-INV-{index}',
                invoice_number=f'SUP-REPORT-{index}',
                invoice_date=timezone.localdate(),
                currency='UGX',
                subtotal=Decimal('100.00'),
                total_amount=Decimal('100.00'),
                status=SupplierInvoice.STATUS_POSTED,
                created_by=self.fixture.finance_officer,
            )

        self.authenticate()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                '/api/v1/finance/reports/supplier-statements/?page_size=100',
            )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 6)
        self.assertEqual(response.data['totals']['base_balance'], Decimal('600.00'))
        self.assertLessEqual(len(queries), 10, [query['sql'] for query in queries])
