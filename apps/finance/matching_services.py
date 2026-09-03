from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.procurement.models import (
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    PurchaseOrder,
    PurchaseOrderItem,
)
from apps.warehouse.models import StockMovement

from .configuration_services import record_finance_audit_event
from .models import (
    FinanceSettings,
    InvoiceApproval,
    InvoiceMatchItemResult,
    InvoiceMatchRun,
    SupplierCreditNote,
    SupplierCreditNoteItem,
    SupplierInvoice,
    SupplierInvoiceItem,
)
from .services import ZERO, _record_invoice_action, _save, base_money, money


APPROVED_INVOICE_STATUSES = {
    # Submitted and verified invoices reserve their accepted receipt quantity.
    # This prevents two invoices for the same PO line being in flight together.
    SupplierInvoice.STATUS_SUBMITTED,
    SupplierInvoice.STATUS_MATCHED,
    SupplierInvoice.STATUS_VERIFIED,
    SupplierInvoice.STATUS_APPROVED,
    SupplierInvoice.STATUS_POSTED,
    SupplierInvoice.STATUS_PARTIALLY_PAID,
    SupplierInvoice.STATUS_PAID,
}


def purchase_order_three_way_summary(*, purchase_order):
    """Return cumulative PO-line controls across GRNs, invoices and payments."""
    from .payment_services import approved_allocations

    lines = []
    for po_item in purchase_order.items.select_related('material').order_by('pk'):
        accepted, rejected, damaged = _receipt_quantities(purchase_order, po_item)
        invoice_items = list(SupplierInvoiceItem.objects.filter(
            company=purchase_order.company,
            purchase_order_item=po_item,
            invoice__status__in=APPROVED_INVOICE_STATUSES,
        ).select_related('invoice'))
        invoiced = money(sum((item.quantity for item in invoice_items), ZERO))
        paid_quantity = ZERO
        paid_amount = ZERO
        for item in invoice_items:
            invoice_paid = approved_allocations(item.invoice)
            if item.invoice.total_amount > ZERO:
                paid_ratio = min(invoice_paid / item.invoice.total_amount, Decimal('1'))
                paid_quantity += item.quantity * paid_ratio
                paid_amount += item.total * paid_ratio
        lines.append({
            'purchase_order_item': po_item.pk,
            'material_name': po_item.material.name,
            'material_code': po_item.material.code,
            'ordered_quantity': money(po_item.quantity),
            'accepted_quantity': accepted,
            'rejected_quantity': rejected,
            'damaged_quantity': damaged,
            'invoiced_quantity': invoiced,
            'paid_quantity': money(paid_quantity),
            'paid_amount': money(paid_amount),
            'remaining_receivable_quantity': money(max(po_item.quantity - accepted, ZERO)),
            'remaining_invoiceable_quantity': money(max(accepted - invoiced, ZERO)),
            'remaining_payable_quantity': money(max(invoiced - paid_quantity, ZERO)),
        })
    return lines


def _receipt_quantities(po, po_item):
    receipt_lines = GoodsReceivedNoteItem.objects.filter(
        company=po.company,
        purchase_order_item=po_item,
        goods_received_note__status=GoodsReceivedNote.STATUS_ACCEPTED,
    )
    totals = receipt_lines.aggregate(
        accepted=Sum('accepted_quantity'), rejected=Sum('rejected_quantity'), damaged=Sum('damaged_quantity'),
    )
    if receipt_lines.exists():
        return (
            money(totals['accepted'] or ZERO), money(totals['rejected'] or ZERO),
            money(totals['damaged'] or ZERO),
        )
    # Backward-compatible evidence for POs received before canonical GRNs existed.
    if po.delivery_destination == PurchaseOrder.DELIVERY_SITE:
        accepted = po_item.quantity if po.status == PurchaseOrder.STATUS_RECEIVED else ZERO
    else:
        accepted = StockMovement.objects.filter(
            company=po.company, purchase_order=po, purchase_order_item=po_item,
            movement_type__in=[StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN],
        ).aggregate(total=Sum('quantity'))['total'] or ZERO
    return money(accepted), ZERO, ZERO


def _previously_invoiced_quantity(company, po_item, current_invoice):
    prior_items = SupplierInvoiceItem.objects.filter(
        company=company, purchase_order_item=po_item,
        invoice__status__in=APPROVED_INVOICE_STATUSES,
    ).exclude(invoice=current_invoice)
    invoiced = prior_items.aggregate(total=Sum('quantity'))['total'] or ZERO
    credited = SupplierCreditNoteItem.objects.filter(
        company=company, invoice_item__in=prior_items,
        credit_note__status=SupplierCreditNote.STATUS_POSTED,
    ).aggregate(total=Sum('quantity'))['total'] or ZERO
    return money(max(invoiced - credited, ZERO))


