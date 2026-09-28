"""Controlled, tenant-scoped non-purchase receipts and borrowed-material custody."""
from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.finance.configuration_services import record_finance_audit_event
from apps.materials.models import Material
from apps.notifications.models import Notification
from apps.projects.models import Project
from .models import (BinLocation, ExternalMoveOrder, ExternalMoveLine, ExternalReceipt,
                     ExternalReceiptLine, ExternalStockEvent, StockMovement, Warehouse)
from . import valuation_services as valuation

OPERATORS = {'admin', 'storekeeper', 'procurement_officer'}
RECEIVERS = {'admin', 'storekeeper'}


def require_role(user, roles):
    if not user.is_authenticated or not user.company_id or not user.company.is_active or user.role not in roles:
        raise PermissionDenied('Your role cannot perform this action.')


def reason_required(reason):
    if len(reason.strip()) < 10:
        raise ValidationError({'reason': 'Explain this action in at least 10 characters.'})


def audit(order, user, action, reason, **metadata):
    if len(reason) > 500:
        metadata['full_reason'] = reason
    record_finance_audit_event(company=order.company, actor=user, action=action,
                              object_type='ExternalMoveOrder', object_id=order.pk,
                              message=reason[:500], metadata=metadata)


def notify(order, roles, title, message):
    for recipient in User.objects.filter(company=order.company, role__in=roles, is_active=True):
        Notification.objects.create(company=order.company, recipient=recipient,
                                    notification_type=Notification.TYPE_SYSTEM,
                                    title=title, message=message,
                                    link=f'/inventory/external-transfers/{order.pk}')


def lock_order(user, order_id):
    order = ExternalMoveOrder.objects.select_for_update().filter(pk=order_id, company=user.company).first()
    if not order:
        raise ValidationError('Move order not found in your company.')
    return order


def line_balances(line):
    totals = {'received': Decimal(0), 'held': Decimal(0), 'outstanding': Decimal(0), 'returned': Decimal(0)}
    projects = {}
    for event in line.events.all():
        q = event.quantity
        if event.action == 'RECEIVE':
            totals['received'] += q
            totals['held'] += q
            totals['outstanding'] += q
        elif event.action == 'REVERSE':
            totals['received'] -= q
            totals['held'] -= q
            totals['outstanding'] -= q
        elif event.action == 'OWNER_RETURN':
            totals['held'] -= q
            totals['outstanding'] -= q
            totals['returned'] += q
        elif event.action == 'ISSUE':
            totals['held'] -= q
            projects[event.project_id] = projects.get(event.project_id, Decimal(0)) + q
        elif event.action == 'PROJECT_RETURN':
            totals['held'] += q
            projects[event.project_id] = projects.get(event.project_id, Decimal(0)) - q
    totals['projects'] = projects
    return totals


@transaction.atomic
def create_order(*, user, sender, reference, ownership, warehouse, expected_date, lines,
                 return_due_date=None, notes=''):
    require_role(user, OPERATORS)
    warehouse = Warehouse.objects.filter(pk=warehouse, company=user.company, is_active=True, project__isnull=True).first()
    if not warehouse:
        raise ValidationError({'warehouse': 'Select an active company warehouse (not a site store).'})
    if ownership == 'BORROWED' and not return_due_date:
        raise ValidationError({'return_due_date': 'A return due date is required for borrowed stock.'})
    if return_due_date and return_due_date < expected_date:
        raise ValidationError({'return_due_date': 'Return due date cannot precede expected arrival.'})
    try:
        with transaction.atomic():
            order = ExternalMoveOrder.objects.create(company=user.company, sender=sender.strip(), reference=reference.strip(),
                sender_key=' '.join(sender.casefold().split()), reference_key=' '.join(reference.casefold().split()),
                ownership=ownership, warehouse=warehouse, expected_date=expected_date,
                return_due_date=return_due_date if ownership == 'BORROWED' else None, notes=notes, created_by=user)
    except IntegrityError as exc:
        raise ValidationError({'reference': 'This sender and move-order reference already exist.'}) from exc
    seen = set()
    for values in lines:
        material = Material.objects.filter(pk=values['material'], company=user.company, is_active=True).first()
        if not material or material.pk in seen:
            raise ValidationError({'lines': 'Select active company materials once each.'})
        seen.add(material.pk)
        bin_id = values.get('bin_location')
        if bin_id and not BinLocation.objects.filter(pk=bin_id, warehouse=warehouse, is_active=True).exists():
            raise ValidationError({'lines': 'The bin must be active and belong to the selected warehouse.'})
        ExternalMoveLine.objects.create(order=order, material=material, bin_location_id=bin_id,
            quantity=values['quantity'], unit_cost=values.get('unit_cost', 0) if ownership == 'PERMANENT' else 0)
    audit(order, user, 'external_move_created', notes or 'External move order recorded.')
    notify(order, RECEIVERS, 'External materials expected', f'MO-{order.pk}: {order.sender} / {order.reference}. Confirm quantities when delivered.')
    return order


