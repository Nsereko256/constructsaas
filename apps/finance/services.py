from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.procurement.models import PurchaseOrder, PurchaseRequest
from apps.warehouse.models import StockMovement
from apps.api.upload_validation import validate_image_upload

from .models import (
    Account,
    BudgetApproval,
    CostCentre,
    Currency,
    FinanceDocumentSequence,
    FinanceSettings,
    InvoiceApproval,
    InvoiceAttachment,
    InvoiceReversal,
    JournalEntry,
    JournalLine,
    Payment,
    PaymentAllocation,
    PaymentReversal,
    ProjectCost,
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierInvoiceItemTax,
    SupplierCreditNote,
    SupplierCreditNoteItem,
    TaxCode,
    ThreeWayMatch,
)


MONEY_PLACES = Decimal('0.01')
ZERO = Decimal('0.00')


def money(value):
    return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def base_money(value, exchange_rate):
    """Convert a transaction-currency amount to the two-place base ledger amount."""
    return money(Decimal(value) * Decimal(exchange_rate))


def _save(instance, **kwargs):
    try:
        instance.save(**kwargs)
    except DjangoValidationError as exc:
        detail = getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}
        raise ValidationError(detail) from exc
    except IntegrityError as exc:
        raise ValidationError({'non_field_errors': ['The operation conflicts with an existing finance record.']}) from exc
    return instance


def _require_company_user(user, company_id):
    if not user or not user.is_authenticated or user.company_id != company_id:
        raise ValidationError({'non_field_errors': ['The record must belong to your company.']})


def _next_number(company, document_type, prefix, model):
    today = timezone.localdate()
    sequence, _ = FinanceDocumentSequence.objects.select_for_update().get_or_create(
        company=company,
        document_type=document_type,
        defaults={'last_value': model.objects.filter(company=company).count()},
    )
    sequence.last_value += 1
    sequence.save(update_fields=['last_value'])
    return f'{prefix}-{today:%Y%m%d}-{sequence.last_value:05d}'


def purchase_request_estimated_total(purchase_request):
    # Once Procurement has created a draft PO, Finance must review the actual
    # supplier quotation rather than the material master estimate.
    purchase_order = purchase_request.purchase_orders.prefetch_related('items').order_by('-created_at').first()
    if purchase_order:
        return money(sum((item.quantity * item.unit_price for item in purchase_order.items.all()), ZERO))
    return money(sum(
        (item.quantity * item.material.unit_price for item in purchase_request.items.select_related('material')),
        ZERO,
    ))


def ensure_budget_clearance(purchase_request):
    try:
        approval = purchase_request.budget_approval
    except BudgetApproval.DoesNotExist:
        raise ValidationError({
            'purchase_request': ['Finance approval is required before purchasing or issuing stock.'],
        })
    if approval.status not in {BudgetApproval.STATUS_APPROVED, BudgetApproval.STATUS_OVERRIDDEN}:
        raise ValidationError({
            'purchase_request': ['This purchase request has not passed finance approval.'],
        })
    return approval


@transaction.atomic
def create_budget_approval(*, purchase_request, user):
    locked_pr = PurchaseRequest.objects.select_for_update().prefetch_related('items__material').get(
        pk=purchase_request.pk,
        company=user.company,
    )
    if locked_pr.status != PurchaseRequest.STATUS_APPROVED:
        raise ValidationError({'purchase_request': ['Technical approval is required first.']})
    if hasattr(locked_pr, 'budget_approval'):
        raise ValidationError({'purchase_request': ['A budget approval already exists for this request.']})
    approval = BudgetApproval(
        company=user.company,
        purchase_request=locked_pr,
        requested_amount=purchase_request_estimated_total(locked_pr),
        created_by=user,
    )
    result = _save(approval)
    from .configuration_services import record_finance_audit_event

    record_finance_audit_event(
        company=user.company, actor=user, action='budget_approval.created',
        object_type='BudgetApproval', object_id=result.pk,
        metadata={'purchase_request': locked_pr.pk, 'requested_amount': result.requested_amount},
    )
    return result


@transaction.atomic
def submit_budget_approval(*, approval, user):
    locked = BudgetApproval.objects.select_for_update().get(pk=approval.pk, company=user.company)
    if locked.status != BudgetApproval.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft budget approvals can be submitted.']})
    locked.requested_amount = purchase_request_estimated_total(locked.purchase_request)
    locked.status = BudgetApproval.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    result = _save(locked, update_fields=['requested_amount', 'status', 'submitted_at', 'updated_at'])
    from .configuration_services import record_finance_audit_event

    record_finance_audit_event(
        company=user.company, actor=user, action='budget_approval.submitted',
        object_type='BudgetApproval', object_id=result.pk,
        metadata={'requested_amount': result.requested_amount},
    )
    from .notification_services import budget_approval_required

    transaction.on_commit(lambda: budget_approval_required(result))
    return result


@transaction.atomic
def review_budget_approval(*, approval, user, approve, reason=''):
    locked = (
        BudgetApproval.objects.select_for_update()
        .select_related('purchase_request__project')
        .get(pk=approval.pk, company=user.company)
    )
    if locked.status != BudgetApproval.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted budget approvals can be reviewed.']})
    reason = reason.strip()
    if not approve and not reason:
        raise ValidationError({'reason': ['A rejection reason is required.']})
    if approve and locked.purchase_request.project_id:
        project = locked.purchase_request.project
        committed = (
            BudgetApproval.objects.filter(
                company=user.company,
                purchase_request__project=project,
                status=BudgetApproval.STATUS_APPROVED,
            )
            .exclude(pk=locked.pk)
            .aggregate(total=Sum('requested_amount'))['total'] or ZERO
        )
        if money(committed + locked.requested_amount) > money(project.budget):
            raise ValidationError({'requested_amount': ['Approval would exceed the project budget.']})
    locked.status = BudgetApproval.STATUS_APPROVED if approve else BudgetApproval.STATUS_REJECTED
    locked.review_reason = reason
    locked.reviewed_by = user
    locked.reviewed_at = timezone.now()
    result = _save(
        locked,
        update_fields=['status', 'review_reason', 'reviewed_by', 'reviewed_at', 'updated_at'],
    )
    from .configuration_services import record_finance_audit_event

    record_finance_audit_event(
        company=user.company, actor=user,
        action=f"budget_approval.{'approved' if approve else 'rejected'}",
        object_type='BudgetApproval', object_id=result.pk, message=reason,
        metadata={'requested_amount': result.requested_amount},
    )
    return result


