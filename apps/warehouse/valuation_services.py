from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.finance.configuration_services import record_finance_audit_event
from apps.finance.models import FinanceSettings
from apps.materials.models import Material
from apps.projects.models import Project

from .models import SiteTransfer, StockMovement, Warehouse


ZERO = Decimal('0.00')
RATE_ZERO = Decimal('0.000000')
MONEY_QUANTUM = Decimal('0.01')
RATE_QUANTUM = Decimal('0.000001')
WAREHOUSE_WRITE_ROLES = {User.ROLE_STOREKEEPER, User.ROLE_ADMIN}
VALUATION_APPROVAL_ROLES = {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}


def _decimal(value, field, *, allow_zero=False):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({field: ['Enter a valid decimal value.']}) from exc
    if result < 0 or (result == 0 and not allow_zero):
        qualifier = 'zero or greater' if allow_zero else 'greater than zero'
        raise ValidationError({field: [f'Value must be {qualifier}.']})
    return result


def money(value):
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def rate(value):
    return Decimal(value).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)


def _require_role(user, roles):
    if not user or not user.is_authenticated or user.role not in roles:
        raise ValidationError({'non_field_errors': ['You are not authorized to perform this inventory action.']})


def get_default_warehouse(company):
    warehouse = Warehouse.objects.filter(company=company, is_default=True).first()
    if warehouse:
        return warehouse
    warehouse, _ = Warehouse.objects.get_or_create(
        company=company,
        code='MAIN',
        defaults={'name': 'Main Warehouse', 'is_default': True},
    )
    if not warehouse.is_default:
        warehouse.is_default = True
        warehouse.save(update_fields=['is_default', 'updated_at'])
    return warehouse


def get_project_site_store(project):
    """Return the controlled inventory location for a project's physical site."""
    if not project or not project.pk:
        raise ValidationError({'project': ['A project is required for a site store.']})
    store, _ = Warehouse.objects.get_or_create(
        company=project.company,
        project=project,
        defaults={
            'name': f'{project.name} Site Store',
            'code': f'SITE-{project.code}'[:30],
            'location': project.location,
            'is_default': False,
            'is_active': True,
        },
    )
    return store


def valuation_state(*, company, material, warehouse):
    totals = StockMovement.objects.filter(
        company=company, material=material, warehouse=warehouse,
    ).aggregate(
        quantity=Coalesce(Sum('quantity_effect'), ZERO),
        value=Coalesce(Sum('value_effect'), ZERO),
    )
    quantity = totals['quantity'] or ZERO
    value = money(totals['value'] or ZERO)
    average_rate = RATE_ZERO if quantity == 0 else rate(value / quantity)
    return {'quantity': quantity, 'value': value, 'average_rate': average_rate}


def available_for_project_issue(*, company, material, warehouse, project):
    """Return stock available to a project without consuming another project's PO reservation.

    A project PO received into the main warehouse remains reserved to that
    project's custody until the Storekeeper dispatches it.  Reservations are
    derived from immutable receipt movements, so they cannot be bypassed by a
    different PR simply because the goods share a material code.
    """
    total = valuation_state(company=company, material=material, warehouse=warehouse)['quantity']
    reserved_by_project = {}
    dispatched_by_project = {}
    movements = StockMovement.objects.filter(
        company=company, material=material, warehouse=warehouse, project__isnull=False,
    ).select_related('purchase_order')
    for movement in movements:
        po = movement.purchase_order
        if (
            movement.transaction_type == StockMovement.TRANSACTION_RECEIPT
            and po is not None
            and po.delivery_destination == po.DELIVERY_WAREHOUSE
            and po.purchase_request_id
        ):
            reserved_by_project[movement.project_id] = reserved_by_project.get(movement.project_id, ZERO) + movement.quantity
        elif movement.movement_type == StockMovement.MOVEMENT_OUT:
            dispatched_by_project[movement.project_id] = dispatched_by_project.get(movement.project_id, ZERO) + movement.quantity
    reserved_for_other_projects = sum(
        (max(quantity - dispatched_by_project.get(project_id, ZERO), ZERO)
         for project_id, quantity in reserved_by_project.items() if project_id != project.pk),
        ZERO,
    )
    return max(total - reserved_for_other_projects, ZERO)


