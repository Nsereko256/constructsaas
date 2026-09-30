"""Read-only, quantity-safe progress shared by procurement views.

Receipt coverage is the mean of each line's coverage, never a sum of bags,
metres and pieces. Reversed receipts are not evidence of physical receipt.
"""
from decimal import Decimal
from urllib.parse import urlencode

from django.db.models import Max

from apps.finance.configuration_services import ensure_finance_settings
from apps.finance.models import PaymentAllocation, SupplierInvoice
from apps.accounts.models import User
from .models import GoodsReceivedNote, PurchaseOrder


def receipt_summary(order):
    items = list(order.items.all())
    prefetched = getattr(order, '_prefetched_objects_cache', {})
    if isinstance(prefetched, dict) and 'goods_received_notes' in prefetched:
        notes = [note for note in prefetched['goods_received_notes']
                 if note.status == GoodsReceivedNote.STATUS_ACCEPTED]
    else:
        notes = list(order.goods_received_notes.filter(
            status=GoodsReceivedNote.STATUS_ACCEPTED,
        ).prefetch_related('items'))
    accepted, exceptions = {}, {}
    for note in notes:
        for line in note.items.all():
            key = line.purchase_order_item_id
            accepted[key] = accepted.get(key, Decimal(0)) + line.accepted_quantity
            exceptions[key] = exceptions.get(key, Decimal(0)) + line.rejected_quantity + line.damaged_quantity
    lines = [{
        'purchase_order_item': item.pk,
        'accepted': str(accepted.get(item.pk, Decimal(0))),
        'exceptions': str(exceptions.get(item.pk, Decimal(0))),
        'outstanding': str(max(Decimal(0), item.quantity - accepted.get(item.pk, Decimal(0)))),
    } for item in items]
    coverage = [min(Decimal(1), accepted.get(item.pk, Decimal(0)) / item.quantity)
                if item.quantity > 0 else Decimal(0) for item in items]
    latest = max(notes, key=lambda note: note.created_at) if notes else None
    return {
        'percent': round(sum(coverage) / len(coverage) * 100, 1) if coverage else 0,
        'basis': 'Average accepted coverage per material line',
        'complete': bool(coverage) and all(value == 1 for value in coverage),
        'receipt_count': len(notes),
        'latest_receipt_number': latest.number if latest else None,
        'latest_receipt_at': latest.created_at if latest else None,
        'lines': lines,
    }


