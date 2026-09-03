from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.procurement.models import GoodsReceivedNote, GoodsReceivedNoteItem
from apps.warehouse import valuation_services
from apps.warehouse.models import StockMovement

from .configuration_services import record_finance_audit_event, validate_exchange_rate
from .models import (
    Currency,
    FinanceSettings,
    LandedCostAllocation,
    LandedCostApproval,
    LandedCostDocument,
    LandedCostItem,
)


ZERO = Decimal('0.00')
PREPARATION_ROLES = {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}
APPROVAL_ROLES = {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}


def _require_role(user, roles):
    if not user or not user.is_authenticated or user.role not in roles:
        raise ValidationError({'non_field_errors': ['You are not authorized for this landed-cost action.']})


def _decimal(value, field, *, positive=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: ['Enter a valid decimal value.']}) from exc
    if result < 0 or (positive and result == 0):
        message = 'Value must be greater than zero.' if positive else 'Value cannot be negative.'
        raise ValidationError({field: [message]})
    return result


def _save(instance):
    try:
        instance.save()
    except DjangoValidationError as exc:
        detail = getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}
        raise ValidationError(detail) from exc
    except IntegrityError as exc:
        raise ValidationError({'non_field_errors': ['A landed-cost record with these values already exists.']}) from exc
    return instance


def _audit(document, user, action, metadata=None):
    record_finance_audit_event(
        company=document.company, actor=user, action=action,
        object_type='LandedCostDocument', object_id=document.pk,
        message=document.description, metadata=metadata or {},
    )


def _action(document, user, action, *, comments='', idempotency_key=''):
    approval = _save(LandedCostApproval(
        company=document.company, document=document, action=action,
        comments=comments, acted_by=user, idempotency_key=idempotency_key,
    ))
    _audit(document, user, f'landed_cost.{action.lower()}', {
        'approval_event': approval.pk, 'total_amount': document.total_amount,
        'base_total_amount': document.base_total_amount,
    })
    return approval


def _normalize_items(company, items):
    if not items:
        raise ValidationError({'items': ['At least one landed-cost item is required.']})
    normalized = []
    for index, raw in enumerate(items):
        amount = valuation_services.money(_decimal(raw.get('amount'), f'items.{index}.amount', positive=True))
        tax_code = raw.get('tax_code')
        if tax_code and tax_code.company_id != company.pk:
            raise ValidationError({'items': [{index: {'tax_code': ['Tax code must belong to your company.']}}]})
        normalized.append({
            'cost_type': raw['cost_type'], 'description': raw.get('description', ''),
            'amount': amount, 'tax_code': tax_code,
        })
    return normalized


def _resolve_grns(company, grns):
    ids = sorted({getattr(grn, 'pk', grn) for grn in grns})
    records = list(GoodsReceivedNote.objects.filter(
        company=company, pk__in=ids, status=GoodsReceivedNote.STATUS_ACCEPTED,
        purchase_order__delivery_destination='WAREHOUSE',
    ).order_by('pk'))
    if len(records) != len(ids) or not records:
        raise ValidationError({'goods_received_notes': ['Select accepted warehouse GRNs from your company.']})
    return records


@transaction.atomic
def create_document(*, user, values, items, goods_received_notes):
    _require_role(user, PREPARATION_ROLES)
    currency = values['currency']
    if currency.company_id != user.company_id or not currency.is_active:
        raise ValidationError({'currency': ['Currency must be active and belong to your company.']})
    normalized_items = _normalize_items(user.company, items)
    grns = _resolve_grns(user.company, goods_received_notes)
    exchange_rate = validate_exchange_rate(
        company=user.company,
        currency=currency,
        exchange_rate=values.get('exchange_rate', 1),
    )
    total = valuation_services.money(sum((item['amount'] for item in normalized_items), ZERO))
    document = _save(LandedCostDocument(
        company=user.company, created_by=user, total_amount=total,
        base_total_amount=valuation_services.money(total * exchange_rate),
        exchange_rate=exchange_rate, **{key: value for key, value in values.items() if key != 'exchange_rate'},
    ))
    for item in normalized_items:
        _save(LandedCostItem(company=user.company, document=document, **item))
    document.goods_received_notes.set(grns)
    _audit(document, user, 'landed_cost.created')
    return document