SYSTEM_ACCOUNTS = (
    ('1000', 'Cash and Bank', Account.TYPE_ASSET, Account.SYSTEM_CASH),
    ('1200', 'Inventory', Account.TYPE_ASSET, Account.SYSTEM_INVENTORY),
    ('1300', 'Supplier Advances', Account.TYPE_ASSET, Account.SYSTEM_SUPPLIER_ADVANCE),
    ('1400', 'Staff Advances', Account.TYPE_ASSET, Account.SYSTEM_STAFF_ADVANCE),
    ('2100', 'GRN Clearing', Account.TYPE_LIABILITY, Account.SYSTEM_GRN_CLEARING),
    ('5100', 'Inventory Adjustments', Account.TYPE_EXPENSE, Account.SYSTEM_INVENTORY_ADJUSTMENT),
    ('5200', 'Inventory Write-offs', Account.TYPE_EXPENSE, Account.SYSTEM_INVENTORY_WRITE_OFF),
    ('5300', 'Landed Cost Clearing', Account.TYPE_LIABILITY, Account.SYSTEM_LANDED_COST_CLEARING),
    ('2000', 'Accounts Payable', Account.TYPE_LIABILITY, Account.SYSTEM_ACCOUNTS_PAYABLE),
    ('5000', 'Project Material Cost', Account.TYPE_EXPENSE, Account.SYSTEM_PROJECT_COST),
)


def ensure_system_accounts(company):
    accounts = {}
    for code, name, account_type, system_key in SYSTEM_ACCOUNTS:
        account = Account.objects.filter(company=company, system_key=system_key).first()
        if not account:
            available_code = code
            suffix = 1
            while Account.objects.filter(company=company, code=available_code).exists():
                suffix += 1
                available_code = f'{code}-L{suffix}'
            account = Account.objects.create(
                company=company, system_key=system_key, code=available_code,
                name=name, account_type=account_type,
            )
        accounts[system_key] = account
    from .ledger_services import ensure_ledger_configuration

    ensure_ledger_configuration(company)
    return accounts


@transaction.atomic
def create_account(*, company, user, code, name, account_type, system_key='', is_active=True, **values):
    _require_company_user(user, company.id)
    account = Account(
        company=company,
        code=code.strip(),
        name=name.strip(),
        account_type=account_type,
        system_key=system_key,
        is_active=is_active,
        **values,
    )
    return _save(account)


def _invoice_totals(
    items, discount_amount=ZERO, withholding_amount=ZERO, freight_amount=ZERO, other_charges_amount=ZERO,
):
    subtotal = money(sum((money(item['quantity']) * money(item['unit_price']) for item in items), ZERO))
    tax = money(sum((money(item.get('tax_amount', ZERO)) for item in items), ZERO))
    discount = money(discount_amount)
    withholding = money(withholding_amount)
    freight = money(freight_amount)
    other_charges = money(other_charges_amount)
    if discount < ZERO or discount > subtotal:
        raise ValidationError({'discount_amount': ['Discount must be between zero and the invoice subtotal.']})
    total = money(subtotal - discount + freight + other_charges + tax - withholding)
    if withholding < ZERO or freight < ZERO or other_charges < ZERO or total < ZERO:
        raise ValidationError({'withholding_amount': ['Withholding cannot make the invoice total negative.']})
    return subtotal, tax, total


def _record_invoice_action(invoice, user, action, comments='', idempotency_key=''):
    approval = InvoiceApproval(
        company=user.company, invoice=invoice, action=action, comments=comments,
        acted_by=user, idempotency_key=idempotency_key,
    )
    _save(approval)
    from .configuration_services import record_finance_audit_event

    record_finance_audit_event(
        company=user.company, actor=user, action=f'invoice.{action.lower()}',
        object_type='SupplierInvoice', object_id=invoice.pk, message=comments,
        correlation_id=idempotency_key,
    )
    return approval


def _normalize_invoice_items(company, po, items):
    po_items = {item.id: item for item in po.items.select_related('material')}
    tax_codes = {item.id: item for item in TaxCode.objects.filter(company=company, is_active=True)}
    seen = set()
    normalized = []
    for index, raw in enumerate(items):
        po_item_id = getattr(raw.get('purchase_order_item'), 'id', raw.get('purchase_order_item'))
        po_item = po_items.get(po_item_id)
        if not po_item:
            raise ValidationError({'items': [{index: {'purchase_order_item': ['Item is not on this purchase order.']}}]})
        if po_item_id in seen:
            raise ValidationError({'items': [{index: {'purchase_order_item': ['Each PO item may appear once.']}}]})
        seen.add(po_item_id)
        quantity = money(raw['quantity'])
        unit_price = money(raw['unit_price'])
        if quantity <= ZERO or unit_price < ZERO:
            raise ValidationError({'items': [{index: {'non_field_errors': ['Quantity must be positive and price non-negative.']}}]})
        line_subtotal = money(quantity * unit_price)
        taxes = []
        tax_total = ZERO
        seen_taxes = set()
        for tax_index, tax_raw in enumerate(raw.get('taxes', [])):
            tax_id = getattr(tax_raw.get('tax_code'), 'id', tax_raw.get('tax_code'))
            tax_code = tax_codes.get(tax_id)
            if not tax_code:
                raise ValidationError({'items': [{index: {'taxes': [{tax_index: {'tax_code': ['Invalid tax code.']}}]}}]})
            if tax_id in seen_taxes:
                raise ValidationError({'items': [{index: {'taxes': [{tax_index: {'tax_code': ['Tax code is duplicated.']}}]}}]})
            seen_taxes.add(tax_id)
            tax_value = money(line_subtotal * tax_code.rate_percent / Decimal('100'))
            taxes.append({'tax_code': tax_code, 'taxable_amount': line_subtotal, 'tax_amount': tax_value})
            tax_total += tax_value
        normalized.append({
            'po_item': po_item, 'quantity': quantity, 'unit_price': unit_price,
            'tax_amount': money(tax_total), 'taxes': taxes, 'description': raw.get('description', ''),
        })
    return normalized


