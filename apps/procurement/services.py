from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.db import transaction
from django.db.models import Sum
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.materials.models import Material
from apps.notifications.helpers import send_notification
from apps.notifications.models import Notification
from apps.warehouse.valuation_services import get_project_site_store, receive_valued_stock

from .models import (
    DocumentSequence,
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    SupplierClaim,
)
from .amendments import PurchaseOrderAmendment


def get_company_users_by_roles(company, roles):
    if company is None:
        return User.objects.none()
    return User.objects.filter(company=company, role__in=roles, is_active=True)


def notify_users(users, notification_type, level, title, message, link):
    sent_user_ids = set()
    for user in users:
        if user.id in sent_user_ids:
            continue
        sent_user_ids.add(user.id)
        send_notification(user, notification_type, level, title, message, link)


def generate_document_number(company, document_type, prefix, model):
    today = timezone.localdate()
    with transaction.atomic():
        sequence, created = DocumentSequence.objects.select_for_update().get_or_create(
            company=company,
            document_type=document_type,
            defaults={'last_value': model.objects.filter(company=company).count()},
        )
        sequence.last_value += 1
        sequence.save(update_fields=['last_value'])
    return f'{prefix}-{today:%Y%m%d}-{sequence.last_value:04d}'


def generate_pr_number(company):
    return generate_document_number(
        company,
        DocumentSequence.TYPE_PURCHASE_REQUEST,
        'PR',
        PurchaseRequest,
    )


def generate_po_number(company):
    return generate_document_number(
        company,
        DocumentSequence.TYPE_PURCHASE_ORDER,
        'PO',
        PurchaseOrder,
    )


def create_purchase_request(*, serializer, user):
    """Persist a purchase request with its canonical identity and initial status.

    Side effects such as notifications remain in the API layer for now; this
    extraction isolates the write's data rules without changing the endpoint.
    """
    is_warehouse_replenishment = user.role == User.ROLE_PROCUREMENT_OFFICER
    purchase_request = serializer.save(
        company=user.company,
        requested_by=user,
        number=generate_pr_number(user.company),
        status=(
            PurchaseRequest.STATUS_APPROVED
            if is_warehouse_replenishment
            else PurchaseRequest.STATUS_PENDING
        ),
    )
    return purchase_request, is_warehouse_replenishment


def create_purchase_order(*, serializer, user):
    """Persist a draft purchase order with its canonical identity."""
    return serializer.save(
        company=user.company,
        number=generate_po_number(user.company),
        delivery_follow_up_owner=user,
    )


def approve_purchase_request(*, purchase_request, approver=None):
    """Apply the technical approval transition to a pending request."""
    if purchase_request.status != PurchaseRequest.STATUS_PENDING:
        raise ValidationError('Only pending purchase requests can be approved.')
    purchase_request.status = PurchaseRequest.STATUS_APPROVED
    if approver is not None:
        if approver.role == User.ROLE_PROJECT_MANAGER:
            purchase_request.manager_approved_by = approver
        purchase_request.technical_approved_by = approver
    purchase_request.rejection_reason = ''
    purchase_request.technical_return_reason = ''
    purchase_request.save(
        update_fields=['status', 'rejection_reason', 'technical_return_reason', 'technical_approved_by', 'manager_approved_by', 'updated_at'],
    )
    return purchase_request


def approve_stock_issue_request(*, purchase_request, approver):
    """Record the separate Admin gate required before warehouse issue."""
    if approver.role != User.ROLE_ADMIN:
        raise ValidationError('Only an Admin can approve a warehouse stock issue.')
    if purchase_request.status != PurchaseRequest.STATUS_APPROVED:
        raise ValidationError('Only approved purchase requests can be approved for warehouse stock issue.')
    if purchase_request.purchase_orders.exists():
        raise ValidationError('A purchase request with a purchase order cannot use warehouse stock issue.')
    if not purchase_request.project_id:
        raise ValidationError('Warehouse replenishment requests cannot use warehouse stock issue.')
    if not purchase_request.manager_approved_by_id or purchase_request.manager_approved_by.role != User.ROLE_PROJECT_MANAGER:
        raise ValidationError('Project Manager approval is required before Admin can approve warehouse stock issue.')
    if not purchase_request.items.exists():
        raise ValidationError('The purchase request must have at least one line item.')
    purchase_request.technical_approved_by = approver
    purchase_request.save(update_fields=['technical_approved_by', 'updated_at'])
    return purchase_request