def _item_match(invoice, line, settings):
    po_item = line.purchase_order_item
    accepted, rejected, damaged = _receipt_quantities(invoice.purchase_order, po_item)
    previous = _previously_invoiced_quantity(invoice.company, po_item, invoice)
    remaining = money(max(accepted - previous, ZERO))
    quantity_variance = money(line.quantity - remaining)
    invoice_base_price = base_money(line.unit_price, invoice.exchange_rate)
    price_variance = money(invoice_base_price - po_item.unit_price)
    price_percent = (
        ZERO if po_item.unit_price == ZERO
        else Decimal(abs(price_variance) * Decimal('100') / po_item.unit_price).quantize(Decimal('0.0001'))
    )
    explanations = []
    status = InvoiceMatchRun.STATUS_MATCHED
    quantity_over = max(quantity_variance, ZERO)
    if quantity_over > settings.quantity_matching_tolerance:
        status = InvoiceMatchRun.STATUS_BLOCKED
        explanations.append('Invoice quantity exceeds cumulative accepted quantity remaining after approved invoices.')
    elif line.quantity > po_item.quantity - previous + settings.quantity_matching_tolerance:
        status = InvoiceMatchRun.STATUS_BLOCKED
        explanations.append('Invoice quantity exceeds the remaining purchase-order quantity.')
    elif price_percent > settings.price_matching_tolerance:
        status = InvoiceMatchRun.STATUS_EXCEPTION
        explanations.append('Invoice price variance exceeds the configured percentage tolerance.')
    elif quantity_over > ZERO or price_variance != ZERO:
        status = InvoiceMatchRun.STATUS_WITHIN_TOLERANCE
        explanations.append('Quantity and price differences are within configured tolerances.')
    else:
        explanations.append('Quantity and price match accepted receipts and the purchase order.')
    if rejected or damaged:
        explanations.append(f'Receipts include {rejected} rejected and {damaged} damaged units; neither is invoiceable.')
    return {
        'line': line, 'po_item': po_item, 'ordered_quantity': money(po_item.quantity),
        'accepted_quantity': accepted, 'rejected_quantity': rejected, 'damaged_quantity': damaged,
        'previously_invoiced_quantity': previous, 'current_invoice_quantity': money(line.quantity),
        'remaining_invoiceable_quantity': remaining, 'po_price': money(po_item.unit_price),
        'invoice_price': invoice_base_price, 'quantity_variance': quantity_variance,
        'price_variance': price_variance, 'price_variance_percent': price_percent,
        'status': status, 'explanation': ' '.join(explanations),
    }


@transaction.atomic
def run_invoice_match(*, invoice, user, idempotency_key=''):
    if idempotency_key:
        existing = InvoiceMatchRun.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
        if existing:
            if existing.invoice_id != invoice.pk:
                raise ValidationError({'idempotency_key': ['This key was used for another match run.']})
            return existing
    locked = (
        SupplierInvoice.objects.select_for_update().select_related('purchase_order')
        .prefetch_related('items__purchase_order_item').get(pk=invoice.pk, company=user.company)
    )
    if locked.status not in {SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCH_EXCEPTION}:
        raise ValidationError({'status': ['Only submitted or match-exception invoices can be matched.']})
    po = PurchaseOrder.objects.select_for_update().get(pk=locked.purchase_order_id, company=user.company)
    po_items = list(PurchaseOrderItem.objects.select_for_update().filter(purchase_order=po).order_by('pk'))
    list(GoodsReceivedNoteItem.objects.select_for_update().filter(
        company=user.company, purchase_order_item__in=po_items,
    ).order_by('pk'))
    settings = FinanceSettings.objects.select_for_update().get(company=user.company)
    results = [_item_match(locked, line, settings) for line in locked.items.all()]
    statuses = {item['status'] for item in results}
    if InvoiceMatchRun.STATUS_BLOCKED in statuses:
        overall = InvoiceMatchRun.STATUS_BLOCKED
    elif InvoiceMatchRun.STATUS_EXCEPTION in statuses or locked.freight_amount or locked.other_charges_amount:
        overall = InvoiceMatchRun.STATUS_EXCEPTION
    elif InvoiceMatchRun.STATUS_WITHIN_TOLERANCE in statuses:
        overall = InvoiceMatchRun.STATUS_WITHIN_TOLERANCE
    else:
        overall = InvoiceMatchRun.STATUS_MATCHED
    explanations = []
    if locked.freight_amount or locked.other_charges_amount:
        explanations.append('Freight or other charges require authorized finance review because the PO has no charge lines.')
    explanations.extend(item['explanation'] for item in results if item['status'] in {
        InvoiceMatchRun.STATUS_EXCEPTION, InvoiceMatchRun.STATUS_BLOCKED,
    })
    run = InvoiceMatchRun(
        company=user.company, invoice=locked, purchase_order=po, status=overall,
        explanation=' '.join(explanations), subtotal=locked.subtotal,
        freight_amount=locked.freight_amount, other_charges_amount=locked.other_charges_amount,
        tax_amount=locked.tax_amount, credit_note_amount=locked.credit_amount,
        quantity_tolerance=settings.quantity_matching_tolerance,
        price_tolerance=settings.price_matching_tolerance,
        idempotency_key=idempotency_key, run_by=user,
    )
    _save(run)
    for item in results:
        line = item.pop('line')
        po_item = item.pop('po_item')
        _save(InvoiceMatchItemResult(
            company=user.company, match_run=run, invoice_item=line,
            purchase_order_item=po_item, **item,
        ))
    locked.status = (
        SupplierInvoice.STATUS_VERIFIED
        if overall in {InvoiceMatchRun.STATUS_MATCHED, InvoiceMatchRun.STATUS_WITHIN_TOLERANCE}
        else SupplierInvoice.STATUS_MATCH_EXCEPTION
    )
    _save(locked, update_fields=['status', 'updated_at'])
    record_finance_audit_event(
        company=user.company, actor=user, action='invoice.match_run', object_type='SupplierInvoice',
        object_id=locked.pk, metadata={'match_run_id': run.pk, 'status': overall},
        correlation_id=idempotency_key,
    )
    if overall in {InvoiceMatchRun.STATUS_EXCEPTION, InvoiceMatchRun.STATUS_BLOCKED}:
        from .notification_services import invoice_matching_exception

        transaction.on_commit(lambda: invoice_matching_exception(locked, run.explanation))
    return run