@transaction.atomic
def confirm_receipt(*, user, order_id, reference, received_date, lines, notes=''):
    require_role(user, RECEIVERS)
    order = lock_order(user, order_id)
    if order.closed:
        raise ValidationError('This move order is closed to further receipts.')
    if received_date > timezone.localdate():
        raise ValidationError({'received_date': 'A physical receipt cannot be future-dated.'})
    reference = ' '.join(reference.upper().split())
    if order.receipts.filter(reference=reference).exists():
        raise ValidationError({'reference': 'This delivery reference was already recorded. Open its existing receipt.'})
    receipt = ExternalReceipt.objects.create(order=order, reference=reference, received_date=received_date, received_by=user, notes=notes)
    seen = set()
    for values in lines:
        line = order.lines.filter(pk=values['order_line']).first()
        if not line or line.pk in seen:
            raise ValidationError({'lines': 'Select each move-order line once.'})
        seen.add(line.pk)
        accepted, damaged, rejected = (values.get(field, Decimal(0)) for field in ('accepted', 'damaged', 'rejected'))
        if accepted + damaged + rejected <= 0:
            raise ValidationError({'lines': 'Enter a received quantity for each included line.'})
        # Damaged/rejected quantities do not consume the accepted allocation: replacements may arrive later.
        allocated = sum((item.accepted for item in line.receipt_lines.filter(receipt__status__in=['PENDING', 'POSTED'])), Decimal(0))
        if accepted + damaged + rejected > line.quantity - allocated:
            raise ValidationError({'lines': f'{line.material.name}: only {line.quantity - allocated} remains to receive.'})
        if (damaged or rejected) and not notes.strip():
            raise ValidationError({'notes': 'Explain damaged or rejected quantities; these will not enter stock.'})
        ExternalReceiptLine.objects.create(receipt=receipt, order_line=line, accepted=accepted, damaged=damaged, rejected=rejected)
    audit(order, user, 'external_receipt_confirmed', notes or 'Physical count confirmed.', receipt=receipt.pk)
    notify(order, {'admin'}, 'External receipt awaiting approval', f'MO-{order.pk}, receipt {reference}: verify ownership, quantities and valuation before posting.')
    return receipt


@transaction.atomic
def review_receipt(*, user, order_id, receipt_id, decision, reason, costs=None):
    require_role(user, {'admin'})
    reason_required(reason)
    order = lock_order(user, order_id)
    receipt = order.receipts.filter(pk=receipt_id).first()
    if not receipt:
        raise ValidationError('Receipt not found on this move order.')
    if receipt.status != 'PENDING':
        raise ValidationError('This receipt has already been reviewed. Refresh the page.')
    if decision == 'post':
        if not order.warehouse.is_active:
            raise ValidationError('The receiving warehouse is inactive.')
        # Acquire all material locks in a stable order before taking warehouse locks.
        list(Material.objects.select_for_update().filter(pk__in=order.lines.values('material_id')).order_by('pk'))
        for item in receipt.lines.select_related('order_line__material').order_by('order_line__material_id'):
            line = item.order_line
            movement = None
            if order.ownership == 'PERMANENT' and item.accepted:
                cost = (costs or {}).get(str(line.pk), line.unit_cost)
                material, warehouse = valuation._resolve_context(company=order.company, material=line.material, warehouse=order.warehouse)
                movement = valuation._record_entry(company=order.company, material=material, warehouse=warehouse,
                    quantity=item.accepted, receipt_unit_cost=cost, transaction_type=StockMovement.TRANSACTION_EXTERNAL_RECEIPT,
                    source=StockMovement.SOURCE_INTERNAL, user=user, date=receipt.received_date,
                    authorized_by=user, authorization_reason=reason, notes=f'MO-{order.pk} / {receipt.reference}: {order.sender}')
                item.movement = movement
                item.save(update_fields=['movement'])
                line.unit_cost = cost
                line.save(update_fields=['unit_cost'])
            if item.accepted:
                ExternalStockEvent.objects.create(line=line, receipt=receipt, action='RECEIVE', quantity=item.accepted,
                    movement=movement, actor=user, reason=reason, request_key=uuid4())
        receipt.status = 'POSTED'
    else:
        receipt.status = 'REJECTED'
    receipt.reviewed_by = user
    receipt.reviewed_at = timezone.now()
    receipt.review_reason = reason
    receipt.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'review_reason'])
    audit(order, user, f'external_receipt_{receipt.status.lower()}', reason, receipt=receipt.pk)
    notify(order, RECEIVERS, f'External receipt {receipt.status.lower()}', f'MO-{order.pk}, {receipt.reference}: {reason}')
    return receipt