def _negative_stock_allowed(company):
    policy = FinanceSettings.objects.filter(company=company).values_list(
        'negative_stock_policy', flat=True,
    ).first()
    return policy in {
        FinanceSettings.NEGATIVE_STOCK_WARN,
        FinanceSettings.NEGATIVE_STOCK_ALLOW,
    }


def _resolve_context(*, company, material, warehouse=None):
    material_id = getattr(material, 'pk', material)
    locked_material = Material.objects.select_for_update().filter(
        company=company, pk=material_id,
    ).first()
    if locked_material is None:
        raise ValidationError({'material': ['Material must belong to your company.']})
    if warehouse is None:
        warehouse = get_default_warehouse(company)
    warehouse_id = getattr(warehouse, 'pk', warehouse)
    locked_warehouse = Warehouse.objects.select_for_update().filter(
        company=company, pk=warehouse_id, is_active=True,
    ).first()
    if locked_warehouse is None:
        raise ValidationError({'warehouse': ['Warehouse must be active and belong to your company.']})
    return locked_material, locked_warehouse


def _persist(movement):
    movement._valuation_prepared = True
    try:
        movement.save()
    except DjangoValidationError as exc:
        detail = getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}
        raise ValidationError(detail) from exc
    return movement


def _record_entry(
    *, company, material, warehouse, quantity, receipt_unit_cost, transaction_type,
    source, user, movement_type=StockMovement.MOVEMENT_IN, **values,
):
    quantity = _decimal(quantity, 'quantity')
    receipt_unit_cost = _decimal(receipt_unit_cost, 'unit_cost', allow_zero=True)
    state = valuation_state(company=company, material=material, warehouse=warehouse)
    receipt_value = money(quantity * receipt_unit_cost)
    new_quantity = state['quantity'] + quantity
    new_value = money(state['value'] + receipt_value)
    new_average = RATE_ZERO if new_quantity == 0 else rate(new_value / new_quantity)
    movement = StockMovement(
        company=company,
        material=material,
        warehouse=warehouse,
        movement_type=movement_type,
        source=source,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=money(receipt_unit_cost),
        unit_cost=rate(receipt_unit_cost),
        valuation_rate=new_average,
        total_cost=receipt_value,
        quantity_effect=quantity,
        value_effect=receipt_value,
        created_by=user,
        **values,
    )
    return _persist(movement)


def _record_exit(
    *, company, material, warehouse, quantity, transaction_type, source, user,
    issue_rate=None, movement_type=StockMovement.MOVEMENT_OUT, **values,
):
    quantity = _decimal(quantity, 'quantity')
    state = valuation_state(company=company, material=material, warehouse=warehouse)
    if quantity > state['quantity'] and not _negative_stock_allowed(company):
        raise ValidationError({
            'quantity': [f'Insufficient stock. Available stock is {state["quantity"]}.'],
        })
    applied_rate = state['average_rate'] if issue_rate is None else rate(issue_rate)
    issue_value = money(quantity * applied_rate)
    movement = StockMovement(
        company=company,
        material=material,
        warehouse=warehouse,
        movement_type=movement_type,
        source=source,
        transaction_type=transaction_type,
        quantity=quantity,
        unit_price=money(applied_rate),
        unit_cost=applied_rate,
        valuation_rate=applied_rate,
        total_cost=issue_value,
        quantity_effect=-quantity,
        value_effect=-issue_value,
        created_by=user,
        **values,
    )
    return _persist(movement)


def _audit(movement, action, user, metadata=None):
    if user is None:
        return
    record_finance_audit_event(
        company=movement.company,
        actor=user,
        action=action,
        object_type='StockMovement',
        object_id=movement.pk,
        message=movement.authorization_reason or movement.notes,
        metadata={
            'material': movement.material_id,
            'warehouse': movement.warehouse_id,
            'quantity': movement.quantity,
            'unit_cost': movement.unit_cost,
            'valuation_rate': movement.valuation_rate,
            'total_cost': movement.total_cost,
            **(metadata or {}),
        },
    )
    from apps.finance.ledger_services import post_inventory_movement

    post_inventory_movement(movement=movement, user=user)