def _replace_invoice_items(invoice, normalized):
    invoice.items.all().delete()
    for item in normalized:
        line = SupplierInvoiceItem(
            company=invoice.company, invoice=invoice, purchase_order_item=item['po_item'],
            material=item['po_item'].material, description=item['description'], quantity=item['quantity'],
            unit_price=item['unit_price'], tax_amount=item['tax_amount'],
        )
        _save(line)
        for tax in item['taxes']:
            _save(SupplierInvoiceItemTax(company=invoice.company, invoice_item=line, **tax))


@transaction.atomic
def create_supplier_invoice(
    *, company, user, purchase_order, supplier, invoice_number, invoice_date, items,
    due_date=None, currency='UGX', exchange_rate=Decimal('1'), cost_centre=None,
    discount_amount=ZERO, withholding_amount=ZERO, freight_amount=ZERO, other_charges_amount=ZERO,
    notes='', idempotency_key='', client_uuid=None, work_order=None, work_order_site=None,
):
    _require_company_user(user, company.id)
    if idempotency_key:
        existing = SupplierInvoice.objects.filter(company=company, idempotency_key=idempotency_key).first()
        if existing:
            if (
                existing.purchase_order_id != purchase_order.id
                or existing.supplier_id != supplier.id
                or existing.invoice_number != invoice_number.strip()
            ):
                raise ValidationError({'idempotency_key': ['This key was already used for a different invoice.']})
            return existing
    po = PurchaseOrder.objects.select_for_update().select_related('supplier', 'project').get(
        pk=purchase_order.pk,
        company=company,
    )
    from apps.procurement.amendments import PurchaseOrderAmendment
    if po.amendments.filter(status=PurchaseOrderAmendment.STATUS_SUBMITTED).exists():
        raise ValidationError({'purchase_order': ['Finance must decide the pending PO amendment before an invoice can be recorded.']})
    if not po.supplier_id or po.supplier_id != supplier.id or supplier.company_id != company.id:
        raise ValidationError({'supplier': ['Supplier must match the purchase order.']})
    if not items:
        raise ValidationError({'items': ['At least one invoice item is required.']})
    if SupplierInvoice.objects.filter(
        company=company, supplier=supplier, invoice_number__iexact=invoice_number.strip(),
    ).exists():
        raise ValidationError({'invoice_number': ['This supplier invoice number already exists.']})
    normalized = _normalize_invoice_items(company, po, items)
    subtotal, tax, total = _invoice_totals(
        normalized, discount_amount, withholding_amount, freight_amount, other_charges_amount,
    )
    currency = currency.upper()
    from .configuration_services import ensure_finance_settings, validate_exchange_rate

    ensure_finance_settings(company)
    if not Currency.objects.filter(company=company, code=currency, is_active=True).exists():
        raise ValidationError({'currency': ['Currency is not configured or active for this company.']})
    exchange_rate = validate_exchange_rate(
        company=company, currency=currency, exchange_rate=exchange_rate,
    )
    if cost_centre and cost_centre.company_id != company.id:
        raise ValidationError({'cost_centre': ['Cost centre must belong to the same company.']})
    if work_order is not None:
        from apps.workorders.models import WorkOrder
        work_order = WorkOrder.objects.filter(pk=getattr(work_order, 'pk', work_order), company=company).first()
        if work_order is None or (work_order.project_id and work_order.project_id != po.project_id):
            raise ValidationError({'work_order': ['Work order must belong to the same project as the purchase order.']})
    if work_order_site is not None:
        from apps.workorders.models import WorkOrderSite
        work_order_site = WorkOrderSite.objects.filter(
            pk=getattr(work_order_site, 'pk', work_order_site), work_order=work_order, project=po.project,
        ).first()
        if work_order_site is None:
            raise ValidationError({'work_order_site': ['Site package must belong to the selected work order and purchase order project.']})
    invoice = SupplierInvoice(
        company=company,
        supplier=supplier,
        purchase_order=po,
        project=po.project,
        work_order=work_order,
        work_order_site=work_order_site,
        cost_centre=cost_centre,
        internal_number=_next_number(company, FinanceDocumentSequence.TYPE_INVOICE, 'INV', SupplierInvoice),
        invoice_number=invoice_number.strip(),
        invoice_date=invoice_date,
        due_date=due_date,
        currency=currency,
        exchange_rate=exchange_rate,
        subtotal=subtotal,
        discount_amount=money(discount_amount),
        freight_amount=money(freight_amount),
        other_charges_amount=money(other_charges_amount),
        tax_amount=tax,
        withholding_amount=money(withholding_amount),
        total_amount=total,
        notes=notes,
        idempotency_key=idempotency_key,
        client_uuid=client_uuid,
        created_by=user,
    )
    _save(invoice)
    _replace_invoice_items(invoice, normalized)
    return invoice


@transaction.atomic
def update_draft_invoice(*, invoice, user, values, items=None):
    locked = SupplierInvoice.objects.select_for_update().select_related('purchase_order').get(
        pk=invoice.pk, company=user.company,
    )
    if locked.status != SupplierInvoice.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft invoices can be edited.']})
    normalized = None
    if items is not None:
        if not items:
            raise ValidationError({'items': ['At least one invoice item is required.']})
        normalized = _normalize_invoice_items(user.company, locked.purchase_order, items)
    for field in (
        'invoice_number', 'invoice_date', 'due_date', 'notes', 'cost_centre', 'currency',
        'exchange_rate', 'discount_amount', 'withholding_amount',
        'freight_amount', 'other_charges_amount',
    ):
        if field in values:
            setattr(locked, field, values[field])
    if normalized is not None:
        _replace_invoice_items(locked, normalized)
    locked.invoice_number = locked.invoice_number.strip()
    if SupplierInvoice.objects.filter(
        company=user.company, supplier=locked.supplier,
        invoice_number__iexact=locked.invoice_number,
    ).exclude(pk=locked.pk).exists():
        raise ValidationError({'invoice_number': ['This supplier invoice number already exists.']})
    locked.currency = locked.currency.upper()
    if not Currency.objects.filter(company=user.company, code=locked.currency, is_active=True).exists():
        raise ValidationError({'currency': ['Currency is not configured or active for this company.']})
    from .configuration_services import validate_exchange_rate

    locked.exchange_rate = validate_exchange_rate(
        company=user.company, currency=locked.currency, exchange_rate=locked.exchange_rate,
    )
    totals_source = normalized or list(locked.items.values('quantity', 'unit_price', 'tax_amount'))
    locked.subtotal, locked.tax_amount, locked.total_amount = _invoice_totals(
        totals_source, locked.discount_amount, locked.withholding_amount,
        locked.freight_amount, locked.other_charges_amount,
    )
    return _save(locked)


