from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.notifications.models import Notification

from ..configuration_services import ensure_finance_settings
from ..factories import FinanceFixtureFactory
from ..ledger_services import ensure_ledger_configuration
from ..models import Account, Payment, StaffAdvance, SupplierInvoice
from ..notification_services import check_finance_deadlines_for_company


class FinanceNotificationIntegrationTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('NOTIFY')
        self.other = FinanceFixtureFactory('NOTIFY-OTHER')
        self.settings = ensure_finance_settings(self.fixture.company)
        ensure_ledger_configuration(self.fixture.company)
        self.cash = Account.objects.get(company=self.fixture.company, system_key=Account.SYSTEM_CASH)
        self.client = APIClient()

    def payment(self, suffix='1'):
        return Payment.objects.create(
            company=self.fixture.company,
            supplier=self.fixture.supplier,
            source_account=self.cash,
            currency=self.settings.base_currency,
            number=f'PAY-NOTIFY-{suffix}',
            amount=Decimal('100.00'),
            payment_date=timezone.localdate(),
            method=Payment.METHOD_BANK,
            reference=f'PAY-NOTIFY-REF-{suffix}',
            idempotency_key=f'pay-notify-{suffix}',
            created_by=self.fixture.finance_officer,
        )

    def test_payment_actions_publish_existing_api_notifications(self):
        payment = self.payment()
        self.client.force_authenticate(self.fixture.finance_officer)
        with self.captureOnCommitCallbacks(execute=True):
            submitted = self.client.post(f'/api/v1/finance/payments/{payment.pk}/submit/')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.finance_manager,
            notification_type=Notification.TYPE_PAYMENT_AWAITING_APPROVAL,
        ).exists())

        self.client.force_authenticate(self.fixture.finance_manager)
        with self.captureOnCommitCallbacks(execute=True):
            approved = self.client.post(f'/api/v1/finance/payments/{payment.pk}/approve/', {
                'authorize_advance': True,
                'advance_reason': 'Approved supplier deposit',
            }, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.finance_officer,
            notification_type=Notification.TYPE_PAYMENT_APPROVED,
        ).exists())

        rejected_payment = self.payment('2')
        self.client.force_authenticate(self.fixture.finance_officer)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/api/v1/finance/payments/{rejected_payment.pk}/submit/')
        self.client.force_authenticate(self.fixture.finance_manager)
        with self.captureOnCommitCallbacks(execute=True):
            rejected = self.client.post(f'/api/v1/finance/payments/{rejected_payment.pk}/reject/', {
                'reason': 'Bank account details need correction',
            }, format='json')
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.finance_officer,
            notification_type=Notification.TYPE_PAYMENT_REJECTED,
        ).exists())

    def test_invoice_submit_and_match_exception_publish_notifications(self):
        purchase_order, purchase_order_item = self.fixture.received_purchase_order()
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post('/api/v1/finance/supplier-invoices/', {
            'supplier': self.fixture.supplier.pk,
            'purchase_order': purchase_order.pk,
            'invoice_number': 'SUP-NOTIFY-INV-1',
            'invoice_date': timezone.localdate().isoformat(),
            'currency': self.settings.base_currency.code,
            'items': [{
                'purchase_order_item': purchase_order_item.pk,
                'quantity': '10.00',
                'unit_price': '36000.00',
                'taxes': [],
            }],
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        invoice_id = created.data['id']
        with self.captureOnCommitCallbacks(execute=True):
            submitted = self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/')
        self.assertEqual(submitted.status_code, 200, submitted.data)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.finance_manager,
            notification_type=Notification.TYPE_INVOICE_SUBMITTED,
        ).exists())

        with self.captureOnCommitCallbacks(execute=True):
            matched = self.client.post(
                f'/api/v1/finance/supplier-invoices/{invoice_id}/run-match/',
                {'idempotency_key': 'notify-match-exception'},
                format='json',
            )
        self.assertEqual(matched.status_code, 201, matched.data)
        self.assertIn(matched.data['status'], {'EXCEPTION', 'BLOCKED'})
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.finance_manager,
            notification_type=Notification.TYPE_INVOICE_MATCH_EXCEPTION,
        ).exists())

    def test_deadline_action_detects_due_documents_and_deduplicates_unread_alerts(self):
        as_of = timezone.localdate() + timedelta(days=10)
        purchase_order, _ = self.fixture.received_purchase_order()
        invoice = SupplierInvoice.objects.create(
            company=self.fixture.company,
            supplier=self.fixture.supplier,
            purchase_order=purchase_order,
            project=self.fixture.project,
            internal_number='INV-DEADLINE-1',
            invoice_number='SUP-DEADLINE-1',
            invoice_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=2),
            currency='UGX',
            subtotal=Decimal('100.00'),
            total_amount=Decimal('100.00'),
            status=SupplierInvoice.STATUS_POSTED,
            created_by=self.fixture.finance_officer,
        )
        due_soon_invoice = SupplierInvoice.objects.create(
            company=self.fixture.company,
            supplier=self.fixture.supplier,
            purchase_order=purchase_order,
            project=self.fixture.project,
            internal_number='INV-DEADLINE-2',
            invoice_number='SUP-DEADLINE-2',
            invoice_date=timezone.localdate(),
            due_date=as_of + timedelta(days=2),
            currency='UGX',
            subtotal=Decimal('50.00'),
            total_amount=Decimal('50.00'),
            status=SupplierInvoice.STATUS_POSTED,
            created_by=self.fixture.finance_officer,
        )
        advance = StaffAdvance.objects.create(
            company=self.fixture.company,
            number='SADV-DEADLINE-1',
            staff=self.fixture.engineer,
            project=self.fixture.project,
            purpose='Site operating advance',
            advance_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=3),
            currency=self.settings.base_currency,
            amount=Decimal('200.00'),
            base_amount=Decimal('200.00'),
            status=StaffAdvance.STATUS_PAID,
            idempotency_key='advance-deadline-1',
            created_by=self.fixture.finance_officer,
        )

        self.client.force_authenticate(self.fixture.finance_manager)
        first = self.client.post('/api/v1/finance/notification-checks/deadlines/', {
            'as_of': as_of.isoformat(), 'due_soon_days': 7,
        }, format='json')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertGreater(first.data['created_count'], 0)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            notification_type=Notification.TYPE_INVOICE_OVERDUE,
            link=f'/api/v1/finance/supplier-invoices/{invoice.pk}/',
        ).exists())
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            notification_type=Notification.TYPE_INVOICE_DUE_SOON,
            link=f'/api/v1/finance/supplier-invoices/{due_soon_invoice.pk}/',
        ).exists())
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.engineer,
            notification_type=Notification.TYPE_STAFF_ADVANCE_OVERDUE,
            link=f'/api/v1/finance/staff-advances/{advance.pk}/',
        ).exists())
        self.assertFalse(Notification.objects.filter(company=self.other.company).exists())

        second = self.client.post('/api/v1/finance/notification-checks/deadlines/', {
            'as_of': as_of.isoformat(), 'due_soon_days': 7,
        }, format='json')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['created_count'], 0)

    def test_deadline_service_does_not_cross_company_boundary(self):
        created = check_finance_deadlines_for_company(self.other.company)
        self.assertEqual(created, [])
        self.assertFalse(Notification.objects.filter(company=self.fixture.company).exists())

    def test_failed_journal_posting_alerts_finance_reviewers(self):
        expense = Account.objects.create(
            company=self.fixture.company,
            code='6999-NOTIFY',
            name='Notification test expense',
            account_type=Account.TYPE_EXPENSE,
        )
        self.client.force_authenticate(self.fixture.finance_officer)
        draft = self.client.post('/api/v1/finance/journals/', {
            'date': timezone.localdate().isoformat(),
            'description': 'Unbalanced journal notification test',
            'lines': [
                {'account': expense.pk, 'debit': '100.00', 'credit': '0.00'},
                {'account': self.cash.pk, 'debit': '0.00', 'credit': '90.00'},
            ],
        }, format='json')
        self.assertEqual(draft.status_code, 201, draft.data)

        self.client.force_authenticate(self.fixture.finance_manager)
        posted = self.client.post(f"/api/v1/finance/journals/{draft.data['id']}/post/")
        self.assertEqual(posted.status_code, 400, posted.data)
        self.assertTrue(Notification.objects.filter(
            company=self.fixture.company,
            recipient=self.fixture.admin,
            notification_type=Notification.TYPE_JOURNAL_POSTING_FAILURE,
        ).exists())

    def test_finance_notification_types_are_part_of_existing_notification_contract(self):
        configured = {value for value, _ in Notification.NOTIFICATION_TYPE_CHOICES}
        expected = {
            Notification.TYPE_BUDGET_APPROVAL_REQUIRED,
            Notification.TYPE_BUDGET_THRESHOLD_REACHED,
            Notification.TYPE_PO_EXCEEDING_BUDGET,
            Notification.TYPE_INVOICE_SUBMITTED,
            Notification.TYPE_INVOICE_MATCH_EXCEPTION,
            Notification.TYPE_INVOICE_DUE_SOON,
            Notification.TYPE_INVOICE_OVERDUE,
            Notification.TYPE_PAYMENT_AWAITING_APPROVAL,
            Notification.TYPE_PAYMENT_APPROVED,
            Notification.TYPE_PAYMENT_REJECTED,
            Notification.TYPE_STAFF_ADVANCE_OVERDUE,
            Notification.TYPE_VALUATION_ADJUSTMENT,
            Notification.TYPE_JOURNAL_POSTING_FAILURE,
        }
        self.assertTrue(expected.issubset(configured))