@transaction.atomic
def record_opening_balance(*, user, material, warehouse=None, quantity, unit_cost, date, reason):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    material, warehouse = _resolve_context(
        company=user.company, material=material, warehouse=warehouse,
    )
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    if StockMovement.objects.filter(
        company=user.company, material=material, warehouse=warehouse,
    ).exists():
        raise ValidationError({'material': ['Opening balance requires an empty material/warehouse ledger.']})
    movement = _record_entry(
        company=user.company, material=material, warehouse=warehouse,
        quantity=quantity, receipt_unit_cost=unit_cost,
        transaction_type=StockMovement.TRANSACTION_OPENING,
        source=StockMovement.SOURCE_INTERNAL, user=user, date=date,
        notes=reason.strip(), authorization_reason=reason.strip(), authorized_by=user,
    )
    _audit(movement, 'inventory.opening_balance.recorded', user)
    return movement


@transaction.atomic
def receive_valued_stock(*, user, goods_received_note_item, warehouse=None, allow_site_receiver=False):
    from apps.procurement.models import GoodsReceivedNote, GoodsReceivedNoteItem

    _require_role(
        user,
        WAREHOUSE_WRITE_ROLES | ({User.ROLE_SITE_ENGINEER} if allow_site_receiver else set()),
    )
    grn_item_id = getattr(goods_received_note_item, 'pk', goods_received_note_item)
    # Lock only the GRN item row.  PostgreSQL rejects FOR UPDATE queries that
    # include an outer join to a nullable related table; the related records
    # are loaded separately below as needed.
    grn_item = GoodsReceivedNoteItem.objects.select_for_update().filter(
        pk=grn_item_id, company=user.company,
        goods_received_note__status=GoodsReceivedNote.STATUS_ACCEPTED,
    ).first()
    if grn_item is None:
        raise ValidationError({'goods_received_note_item': ['Accepted GRN item not found.']})
    if grn_item.accepted_quantity <= 0:
        raise ValidationError({'goods_received_note_item': ['GRN item has no accepted quantity.']})
    if grn_item.goods_received_note.purchase_order.status not in {
        grn_item.goods_received_note.purchase_order.STATUS_ORDERED,
        # Direct-to-site POs are released for receipt through Procurement's
        # dispatch confirmation.  The Storekeeper still owns the GRN, but the
        # valuation guard must recognize this approved delivery state.
        grn_item.goods_received_note.purchase_order.STATUS_DISPATCH_CONFIRMED,
        grn_item.goods_received_note.purchase_order.STATUS_PARTIAL,
        grn_item.goods_received_note.purchase_order.STATUS_RECEIVED,
    }:
        raise ValidationError({'goods_received_note_item': ['GRN cost is not from an approved purchase order.']})
    if StockMovement.objects.filter(goods_received_note_item=grn_item).exists():
        raise ValidationError({'goods_received_note_item': ['This accepted GRN quantity is already valued.']})
    material, warehouse = _resolve_context(
        company=user.company, material=grn_item.purchase_order_item.material, warehouse=warehouse,
    )
    po = grn_item.goods_received_note.purchase_order
    movement = _record_entry(
        company=user.company, material=material, warehouse=warehouse,
        quantity=grn_item.accepted_quantity,
        receipt_unit_cost=grn_item.purchase_order_item.unit_price,
        transaction_type=StockMovement.TRANSACTION_RECEIPT,
        source=StockMovement.SOURCE_SUPPLIER, user=user,
        date=grn_item.goods_received_note.receipt_date,
        notes=f'Received into {"project site store" if po.delivery_destination == po.DELIVERY_SITE else "warehouse"} via {grn_item.goods_received_note.number}',
        purchase_order=po, purchase_order_item=grn_item.purchase_order_item,
        goods_received_note_item=grn_item, project=po.project,
    )
    _audit(movement, 'inventory.valued_stock.received', user, {'grn_item': grn_item.pk})
    return movement