def reject_purchase_request(*, purchase_request, rejection_reason):
    """Apply the technical rejection transition to a pending request."""
    if purchase_request.status != PurchaseRequest.STATUS_PENDING:
        raise ValidationError('Only pending purchase requests can be rejected.')
    purchase_request.status = PurchaseRequest.STATUS_REJECTED
    purchase_request.rejection_reason = rejection_reason
    purchase_request.save(update_fields=['status', 'rejection_reason', 'updated_at'])
    return purchase_request


def return_purchase_request_for_correction(*, purchase_request, comments):
    """Return a pending request with a mandatory correction explanation."""
    if purchase_request.status != PurchaseRequest.STATUS_PENDING:
        raise ValidationError('Only pending purchase requests can be returned for correction.')
    purchase_request.status = PurchaseRequest.STATUS_RETURNED
    purchase_request.technical_return_reason = comments
    purchase_request.rejection_reason = ''
    purchase_request.save(
        update_fields=['status', 'technical_return_reason', 'rejection_reason', 'updated_at'],
    )
    return purchase_request


def purchase_order_amendment_snapshot(purchase_order):
    """Return JSON-safe immutable evidence of the submitted PO state."""
    return {
        'supplier': purchase_order.supplier_id,
        'delivery_destination': purchase_order.delivery_destination,
        'expected_delivery_date': purchase_order.expected_delivery_date.isoformat() if purchase_order.expected_delivery_date else None,
        'supplier_confirmed_delivery_date': purchase_order.supplier_confirmed_delivery_date.isoformat() if purchase_order.supplier_confirmed_delivery_date else None,
        'revised_delivery_date': purchase_order.revised_delivery_date.isoformat() if purchase_order.revised_delivery_date else None,
        'delivery_revision_reason': purchase_order.delivery_revision_reason,
        'notes': purchase_order.notes,
        'items': [
            {
                'id': item.pk, 'material': item.material_id, 'material_name': item.material.name,
                'quantity': str(item.quantity), 'unit_price': str(item.unit_price), 'notes': item.notes,
            }
            for item in purchase_order.items.select_related('material').order_by('pk')
        ],
    }


@transaction.atomic
def create_purchase_order_amendment(*, purchase_order, user, reason, proposed_values):
    """Create the next immutable submitted amendment version."""
    version = (
        purchase_order.amendments.select_for_update()
        .order_by('-version').values_list('version', flat=True).first() or 0
    ) + 1
    return PurchaseOrderAmendment.objects.create(
        purchase_order=purchase_order,
        company=purchase_order.company,
        version=version,
        reason=reason,
        original_values=purchase_order_amendment_snapshot(purchase_order),
        proposed_values=proposed_values,
        submitted_by=user,
    )