@transaction.atomic
def update_draft_document(*, document, user, values, items=None, goods_received_notes=None):
    _require_role(user, PREPARATION_ROLES)
    locked = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if locked.status != LandedCostDocument.STATUS_DRAFT or locked.reversal_of_id:
        raise ValidationError({'status': ['Only original draft landed-cost documents can be updated.']})
    if 'currency' in values and (values['currency'].company_id != user.company_id or not values['currency'].is_active):
        raise ValidationError({'currency': ['Currency must be active and belong to your company.']})
    for field, value in values.items():
        setattr(locked, field, value)
    locked.exchange_rate = validate_exchange_rate(
        company=user.company, currency=locked.currency, exchange_rate=locked.exchange_rate,
    )
    if items is not None:
        normalized_items = _normalize_items(user.company, items)
        locked.items.all().delete()
        for item in normalized_items:
            _save(LandedCostItem(company=user.company, document=locked, **item))
    if goods_received_notes is not None:
        locked.goods_received_notes.set(_resolve_grns(user.company, goods_received_notes))
    total = valuation_services.money(locked.items.aggregate(
        total=Coalesce(Sum('amount'), ZERO),
    )['total'])
    locked.total_amount = total
    locked.base_total_amount = valuation_services.money(total * locked.exchange_rate)
    locked.allocations.all().delete()
    _save(locked)
    _audit(locked, user, 'landed_cost.updated')
    return locked


def _preview_targets(document):
    grn_ids = list(document.goods_received_notes.values_list('pk', flat=True))
    rows = list(GoodsReceivedNoteItem.objects.select_for_update().select_related(
        'goods_received_note', 'purchase_order_item__material', 'stock_movement__warehouse',
    ).filter(
        company=document.company, goods_received_note_id__in=grn_ids,
        accepted_quantity__gt=0,
        stock_movement__transaction_type=StockMovement.TRANSACTION_RECEIPT,
    ).order_by('goods_received_note_id', 'pk'))
    if not rows:
        raise ValidationError({'goods_received_notes': ['Selected GRNs have no valued accepted receipt items.']})
    return rows


def _exact_allocations(total, bases):
    basis_total = sum((basis for _, basis in bases), Decimal('0'))
    if basis_total <= 0:
        raise ValidationError({'allocation_method': ['Allocation basis total must be greater than zero.']})
    allocations = []
    allocated = ZERO
    for index, (target, basis) in enumerate(bases):
        amount = (
            valuation_services.money(total - allocated)
            if index == len(bases) - 1
            else valuation_services.money(total * basis / basis_total)
        )
        allocations.append((target, amount))
        allocated += amount
    return allocations


@transaction.atomic
def preview_allocations(*, document, user, inputs=None):
    _require_role(user, PREPARATION_ROLES)
    locked = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if locked.status != LandedCostDocument.STATUS_DRAFT or locked.reversal_of_id:
        raise ValidationError({'status': ['Allocation preview is only available for original draft documents.']})
    targets = _preview_targets(locked)
    input_by_item = {
        int(item['goods_received_note_item']): item for item in (inputs or [])
    }
    bases = []
    details = {}
    for target in targets:
        quantity = Decimal(target.accepted_quantity)
        value = Decimal(target.stock_movement.total_cost)
        weight = Decimal('0')
        if locked.allocation_method == LandedCostDocument.ALLOCATION_QUANTITY:
            basis = quantity
        elif locked.allocation_method == LandedCostDocument.ALLOCATION_VALUE:
            basis = value
        elif locked.allocation_method == LandedCostDocument.ALLOCATION_EQUAL:
            basis = Decimal('1')
        elif locked.allocation_method == LandedCostDocument.ALLOCATION_WEIGHT:
            weight_per_unit = _decimal(
                input_by_item.get(target.pk, {}).get('weight_per_unit'),
                f'inputs.{target.pk}.weight_per_unit', positive=True,
            )
            weight = valuation_services.rate(quantity * weight_per_unit)
            basis = weight
        else:
            basis = Decimal('0')
        bases.append((target, basis))
        details[target.pk] = {'quantity': quantity, 'value': value, 'weight': weight}

    if locked.allocation_method == LandedCostDocument.ALLOCATION_MANUAL:
        allocations = []
        manual_total = ZERO
        for target in targets:
            amount = valuation_services.money(_decimal(
                input_by_item.get(target.pk, {}).get('manual_amount'),
                f'inputs.{target.pk}.manual_amount',
            ))
            allocations.append((target, amount))
            manual_total += amount
        if valuation_services.money(manual_total) != locked.base_total_amount:
            raise ValidationError({
                'inputs': [f'Manual allocations must equal {locked.base_total_amount}.'],
            })
    else:
        allocations = _exact_allocations(locked.base_total_amount, bases)

    locked.allocations.all().delete()
    for target, amount in allocations:
        detail = details[target.pk]
        _save(LandedCostAllocation(
            company=user.company, document=locked, goods_received_note_item=target,
            receipt_movement=target.stock_movement,
            basis_quantity=detail['quantity'], basis_weight=detail['weight'],
            basis_value=detail['value'], allocated_amount=amount,
        ))
    _audit(locked, user, 'landed_cost.previewed', {'allocation_method': locked.allocation_method})
    return locked