@transaction.atomic
def submit_invoice(*, invoice, user):
    locked = SupplierInvoice.objects.select_for_update().prefetch_related('items').get(
        pk=invoice.pk,
        company=user.company,
    )
    if locked.status != SupplierInvoice.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft invoices can be submitted.']})
    if not locked.items.exists():
        raise ValidationError({'items': ['An invoice must contain at least one item.']})
    from .configuration_services import ensure_finance_settings
    settings = ensure_finance_settings(user.company)
    if settings.require_invoice_attachment and not locked.attachments.exists():
        raise ValidationError({'attachments': ['Attach the supplier invoice or supporting document before submitting.']})
    # Lock and reserve the cumulative GRN quantity before this invoice enters
    # the finance workflow, rather than discovering a duplicate only at match.
    from .matching_services import assert_invoice_quantity_available

    assert_invoice_quantity_available(invoice=locked)
    locked.status = SupplierInvoice.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    _save(locked, update_fields=['status', 'submitted_at', 'updated_at'])
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_SUBMIT)
    from .notification_services import invoice_submitted

    transaction.on_commit(lambda: invoice_submitted(locked))
    return locked


@transaction.atomic
def withdraw_invoice(*, invoice, user):
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if locked.status not in {SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCH_EXCEPTION}:
        raise ValidationError({'status': ['Only submitted or match-exception invoices can be withdrawn.']})
    if hasattr(locked, 'three_way_match'):
        if locked.three_way_match.status != ThreeWayMatch.STATUS_EXCEPTION:
            raise ValidationError({'status': ['A successfully verified invoice cannot be withdrawn.']})
        ThreeWayMatch.objects.filter(pk=locked.three_way_match.pk).delete()
    locked.status = SupplierInvoice.STATUS_DRAFT
    locked.submitted_at = None
    _save(locked, update_fields=['status', 'submitted_at', 'updated_at'])
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_WITHDRAW)
    return locked


def _received_quantity(po, po_item):
    if po.delivery_destination == PurchaseOrder.DELIVERY_SITE:
        return po_item.quantity if po.status == PurchaseOrder.STATUS_RECEIVED else ZERO
    return (
        StockMovement.objects.filter(
            company=po.company,
            purchase_order=po,
            purchase_order_item=po_item,
            movement_type__in=[StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN],
        ).aggregate(total=Sum('quantity'))['total'] or ZERO
    )


@transaction.atomic
def match_invoice(*, invoice, user, tolerance=ZERO, idempotency_key=''):
    if idempotency_key:
        existing_by_key = ThreeWayMatch.objects.filter(
            company=user.company, idempotency_key=idempotency_key,
        ).first()
        if existing_by_key:
            if existing_by_key.invoice_id != invoice.pk:
                raise ValidationError({'idempotency_key': ['This key was already used for a different match.']})
            return existing_by_key
    locked = (
        SupplierInvoice.objects.select_for_update()
        .select_related('purchase_order')
        .prefetch_related('items__purchase_order_item')
        .get(pk=invoice.pk, company=user.company)
    )
    if hasattr(locked, 'three_way_match'):
        existing = locked.three_way_match
        if not idempotency_key or existing.idempotency_key == idempotency_key:
            return existing
        raise ValidationError({'non_field_errors': ['This invoice has already been matched.']})
    if locked.status != SupplierInvoice.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted invoices can be matched.']})
    po = PurchaseOrder.objects.select_for_update().get(pk=locked.purchase_order_id, company=user.company)
    if po.status != PurchaseOrder.STATUS_RECEIVED:
        raise ValidationError({'purchase_order': ['Goods must be received before matching.']})
    tolerance = money(tolerance)
    if tolerance < ZERO:
        raise ValidationError({'tolerance': ['Tolerance cannot be negative.']})
    exceptions = []
    quantity_variance = ZERO
    received_total = ZERO
    for line in locked.items.all():
        po_item = line.purchase_order_item
        received = money(_received_quantity(po, po_item))
        received_total += money(received * po_item.unit_price)
        ordered_variance = abs(money(line.quantity - po_item.quantity))
        receipt_variance = abs(money(line.quantity - received))
        quantity_variance += ordered_variance + receipt_variance
        if ordered_variance > tolerance:
            exceptions.append(f'{line.material.code}: invoiced quantity differs from ordered quantity.')
        if receipt_variance > tolerance:
            exceptions.append(f'{line.material.code}: invoiced quantity differs from received quantity.')
    po_total = money(sum((item.quantity * item.unit_price for item in po.items.all()), ZERO))
    amount_variance = abs(money(locked.subtotal - po_total))
    if amount_variance > tolerance:
        exceptions.append('Invoice subtotal differs from the purchase order total.')
    result = ThreeWayMatch(
        company=user.company,
        invoice=locked,
        purchase_order=po,
        status=ThreeWayMatch.STATUS_EXCEPTION if exceptions else ThreeWayMatch.STATUS_MATCHED,
        tolerance=tolerance,
        po_total=po_total,
        invoice_total=locked.total_amount,
        received_total=money(received_total),
        quantity_variance=money(quantity_variance),
        amount_variance=amount_variance,
        exceptions=exceptions,
        idempotency_key=idempotency_key,
        matched_by=user,
    )
    _save(result)
    if not exceptions:
        locked.status = SupplierInvoice.STATUS_MATCHED
        _save(locked, update_fields=['status', 'updated_at'])
    else:
        from .notification_services import invoice_matching_exception

        transaction.on_commit(lambda: invoice_matching_exception(locked, '; '.join(exceptions)))
    return result