@transaction.atomic
def issue_stock_to_project(
    *, user, material, project, warehouse=None, quantity, date, reason,
    purchase_request=None, purchase_request_item=None, work_order=None, work_order_site=None,
):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    if purchase_request is None:
        raise ValidationError({
            'purchase_request': ['An approved stock issue request is required.'],
        })
    from apps.procurement.models import PurchaseRequest, PurchaseRequestItem

    purchase_request_id = getattr(purchase_request, 'pk', purchase_request)
    purchase_request = PurchaseRequest.objects.select_for_update().filter(
        pk=purchase_request_id,
        company=user.company,
        status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
    ).first()
    if purchase_request is None:
        raise ValidationError({
            'purchase_request': ['The request must be approved and awaiting warehouse stock issue.'],
        })
    material, warehouse = _resolve_context(
        company=user.company, material=material, warehouse=warehouse,
    )
    project_id = getattr(project, 'pk', project)
    project = Project.objects.select_for_update().filter(company=user.company, pk=project_id).first()
    if project is None:
        raise ValidationError({'project': ['Project must belong to your company.']})
    if purchase_request.project_id != project.pk:
        raise ValidationError({'project': ['Project must match the approved purchase request.']})
    if work_order is not None:
        from apps.workorders.models import WorkOrder
        work_order = WorkOrder.objects.select_for_update().filter(
            pk=getattr(work_order, 'pk', work_order), company=user.company,
        ).first()
        if work_order is None or purchase_request.work_order_id != work_order.pk:
            raise ValidationError({'work_order': ['Work order must match the linked material request and project.']})
    if work_order_site is not None:
        from apps.workorders.models import WorkOrderSite
        work_order_site = WorkOrderSite.objects.select_for_update().filter(
            pk=getattr(work_order_site, 'pk', work_order_site), work_order=work_order, project=project,
        ).first()
        if work_order_site is None or purchase_request.work_order_site_id != work_order_site.pk:
            raise ValidationError({'work_order_site': ['Site package must match the linked material request and project.']})
    if purchase_request_item is None:
        purchase_request_item = PurchaseRequestItem.objects.select_for_update().filter(
            purchase_request=purchase_request,
            material=material,
        ).first()
    else:
        item_id = getattr(purchase_request_item, 'pk', purchase_request_item)
        purchase_request_item = PurchaseRequestItem.objects.select_for_update().filter(
            pk=item_id,
            purchase_request=purchase_request,
            material=material,
        ).first()
    if purchase_request_item is None:
        raise ValidationError({'material': ['Material is not on the approved purchase request.']})
    if Decimal(quantity) > purchase_request_item.quantity:
        raise ValidationError({'quantity': ['Quantity cannot exceed the approved request quantity.']})
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    movement = _record_exit(
        company=user.company, material=material, warehouse=warehouse,
        quantity=quantity, transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
        source=StockMovement.SOURCE_SITE, user=user, project=project, date=date,
        notes=reason.strip(), purchase_request=purchase_request,
        purchase_request_item=purchase_request_item, work_order=work_order, work_order_site=work_order_site,
    )
    from apps.finance.budget_services import record_stock_movement_actual
    record_stock_movement_actual(movement=movement, user=user)
    _audit(movement, 'inventory.stock.issued_to_project', user)
    return movement


