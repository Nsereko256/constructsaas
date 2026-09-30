from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from django.utils import timezone

from .progress import order_follow_up, receipt_summary, purchase_order_next_step
from .stage_tracking import _stage_payload, _inferred_current_stage


class OrderProgressTests(SimpleTestCase):
    def setUp(self):
        self.order = Mock(status='PARTIAL', received_at=timezone.now(), updated_at=timezone.now())
        self.order.get_status_display.return_value = 'Partial'
        self.order.items.all.return_value = [SimpleNamespace(pk=1, quantity=Decimal(1000)), SimpleNamespace(pk=2, quantity=Decimal(1))]
        note = Mock(created_at=timezone.now(), number='GRN-1')
        note.items.all.return_value = [SimpleNamespace(purchase_order_item_id=1, accepted_quantity=Decimal(1000), rejected_quantity=Decimal(0), damaged_quantity=Decimal(0))]
        self.order.goods_received_notes.filter.return_value.prefetch_related.return_value = [note]
        self.order.supplier_invoices.exclude.return_value.prefetch_related.return_value = []
        self.settings = SimpleNamespace(soft_finance_enabled=True, invoice_tracking_enabled=True, payment_tracking_enabled=True, budget_control_mode='block')
        patcher = patch('apps.procurement.progress.ensure_finance_settings', return_value=self.settings)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_progress_does_not_add_different_material_units(self):
        summary = receipt_summary(self.order)
        self.assertEqual(summary['percent'], 50)
        self.assertFalse(summary['complete'])
        self.assertEqual(summary['lines'][1]['outstanding'], '1')
        self.order.goods_received_notes.filter.assert_called_once_with(status='ACCEPTED')

    def test_no_receipt_does_not_infer_accepted_quantity_from_status(self):
        self.order.status = 'RECEIVED'
        self.order.goods_received_notes.filter.return_value.prefetch_related.return_value = []
        self.assertEqual(receipt_summary(self.order)['percent'], 0)

    def test_prefetched_receipts_are_reused_and_reversed_receipts_excluded(self):
        note = Mock(status='ACCEPTED', created_at=timezone.now(), number='GRN-OK')
        note.items.all.return_value = [SimpleNamespace(purchase_order_item_id=2, accepted_quantity=Decimal(1), rejected_quantity=Decimal(0), damaged_quantity=Decimal(0))]
        self.order._prefetched_objects_cache = {'goods_received_notes': [note, Mock(status='REVERSED')]}
        summary = receipt_summary(self.order)
        self.assertEqual(summary['percent'], 50)
        self.assertEqual(summary['receipt_count'], 1)
        self.order.goods_received_notes.filter.assert_not_called()

    def test_partial_delivery_is_not_completed_by_a_paid_invoice(self):
        self.assertEqual(order_follow_up(self.order)['stage'], 'delivery')
        self.order.supplier_invoices.exclude.assert_not_called()

    def test_received_finance_off_has_no_invoice_blocker(self):
        self.order.status = 'RECEIVED'
        self.settings.soft_finance_enabled = False
        result = order_follow_up(self.order)
        self.assertIsNone(result['stage'])
        self.assertEqual(result['completed_at'], self.order.received_at)

    def test_received_finance_on_requires_invoice(self):
        self.order.status = 'RECEIVED'
        self.assertEqual(order_follow_up(self.order)['stage'], 'invoice_payment')

    def invoice(self, status, quantity=1000):
        invoice = Mock(status=status, posted_at=timezone.now() - timedelta(hours=1))
        invoice.items.all.return_value = [SimpleNamespace(purchase_order_item_id=1, quantity=Decimal(quantity))]
        return invoice

    def test_latest_paid_invoice_does_not_hide_another_unpaid_invoice(self):
        self.order.status = 'RECEIVED'
        self.order.supplier_invoices.exclude.return_value.prefetch_related.return_value = [self.invoice('POSTED'), self.invoice('PAID')]
        self.assertEqual(order_follow_up(self.order)['stage'], 'invoice_payment')

    def test_partial_billing_still_requires_follow_up(self):
        self.order.status = 'RECEIVED'
        self.order.supplier_invoices.exclude.return_value.prefetch_related.return_value = [self.invoice('PAID', 100)]
        self.assertEqual(order_follow_up(self.order)['stage'], 'invoice_payment')

    @patch('apps.procurement.progress.PaymentAllocation.objects')
    def test_payment_completion_uses_posted_evidence(self, allocations):
        self.order.status = 'RECEIVED'
        self.order.supplier_invoices.exclude.return_value.prefetch_related.return_value = [self.invoice('PAID')]
        paid_at = timezone.now() + timedelta(hours=1)
        allocations.filter.return_value.aggregate.return_value = {'value': paid_at}
        result = order_follow_up(self.order)
        self.assertIsNone(result['stage'])
        self.assertEqual(result['completed_at'], paid_at)

    def test_cancelled_confirmation_without_decided_timestamp_is_not_current(self):
        result = _stage_payload(key='manager_review', started_at=timezone.now() - timedelta(days=3), status='CANCELLED')
        self.assertFalse(result['is_current'])
        self.assertFalse(result['is_stalled'])

    def test_partial_request_stays_with_receiving_team(self):
        request = Mock(status='PO_CREATED', updated_at=timezone.now())
        self.order.pk = 1
        self.order.delivery_destination = 'WAREHOUSE'
        stage, _ = _inferred_current_stage(request, [self.order], [])
        self.assertEqual(stage, 'warehouse_receipt')

    def next_step(self, status, role, finance='DRAFT', pending_edit=False):
        self.order.status = status
        self.order.pk = 10
        self.order.number = 'PO-10'
        self.order.purchase_request_id = 20
        self.order.purchase_request.number = 'MR-20'
        self.order.delivery_destination = 'WAREHOUSE'
        return purchase_order_next_step(self.order, SimpleNamespace(role=role), SimpleNamespace(status=finance), pending_edit)

    def test_pending_order_offers_finance_handoff_not_premature_approval(self):
        self.assertEqual(self.next_step('PENDING', 'procurement_officer')['action']['key'], 'send_finance')

    def test_pending_finance_review_blocks_procurement(self):
        step = self.next_step('PENDING', 'procurement_officer', 'SUBMITTED')
        self.assertIsNone(step['action'])
        self.assertEqual(step['owner'], 'Finance Manager')

    def test_next_action_does_not_offer_a_forbidden_self_review(self):
        self.next_step('PENDING', 'admin', 'SUBMITTED')
        self.settings.maker_checker_enforced = True
        step = purchase_order_next_step(self.order, SimpleNamespace(role='admin', id=7), SimpleNamespace(status='SUBMITTED', created_by_id=7))
        self.assertIsNone(step['action'])
        self.assertIn('different Finance reviewer', step['message'])

    def test_cleared_order_can_be_issued_and_finance_off_does_not_block_it(self):
        self.assertEqual(self.next_step('PENDING', 'procurement_officer', 'APPROVED')['action']['key'], 'approve')
        self.settings.soft_finance_enabled = False
        self.assertEqual(self.next_step('PENDING', 'procurement_officer')['action']['key'], 'approve')

    def test_unconfirmed_price_edit_prevents_issuing_previously_cleared_order(self):
        step = self.next_step('PENDING', 'procurement_officer', 'APPROVED', pending_edit=True)
        self.assertIsNone(step['action'])
        self.assertIn('edited PO', step['message'])

    def test_warehouse_receipt_action_only_goes_to_storekeeper(self):
        self.assertEqual(self.next_step('ORDERED', 'storekeeper')['action']['key'], 'receive')
        self.assertEqual(self.next_step('ORDERED', 'site_engineer')['action']['key'], 'track')

    def test_engineer_never_gets_finance_navigation(self):
        step = self.next_step('RECEIVED', 'site_engineer')
        self.assertEqual(step['action']['key'], 'receipts')
        self.assertNotIn('/finance', step['action']['href'])

    def test_received_with_invoice_tracking_off_has_no_finance_action(self):
        self.settings.invoice_tracking_enabled = False
        step = self.next_step('RECEIVED', 'finance_manager')
        self.assertEqual(step['action']['key'], 'receipts')
        self.assertEqual(step['owner'], '—')

    def test_request_message_uses_order_progress_not_latest_invoice_status(self):
        from apps.api.serializers import PurchaseRequestSerializer, PurchaseOrderSerializer
        request = Mock(status='PO_CREATED')
        request.purchase_orders.order_by.return_value.first.return_value = self.order
        with patch.object(PurchaseOrderSerializer, 'get_next_step', return_value={'message': 'Record outstanding receipt quantities.'}) as next_step:
            message = PurchaseRequestSerializer().get_next_action_message(request)
        self.assertEqual(message, 'Record outstanding receipt quantities.')
        next_step.assert_called_once_with(self.order)
        self.order.supplier_invoices.order_by.assert_not_called()

    def test_request_label_does_not_present_pending_po_as_pending_manager_review(self):
        from apps.api.serializers import PurchaseRequestSerializer
        request = Mock(status='PO_CREATED')
        request.purchase_orders.order_by.return_value.first.return_value = self.order
        self.order.status = 'PENDING'
        self.assertEqual(PurchaseRequestSerializer().get_status_display(request), 'PO awaiting issue')