@transaction.atomic
def approve_purchase_order_amendment(*, purchase_order, amendment_id, user, comments):
    """Apply a submitted controlled amendment and its finance recommitment."""
    from apps.finance.models import SupplierInvoice
    from apps.finance import budget_services

    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    amendment = po.amendments.select_for_update().filter(
        pk=amendment_id, status=PurchaseOrderAmendment.STATUS_SUBMITTED,
    ).first()
    if (
        not amendment
        or amendment.amendment_type != PurchaseOrderAmendment.TYPE_CONTROLLED
        or po.goods_received_notes.exists()
        or SupplierInvoice.objects.filter(purchase_order=po).exists()
    ):
        raise ValidationError('Amendment is unavailable because receipt or invoicing has begun.')

    values = amendment.proposed_values.copy()
    items = values.pop('items', None)
    price_lines = values.pop('price_lines', None)
    for field, value in values.items():
        setattr(po, field, value)
    po.save()
    if items is not None:
        po.items.all().delete()
        PurchaseOrderItem.objects.bulk_create([
            PurchaseOrderItem(
                purchase_order=po,
                material_id=item['material'],
                quantity=Decimal(item['quantity']),
                unit_price=Decimal(item['unit_price']),
                notes=item['notes'],
            )
            for item in items
        ])
    if price_lines is not None:
        locked_items = {item.pk: item for item in po.items.select_for_update()}
        for line in price_lines:
            po_item = locked_items.get(int(line['purchase_order_item']))
            if not po_item:
                raise ValidationError({'price_lines': ['A proposed line is no longer part of this purchase order.']})
            po_item.unit_price = Decimal(str(line['unit_price']))
            po_item.save(update_fields=['unit_price'])
    budget_services.recommit_purchase_order_after_amendment(
        purchase_order=po, user=user, amendment=amendment,
    )
    amendment.status = PurchaseOrderAmendment.STATUS_APPROVED
    amendment.decided_by = user
    amendment.decision_reason = comments
    amendment.decided_at = timezone.now()
    amendment.save()
    return po, amendment


@transaction.atomic
def confirm_purchase_order_preapproval_edit(*, purchase_order, user, comments):
    """Confirm the pending pre-approval edit without changing PO values again."""
    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    edit = po.amendments.select_for_update().filter(
        amendment_type=PurchaseOrderAmendment.TYPE_PRE_APPROVAL_EDIT,
        status=PurchaseOrderAmendment.STATUS_SUBMITTED,
    ).first()
    if not edit:
        raise ValidationError('There is no pending pre-approval PO edit.')
    edit.status = PurchaseOrderAmendment.STATUS_APPROVED
    edit.decided_by = user
    edit.decision_reason = comments
    edit.decided_at = timezone.now()
    edit.save(update_fields=['status', 'decided_by', 'decision_reason', 'decided_at'])
    return po, edit


@transaction.atomic
def reject_purchase_order_amendment(*, purchase_order, amendment_id, user, comments):
    """Reject a submitted controlled amendment."""
    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk)
    amendment = po.amendments.select_for_update().filter(
        pk=amendment_id, status=PurchaseOrderAmendment.STATUS_SUBMITTED,
    ).first()
    if not amendment:
        raise ValidationError('Amendment is unavailable.')
    amendment.status = PurchaseOrderAmendment.STATUS_REJECTED
    amendment.decided_by = user
    amendment.decision_reason = comments
    amendment.decided_at = timezone.now()
    amendment.save()
    return po, amendment


def generate_grn_number(company):
    return generate_document_number(
        company, DocumentSequence.TYPE_GOODS_RECEIVED_NOTE, 'GRN', GoodsReceivedNote,
    )