@transaction.atomic
def return_stock_from_project(
    *, user, original_issue, warehouse=None, quantity, date, reason,
):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    issue_id = getattr(original_issue, 'pk', original_issue)
    issue = StockMovement.objects.select_for_update().filter(
        pk=issue_id, company=user.company,
        transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
    ).select_related('material', 'warehouse', 'project').first()
    if issue is None:
        raise ValidationError({'original_issue': ['Project issue movement not found.']})
    quantity = _decimal(quantity, 'quantity')
    returned = issue.return_movements.filter(
        transaction_type=StockMovement.TRANSACTION_PROJECT_RETURN,
    ).aggregate(total=Coalesce(Sum('quantity'), ZERO))['total'] or ZERO
    if quantity > issue.quantity - returned:
        raise ValidationError({'quantity': [f'Only {issue.quantity - returned} remains returnable.']})
    material, warehouse = _resolve_context(
        company=user.company, material=issue.material, warehouse=warehouse or issue.warehouse,
    )
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    movement = _record_entry(
        company=user.company, material=material, warehouse=warehouse,
        quantity=quantity, receipt_unit_cost=issue.valuation_rate,
        transaction_type=StockMovement.TRANSACTION_PROJECT_RETURN,
        source=StockMovement.SOURCE_SITE, user=user,
        movement_type=StockMovement.MOVEMENT_IN, project=issue.project, date=date,
        notes=reason.strip(), original_movement=issue,
    )
    from apps.finance.budget_services import record_stock_movement_actual
    record_stock_movement_actual(movement=movement, user=user, reversal=True)
    _audit(movement, 'inventory.stock.returned_from_project', user, {'original_issue': issue.pk})
    return movement


@transaction.atomic
def dispatch_to_site(*, user, material, project, warehouse=None, quantity, date, reason):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    project = Project.objects.select_for_update().filter(pk=getattr(project, 'pk', project), company=user.company, is_active=True).first()
    if project is None:
        raise ValidationError({'project': ['Select an active company project.']})
    material, warehouse = _resolve_context(company=user.company, material=material, warehouse=warehouse)
    available = available_for_project_issue(
        company=user.company, material=material, warehouse=warehouse, project=project,
    )
    if Decimal(str(quantity)) > available:
        raise ValidationError({'quantity': ['This quantity is reserved for another project or is not available in the selected warehouse.']})
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A dispatch reason is required.']})
    site_store = get_project_site_store(project)
    outbound = _record_exit(
        company=user.company, material=material, warehouse=warehouse, quantity=quantity,
        transaction_type=StockMovement.TRANSACTION_SITE_TRANSFER_OUT, source=StockMovement.SOURCE_INTERNAL,
        user=user, project=project, date=date, notes=reason.strip(),
    )
    transfer = SiteTransfer.objects.create(
        company=user.company, project=project, material=material, source_warehouse=warehouse,
        destination_store=site_store, quantity=outbound.quantity, reason=reason.strip(),
        dispatched_by=user, outbound_movement=outbound,
    )
    _audit(outbound, 'inventory.site_transfer.dispatched', user, {'site_transfer': transfer.pk, 'destination_store': site_store.pk})
    return transfer


@transaction.atomic
def acknowledge_site_transfer(*, user, site_transfer):
    transfer = SiteTransfer.objects.select_for_update().select_related(
        'project', 'material', 'destination_store', 'outbound_movement',
    ).filter(pk=getattr(site_transfer, 'pk', site_transfer), company=user.company).first()
    if transfer is None or transfer.status != SiteTransfer.STATUS_DISPATCHED:
        raise ValidationError({'site_transfer': ['This site transfer is not awaiting acknowledgement.']})
    if user.role not in {User.ROLE_SITE_ENGINEER, User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN}:
        raise ValidationError({'non_field_errors': ['Only the assigned site team can acknowledge a site transfer.']})
    if user.role == User.ROLE_SITE_ENGINEER and not transfer.project.site_engineers.filter(pk=user.pk).exists():
        raise ValidationError({'non_field_errors': ['You are not assigned to this project.']})
    inbound = _record_entry(
        company=user.company, material=transfer.material, warehouse=transfer.destination_store,
        quantity=transfer.quantity, receipt_unit_cost=transfer.outbound_movement.valuation_rate,
        transaction_type=StockMovement.TRANSACTION_SITE_TRANSFER_IN, source=StockMovement.SOURCE_INTERNAL,
        user=user, project=transfer.project, date=timezone.localdate(),
        notes=f'Acknowledged site transfer #{transfer.pk}: {transfer.reason}', original_movement=transfer.outbound_movement,
    )
    transfer.status = SiteTransfer.STATUS_ACKNOWLEDGED
    transfer.acknowledged_by = user
    transfer.acknowledged_at = timezone.now()
    transfer.inbound_movement = inbound
    transfer.save(update_fields=['status', 'acknowledged_by', 'acknowledged_at', 'inbound_movement'])
    _audit(inbound, 'inventory.site_transfer.acknowledged', user, {'site_transfer': transfer.pk})
    return transfer


