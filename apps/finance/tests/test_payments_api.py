from decimal import Decimal
from threading import Barrier, Thread

from django.db import close_old_connections
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User

from .. import services
from ..factories import FinanceFixtureFactory
from ..models import (
    Account,
    Currency,
    JournalEntry,
    Payment,
    PaymentBatch,
    PaymentAllocation,
    SupplierAdvance,
    SupplierInvoice,
)
from ..payment_services import approve_payment, create_payment, submit_payment


def posted_invoice(fixture, key):
    po, po_item = fixture.received_purchase_order()
    invoice = services.create_supplier_invoice(
        company=fixture.company, user=fixture.finance_officer,
        **fixture.invoice_payload(po, po_item, idempotency_key=f'invoice-{key}'),
    )
    invoice.invoice_number = f'PAY-{key}'
    SupplierInvoice.objects.filter(pk=invoice.pk).update(invoice_number=invoice.invoice_number)
    services.submit_invoice(invoice=invoice, user=fixture.finance_officer)
    services.match_invoice(invoice=invoice, user=fixture.finance_officer, idempotency_key=f'match-{key}')
    services.approve_invoice(invoice=invoice, user=fixture.finance_manager)
    services.post_invoice(invoice=invoice, user=fixture.finance_manager, idempotency_key=f'post-invoice-{key}')
    invoice.refresh_from_db()
    return invoice