@transaction.atomic
def stock_action(*, user, order_id, line_id, action, quantity, reason, request_key, project=None):
    # Returns and borrowed dispatch require an Admin authorization, not an unrestricted stock adjustment.
    require_role(user, {'admin'})
    reason_required(reason)
    quantity = valuation._decimal(quantity, 'quantity')
    if action not in {'ISSUE', 'PROJECT_RETURN', 'OWNER_RETURN'}:
        raise ValidationError('Unknown custody action.')
    order = lock_order(user, order_id)
    if ExternalStockEvent.objects.filter(request_key=request_key).exists():
        raise ValidationError('This action was already recorded. Refresh before continuing.')
    line = order.lines.filter(pk=line_id).first()
    if not line:
        raise ValidationError('Material line not found on this move order.')
    balances = line_balances(line)
    movement = None
    if action in {'ISSUE', 'PROJECT_RETURN'}:
        if order.ownership != 'BORROWED':
            raise ValidationError('Use the normal approved material-request workflow to issue company-owned stock.')
        project = Project.objects.filter(pk=project, company=order.company).first()
        if not project:
            raise ValidationError({'project': 'Select a project in your company.'})
        available = balances['held'] if action == 'ISSUE' else balances['projects'].get(project.pk, Decimal(0))
    else:
        project = None
        available = balances['held']
        if order.ownership == 'PERMANENT':
            material, warehouse = valuation._resolve_context(company=order.company, material=line.material, warehouse=order.warehouse)
            state = valuation.valuation_state(company=order.company, material=material, warehouse=warehouse)
            # Do not bypass project-reserved stock or a permissive negative-stock policy.
            unreserved = valuation.available_for_project_issue(company=order.company, material=material, warehouse=warehouse, project=type('Unassigned', (), {'pk': None})())
            available = min(available, state['quantity'], unreserved)
            if quantity <= available:
                movement = valuation._record_exit(company=order.company, material=material, warehouse=warehouse,
                    quantity=quantity, transaction_type=StockMovement.TRANSACTION_EXTERNAL_RETURN,
                    source=StockMovement.SOURCE_INTERNAL, user=user, authorized_by=user, authorization_reason=reason,
                    notes=f'Return to {order.sender}, MO-{order.pk}')
    if quantity > available:
        raise ValidationError({'quantity': f'Only {available} is available for this action.'})
    event = ExternalStockEvent.objects.create(line=line, action=action, quantity=quantity, project=project,
        actor=user, reason=reason, request_key=request_key, movement=movement)
    audit(order, user, f'external_stock_{action.lower()}', reason, quantity=str(quantity), line=line.pk, event=event.pk)
    return event


@transaction.atomic
def reverse_receipt(*, user, order_id, receipt_id, reason):
    require_role(user, {'admin'})
    reason_required(reason)
    order = lock_order(user, order_id)
    receipt = order.receipts.filter(pk=receipt_id, status='POSTED').first()
    if not receipt:
        raise ValidationError('Only a posted receipt can be reversed once.')
    list(Material.objects.select_for_update().filter(pk__in=order.lines.values('material_id')).order_by('pk'))
    for item in receipt.lines.select_related('order_line').order_by('order_line__material_id'):
        if not item.accepted:
            continue
        line = item.order_line
        original = line.events.get(receipt=receipt, action='RECEIVE')
        if line.events.filter(pk__gt=original.pk).exists():
            raise ValidationError('Later custody transactions exist. Return available materials to the sender instead.')
        reversal = None
        if item.movement_id:
            material, warehouse = valuation._resolve_context(company=order.company, material=line.material, warehouse=order.warehouse)
            if StockMovement.objects.filter(material=material, warehouse=warehouse, pk__gt=item.movement_id).exists():
                raise ValidationError('Later stock transactions exist. Use a controlled return to the sender instead.')
            reversal = valuation._record_exit(company=order.company, material=material, warehouse=warehouse,
                quantity=item.accepted, issue_rate=item.movement.unit_cost,
                transaction_type=StockMovement.TRANSACTION_EXTERNAL_RETURN, source=StockMovement.SOURCE_INTERNAL,
                user=user, authorized_by=user, authorization_reason=reason, original_movement=item.movement,
                notes=f'Reversal MO-{order.pk}, receipt {receipt.reference}')
            item.reversal = reversal
            item.save(update_fields=['reversal'])
        ExternalStockEvent.objects.create(line=line, receipt=receipt, action='REVERSE', quantity=item.accepted,
            actor=user, reason=reason, movement=reversal, request_key=uuid4())
    receipt.status = 'REVERSED'
    receipt.save(update_fields=['status'])
    audit(order, user, 'external_receipt_reversed', reason, receipt=receipt.pk)


@transaction.atomic
def close_order(*, user, order_id, reason):
    require_role(user, {'admin'})
    reason_required(reason)
    order = lock_order(user, order_id)
    if order.closed:
        raise ValidationError('This move order is already closed.')
    if order.receipts.filter(status='PENDING').exists():
        raise ValidationError('Review pending receipts first.')
    # Closing stops additional receipts; return obligations remain visible and actionable.
    order.closed = True
    order.save(update_fields=['closed'])
    audit(order, user, 'external_move_closed', reason)