@transaction.atomic
def consume_site_stock(*, user, material, project, quantity, date, reason):
    _require_role(user, {User.ROLE_SITE_ENGINEER, User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN})
    project = Project.objects.select_for_update().filter(pk=getattr(project, 'pk', project), company=user.company, is_active=True).first()
    if project is None:
        raise ValidationError({'project': ['Select an active company project.']})
    if user.role == User.ROLE_SITE_ENGINEER and not project.site_engineers.filter(pk=user.pk).exists():
        raise ValidationError({'project': ['You are not assigned to this project.']})
    material, site_store = _resolve_context(company=user.company, material=material, warehouse=get_project_site_store(project))
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['State where or why the material was consumed.']})
    movement = _record_exit(company=user.company, material=material, warehouse=site_store, quantity=quantity,
        transaction_type=StockMovement.TRANSACTION_SITE_CONSUMPTION, source=StockMovement.SOURCE_SITE,
        user=user, project=project, date=date, notes=reason.strip())
    _audit(movement, 'inventory.site_stock.consumed', user)
    return movement


@transaction.atomic
def return_site_stock_to_warehouse(*, user, material, project, warehouse, quantity, date, reason):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    project = Project.objects.select_for_update().filter(pk=getattr(project, 'pk', project), company=user.company).first()
    if project is None:
        raise ValidationError({'project': ['Select a company project.']})
    material, site_store = _resolve_context(company=user.company, material=material, warehouse=get_project_site_store(project))
    _, destination = _resolve_context(company=user.company, material=material, warehouse=warehouse)
    if destination.pk == site_store.pk or not reason or not reason.strip():
        raise ValidationError({'reason': ['Choose a warehouse and provide a return reason.']})
    outbound = _record_exit(company=user.company, material=material, warehouse=site_store, quantity=quantity,
        transaction_type=StockMovement.TRANSACTION_SITE_RETURN_OUT, source=StockMovement.SOURCE_SITE, user=user,
        project=project, date=date, notes=reason.strip())
    inbound = _record_entry(company=user.company, material=material, warehouse=destination, quantity=quantity,
        receipt_unit_cost=outbound.valuation_rate, transaction_type=StockMovement.TRANSACTION_SITE_RETURN_IN,
        source=StockMovement.SOURCE_SITE, user=user, project=project, date=date, notes=reason.strip(), original_movement=outbound)
    _audit(inbound, 'inventory.site_stock.returned_to_warehouse', user, {'site_outbound_movement': outbound.pk})
    return inbound


@transaction.atomic
def return_stock_to_supplier(
    *, user, material, warehouse=None, quantity, date, reason, original_receipt=None,
):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    material, warehouse = _resolve_context(
        company=user.company, material=material, warehouse=warehouse,
    )
    receipt = None
    issue_rate = None
    # The application uses moving weighted-average valuation per warehouse.
    # Keep the original receipt only for traceability; a supplier return must
    # remove stock at the warehouse's current average rate, not the historical
    # receipt rate, unless lot/FIFO valuation is introduced explicitly.
    if original_receipt is not None:
        receipt_id = getattr(original_receipt, 'pk', original_receipt)
        receipt = StockMovement.objects.select_for_update().filter(
            pk=receipt_id, company=user.company, material=material,
            transaction_type=StockMovement.TRANSACTION_RECEIPT,
        ).first()
        if receipt is None:
            raise ValidationError({'original_receipt': ['Valued supplier receipt not found.']})
        returned = receipt.return_movements.filter(
            transaction_type=StockMovement.TRANSACTION_SUPPLIER_RETURN,
        ).aggregate(total=Coalesce(Sum('quantity'), ZERO))['total'] or ZERO
        requested_quantity = _decimal(quantity, 'quantity')
        if requested_quantity > receipt.quantity - returned:
            raise ValidationError({
                'quantity': [f'Only {receipt.quantity - returned} remains returnable to the supplier.'],
            })
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    movement = _record_exit(
        company=user.company, material=material, warehouse=warehouse,
        quantity=quantity, issue_rate=issue_rate,
        transaction_type=StockMovement.TRANSACTION_SUPPLIER_RETURN,
        source=StockMovement.SOURCE_SUPPLIER, user=user, date=date,
        notes=reason.strip(), original_movement=receipt,
        purchase_order=receipt.purchase_order if receipt else None,
        purchase_order_item=receipt.purchase_order_item if receipt else None,
    )
    _audit(movement, 'inventory.stock.returned_to_supplier', user)
    return movement