@transaction.atomic
def verify_invoice(*, invoice, user, idempotency_key=''):
    if idempotency_key:
        existing = ThreeWayMatch.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
        if existing:
            if existing.invoice_id != invoice.pk:
                raise ValidationError({'idempotency_key': ['This key was already used for a different verification.']})
            return existing
    locked = (
        SupplierInvoice.objects.select_for_update().select_related('purchase_order')
        .prefetch_related('items__purchase_order_item').get(pk=invoice.pk, company=user.company)
    )
    if locked.status != SupplierInvoice.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted invoices can be verified.']})
    if hasattr(locked, 'three_way_match'):
        return locked.three_way_match
    po = PurchaseOrder.objects.select_for_update().get(pk=locked.purchase_order_id, company=user.company)
    if po.status != PurchaseOrder.STATUS_RECEIVED:
        raise ValidationError({'purchase_order': ['Goods must be received before verification.']})
    settings = FinanceSettings.objects.select_for_update().get(company=user.company)
    exceptions = []
    quantity_variance = ZERO
    received_total = ZERO
    eligible_statuses = [
        SupplierInvoice.STATUS_VERIFIED, SupplierInvoice.STATUS_MATCHED, SupplierInvoice.STATUS_APPROVED,
        SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID,
    ]
    for line in locked.items.all():
        po_item = line.purchase_order_item
        received = money(_received_quantity(po, po_item))
        prior = SupplierInvoiceItem.objects.filter(
            company=user.company, purchase_order_item=po_item, invoice__status__in=eligible_statuses,
        ).exclude(invoice=locked).aggregate(total=Sum('quantity'))['total'] or ZERO
        remaining_ordered = money(po_item.quantity - prior)
        remaining_received = money(received - prior)
        quantity_over = max(line.quantity - min(remaining_ordered, remaining_received), ZERO)
        quantity_variance += quantity_over
        received_total += money(min(line.quantity, max(remaining_received, ZERO)) * po_item.unit_price)
        if quantity_over > settings.quantity_matching_tolerance:
            exceptions.append(f'{line.material.code}: invoiced quantity exceeds the un-invoiced received quantity.')
        invoice_base_price = base_money(line.unit_price, locked.exchange_rate)
        price_variance = abs(money(invoice_base_price - po_item.unit_price))
        price_percent = ZERO if po_item.unit_price == ZERO else money(price_variance * Decimal('100') / po_item.unit_price)
        if price_percent > settings.price_matching_tolerance:
            exceptions.append(f'{line.material.code}: unit price exceeds the configured tolerance.')
    po_total = money(sum((item.quantity * item.unit_price for item in po.items.all()), ZERO))
    amount_variance = money(sum((
        abs(base_money(line.unit_price, locked.exchange_rate) - line.purchase_order_item.unit_price)
        * line.quantity for line in locked.items.all()
    ), ZERO))
    result = ThreeWayMatch(
        company=user.company, invoice=locked, purchase_order=po,
        status=ThreeWayMatch.STATUS_EXCEPTION if exceptions else ThreeWayMatch.STATUS_MATCHED,
        tolerance=money(settings.quantity_matching_tolerance), po_total=po_total, invoice_total=locked.total_amount,
        received_total=money(received_total), quantity_variance=money(quantity_variance),
        amount_variance=money(amount_variance), exceptions=exceptions,
        idempotency_key=idempotency_key, matched_by=user,
    )
    _save(result)
    locked.status = SupplierInvoice.STATUS_MATCH_EXCEPTION if exceptions else SupplierInvoice.STATUS_VERIFIED
    _save(locked, update_fields=['status', 'updated_at'])
    _record_invoice_action(
        locked, user, InvoiceApproval.ACTION_VERIFY,
        comments='; '.join(exceptions), idempotency_key=f'approval:{idempotency_key}' if idempotency_key else '',
    )
    return result


@transaction.atomic
def approve_invoice(*, invoice, user):
    locked = SupplierInvoice.objects.select_for_update().select_related('purchase_order').get(
        pk=invoice.pk, company=user.company,
    )
    if locked.status not in {SupplierInvoice.STATUS_MATCHED, SupplierInvoice.STATUS_VERIFIED}:
        raise ValidationError({'status': ['Only successfully verified invoices can be approved.']})
    settings = FinanceSettings.objects.get(company=user.company)
    if settings.maker_checker_enforced and locked.created_by_id == user.id:
        raise ValidationError({'non_field_errors': ['Maker-checker policy prevents the preparer approving this invoice.']})
    latest_run = locked.match_runs.first()
    if latest_run:
        if latest_run.status == latest_run.STATUS_BLOCKED:
            raise ValidationError({'match': ['A blocked match run cannot be approved.']})
        if latest_run.status == latest_run.STATUS_EXCEPTION and not latest_run.exception_is_approved:
            raise ValidationError({'match': ['The match exception requires Finance Manager authorization.']})
        from .matching_services import assert_invoice_quantity_available

        assert_invoice_quantity_available(invoice=locked)
    locked.status = SupplierInvoice.STATUS_APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    _save(locked, update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_APPROVE)
    return locked


@transaction.atomic
def reject_invoice(*, invoice, user, reason):
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if locked.status not in {
        SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCHED,
        SupplierInvoice.STATUS_MATCH_EXCEPTION, SupplierInvoice.STATUS_VERIFIED,
    }:
        raise ValidationError({'status': ['Only submitted or verified invoices can be rejected.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A rejection reason is required.']})
    locked.status = SupplierInvoice.STATUS_REJECTED
    locked.rejection_reason = reason
    _save(locked, update_fields=['status', 'rejection_reason', 'updated_at'])
    _record_invoice_action(locked, user, InvoiceApproval.ACTION_REJECT, comments=reason)
    return locked


def _create_journal(*, company, user, date, description, source_type, source_object_id, lines, reversal_of=None):
    from .ledger_services import create_and_post_source_journal

    return create_and_post_source_journal(
        company=company,
        user=user,
        entry_date=date,
        description=description,
        source_type=source_type,
        source_object_id=source_object_id,
        reversal_of=reversal_of,
        lines=lines,
    )


