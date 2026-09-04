from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.procurement.models import PurchaseRequest

from .. import services
from ..factories import FinanceFixtureFactory
from ..models import ApprovalMatrixRule, BudgetApproval, JournalEntry, Payment, ProjectCost, SupplierInvoice, ThreeWayMatch


class FinanceServiceTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('S')

    def _posted_invoice(self):
        po, po_item = self.fixture.received_purchase_order()
        invoice = services.create_supplier_invoice(
            company=self.fixture.company,
            user=self.fixture.procurement,
            **self.fixture.invoice_payload(po, po_item),
        )
        services.submit_invoice(invoice=invoice, user=self.fixture.procurement)
        result = services.match_invoice(invoice=invoice, user=self.fixture.procurement, idempotency_key='match-1')
        self.assertEqual(result.status, ThreeWayMatch.STATUS_MATCHED)
        services.approve_invoice(invoice=invoice, user=self.fixture.admin)
        services.post_invoice(invoice=invoice, user=self.fixture.admin)
        invoice.refresh_from_db()
        return invoice

    def test_budget_approval_requires_technical_approval_and_blocks_over_budget(self):
        pending = self.fixture.purchase_request(status=PurchaseRequest.STATUS_PENDING)
        with self.assertRaises(ValidationError):
            services.create_budget_approval(purchase_request=pending, user=self.fixture.procurement)

        approved = self.fixture.purchase_request(quantity=Decimal('10.00'))
        approval = services.create_budget_approval(purchase_request=approved, user=self.fixture.procurement)
        self.assertEqual(approval.requested_amount, Decimal('350000.00'))
        approval = services.submit_budget_approval(approval=approval, user=self.fixture.procurement)
        approval = services.review_budget_approval(approval=approval, user=self.fixture.admin, approve=True)
        self.assertEqual(approval.status, BudgetApproval.STATUS_APPROVED)

    def test_three_way_match_records_exception_without_advancing_invoice(self):
        po, po_item = self.fixture.received_purchase_order()
        payload = self.fixture.invoice_payload(po, po_item)
        payload['items'][0]['quantity'] = Decimal('9.00')
        invoice = services.create_supplier_invoice(
            company=self.fixture.company, user=self.fixture.procurement, **payload,
        )
        services.submit_invoice(invoice=invoice, user=self.fixture.procurement)
        result = services.match_invoice(invoice=invoice, user=self.fixture.procurement)
        invoice.refresh_from_db()
        self.assertEqual(result.status, ThreeWayMatch.STATUS_EXCEPTION)
        self.assertEqual(invoice.status, SupplierInvoice.STATUS_SUBMITTED)
        self.assertTrue(result.exceptions)

    def test_invoice_approval_uses_configured_matrix_role(self):
        po, po_item = self.fixture.received_purchase_order()
        invoice = services.create_supplier_invoice(
            company=self.fixture.company, user=self.fixture.procurement,
            **self.fixture.invoice_payload(po, po_item, idempotency_key='matrix-invoice'),
        )
        services.submit_invoice(invoice=invoice, user=self.fixture.procurement)
        services.match_invoice(invoice=invoice, user=self.fixture.procurement, idempotency_key='matrix-match')
        ApprovalMatrixRule.objects.create(
            company=self.fixture.company,
            document_type=ApprovalMatrixRule.DOCUMENT_INVOICE,
            stage=ApprovalMatrixRule.STAGE_FINAL,
            approver_role=self.fixture.finance_manager.role,
            project=self.fixture.project,
            minimum_amount=Decimal('0.00'),
        )
        with self.assertRaises(DjangoValidationError):
            services.approve_invoice(invoice=invoice, user=self.fixture.finance_officer)
        services.approve_invoice(invoice=invoice, user=self.fixture.finance_manager)

    def test_post_payment_and_reversals_are_balanced_and_idempotent(self):
        invoice = self._posted_invoice()
        invoice_entry = JournalEntry.objects.get(
            source_type=JournalEntry.SOURCE_INVOICE, source_object_id=invoice.pk,
        )
        self.assertEqual(sum(line.debit for line in invoice_entry.lines.all()), invoice.total_amount)
        self.assertEqual(sum(line.credit for line in invoice_entry.lines.all()), invoice.total_amount)

        payment = services.pay_invoice(
            invoice=invoice,
            user=self.fixture.admin,
            amount=invoice.total_amount,
            payment_date=timezone.localdate(),
            method=Payment.METHOD_BANK,
            idempotency_key='payment-1',
        )
        repeated = services.pay_invoice(
            invoice=invoice,
            user=self.fixture.admin,
            amount=invoice.total_amount,
            payment_date=timezone.localdate(),
            method=Payment.METHOD_BANK,
            idempotency_key='payment-1',
        )
        self.assertEqual(payment.pk, repeated.pk)
        self.assertEqual(ProjectCost.objects.filter(payment=payment, is_reversal=False).count(), 1)

        payment_reversal = services.reverse_payment(
            payment=payment, user=self.fixture.admin, reason='Duplicate payment', idempotency_key='pay-reverse-1',
        )
        self.assertIsNotNone(payment_reversal.project_cost)
        invoice_reversal = services.reverse_invoice(
            invoice=invoice, user=self.fixture.admin, reason='Incorrect invoice', idempotency_key='inv-reverse-1',
        )
        self.assertEqual(invoice_reversal.journal_entry.reversal_of_id, invoice_entry.id)

    def test_posted_records_are_immutable(self):
        invoice = self._posted_invoice()
        invoice.notes = 'Mutated after posting'
        with self.assertRaises(DjangoValidationError):
            invoice.save()

    def test_idempotency_key_cannot_be_reused_for_different_payment(self):
        first = self._posted_invoice()
        po, po_item = self.fixture.received_purchase_order()
        second = services.create_supplier_invoice(
            company=self.fixture.company,
            user=self.fixture.procurement,
            **self.fixture.invoice_payload(po, po_item, idempotency_key='invoice-2'),
        )
        services.submit_invoice(invoice=second, user=self.fixture.procurement)
        services.match_invoice(invoice=second, user=self.fixture.procurement)
        services.approve_invoice(invoice=second, user=self.fixture.admin)
        services.post_invoice(invoice=second, user=self.fixture.admin)
        services.pay_invoice(
            invoice=first, user=self.fixture.admin, amount=first.total_amount,
            payment_date=timezone.localdate(), method=Payment.METHOD_BANK, idempotency_key='shared-key',
        )
        with self.assertRaises(ValidationError):
            services.pay_invoice(
                invoice=second, user=self.fixture.admin, amount=second.total_amount,
                payment_date=timezone.localdate(), method=Payment.METHOD_BANK, idempotency_key='shared-key',
            )