@transaction.atomic
def write_off_damaged_stock(*, user, material, warehouse=None, quantity, date, reason):
    _require_role(user, WAREHOUSE_WRITE_ROLES)
    material, warehouse = _resolve_context(
        company=user.company, material=material, warehouse=warehouse,
    )
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    movement = _record_exit(
        company=user.company, material=material, warehouse=warehouse,
        quantity=quantity, transaction_type=StockMovement.TRANSACTION_WRITE_OFF,
        source=StockMovement.SOURCE_ADJUSTMENT, user=user,
        movement_type=StockMovement.MOVEMENT_ADJUSTMENT_OUT,
        date=date, notes=reason.strip(), authorization_reason=reason.strip(), authorized_by=user,
    )
    _audit(movement, 'inventory.damaged_stock.written_off', user)
    return movement


@transaction.atomic
def adjust_valuation(*, user, material, warehouse=None, new_unit_cost, date, reason):
    _require_role(user, VALUATION_APPROVAL_ROLES)
    material, warehouse = _resolve_context(
        company=user.company, material=material, warehouse=warehouse,
    )
    if not reason or not reason.strip():
        raise ValidationError({'reason': ['A reason is required.']})
    new_unit_cost = _decimal(new_unit_cost, 'new_unit_cost', allow_zero=True)
    state = valuation_state(company=user.company, material=material, warehouse=warehouse)
    if state['quantity'] <= 0:
        raise ValidationError({'material': ['Valuation can only be adjusted when stock is positive.']})
    target_value = money(state['quantity'] * new_unit_cost)
    value_effect = money(target_value - state['value'])
    if value_effect == ZERO:
        raise ValidationError({'new_unit_cost': ['The new rate does not change the current valuation.']})
    movement = StockMovement(
        company=user.company, material=material, warehouse=warehouse,
        movement_type=(
            StockMovement.MOVEMENT_ADJUSTMENT_IN
            if value_effect > 0 else StockMovement.MOVEMENT_ADJUSTMENT_OUT
        ),
        source=StockMovement.SOURCE_ADJUSTMENT,
        transaction_type=StockMovement.TRANSACTION_VALUATION_ADJUSTMENT,
        quantity=ZERO, unit_price=money(new_unit_cost), unit_cost=rate(new_unit_cost),
        valuation_rate=rate(new_unit_cost), total_cost=abs(value_effect),
        quantity_effect=ZERO, value_effect=value_effect,
        date=date, notes=reason.strip(), authorization_reason=reason.strip(),
        authorized_by=user, created_by=user,
    )
    movement = _persist(movement)
    _audit(movement, 'inventory.valuation.adjusted', user, {
        'previous_rate': state['average_rate'], 'previous_value': state['value'],
        'new_value': target_value,
    })
    from apps.finance.notification_services import valuation_adjusted

    transaction.on_commit(lambda: valuation_adjusted(movement))
    return movement