@transaction.atomic
def post_invoice(*, invoice, user, idempotency_key=''):
    locked = SupplierInvoice.objects.select_for_update().select_related('purchase_order').get(
        pk=invoice.pk,
        company=user.company,
    )
    existing = JournalEntry.objects.filter(
        company=user.company,
        source_type=JournalEntry.SOURCE_INVOICE,
        source_object_id=locked.pk,
    ).first()
    if existing:
        if idempotency_key and locked.posting_idempotency_key not in {'', idempotency_key}:
            raise ValidationError({'idempotency_key': ['A different key was used to post this invoice.']})
        return existing
    if locked.status != SupplierInvoice.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved invoices can be posted.']})
    from .budget_services import convert_invoice_commitment_to_actual

    convert_invoice_commitment_to_actual(invoice=locked, user=user)
    from .ledger_services import resolve_mapping, resolve_rule_accounts
    from .models import PostingRule

    rule_debit, rule_credit = resolve_rule_accounts(
        company=user.company, event_type=PostingRule.EVENT_SUPPLIER_INVOICE,
    )
    debit_account = rule_debit
    if locked.purchase_order.delivery_destination != PurchaseOrder.DELIVERY_WAREHOUSE:
        debit_account = resolve_mapping(company=user.company, mapping_key='PROJECT_MATERIAL_COST')
    base_total = base_money(locked.total_amount, locked.exchange_rate)
    base_tax = base_money(locked.tax_amount, locked.exchange_rate)
    base_withholding = base_money(locked.withholding_amount, locked.exchange_rate)
    # Supplier totals are net of withholding.  Expense/clearing and recoverable
    # VAT remain gross, while the withheld portion is a separate tax liability.
    base_cost = base_total - base_tax + base_withholding
    lines = [
        {
            'account': debit_account,
            'project': locked.project,
            'supplier': locked.supplier,
            'description': locked.invoice_number,
            'debit': base_cost,
            'credit': ZERO,
        },
        {
            'account': rule_credit,
            'project': locked.project,
            'supplier': locked.supplier,
            'description': locked.invoice_number,
            'debit': ZERO,
            'credit': base_total,
        },
    ]
    if base_tax:
        lines.append({
            'account': resolve_mapping(company=user.company, mapping_key='RECOVERABLE_VAT'),
            'project': locked.project,
            'supplier': locked.supplier,
            'description': f'Recoverable VAT / {locked.invoice_number}',
            'debit': base_tax,
            'credit': ZERO,
        })
    if base_withholding:
        lines.append({
            'account': resolve_mapping(company=user.company, mapping_key='WITHHOLDING_TAX_PAYABLE'),
            'project': locked.project,
            'supplier': locked.supplier,
            'description': f'Withholding tax / {locked.invoice_number}',
            'debit': ZERO,
            'credit': base_withholding,
        })
    entry = _create_journal(
        company=user.company,
        user=user,
        date=locked.invoice_date,
        description=f'Post supplier invoice {locked.internal_number}',
        source_type=JournalEntry.SOURCE_INVOICE,
        source_object_id=locked.pk,
        lines=lines,
    )
    locked.status = SupplierInvoice.STATUS_POSTED
    locked.posted_by = user
    locked.posted_at = timezone.now()
    locked.posting_idempotency_key = idempotency_key
    _save(locked, update_fields=[
        'status', 'posted_by', 'posted_at', 'posting_idempotency_key', 'updated_at',
    ])
    _record_invoice_action(
        locked, user, InvoiceApproval.ACTION_POST,
        idempotency_key=f'approval:{idempotency_key}' if idempotency_key else '',
    )
    return entry


def invoice_paid_amount(invoice):
    paid = invoice.payment_allocations.filter(
        status__in=[PaymentAllocation.STATUS_APPROVED, PaymentAllocation.STATUS_POSTED],
        payment__reversal__isnull=True,
    ).aggregate(total=Sum('amount'))['total'] or ZERO
    return money(paid)


def invoice_credit_amount(invoice):
    credited = invoice.credit_notes.filter(status=SupplierCreditNote.STATUS_POSTED).aggregate(
        total=Sum('total_amount'),
    )['total'] or ZERO
    return money(credited)


@transaction.atomic
def pay_invoice(*, invoice, user, amount, payment_date, method, reference='', notes='', idempotency_key):
    existing = Payment.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if (
            existing.invoice_id != invoice.pk
            or existing.amount != money(amount)
            or existing.payment_date != payment_date
            or existing.method != method
        ):
            raise ValidationError({'idempotency_key': ['This key was already used for a different payment.']})
        return existing
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if locked.status not in {SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID} or hasattr(locked, 'reversal'):
        raise ValidationError({'status': ['Only an active posted invoice can be paid.']})
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({'amount': ['Payment amount must be greater than zero.']})
    balance = money(locked.total_amount - invoice_paid_amount(locked) - invoice_credit_amount(locked))
    if amount > balance:
        raise ValidationError({'amount': [f'Payment exceeds the outstanding balance of {balance}.']})
    from .ledger_services import resolve_mapping, resolve_rule_accounts
    from .models import PostingRule

    rule_debit, rule_credit = resolve_rule_accounts(
        company=user.company, event_type=PostingRule.EVENT_SUPPLIER_PAYMENT,
    )
    currency = Currency.objects.get(company=user.company, code=locked.currency)
    number = _next_number(user.company, FinanceDocumentSequence.TYPE_PAYMENT, 'PAY', Payment)
    base_amount = base_money(amount, locked.exchange_rate)
    entry = _create_journal(
        company=user.company,
        user=user,
        date=payment_date,
        description=f'Pay supplier invoice {locked.internal_number}',
        source_type=JournalEntry.SOURCE_PAYMENT,
        source_object_id=0,
        lines=[
            {
                'account': rule_debit,
                'project': locked.project,
                'supplier': locked.supplier,
                'description': number,
                'debit': base_amount,
                'credit': ZERO,
            },
            {
                'account': rule_credit,
                'project': locked.project,
                'supplier': locked.supplier,
                'description': number,
                'debit': ZERO,
                'credit': base_amount,
            },
        ],
    )
    payment = Payment(
        company=user.company,
        supplier=locked.supplier,
        invoice=locked,
        source_account=rule_credit,
        currency=currency,
        exchange_rate=locked.exchange_rate,
        number=number,
        amount=amount,
        payment_date=payment_date,
        method=method,
        reference=reference,
        notes=notes,
        idempotency_key=idempotency_key,
        created_by=user,
        status=Payment.STATUS_POSTED,
        posted_by=user,
        posted_at=timezone.now(),
        journal_entry=entry,
    )
    _save(payment)
    entry.source_object_id = payment.pk
    _save(PaymentAllocation(
        company=user.company, payment=payment, invoice=locked, amount=amount,
        status=PaymentAllocation.STATUS_POSTED, created_by=user,
    ))
    JournalEntry.objects.filter(pk=entry.pk).update(source_object_id=payment.pk)
    entry.source_object_id = payment.pk
    if locked.project_id:
        _save(ProjectCost(
            company=user.company,
            project=locked.project,
            supplier_invoice=locked,
            payment=payment,
            journal_entry=entry,
            amount=base_amount,
            date=payment_date,
            description=f'Paid cost for {locked.internal_number}',
        ))
    remaining = money(balance - amount)
    new_status = SupplierInvoice.STATUS_PAID if remaining == ZERO else SupplierInvoice.STATUS_PARTIALLY_PAID
    SupplierInvoice.objects.filter(pk=locked.pk).update(status=new_status, updated_at=timezone.now())
    return payment