def _validate_allocation_total(document):
    total = valuation_services.money(document.allocations.aggregate(
        total=Coalesce(Sum('allocated_amount'), ZERO),
    )['total'])
    if total != document.base_total_amount:
        raise ValidationError({
            'allocations': [f'Allocated amount {total} must equal approved total {document.base_total_amount}.'],
        })
    return total


@transaction.atomic
def submit_document(*, document, user, comments=''):
    _require_role(user, PREPARATION_ROLES)
    locked = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if locked.status != LandedCostDocument.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft landed-cost documents can be submitted.']})
    if not locked.allocations.exists():
        raise ValidationError({'allocations': ['Run allocation preview before submission.']})
    _validate_allocation_total(locked)
    now = timezone.now()
    LandedCostDocument.objects.filter(pk=locked.pk).update(status=locked.STATUS_SUBMITTED, submitted_at=now)
    locked.status, locked.submitted_at = locked.STATUS_SUBMITTED, now
    _action(locked, user, LandedCostApproval.ACTION_SUBMIT, comments=comments)
    return locked


@transaction.atomic
def approve_document(*, document, user, comments=''):
    _require_role(user, APPROVAL_ROLES)
    locked = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if locked.status != LandedCostDocument.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted landed-cost documents can be approved.']})
    maker_checker = FinanceSettings.objects.filter(company=user.company).values_list(
        'maker_checker_enforced', flat=True,
    ).first()
    if maker_checker is not False and locked.created_by_id == user.pk:
        raise ValidationError({'non_field_errors': ['Maker-checker policy prevents self-approval.']})
    _validate_allocation_total(locked)
    now = timezone.now()
    LandedCostDocument.objects.filter(pk=locked.pk).update(
        status=locked.STATUS_APPROVED, approved_by=user, approved_at=now,
    )
    locked.status, locked.approved_by, locked.approved_at = locked.STATUS_APPROVED, user, now
    _action(locked, user, LandedCostApproval.ACTION_APPROVE, comments=comments)
    return locked


@transaction.atomic
def post_document(*, document, user, idempotency_key):
    _require_role(user, APPROVAL_ROLES)
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError({'idempotency_key': ['This field is required.']})
    existing = LandedCostApproval.objects.filter(
        company=user.company, idempotency_key=idempotency_key,
        action=LandedCostApproval.ACTION_POST,
    ).select_related('document').first()
    if existing:
        return existing.document
    locked = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if locked.status != LandedCostDocument.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved landed-cost documents can be posted.']})
    allocations = list(locked.allocations.select_for_update().select_related(
        'receipt_movement__material', 'receipt_movement__warehouse',
    ).order_by('receipt_movement__material_id', 'receipt_movement__warehouse_id', 'pk'))
    _validate_allocation_total(locked)
    if any(allocation.valuation_movement_id for allocation in allocations):
        raise ValidationError({'allocations': ['This landed cost has already affected inventory.']})
    posting_date = timezone.localdate()
    for allocation in allocations:
        movement = None
        if allocation.allocated_amount > ZERO:
            movement = valuation_services.apply_landed_cost_value(
                user=user, receipt_movement=allocation.receipt_movement,
                amount=allocation.allocated_amount, date=posting_date,
                reason=f'Landed cost {locked.number}',
            )
        LandedCostAllocation.objects.filter(pk=allocation.pk).update(
            status=LandedCostAllocation.STATUS_POSTED, valuation_movement=movement,
        )
    from .ledger_services import post_rule_event
    from .models import JournalEntry, PostingRule

    post_rule_event(
        company=user.company,
        user=user,
        event_type=PostingRule.EVENT_LANDED_COST,
        entry_date=posting_date,
        source_type=JournalEntry.SOURCE_LANDED_COST,
        source_object_id=locked.pk,
        amount=locked.base_total_amount,
        description=f'Post landed cost {locked.number}',
        source_reference=locked.number,
    )
    now = timezone.now()
    LandedCostDocument.objects.filter(pk=locked.pk).update(
        status=locked.STATUS_POSTED, posted_by=user, posted_at=now,
    )
    locked.status, locked.posted_by, locked.posted_at = locked.STATUS_POSTED, user, now
    _action(
        locked, user, LandedCostApproval.ACTION_POST,
        idempotency_key=idempotency_key.strip(),
    )
    return locked