@transaction.atomic
def apply_landed_cost_value(*, user, receipt_movement, amount, date, reason, reversal=False):
    """Apply an approved landed-cost value effect without changing stock quantity."""
    _require_role(user, VALUATION_APPROVAL_ROLES)
    receipt_id = getattr(receipt_movement, 'pk', receipt_movement)
    receipt = StockMovement.objects.select_for_update().select_related(
        'material', 'warehouse',
    ).filter(
        pk=receipt_id, company=user.company,
        transaction_type=StockMovement.TRANSACTION_RECEIPT,
        goods_received_note_item__isnull=False,
    ).first()
    if receipt is None:
        raise ValidationError({'receipt_movement': ['Valued GRN receipt movement not found.']})
    material, warehouse = _resolve_context(
        company=user.company, material=receipt.material, warehouse=receipt.warehouse,
    )
    amount = money(_decimal(amount, 'allocated_amount'))
    state = valuation_state(company=user.company, material=material, warehouse=warehouse)
    if state['quantity'] <= 0:
        raise ValidationError({
            'receipt_movement': ['Landed cost requires positive stock in the receipt warehouse.'],
        })
    value_effect = -amount if reversal else amount
    new_value = money(state['value'] + value_effect)
    if new_value < 0:
        raise ValidationError({'allocated_amount': ['Reversal would make inventory value negative.']})
    new_rate = rate(new_value / state['quantity'])
    movement = StockMovement(
        company=user.company, material=material, warehouse=warehouse,
        movement_type=(
            StockMovement.MOVEMENT_ADJUSTMENT_OUT if reversal
            else StockMovement.MOVEMENT_ADJUSTMENT_IN
        ),
        source=StockMovement.SOURCE_ADJUSTMENT,
        transaction_type=(
            StockMovement.TRANSACTION_LANDED_COST_REVERSAL if reversal
            else StockMovement.TRANSACTION_LANDED_COST
        ),
        quantity=ZERO, unit_price=ZERO, unit_cost=RATE_ZERO,
        valuation_rate=new_rate, total_cost=amount,
        quantity_effect=ZERO, value_effect=value_effect,
        date=date, notes=reason.strip(), authorization_reason=reason.strip(),
        authorized_by=user, created_by=user, original_movement=receipt,
    )
    return _persist(movement)


@transaction.atomic
def save_legacy_movement(instance, save_args=(), save_kwargs=None):
    """Value legacy creates while preserving the original public model contract."""
    if save_args or save_kwargs:
        unsupported = set((save_kwargs or {}).keys()) - {'force_insert', 'using'}
        if unsupported:
            raise ValidationError({'non_field_errors': ['Legacy movement creation does not support update options.']})
    company = instance.company
    material, warehouse = _resolve_context(
        company=company, material=instance.material, warehouse=instance.warehouse_id or None,
    )
    common = {
        'date': instance.date,
        'notes': instance.notes,
        'authorization_reason': instance.authorization_reason,
    }
    for field in (
        'project', 'purchase_order', 'purchase_order_item', 'purchase_request',
        'purchase_request_item', 'goods_received_note_item', 'original_movement', 'authorized_by',
    ):
        if getattr(instance, f'{field}_id', None):
            common[field] = getattr(instance, field)
    incoming = instance.movement_type in {
        StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN,
    }
    transaction_type = instance.transaction_type
    if transaction_type == StockMovement.TRANSACTION_LEGACY:
        if instance.movement_type in {
            StockMovement.MOVEMENT_ADJUSTMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_OUT,
        }:
            transaction_type = StockMovement.TRANSACTION_QUANTITY_ADJUSTMENT
        elif incoming:
            transaction_type = StockMovement.TRANSACTION_RECEIPT
        elif instance.project_id:
            transaction_type = StockMovement.TRANSACTION_PROJECT_ISSUE
    if incoming:
        valued = _record_entry(
            company=company, material=material, warehouse=warehouse,
            quantity=instance.quantity, receipt_unit_cost=instance.unit_price,
            transaction_type=transaction_type, source=instance.source,
            user=instance.created_by, movement_type=instance.movement_type, **common,
        )
    else:
        valued = _record_exit(
            company=company, material=material, warehouse=warehouse,
            quantity=instance.quantity, transaction_type=transaction_type,
            source=instance.source, user=instance.created_by,
            movement_type=instance.movement_type, **common,
        )
    instance.__dict__.update(valued.__dict__)
    if instance.created_by_id:
        from apps.finance.ledger_services import post_inventory_movement

        post_inventory_movement(movement=valued, user=instance.created_by)
    return None