def _reverse_lines(entry):
    return [
        {
            'account': line.account,
            'project': line.project,
            'supplier': line.supplier,
            'description': f'Reversal: {line.description}',
            'debit': line.credit,
            'credit': line.debit,
        }
        for line in entry.lines.select_related('account', 'project', 'supplier')
    ]


@transaction.atomic
def reverse_payment(*, payment, user, reason, idempotency_key, reversal_date=None):
    existing = PaymentReversal.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.payment_id != payment.pk:
            raise ValidationError({'idempotency_key': ['This key was already used for a different reversal.']})
        return existing
    locked = Payment.objects.select_for_update().select_related('journal_entry', 'invoice').get(
        pk=payment.pk,
        company=user.company,
    )
    if hasattr(locked, 'reversal'):
        raise ValidationError({'non_field_errors': ['This payment has already been reversed.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    reversal = PaymentReversal(
        company=user.company,
        payment=locked,
        reason=reason,
        idempotency_key=idempotency_key,
        reversed_by=user,
    )
    # A temporary unsaved object ID is not used; source is linked after creation.
    entry = _create_journal(
        company=user.company,
        user=user,
        date=reversal_date or timezone.localdate(),
        description=f'Reverse payment {locked.number}: {reason}',
        source_type=JournalEntry.SOURCE_PAYMENT_REVERSAL,
        source_object_id=locked.pk,
        reversal_of=locked.journal_entry,
        lines=_reverse_lines(locked.journal_entry),
    )
    reversal.journal_entry = entry
    original_cost = locked.project_costs.filter(is_reversal=False).first()
    if original_cost:
        reversal_cost = ProjectCost(
            company=user.company,
            project=original_cost.project,
            supplier_invoice=original_cost.supplier_invoice,
            payment=locked,
            journal_entry=entry,
            amount=original_cost.amount,
            date=entry.date,
            description=f'Reversal of {original_cost.description}',
            is_reversal=True,
            reversal_of=original_cost,
        )
        _save(reversal_cost)
        reversal.project_cost = reversal_cost
    _save(reversal)
    active_paid = invoice_paid_amount(locked.invoice)
    credited = invoice_credit_amount(locked.invoice)
    remaining = money(locked.invoice.total_amount - active_paid - credited)
    new_status = SupplierInvoice.STATUS_POSTED if active_paid == ZERO else (
        SupplierInvoice.STATUS_PAID if remaining == ZERO else SupplierInvoice.STATUS_PARTIALLY_PAID
    )
    SupplierInvoice.objects.filter(pk=locked.invoice_id).update(status=new_status, updated_at=timezone.now())
    return reversal


@transaction.atomic
def reverse_invoice(*, invoice, user, reason, idempotency_key, reversal_date=None):
    existing = InvoiceReversal.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.invoice_id != invoice.pk:
            raise ValidationError({'idempotency_key': ['This key was already used for a different reversal.']})
        return existing
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if locked.status != SupplierInvoice.STATUS_POSTED:
        raise ValidationError({'status': ['Only posted invoices can be reversed.']})
    if hasattr(locked, 'reversal'):
        raise ValidationError({'non_field_errors': ['This invoice has already been reversed.']})
    if locked.payment_allocations.filter(
        status__in=[PaymentAllocation.STATUS_APPROVED, PaymentAllocation.STATUS_POSTED],
        payment__reversal__isnull=True,
    ).exists():
        raise ValidationError({'payments': ['Reverse all active payments before reversing the invoice.']})
    if locked.credit_notes.filter(status=SupplierCreditNote.STATUS_POSTED).exists():
        raise ValidationError({'credit_notes': ['An invoice with posted credit notes cannot be fully reversed.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    original_entry = JournalEntry.objects.select_for_update().get(
        company=user.company,
        source_type=JournalEntry.SOURCE_INVOICE,
        source_object_id=locked.pk,
    )
    from .budget_services import reverse_invoice_actual

    reverse_invoice_actual(invoice=locked, user=user)
    entry = _create_journal(
        company=user.company,
        user=user,
        date=reversal_date or timezone.localdate(),
        description=f'Reverse invoice {locked.internal_number}: {reason}',
        source_type=JournalEntry.SOURCE_INVOICE_REVERSAL,
        source_object_id=locked.pk,
        reversal_of=original_entry,
        lines=_reverse_lines(original_entry),
    )
    reversal = InvoiceReversal(
        company=user.company,
        invoice=locked,
        journal_entry=entry,
        reason=reason,
        idempotency_key=idempotency_key,
        reversed_by=user,
    )
    _save(reversal)
    SupplierInvoice.objects.filter(pk=locked.pk).update(
        status=SupplierInvoice.STATUS_REVERSED, updated_at=timezone.now(),
    )
    _record_invoice_action(
        locked, user, InvoiceApproval.ACTION_REVERSE, comments=reason,
        idempotency_key=f'approval:{idempotency_key}',
    )
    return reversal


@transaction.atomic
def create_invoice_attachment(*, invoice, user, uploaded_file):
    locked = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if uploaded_file.size > 10 * 1024 * 1024:
        raise ValidationError({'file': ['Attachments cannot exceed 10 MB.']})
    validate_image_upload(uploaded_file)
    allowed_types = {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}
    content_type = getattr(uploaded_file, 'content_type', '')
    if content_type not in allowed_types:
        raise ValidationError({'file': ['Only PDF, JPEG, PNG, and WebP attachments are allowed.']})
    attachment = InvoiceAttachment(
        company=user.company, invoice=locked, file=uploaded_file,
        original_name=Path(uploaded_file.name).name[:255], content_type=content_type,
        size=uploaded_file.size, uploaded_by=user,
    )
    return _save(attachment)


@transaction.atomic
def create_supplier_credit_note(
    *, invoice, user, credit_note_number, credit_note_date, reason, items, idempotency_key,
):
    existing = SupplierCreditNote.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.invoice_id != invoice.pk:
            raise ValidationError({'idempotency_key': ['This key was already used for another credit note.']})
        return existing
    locked = SupplierInvoice.objects.select_for_update().select_related('supplier', 'project').get(
        pk=invoice.pk, company=user.company,
    )
    if locked.status not in {
        SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID,
    } or hasattr(locked, 'reversal'):
        raise ValidationError({'status': ['Credit notes can only correct active posted invoices.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A credit-note reason is required.']})
    invoice_items = {item.id: item for item in locked.items.select_related('material')}
    credited_quantities = {
        row['invoice_item_id']: row['total'] or ZERO
        for row in SupplierCreditNoteItem.objects.select_for_update().filter(
            company=user.company,
            invoice_item__invoice=locked,
            credit_note__status=SupplierCreditNote.STATUS_POSTED,
        ).values('invoice_item_id').annotate(total=Sum('quantity'))
    }
    normalized = []
    for index, raw in enumerate(items):
        invoice_item_id = getattr(raw.get('invoice_item'), 'id', raw.get('invoice_item'))
        invoice_item = invoice_items.get(invoice_item_id)
        if not invoice_item:
            raise ValidationError({'items': [{index: {'invoice_item': ['Item is not on this invoice.']}}]})
        quantity = money(raw['quantity'])
        unit_price = money(raw.get('unit_price', invoice_item.unit_price))
        remaining_quantity = invoice_item.quantity - credited_quantities.get(invoice_item.id, ZERO)
        if quantity <= ZERO or quantity > remaining_quantity:
            raise ValidationError({
                'items': [{index: {'quantity': [
                    f'Quantity must be positive and cannot exceed the remaining creditable quantity of {remaining_quantity}.',
                ]}}],
            })
        tax_code = raw.get('tax_code')
        if tax_code and tax_code.company_id != user.company_id:
            raise ValidationError({'items': [{index: {'tax_code': ['Invalid tax code.']}}]})
        subtotal = money(quantity * unit_price)
        tax_amount = money(subtotal * tax_code.rate_percent / Decimal('100')) if tax_code else ZERO
        normalized.append({
            'invoice_item': invoice_item, 'material': invoice_item.material,
            'quantity': quantity, 'unit_price': unit_price, 'tax_code': tax_code,
            'tax_amount': tax_amount, 'description': raw.get('description', invoice_item.description),
        })
    if not normalized:
        raise ValidationError({'items': ['At least one credit-note item is required.']})
    subtotal = money(sum((item['quantity'] * item['unit_price'] for item in normalized), ZERO))
    tax = money(sum((item['tax_amount'] for item in normalized), ZERO))
    total = money(subtotal + tax)
    remaining_creditable = money(locked.total_amount - invoice_credit_amount(locked))
    if total > remaining_creditable:
        raise ValidationError({'items': [f'Credit note exceeds the remaining creditable amount of {remaining_creditable}.']})
    note = SupplierCreditNote(
        company=user.company, supplier=locked.supplier, invoice=locked,
        credit_note_number=credit_note_number.strip(), credit_note_date=credit_note_date,
        currency=locked.currency, exchange_rate=locked.exchange_rate, subtotal=subtotal,
        tax_amount=tax, total_amount=total, reason=reason, status=SupplierCreditNote.STATUS_DRAFT,
        idempotency_key=idempotency_key, created_by=user,
    )
    _save(note)
    for item in normalized:
        _save(SupplierCreditNoteItem(company=user.company, credit_note=note, **item))
    from .ledger_services import resolve_mapping, resolve_rule_accounts
    from .models import PostingRule

    rule_debit, _ = resolve_rule_accounts(
        company=user.company, event_type=PostingRule.EVENT_CREDIT_NOTE,
    )
    original_entry = JournalEntry.objects.get(
        company=user.company, source_type=JournalEntry.SOURCE_INVOICE, source_object_id=locked.pk,
    )
    original_debit = original_entry.lines.filter(debit__gt=ZERO).exclude(
        account__system_key=Account.SYSTEM_RECOVERABLE_VAT,
    ).select_related('account').first()
    if not original_debit:
        raise ValidationError({'invoice': ['The original invoice has no reversible cost line.']})
    base_total = base_money(total, locked.exchange_rate)
    base_tax = base_money(tax, locked.exchange_rate)
    base_cost = base_total - base_tax
    lines = [
        {'account': rule_debit, 'project': locked.project,
         'supplier': locked.supplier, 'description': note.credit_note_number, 'debit': base_total, 'credit': ZERO},
        {'account': original_debit.account, 'project': locked.project, 'supplier': locked.supplier,
         'description': note.credit_note_number, 'debit': ZERO, 'credit': base_cost},
    ]
    if base_tax:
        lines.append({
            'account': resolve_mapping(company=user.company, mapping_key='RECOVERABLE_VAT'),
            'project': locked.project, 'supplier': locked.supplier,
            'description': f'Reverse VAT / {note.credit_note_number}', 'debit': ZERO, 'credit': base_tax,
        })
    _create_journal(
        company=user.company, user=user, date=credit_note_date,
        description=f'Post supplier credit note {note.credit_note_number}',
        source_type=JournalEntry.SOURCE_CREDIT_NOTE, source_object_id=note.pk,
        lines=lines,
    )
    note.status = SupplierCreditNote.STATUS_POSTED
    note.posted_by = user
    note.posted_at = timezone.now()
    _save(note, update_fields=['status', 'posted_by', 'posted_at'])
    from .budget_services import apply_credit_note_to_actual

    apply_credit_note_to_actual(credit_note=note, user=user)
    _record_invoice_action(
        locked, user, InvoiceApproval.ACTION_CREDIT_NOTE, comments=reason,
        idempotency_key=f'approval:{idempotency_key}',
    )
    active_paid = invoice_paid_amount(locked)
    remaining = money(locked.total_amount - active_paid - invoice_credit_amount(locked))
    new_status = SupplierInvoice.STATUS_PAID if remaining == ZERO else (
        SupplierInvoice.STATUS_PARTIALLY_PAID if active_paid > ZERO else SupplierInvoice.STATUS_POSTED
    )
    SupplierInvoice.objects.filter(pk=locked.pk).update(status=new_status, updated_at=timezone.now())
    return note