def purchase_order_next_step(order, user, approval=None, pending_edit=False):
    """Presentation contract only: mutation services still enforce every control."""
    settings = ensure_finance_settings(order.company)
    review_required = settings.soft_finance_enabled and settings.budget_control_mode != 'off'
    role = getattr(user, 'role', None)
    buyer = role in {User.ROLE_ADMIN, User.ROLE_PROCUREMENT_OFFICER}
    reviewer = role in {User.ROLE_ADMIN, User.ROLE_FINANCE_MANAGER}
    approval_status = approval.status if approval else 'DRAFT'
    search = urlencode({'search': order.number})
    result = {'owner': 'Procurement', 'message': '', 'action': None, 'finance_review_required': review_required}

    def action(key, label, href=None):
        result['action'] = {'key': key, 'label': label, 'href': href}

    if order.status == PurchaseOrder.STATUS_CANCELLED:
        result.update(owner='—', message='This order is cancelled. Historical records remain available.')
    elif order.status == PurchaseOrder.STATUS_DRAFT:
        result['message'] = 'Complete the draft before submitting it for approval.'
        if buyer:
            action('edit', 'Edit draft', f'/procurement/purchase-orders?{search}&edit={order.pk}')
    elif order.status == PurchaseOrder.STATUS_PENDING:
        if review_required and pending_edit:
            result.update(owner='Finance Manager', message='Finance must confirm the edited PO before it can be issued.')
            if reviewer:
                action('review_edit', 'Review edited PO', f'/procurement/purchase-orders?{search}&review_edit={order.pk}')
        elif review_required and approval_status in {'SUBMITTED', 'HOLD'}:
            result.update(owner='Finance Manager', message='Finance review is outstanding. Procurement cannot issue the order yet.')
            independent_review = (
                getattr(settings, 'maker_checker_enforced', False)
                and getattr(approval, 'created_by_id', None) is not None
                and approval.created_by_id == getattr(user, 'id', None)
            )
            if independent_review:
                result['message'] = 'You submitted this Finance request. A different Finance reviewer must decide it under company maker-checker policy.'
            elif reviewer and order.purchase_request_id:
                action('review_finance', 'Review Finance request', f'/procurement/requests?{urlencode({"search": order.purchase_request.number})}&review_finance={order.purchase_request_id}')
        elif review_required and approval_status == 'REJECTED':
            result['message'] = 'Finance rejected this order. Review the decision and correct it before resubmission.'
            if buyer:
                action('edit', 'Correct PO', f'/procurement/purchase-orders?{search}&edit={order.pk}')
        elif review_required and approval_status not in {'APPROVED', 'OVERRIDDEN'}:
            result['message'] = 'Send the priced order to Finance for budget review.'
            if buyer:
                action('send_finance', 'Send to Finance')
        else:
            result['message'] = 'Procurement can approve and issue this cleared purchase order.'
            if buyer:
                action('approve', 'Approve and issue PO')
    elif order.delivery_destination == PurchaseOrder.DELIVERY_SITE and order.status == PurchaseOrder.STATUS_ORDERED:
        result['message'] = 'Confirm supplier dispatch before the receiving team records arrival.'
        if buyer:
            action('dispatch', 'Confirm dispatch')
    elif order.status in {PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_DISPATCH_CONFIRMED, PurchaseOrder.STATUS_PARTIAL}:
        site = order.delivery_destination == PurchaseOrder.DELIVERY_SITE
        receivers = {User.ROLE_STOREKEEPER, User.ROLE_SITE_ENGINEER} if site else {User.ROLE_STOREKEEPER}
        result.update(owner='Storekeeper / Site Engineer' if site else 'Storekeeper',
                      message='Verify the delivered materials and record physical receipt quantities.')
        if role in receivers:
            action('receive', 'Record receipt', f'/procurement/deliveries?{search}&open_receipt={order.pk}')
        else:
            action('track', 'Track delivery', f'/procurement/deliveries?{search}')
    elif order.status == PurchaseOrder.STATUS_RECEIVED:
        follow_up = order_follow_up(order)
        outstanding = follow_up['stage'] is not None
        result.update(owner='Finance' if outstanding else '—',
                      message='Receiving finished. Review the outstanding invoice/payment work.' if outstanding else f"{follow_up['label']}. No outstanding operational stage; receipt history remains available.")
        if outstanding and role in {User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
            action('invoices', 'Review linked invoices', f'/finance/payables?purchase_order={order.pk}')
        else:
            action('receipts', 'View receipts', f'/procurement/grns?{search}')
    return result


def order_follow_up(order):
    """Delivery must finish before invoice settlement can complete an order."""
    settings = ensure_finance_settings(order.company)
    finance = settings.soft_finance_enabled and settings.invoice_tracking_enabled
    if order.status == PurchaseOrder.STATUS_CANCELLED:
        return {'stage': None, 'label': 'Cancelled', 'completed_at': order.updated_at}
    if order.status != PurchaseOrder.STATUS_RECEIVED:
        return {'stage': 'delivery', 'label': order.get_status_display(), 'completed_at': None}
    if not finance:
        return {'stage': None, 'label': 'Received / complete', 'completed_at': order.received_at}
    invoices = list(order.supplier_invoices.exclude(status__in=[
        SupplierInvoice.STATUS_REJECTED, SupplierInvoice.STATUS_REVERSED,
    ]).prefetch_related('items'))
    billed = {}
    for invoice in invoices:
        for line in invoice.items.all():
            billed[line.purchase_order_item_id] = billed.get(line.purchase_order_item_id, Decimal(0)) + line.quantity
    receipt = receipt_summary(order)
    fully_billed = bool(receipt['lines']) and all(
        billed.get(line['purchase_order_item'], Decimal(0)) >= Decimal(line['accepted'])
        for line in receipt['lines']
    )
    settled_statuses = {SupplierInvoice.STATUS_PAID}
    if not settings.payment_tracking_enabled:
        settled_statuses.add(SupplierInvoice.STATUS_POSTED)
    if invoices and fully_billed and all(invoice.status in settled_statuses for invoice in invoices):
        # Payment completion comes from posted allocation evidence, not an
        # invoice's mutable updated_at timestamp.
        paid_at = PaymentAllocation.objects.filter(
            company=order.company, invoice__in=invoices, status=PaymentAllocation.STATUS_POSTED,
            payment__status='POSTED',
        ).aggregate(value=Max('payment__posted_at'))['value']
        invoice_posted_at = max((invoice.posted_at for invoice in invoices if invoice.posted_at), default=None)
        return {'stage': None, 'label': 'Received / paid' if settings.payment_tracking_enabled else 'Received / invoiced',
                'completed_at': max(filter(None, [order.received_at, paid_at, invoice_posted_at]), default=None)}
    if any(invoice.status in {SupplierInvoice.STATUS_PAID, SupplierInvoice.STATUS_PARTIALLY_PAID} for invoice in invoices):
        label = 'Received / payment outstanding'
    elif invoices:
        label = 'Received / invoice follow-up'
    else:
        label = 'Received / ready to invoice'
    return {'stage': 'invoice_payment', 'label': label, 'completed_at': None}