def assert_invoice_quantity_available(*, invoice):
    po_items = list(PurchaseOrderItem.objects.select_for_update().filter(
        purchase_order_id=invoice.purchase_order_id,
    ).order_by('pk'))
    list(GoodsReceivedNoteItem.objects.select_for_update().filter(
        company=invoice.company, purchase_order_item__in=po_items,
    ).order_by('pk'))
    settings = FinanceSettings.objects.get(company=invoice.company)
    for line in invoice.items.select_related('purchase_order_item'):
        result = _item_match(invoice, line, settings)
        if result['status'] == InvoiceMatchRun.STATUS_BLOCKED:
            raise ValidationError({'items': [{line.pk: {'quantity': [result['explanation']]}}]})


def _require_finance_manager(user):
    if user.role != User.ROLE_FINANCE_MANAGER:
        raise ValidationError({'non_field_errors': ['Only a Finance Manager may decide match exceptions.']})


@transaction.atomic
def approve_match_exception(*, invoice, user, reason):
    _require_finance_manager(user)
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reason is required.']})
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    run = InvoiceMatchRun.objects.select_for_update().filter(invoice=locked, company=user.company).first()
    if not run or run.status != InvoiceMatchRun.STATUS_EXCEPTION or run.exception_approved_by_id:
        raise ValidationError({'status': ['The latest match run has no approvable exception.']})
    assert_invoice_quantity_available(invoice=locked)
    InvoiceMatchRun.objects.filter(pk=run.pk).update(
        exception_reason=reason, exception_approved_by=user, exception_approved_at=timezone.now(),
    )
    SupplierInvoice.objects.filter(pk=locked.pk).update(status=SupplierInvoice.STATUS_VERIFIED)
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_APPROVE_EXCEPTION, comments=reason)
    run.refresh_from_db()
    return run


@transaction.atomic
def reject_match_exception(*, invoice, user, reason):
    _require_finance_manager(user)
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reason is required.']})
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    run = InvoiceMatchRun.objects.select_for_update().filter(invoice=locked, company=user.company).first()
    if not run or run.status != InvoiceMatchRun.STATUS_EXCEPTION or run.exception_rejected_by_id:
        raise ValidationError({'status': ['The latest match run has no rejectable exception.']})
    InvoiceMatchRun.objects.filter(pk=run.pk).update(
        status=InvoiceMatchRun.STATUS_BLOCKED, exception_reason=reason,
        exception_rejected_by=user, exception_rejected_at=timezone.now(),
    )
    SupplierInvoice.objects.filter(pk=locked.pk).update(status=SupplierInvoice.STATUS_MATCH_EXCEPTION)
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_REJECT_EXCEPTION, comments=reason)
    run.refresh_from_db()
    return run