@transaction.atomic
def record_goods_received_note(*, purchase_order, user, receipt_date, items=None, notes='', client_uuid=None, replacement_claim=None):
    po = PurchaseOrder.objects.select_for_update().get(pk=purchase_order.pk, company=user.company)
    po_items = list(po.items.select_for_update().select_related('material').order_by('pk'))
    if not po_items:
        raise ValidationError({'items': ['A purchase order must have items before receipt.']})
    prior = {
        row['purchase_order_item']: {
            'accepted': row['accepted'] or Decimal('0.00'),
            'dispositioned': row['dispositioned'] or Decimal('0.00'),
        }
        for row in GoodsReceivedNoteItem.objects.select_for_update().filter(
            company=user.company, purchase_order_item__in=po_items,
            goods_received_note__status=GoodsReceivedNote.STATUS_ACCEPTED,
        ).values('purchase_order_item').annotate(
            accepted=Sum('accepted_quantity'),
            dispositioned=Sum('accepted_quantity') + Sum('rejected_quantity') + Sum('damaged_quantity'),
        )
    }
    by_id = {item.pk: item for item in po_items}
    if items is None and replacement_claim is None:
        items = [{
            'purchase_order_item': po_item,
            'accepted_quantity': max(
                po_item.quantity - prior.get(po_item.pk, {}).get('dispositioned', Decimal('0.00')),
                Decimal('0.00'),
            ),
            'rejected_quantity': Decimal('0.00'), 'damaged_quantity': Decimal('0.00'), 'notes': '',
        } for po_item in po_items if po_item.quantity > prior.get(po_item.pk, {}).get('dispositioned', Decimal('0.00'))]
    if not items:
        raise ValidationError({'items': ['At least one outstanding receipt item is required.']})
    replacement_claim_instance = None
    if replacement_claim is not None:
        replacement_claim_instance = SupplierClaim.objects.select_for_update().select_related('goods_received_note_item__purchase_order_item').get(
            pk=getattr(replacement_claim, 'pk', replacement_claim), company=user.company,
        )
        original = replacement_claim_instance.goods_received_note_item
        if replacement_claim_instance.purchase_order_id != po.pk or replacement_claim_instance.status != SupplierClaim.STATUS_REPLACEMENT_PENDING or replacement_claim_instance.replacement_grn_item_id:
            raise ValidationError({'supplier_claim': ['This claim is not awaiting one replacement receipt.']})
    normalized = []
    seen = set()
    for index, raw in enumerate(items):
        po_item_id = getattr(raw['purchase_order_item'], 'pk', raw['purchase_order_item'])
        po_item = by_id.get(po_item_id)
        if not po_item:
            raise ValidationError({'items': [{index: {'purchase_order_item': ['Item is not on this PO.']}}]})
        if po_item_id in seen:
            raise ValidationError({'items': [{index: {'purchase_order_item': ['Item is duplicated.']}}]})
        seen.add(po_item_id)
        accepted = Decimal(raw.get('accepted_quantity', 0))
        rejected = Decimal(raw.get('rejected_quantity', 0))
        damaged = Decimal(raw.get('damaged_quantity', 0))
        if min(accepted, rejected, damaged) < 0 or accepted + rejected + damaged <= 0:
            raise ValidationError({'items': [{index: {'non_field_errors': ['Disposition quantities are invalid.']}}]})
        line_notes = raw.get('notes', '').strip()
        if (rejected > 0 or damaged > 0) and not line_notes:
            raise ValidationError({'items': [{index: {'notes': ['A line note is required when goods are rejected or damaged.']}}]})
        dispositioned = accepted + rejected + damaged
        if replacement_claim_instance:
            replacement_due = original.rejected_quantity + original.damaged_quantity
            if po_item_id != original.purchase_order_item_id or rejected or damaged or accepted != replacement_due:
                raise ValidationError({'items': [{index: {'non_field_errors': ['A replacement receipt must accept exactly the rejected/damaged quantity on its linked supplier claim.']}}]})
        else:
            remaining = po_item.quantity - prior.get(po_item_id, {}).get('dispositioned', Decimal('0.00'))
            if dispositioned > remaining:
                raise ValidationError({'items': [{index: {
                    'non_field_errors': [
                        f'Only {remaining} remains on this PO line; accepted, rejected, and damaged quantities together cannot exceed the ordered quantity.'
                    ]
                }}]})
        normalized.append((po_item, accepted, rejected, damaged, line_notes))
    if po.delivery_destination == PurchaseOrder.DELIVERY_WAREHOUSE:
        list(Material.objects.select_for_update().filter(
            company=user.company, pk__in=sorted(item.material_id for item, *_ in normalized),
        ))
    grn = GoodsReceivedNote.objects.create(
        company=user.company, purchase_order=po, number=generate_grn_number(user.company),
        receipt_date=receipt_date, notes=notes, received_by=user, client_uuid=client_uuid,
    )
    replacement_grn_item = None
    for po_item, accepted, rejected, damaged, line_notes in normalized:
        grn_item = GoodsReceivedNoteItem.objects.create(
            company=user.company, goods_received_note=grn, purchase_order_item=po_item,
            accepted_quantity=accepted, rejected_quantity=rejected,
            damaged_quantity=damaged, notes=line_notes,
        )
        if rejected > 0 or damaged > 0:
            new_claim = SupplierClaim.objects.create(
                company=user.company,
                goods_received_note_item=grn_item,
                purchase_order=po,
                supplier=po.supplier,
                project=po.project,
                reported_by=user,
                due_date=timezone.localdate() + timedelta(days=3),
                notes=(
                    f'{rejected} rejected and {damaged} damaged from PO line '
                    f'{po_item.material.code}. {line_notes}'
                ).strip(),
            )
            recipients = get_company_users_by_roles(
                user.company, [User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN],
            )
            notify_users(
                recipients,
                Notification.TYPE_SUPPLIER_CLAIM_OPENED,
                Notification.LEVEL_WARNING,
                f'Supplier claim opened: {po.number}',
                f'{po_item.material.name} was rejected or damaged. Resolve claim #{new_claim.pk} by {new_claim.due_date:%d %b %Y}.',
                f'/procurement/purchase-orders/{po.pk}',
            )
        if accepted > 0:
            destination_store = None
            if po.delivery_destination == PurchaseOrder.DELIVERY_SITE:
                destination_store = get_project_site_store(po.project)
            receive_valued_stock(
                user=user, goods_received_note_item=grn_item, warehouse=destination_store,
                allow_site_receiver=po.delivery_destination == PurchaseOrder.DELIVERY_SITE,
            )
        if replacement_claim_instance:
            replacement_grn_item = grn_item
    if replacement_claim_instance:
        replacement_claim_instance.replacement_grn_item = replacement_grn_item
        # A physical replacement is evidence, not commercial closure.
        # Procurement must still confirm the supplier claim is settled.
        replacement_claim_instance.status = SupplierClaim.STATUS_REPLACEMENT_RECEIVED
        replacement_claim_instance.resolution_notes = (replacement_claim_instance.resolution_notes + '\n' if replacement_claim_instance.resolution_notes else '') + f'Replacement received on {grn.number}.'
        replacement_claim_instance.save(update_fields=['replacement_grn_item', 'status', 'resolution_notes', 'updated_at'])
    cumulative = {
        row['purchase_order_item']: row['dispositioned'] or Decimal('0.00')
        for row in GoodsReceivedNoteItem.objects.filter(
            company=user.company, purchase_order_item__in=po_items,
            goods_received_note__status=GoodsReceivedNote.STATUS_ACCEPTED,
        ).values('purchase_order_item').annotate(
            dispositioned=Sum('accepted_quantity') + Sum('rejected_quantity') + Sum('damaged_quantity'),
        )
    }
    complete = all(cumulative.get(item.pk, Decimal('0.00')) >= item.quantity for item in po_items)
    po.status = PurchaseOrder.STATUS_RECEIVED if complete else PurchaseOrder.STATUS_PARTIAL
    po.received_by = user
    po.received_at = timezone.now()
    po.save(update_fields=['status', 'received_by', 'received_at', 'updated_at'])
    accepted_value = sum(
        (accepted * po_item.unit_price for po_item, accepted, *_ in normalized),
        Decimal('0.00'),
    )
    if accepted_value > 0:
        from apps.finance.ledger_services import post_rule_event
        from apps.finance.models import JournalEntry, PostingRule

        post_rule_event(
            company=user.company,
            user=user,
            event_type=PostingRule.EVENT_GRN_RECEIPT,
            entry_date=receipt_date,
            source_type=JournalEntry.SOURCE_GRN,
            source_object_id=grn.pk,
            amount=accepted_value,
            description=f'{"Site" if po.delivery_destination == PurchaseOrder.DELIVERY_SITE else "Warehouse"} receipt {grn.number}',
            source_reference=grn.number,
            project=po.project,
            supplier=po.supplier,
        )
    return po, grn


