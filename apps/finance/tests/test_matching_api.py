from decimal import Decimal
from threading import Barrier, Thread

from django.db import close_old_connections
from django.test import TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, PurchaseOrderItem

from .. import matching_services, services
from ..configuration_services import ensure_finance_settings
from ..factories import FinanceFixtureFactory
from ..models import InvoiceMatchRun, SupplierInvoice


class ThreeWayMatchingApiTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        self.fixture = FinanceFixtureFactory('M')
        self.other = FinanceFixtureFactory('MX')
        self.storekeeper = User.objects.create_user(
            username='matching_storekeeper', password='password', company=self.fixture.company,
            role=User.ROLE_STOREKEEPER,
        )
        self.purchase_request = self.fixture.purchase_request(quantity=Decimal('10.00'))
        self.fixture.finance_clear_purchase_request(self.purchase_request)
        self.po = PurchaseOrder.objects.create(
            company=self.fixture.company, project=self.fixture.project, number='PO-MATCH-1',
            supplier=self.fixture.supplier, status=PurchaseOrder.STATUS_ORDERED,
            purchase_request=self.purchase_request,
        )
        self.po_item = PurchaseOrderItem.objects.create(
            purchase_order=self.po, material=self.fixture.material,
            quantity=Decimal('10.00'), unit_price=Decimal('35000.00'),
        )
        self.client = APIClient()

    def receive(self, accepted, rejected='0.00', damaged='0.00'):
        self.client.force_authenticate(self.storekeeper)
        return self.client.post(
            f'/api/purchase-orders/{self.po.pk}/receive/',
            {'items': [{
                'purchase_order_item': self.po_item.pk, 'accepted_quantity': str(accepted),
                'rejected_quantity': str(rejected), 'damaged_quantity': str(damaged),
                'notes': 'Quality exception recorded.' if Decimal(rejected) > 0 or Decimal(damaged) > 0 else '',
            }]}, format='json',
        )

    def create_and_match(self, number, quantity, price='35000.00', key=None, freight='0.00'):
        key = key or number.lower()
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post('/api/v1/finance/supplier-invoices/', {
            'supplier': self.fixture.supplier.pk, 'purchase_order': self.po.pk,
            'invoice_number': number, 'invoice_date': str(timezone.localdate()),
            'currency': 'UGX', 'freight_amount': str(freight), 'idempotency_key': key,
            'items': [{
                'purchase_order_item': self.po_item.pk, 'quantity': str(quantity),
                'unit_price': str(price), 'taxes': [],
            }],
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        invoice_id = created.data['id']
        self.assertEqual(
            self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/submit/').status_code, 200,
        )
        matched = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/run-match/',
            {'idempotency_key': f'match-{key}'}, format='json',
        )
        self.assertEqual(matched.status_code, 201, matched.data)
        return invoice_id, matched

    def test_several_grns_and_dispositions_feed_item_result(self):
        first = self.receive('4.00', rejected='1.00', damaged='1.00')
        self.assertEqual(first.status_code, 200, first.data)
        self.assertEqual(first.data['status'], PurchaseOrder.STATUS_PARTIAL)
        second = self.receive('4.00')
        self.assertEqual(second.status_code, 200, second.data)
        self.assertEqual(second.data['status'], PurchaseOrder.STATUS_RECEIVED)
        self.assertEqual(GoodsReceivedNote.objects.filter(purchase_order=self.po).count(), 2)
        self.assertEqual(self.fixture.material.current_stock, Decimal('8.00'))

        _, result = self.create_and_match('MATCH-1', '4.00')
        item = result.data['item_results'][0]
        self.assertEqual(result.data['status'], InvoiceMatchRun.STATUS_MATCHED)
        self.assertEqual(item['ordered_quantity'], '10.00')
        self.assertEqual(item['accepted_quantity'], '8.00')
        self.assertEqual(item['rejected_quantity'], '1.00')
        self.assertEqual(item['damaged_quantity'], '1.00')
        self.assertEqual(item['remaining_invoiceable_quantity'], '8.00')

    def test_partial_invoice_uses_only_previously_approved_quantity(self):
        self.receive('10.00')
        first_id, _ = self.create_and_match('PARTIAL-1', '4.00')
        self.client.force_authenticate(self.fixture.finance_manager)
        approved = self.client.post(f'/api/v1/finance/supplier-invoices/{first_id}/approve/')
        self.assertEqual(approved.status_code, 200, approved.data)

        _, second = self.create_and_match('PARTIAL-2', '6.00')
        item = second.data['item_results'][0]
        self.assertEqual(item['previously_invoiced_quantity'], '4.00')
        self.assertEqual(item['remaining_invoiceable_quantity'], '6.00')
        self.assertEqual(second.data['status'], InvoiceMatchRun.STATUS_MATCHED)

    def test_unaccepted_or_duplicate_quantity_is_blocked_at_submission(self):
        self.receive('4.00', rejected='3.00', damaged='3.00')
        self.client.force_authenticate(self.fixture.finance_officer)
        created = self.client.post('/api/v1/finance/supplier-invoices/', {
            'supplier': self.fixture.supplier.pk, 'purchase_order': self.po.pk,
            'invoice_number': 'BLOCKED-1', 'invoice_date': str(timezone.localdate()),
            'currency': 'UGX', 'idempotency_key': 'blocked-submit',
            'items': [{'purchase_order_item': self.po_item.pk, 'quantity': '5.00', 'unit_price': '35000.00', 'taxes': []}],
        }, format='json')
        self.assertEqual(created.status_code, 201, created.data)
        decision = self.client.post(f"/api/v1/finance/supplier-invoices/{created.data['id']}/submit/")
        self.assertEqual(decision.status_code, 400)

    def test_po_summary_is_cumulative_across_multiple_grns_and_invoices(self):
        self.receive('4.00')
        self.receive('6.00')
        first_id, _ = self.create_and_match('SUMMARY-1', '4.00')
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(f'/api/v1/finance/supplier-invoices/{first_id}/approve/').status_code, 200)
        self.client.force_authenticate(self.fixture.finance_officer)
        summary = self.client.get(f'/api/purchase-orders/{self.po.pk}/three-way-summary/')
        self.assertEqual(summary.status_code, 200, summary.data)
        item = summary.data['items'][0]
        self.assertEqual(item['ordered_quantity'], Decimal('10.00'))
        self.assertEqual(item['accepted_quantity'], Decimal('10.00'))
        self.assertEqual(item['invoiced_quantity'], Decimal('4.00'))
        self.assertEqual(item['remaining_invoiceable_quantity'], Decimal('6.00'))

    def test_only_finance_manager_can_approve_price_exception_with_reason(self):
        self.receive('10.00')
        invoice_id, result = self.create_and_match('PRICE-1', '2.00', price='36000.00')
        self.assertEqual(result.data['status'], InvoiceMatchRun.STATUS_EXCEPTION)
        self.client.force_authenticate(self.fixture.admin)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/approve-exception/',
            {'reason': 'Admin override'}, format='json',
        ).status_code, 403)
        self.client.force_authenticate(self.fixture.finance_manager)
        self.assertEqual(self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/approve-exception/', {}, format='json',
        ).status_code, 400)
        approved = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/approve-exception/',
            {'reason': 'Approved supplier escalation'}, format='json',
        )
        self.assertEqual(approved.status_code, 200, approved.data)
        self.assertTrue(approved.data['exception_is_approved'])
        self.assertEqual(
            self.client.post(f'/api/v1/finance/supplier-invoices/{invoice_id}/approve/').status_code, 200,
        )

    def test_price_difference_within_configured_tolerance_is_not_an_exception(self):
        self.receive('10.00')
        settings = ensure_finance_settings(self.fixture.company)
        settings.price_matching_tolerance = Decimal('3.0000')
        settings.save(update_fields=['price_matching_tolerance', 'updated_at'])
        _, result = self.create_and_match('TOLERANCE-1', '2.00', price='36000.00')
        self.assertEqual(result.data['status'], InvoiceMatchRun.STATUS_WITHIN_TOLERANCE)
        self.assertEqual(result.data['item_results'][0]['status'], InvoiceMatchRun.STATUS_WITHIN_TOLERANCE)

    def test_freight_requires_exception_decision_and_rejection_is_audited(self):
        self.receive('10.00')
        invoice_id, result = self.create_and_match('FREIGHT-1', '2.00', freight='5000.00')
        self.assertEqual(result.data['status'], InvoiceMatchRun.STATUS_EXCEPTION)
        self.client.force_authenticate(self.fixture.finance_manager)
        rejected = self.client.post(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/reject-exception/',
            {'reason': 'Freight was not authorized by the PO'}, format='json',
        )
        self.assertEqual(rejected.status_code, 200, rejected.data)
        self.assertEqual(rejected.data['status'], InvoiceMatchRun.STATUS_BLOCKED)
        self.assertTrue(SupplierInvoice.objects.get(pk=invoice_id).approvals.filter(
            action='REJECT_EXCEPTION', comments__icontains='not authorized',
        ).exists())

    def test_posted_credit_note_restores_invoiceable_quantity(self):
        self.receive('10.00')
        first_id, _ = self.create_and_match('CREDITED-1', '4.00')
        self.client.force_authenticate(self.fixture.finance_manager)
        self.client.post(f'/api/v1/finance/supplier-invoices/{first_id}/approve/')
        posted = self.client.post(
            f'/api/v1/finance/supplier-invoices/{first_id}/post/',
            {'idempotency_key': 'post-credited-1'}, format='json',
        )
        self.assertEqual(posted.status_code, 201, posted.data)
        invoice_item = SupplierInvoice.objects.get(pk=first_id).items.get()
        credited = self.client.post(
            f'/api/v1/finance/supplier-invoices/{first_id}/create-credit-note/',
            {
                'credit_note_number': 'MATCH-CN-1', 'credit_note_date': str(timezone.localdate()),
                'reason': 'Returned accepted unit', 'idempotency_key': 'match-credit-1',
                'items': [{'invoice_item': invoice_item.pk, 'quantity': '1.00'}],
            }, format='json',
        )
        self.assertEqual(credited.status_code, 201, credited.data)
        _, second = self.create_and_match('CREDITED-2', '7.00')
        item = second.data['item_results'][0]
        self.assertEqual(item['previously_invoiced_quantity'], '3.00')
        self.assertEqual(item['remaining_invoiceable_quantity'], '7.00')

    def test_match_results_are_company_isolated(self):
        self.receive('10.00')
        invoice_id, _ = self.create_and_match('ISOLATED-1', '1.00')
        self.client.force_authenticate(self.other.finance_manager)
        self.assertEqual(self.client.get(
            f'/api/v1/finance/supplier-invoices/{invoice_id}/match-results/',
        ).status_code, 404)