class SupplierPaymentApiTests(TestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('P')
        self.other = FinanceFixtureFactory('PX')
        self.invoice_one = posted_invoice(self.fixture, 'one')
        self.invoice_two = posted_invoice(self.fixture, 'two')
        self.cash = Account.objects.get(company=self.fixture.company, system_key=Account.SYSTEM_CASH)
        self.currency = Currency.objects.get(company=self.fixture.company, code='UGX')
        self.client = APIClient()

    def payment_payload(self, amount='150000.00', key='payment-one', reference='TXN-ONE'):
        return {
            'supplier': self.fixture.supplier.pk, 'source_account': self.cash.pk,
            'currency': self.currency.pk, 'exchange_rate': '1.000000',
            'amount': amount, 'payment_date': str(timezone.localdate()),
            'method': Payment.METHOD_BANK, 'reference': reference,
            'voucher_reference': f'V-{key}', 'idempotency_key': key,
        }

    def create_payment(self, **kwargs):
        self.client.force_authenticate(self.fixture.finance_officer)
        response = self.client.post('/api/v1/finance/payments/', self.payment_payload(**kwargs), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data['id']

    def allocate(self, payment_id, invoice, amount):
        response = self.client.post(
            f'/api/v1/finance/payments/{payment_id}/allocate/',
            {'invoice': invoice.pk, 'amount': str(amount)}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.data)
        return response

    def approve_and_post(self, payment_id, **approval):
        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.post(f'/api/v1/finance/payments/{payment_id}/submit/').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(
            f'/api/v1/finance/payments/{payment_id}/approve/', approval, format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        posted = self.client.post(
            f'/api/v1/finance/payments/{payment_id}/post/',
            {'idempotency_key': f'post-payment-{payment_id}'}, format='json',
        )
        self.assertEqual(posted.status_code, 201, posted.data)
        return posted

    def test_one_payment_allocates_partially_to_several_invoices(self):
        payment_id = self.create_payment()
        self.allocate(payment_id, self.invoice_one, '100000.00')
        self.allocate(payment_id, self.invoice_two, '50000.00')
        self.invoice_one.refresh_from_db()
        self.assertEqual(self.invoice_one.status, SupplierInvoice.STATUS_POSTED)
        self.approve_and_post(payment_id)
        self.invoice_one.refresh_from_db()
        self.invoice_two.refresh_from_db()
        self.assertEqual(self.invoice_one.balance, Decimal('250000.00'))
        self.assertEqual(self.invoice_two.balance, Decimal('300000.00'))
        self.assertEqual(PaymentAllocation.objects.filter(payment_id=payment_id, status='POSTED').count(), 2)
        entry = JournalEntry.objects.get(source_type=JournalEntry.SOURCE_PAYMENT, source_object_id=payment_id)
        self.assertEqual(sum(line.debit for line in entry.lines.all()), Decimal('150000.00'))
        self.assertEqual(sum(line.credit for line in entry.lines.all()), Decimal('150000.00'))

    def test_several_payments_can_partially_pay_one_invoice(self):
        first = self.create_payment(amount='100000.00', key='several-one', reference='SEVERAL-1')
        self.allocate(first, self.invoice_one, '100000.00')
        self.approve_and_post(first)
        second = self.create_payment(amount='50000.00', key='several-two', reference='SEVERAL-2')
        self.allocate(second, self.invoice_one, '50000.00')
        self.approve_and_post(second)
        self.invoice_one.refresh_from_db()
        self.assertEqual(self.invoice_one.balance, Decimal('200000.00'))
        self.assertEqual(self.invoice_one.status, SupplierInvoice.STATUS_PARTIALLY_PAID)

    def test_unapproved_allocations_never_change_invoice_balance(self):
        payment_id = self.create_payment(amount='350000.00', key='draft-allocation', reference='DRAFT-1')
        self.allocate(payment_id, self.invoice_one, '350000.00')
        self.invoice_one.refresh_from_db()
        self.assertEqual(self.invoice_one.balance, Decimal('350000.00'))
        self.assertEqual(self.invoice_one.status, SupplierInvoice.STATUS_POSTED)

    def test_unallocate_before_submission_and_reject_require_controlled_actions(self):
        payment_id = self.create_payment(amount='100000.00', key='unallocate', reference='UNALLOCATE-1')
        self.allocate(payment_id, self.invoice_one, '100000.00')
        removed = self.client.post(
            f'/api/v1/finance/payments/{payment_id}/unallocate/',
            {'invoice': self.invoice_one.pk}, format='json',
        )
        self.assertEqual(removed.status_code, 204)
        self.assertFalse(PaymentAllocation.objects.filter(payment_id=payment_id).exists())
        self.client.post(f'/api/v1/finance/payments/{payment_id}/submit/')
        self.client.force_authenticate(self.fixture.finance_manager)
        rejected = self.client.post(
            f'/api/v1/finance/payments/{payment_id}/reject/',
            {'reason': 'Supporting documents are incomplete'}, format='json',
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data['status'], Payment.STATUS_REJECTED)
        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/payments/{payment_id}/unallocate/',
            {'invoice': self.invoice_one.pk}, format='json',
        ).status_code, 400)

    def test_overpayment_requires_authorized_supplier_advance(self):
        payment_id = self.create_payment(amount='400000.00', key='advance', reference='ADVANCE-1')
        self.allocate(payment_id, self.invoice_one, '350000.00')
        self.client.post(f'/api/v1/finance/payments/{payment_id}/submit/')
        self.client.force_authenticate(self.fixture.finance_manager)
        refused = self.client.post(f'/api/v1/finance/payments/{payment_id}/approve/', {}, format='json')
        self.assertEqual(refused.status_code, 400)
        approved = self.client.post(f'/api/v1/finance/payments/{payment_id}/approve/', {
            'authorize_advance': True, 'advance_reason': 'Mobilization advance',
        }, format='json')
        self.assertEqual(approved.status_code, 200, approved.data)
        advance = SupplierAdvance.objects.get(payment_id=payment_id)
        self.assertEqual(advance.amount, Decimal('50000.00'))

    def test_duplicate_account_reference_and_idempotency_are_enforced(self):
        first_id = self.create_payment(key='duplicate-key', reference='DUP-REFERENCE')
        self.client.force_authenticate(self.fixture.finance_officer)
        repeated = self.client.post(
            '/api/v1/finance/payments/', self.payment_payload(key='duplicate-key', reference='DUP-REFERENCE'),
            format='json',
        )
        self.assertEqual(repeated.status_code, 201, repeated.data)
        self.assertEqual(repeated.data['id'], first_id)
        duplicate = self.client.post(
            '/api/v1/finance/payments/', self.payment_payload(key='another-key', reference='DUP-REFERENCE'),
            format='json',
        )
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn('reference', duplicate.data)

    def test_maker_checker_blocks_self_approval(self):
        payment = create_payment(
            user=self.fixture.finance_manager, supplier=self.fixture.supplier,
            source_account=self.cash, currency=self.currency, amount=Decimal('10000.00'),
            payment_date=timezone.localdate(), method=Payment.METHOD_CASH,
            reference='SELF-1', idempotency_key='self-payment',
        )
        submit_payment(payment=payment, user=self.fixture.finance_manager)
        with self.assertRaises(ValidationError):
            approve_payment(
                payment=payment, user=self.fixture.finance_manager,
                authorize_advance=True, advance_reason='Self-approved advance',
            )

    def test_payment_batch_requires_separate_approval_then_posts_every_voucher(self):
        first = self.create_payment(amount='100000.00', key='batch-one', reference='BATCH-1')
        second = self.create_payment(amount='50000.00', key='batch-two', reference='BATCH-2')
        self.allocate(first, self.invoice_one, '100000.00')
        self.allocate(second, self.invoice_two, '50000.00')
        self.client.post(f'/api/v1/finance/payments/{first}/submit/')
        self.client.post(f'/api/v1/finance/payments/{second}/submit/')
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(f'/api/v1/finance/payments/{first}/approve/', {}, format='json').status_code, 200)
        self.assertEqual(self.client.post(f'/api/v1/finance/payments/{second}/approve/', {}, format='json').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post('/api/v1/finance/payment-batches/', {
            'source_account': self.cash.pk, 'currency': self.currency.pk,
            'payment_date': str(timezone.localdate()), 'payment_ids': [first, second], 'notes': 'Friday bank run',
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        batch_id = created.data['id']
        self.assertEqual(self.client.post(f'/api/v1/finance/payment-batches/{batch_id}/submit/').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(f'/api/v1/finance/payment-batches/{batch_id}/approve/').status_code, 200)
        released = self.client.post(f'/api/v1/finance/payment-batches/{batch_id}/release/')
        self.assertEqual(released.status_code, 200, released.data)
        self.assertEqual(released.data['status'], PaymentBatch.STATUS_RELEASED)
        self.assertEqual(Payment.objects.get(pk=first).status, Payment.STATUS_POSTED)
        self.assertEqual(Payment.objects.get(pk=second).status, Payment.STATUS_POSTED)

    def test_posted_payment_is_immutable_and_reversal_restores_balance(self):
        payment_id = self.create_payment(amount='100000.00', key='reversible', reference='REV-1')
        self.allocate(payment_id, self.invoice_one, '100000.00')
        self.approve_and_post(payment_id)
        self.client.force_authenticate(self.fixture.finance_officer)
        self.assertEqual(self.client.patch(
            f'/api/v1/finance/payments/{payment_id}/', {'notes': 'mutated'}, format='json',
        ).status_code, 400)
        self.client.force_authenticate(self.fixture.finance_manager)
        reversed_response = self.client.post(f'/api/v1/finance/payments/{payment_id}/reverse/', {
            'reason': 'Wrong bank account', 'idempotency_key': 'reverse-payment-one',
        }, format='json')
        self.assertEqual(reversed_response.status_code, 201, reversed_response.data)
        self.invoice_one.refresh_from_db()
        self.assertEqual(self.invoice_one.balance, Decimal('350000.00'))
        self.assertEqual(Payment.objects.get(pk=payment_id).status, Payment.STATUS_REVERSED)

    def test_voucher_statement_balances_and_company_isolation(self):
        payment_id = self.create_payment(amount='50000.00', key='voucher', reference='VOUCHER-1')
        self.allocate(payment_id, self.invoice_one, '50000.00')
        self.approve_and_post(payment_id)
        voucher = self.client.get(f'/api/v1/finance/payments/{payment_id}/voucher/')
        self.assertEqual(voucher.status_code, 200, voucher.data)
        self.assertEqual(voucher.data['voucher_number'], Payment.objects.get(pk=payment_id).number)
        statement = self.client.get(
            f'/api/v1/finance/suppliers/{self.fixture.supplier.pk}/statement/',
        )
        self.assertEqual(statement.status_code, 200, statement.data)
        outstanding = self.client.get(
            f'/api/v1/finance/suppliers/{self.fixture.supplier.pk}/outstanding-balance/',
        )
        self.assertEqual(outstanding.status_code, 200, outstanding.data)
        self.client.force_authenticate(self.other.finance_viewer)
        self.assertEqual(self.client.get(
            f'/api/v1/finance/suppliers/{self.fixture.supplier.pk}/statement/',
        ).status_code, 404)


@skipUnlessDBFeature('has_select_for_update')
class ConcurrentSupplierPaymentTests(TransactionTestCase):
    def setUp(self):
        self.fixture = FinanceFixtureFactory('PC')
        self.invoice = posted_invoice(self.fixture, 'concurrent')
        self.cash = Account.objects.get(company=self.fixture.company, system_key=Account.SYSTEM_CASH)
        self.currency = Currency.objects.get(company=self.fixture.company, code='UGX')
        self.payments = []
        for index in range(2):
            payment = create_payment(
                user=self.fixture.finance_officer, supplier=self.fixture.supplier,
                source_account=self.cash, currency=self.currency, amount=Decimal('250000.00'),
                payment_date=timezone.localdate(), method=Payment.METHOD_BANK,
                reference=f'RACE-PAY-{index}', idempotency_key=f'race-pay-{index}',
            )
            from ..payment_services import allocate_payment
            allocate_payment(
                payment=payment, user=self.fixture.finance_officer,
                invoice=self.invoice, amount=Decimal('250000.00'),
            )
            submit_payment(payment=payment, user=self.fixture.finance_officer)
            self.payments.append(payment)

    def test_concurrent_approvals_cannot_overpay_invoice(self):
        barrier = Barrier(2)
        outcomes = []

        def approve(payment_id):
            close_old_connections()
            try:
                payment = Payment.objects.get(pk=payment_id)
                manager = User.objects.get(pk=self.fixture.finance_manager.pk)
                barrier.wait()
                approve_payment(payment=payment, user=manager)
                outcomes.append('approved')
            except ValidationError:
                outcomes.append('blocked')
            finally:
                close_old_connections()

        threads = [Thread(target=approve, args=(payment.pk,)) for payment in self.payments]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ['approved', 'blocked'])