def notify_pr_submitted(purchase_request):
    project_name = purchase_request.project.name if purchase_request.project else 'No project assigned'
    requester = purchase_request.requested_by.get_full_name() or purchase_request.requested_by.username
    message = (
        f'{purchase_request.number} was submitted for {project_name} by {requester}. '
        'Please review it for approval.'
    )
    recipients = list(get_company_users_by_roles(
        purchase_request.company,
        [User.ROLE_ADMIN],
    ))
    if purchase_request.project and purchase_request.project.manager:
        recipients.append(purchase_request.project.manager)
    notify_users(
        recipients,
        Notification.TYPE_PR_SUBMITTED,
        Notification.LEVEL_INFO,
        f'New PR submitted: {purchase_request.number}',
        message,
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_pr_approved(purchase_request):
    project_name = purchase_request.project.name if purchase_request.project else 'No project assigned'
    message = f'{purchase_request.number} for {project_name} has been approved and is ready for purchase order creation.'
    recipients = list(
        get_company_users_by_roles(
            purchase_request.company,
            [User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN],
        )
    )
    if purchase_request.requested_by:
        recipients.append(purchase_request.requested_by)
    notify_users(
        recipients,
        Notification.TYPE_PR_APPROVED,
        Notification.LEVEL_SUCCESS,
        f'PR approved: {purchase_request.number}',
        message,
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_pr_rejected(purchase_request):
    if not purchase_request.requested_by:
        return
    reason = purchase_request.rejection_reason or 'No rejection reason was provided.'
    message = f'{purchase_request.number} was rejected. Reason: {reason}'
    notify_users(
        [purchase_request.requested_by],
        Notification.TYPE_PR_REJECTED,
        Notification.LEVEL_DANGER,
        f'PR rejected: {purchase_request.number}',
        message,
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_pr_returned_for_correction(purchase_request):
    if not purchase_request.requested_by:
        return
    reason = purchase_request.technical_return_reason or 'Please review and correct the request.'
    notify_users(
        [purchase_request.requested_by],
        Notification.TYPE_SYSTEM,
        Notification.LEVEL_WARNING,
        f'PR returned for correction: {purchase_request.number}',
        f'{purchase_request.number} was returned by the project manager. Reason: {reason}',
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_pr_stock_issued(purchase_request):
    project_name = purchase_request.project.name if purchase_request.project else 'No project assigned'
    message = f'{purchase_request.number} for {project_name} has been fulfilled by warehouse and stock has been issued.'
    recipients = list(
        get_company_users_by_roles(
            purchase_request.company,
            [User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN],
        )
    )
    if purchase_request.requested_by:
        recipients.append(purchase_request.requested_by)
    notify_users(
        recipients,
        Notification.TYPE_SYSTEM,
        Notification.LEVEL_SUCCESS,
        f'Stock issued: {purchase_request.number}',
        message,
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_pr_stock_issue_requested(purchase_request, requested_by):
    project_name = purchase_request.project.name if purchase_request.project else 'No project assigned'
    requester = requested_by.get_full_name() or requested_by.username
    message = (
        f'{purchase_request.number} for {project_name} was accepted for warehouse stock issue by {requester}. '
        'Please confirm the materials have left the warehouse before recording stock OUT.'
    )
    recipients = get_company_users_by_roles(
        purchase_request.company,
        [
            User.ROLE_STOREKEEPER,
            User.ROLE_FINANCE_OFFICER,
            User.ROLE_FINANCE_MANAGER,
            User.ROLE_ADMIN,
        ],
    )
    notify_users(
        recipients,
        Notification.TYPE_SYSTEM,
        Notification.LEVEL_WARNING,
        f'Stock issue requested: {purchase_request.number}',
        message,
        f'/api/purchase-requests/{purchase_request.pk}/',
    )


def notify_po_created_from_pr(purchase_order, creator):
    project_name = purchase_order.project.name if purchase_order.project else 'No project assigned'
    supplier = purchase_order.supplier_name or 'No supplier specified'
    pr_number = purchase_order.purchase_request.number if purchase_order.purchase_request else 'the linked PR'
    message = (
        f'{purchase_order.number} was created from {pr_number}. '
        f'Supplier: {supplier}. Project: {project_name}.'
    )
    recipients = list(get_company_users_by_roles(
        purchase_order.company,
        [User.ROLE_ADMIN, User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER],
    ))
    recipients.append(creator)
    if purchase_order.purchase_request and purchase_order.purchase_request.requested_by:
        recipients.append(purchase_order.purchase_request.requested_by)
    # Every PO requires a Storekeeper GRN.  This includes direct-to-site
    # deliveries: Procurement manages dispatch, while physical receipt remains
    # independent from the buyer and requester.
    recipients.extend(
        get_company_users_by_roles(purchase_order.company, [User.ROLE_STOREKEEPER])
    )
    if purchase_order.delivery_destination == PurchaseOrder.DELIVERY_SITE and purchase_order.project:
        recipients.extend(purchase_order.project.site_engineers.filter(is_active=True))
    notify_users(
        recipients,
        Notification.TYPE_PO_CREATED,
        Notification.LEVEL_SUCCESS,
        f'PO created: {purchase_order.number}',
        message,
        f'/procurement/purchase-orders?search={purchase_order.number}',
    )


def notify_po_approved(purchase_order):
    """Tell Finance when Procurement has released a PO for fulfilment."""
    project_name = purchase_order.project.name if purchase_order.project else 'No project assigned'
    supplier = purchase_order.supplier_name or 'No supplier specified'
    recipients = get_company_users_by_roles(
        purchase_order.company,
        [User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER],
    )
    notify_users(
        recipients,
        Notification.TYPE_SYSTEM,
        Notification.LEVEL_INFO,
        f'PO approved: {purchase_order.number}',
        f'{purchase_order.number} is approved for fulfilment. Supplier: {supplier}. Project: {project_name}.',
        f'/procurement/purchase-orders?search={purchase_order.number}',
    )


def notify_po_dispatch_confirmed(purchase_order):
    project_name = purchase_order.project.name if purchase_order.project else 'No project assigned'
    supplier = purchase_order.supplier_name or 'No supplier specified'
    message = (
        f'{purchase_order.number} dispatch has been confirmed by procurement. '
        f'Supplier: {supplier}. Project: {project_name}. Please confirm physical receipt on site.'
    )
    recipients = list(get_company_users_by_roles(purchase_order.company, [User.ROLE_ADMIN]))
    recipients.extend(get_company_users_by_roles(purchase_order.company, [User.ROLE_STOREKEEPER]))
    if purchase_order.project:
        recipients.extend(purchase_order.project.site_engineers.filter(is_active=True))
    if purchase_order.purchase_request and purchase_order.purchase_request.requested_by:
        recipients.append(purchase_order.purchase_request.requested_by)
    notify_users(
        recipients,
        Notification.TYPE_SYSTEM,
        Notification.LEVEL_INFO,
        f'Dispatch confirmed: {purchase_order.number}',
        message,
        f'/api/purchase-orders/{purchase_order.pk}/',
    )


def notify_po_received(purchase_order):
    project_name = purchase_order.project.name if purchase_order.project else 'No project assigned'
    supplier = purchase_order.supplier_name or 'No supplier specified'
    destination = purchase_order.get_delivery_destination_display()
    message = (
        f'{purchase_order.number} has been marked as received. '
        f'Supplier: {supplier}. Project: {project_name}. Destination: {destination}. '
        f'Physical GRN recorded by {purchase_order.received_by.get_full_name() or purchase_order.received_by.username if purchase_order.received_by_id else "Storekeeper"}.'
    )
    recipients = get_company_users_by_roles(
        purchase_order.company,
        [
            User.ROLE_STOREKEEPER,
            User.ROLE_PROJECT_MANAGER,
            User.ROLE_PROCUREMENT_OFFICER,
            User.ROLE_ADMIN,
        ],
    )
    notify_users(
        recipients,
        Notification.TYPE_PO_RECEIVED,
        Notification.LEVEL_INFO,
        f'PO received: {purchase_order.number}',
        message,
        f'/api/purchase-orders/{purchase_order.pk}/',
    )