@skipUnlessDBFeature('has_select_for_update')
class MatchConsumptionConcurrencyTests(TransactionTestCase):
    """Executed on PostgreSQL; SQLite cannot exercise row-level SELECT FOR UPDATE."""

    def setUp(self):
        self.fixture = FinanceFixtureFactory('MC')
        self.po, self.po_item = self.fixture.received_purchase_order(quantity=Decimal('10.00'))
        self.invoices = []
        for index in range(2):
            invoice = services.create_supplier_invoice(
                company=self.fixture.company, user=self.fixture.finance_officer,
                purchase_order=self.po, supplier=self.fixture.supplier,
                invoice_number=f'RACE-{index}', invoice_date=timezone.localdate(),
                items=[{'purchase_order_item': self.po_item, 'quantity': Decimal('6.00'),
                        'unit_price': self.po_item.unit_price}], idempotency_key=f'race-{index}',
            )
            services.submit_invoice(invoice=invoice, user=self.fixture.finance_officer)
            matching_services.run_invoice_match(invoice=invoice, user=self.fixture.finance_officer)
            self.invoices.append(invoice)

    def test_concurrent_approvals_cannot_consume_same_receipt_quantity(self):
        barrier = Barrier(2)
        outcomes = []

        def approve(invoice_id):
            close_old_connections()
            try:
                invoice = SupplierInvoice.objects.get(pk=invoice_id)
                manager = User.objects.get(pk=self.fixture.finance_manager.pk)
                barrier.wait()
                services.approve_invoice(invoice=invoice, user=manager)
                outcomes.append('approved')
            except ValidationError:
                outcomes.append('blocked')
            finally:
                close_old_connections()

        threads = [Thread(target=approve, args=(invoice.pk,)) for invoice in self.invoices]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertCountEqual(outcomes, ['approved', 'blocked'])
        self.assertEqual(SupplierInvoice.objects.filter(status=SupplierInvoice.STATUS_APPROVED).count(), 1)