def _reversal_number(document):
    base = f'{document.number[:42]}-REV'
    number = base
    suffix = 1
    while LandedCostDocument.objects.filter(company=document.company, number=number).exists():
        suffix += 1
        number = f'{base[:46]}-{suffix}'
    return number


@transaction.atomic
def reverse_document(*, document, user, reason, idempotency_key):
    _require_role(user, APPROVAL_ROLES)
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reversal reason is required.']})
    if not idempotency_key or not idempotency_key.strip():
        raise ValidationError({'idempotency_key': ['This field is required.']})
    existing = LandedCostApproval.objects.filter(
        company=user.company, idempotency_key=idempotency_key,
        action=LandedCostApproval.ACTION_REVERSE,
    ).select_related('document__reversal_document').first()
    if existing:
        return existing.document.reversal_document
    original = LandedCostDocument.objects.select_for_update().get(pk=document.pk, company=user.company)
    if original.status != LandedCostDocument.STATUS_POSTED or hasattr(original, 'reversal_document'):
        raise ValidationError({'status': ['Only an active posted landed cost can be reversed.']})
    original_allocations = list(original.allocations.select_for_update().select_related(
        'receipt_movement', 'goods_received_note_item',
    ).order_by('receipt_movement__material_id', 'receipt_movement__warehouse_id', 'pk'))
    now = timezone.now()
    reversal = _save(LandedCostDocument(
        company=user.company, number=_reversal_number(original),
        description=f'Reversal of {original.number}: {reason.strip()}',
        allocation_method=original.allocation_method, currency=original.currency,
        exchange_rate=original.exchange_rate, total_amount=original.total_amount,
        base_total_amount=original.base_total_amount, status=LandedCostDocument.STATUS_DRAFT,
        reversal_of=original, created_by=user, submitted_at=now,
        approved_by=user, approved_at=now, posted_by=user, posted_at=now,
    ))
    for item in original.items.all():
        _save(LandedCostItem(
            company=user.company, document=reversal, cost_type=item.cost_type,
            description=item.description, amount=item.amount, tax_code=item.tax_code,
        ))
    reversal.goods_received_notes.set(original.goods_received_notes.all())
    for allocation in original_allocations:
        movement = None
        if allocation.allocated_amount > ZERO:
            movement = valuation_services.apply_landed_cost_value(
                user=user, receipt_movement=allocation.receipt_movement,
                amount=allocation.allocated_amount, date=timezone.localdate(),
                reason=reversal.description, reversal=True,
            )
        _save(LandedCostAllocation(
            company=user.company, document=reversal,
            goods_received_note_item=allocation.goods_received_note_item,
            receipt_movement=allocation.receipt_movement,
            basis_quantity=allocation.basis_quantity, basis_weight=allocation.basis_weight,
            basis_value=allocation.basis_value, allocated_amount=allocation.allocated_amount,
            status=LandedCostAllocation.STATUS_POSTED,
            valuation_movement=movement, reverses=allocation,
        ))
    LandedCostDocument.objects.filter(pk=reversal.pk).update(status=LandedCostDocument.STATUS_POSTED)
    LandedCostDocument.objects.filter(pk=original.pk).update(status=LandedCostDocument.STATUS_REVERSED)
    reversal.status, original.status = reversal.STATUS_POSTED, original.STATUS_REVERSED
    from .ledger_services import reverse_journal
    from .models import JournalEntry

    original_journal = JournalEntry.objects.get(
        company=user.company,
        source_type=JournalEntry.SOURCE_LANDED_COST,
        source_object_id=original.pk,
    )
    reverse_journal(
        journal=original_journal,
        user=user,
        reason=reason.strip(),
        idempotency_key=f'landed-cost-ledger:{idempotency_key}',
    )
    _action(
        original, user, LandedCostApproval.ACTION_REVERSE,
        comments=reason.strip(), idempotency_key=idempotency_key.strip(),
    )
    _audit(reversal, user, 'landed_cost.reversal_posted', {'reversal_of': original.pk})
    return reversal
