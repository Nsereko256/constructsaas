"""Material-request stage timing derived from immutable workflow handoffs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

from apps.finance.models import BudgetApproval, FinanceAuditEvent, WorkflowConfirmation

from .models import PurchaseOrder, PurchaseRequest


@dataclass(frozen=True)
class StageDefinition:
    label: str
    owner: str
    target_hours: int


STAGES = {
    'manager_review': StageDefinition('Project Manager review', 'Project Manager', 24),
    'requester_correction': StageDefinition('Requester correction', 'Requester', 48),
    'procurement_decision': StageDefinition('Procurement fulfilment decision', 'Procurement', 24),
    'admin_stock_approval': StageDefinition('Admin stock approval', 'Admin', 8),
    'storekeeper_issue': StageDefinition('Warehouse stock issue', 'Storekeeper', 8),
    'finance_review': StageDefinition('Finance review', 'Finance', 24),
    'procurement_progress': StageDefinition('Procurement order progression', 'Procurement', 24),
    'supplier_delivery': StageDefinition('Supplier delivery', 'Supplier / Procurement', 48),
    'site_receipt': StageDefinition('Site receipt confirmation', 'Site Engineer', 8),
    'warehouse_receipt': StageDefinition('Warehouse receipt confirmation', 'Storekeeper', 8),
    'invoice_payment': StageDefinition('Invoice and payment follow-up', 'Finance', 48),
    'completed': StageDefinition('Completed', '—', 0),
    'rejected': StageDefinition('Rejected', '—', 0),
}


def _duration_display(seconds: int) -> str:
    seconds = max(0, int(seconds))
    minutes = seconds // 60
    if minutes < 1:
        return 'Less than 1 min'
    if minutes < 60:
        return f'{minutes} min'
    hours = minutes // 60
    remaining_minutes = minutes % 60
    if hours < 24:
        return f'{hours}h {remaining_minutes}m' if remaining_minutes else f'{hours}h'
    days = hours // 24
    remaining_hours = hours % 24
    return f'{days}d {remaining_hours}h' if remaining_hours else f'{days}d'


def _stage_payload(
    *, key: str, started_at: datetime, ended_at: datetime | None = None,
    status: str = 'CURRENT', version: int | None = None,
) -> dict:
    definition = STAGES[key]
    finish = ended_at or timezone.now()
    duration_seconds = max(0, int((finish - started_at).total_seconds()))
    target_seconds = definition.target_hours * 3600
    is_current = ended_at is None
    exceeded_target = bool(target_seconds and duration_seconds > target_seconds)
    return {
        'key': key,
        'label': definition.label,
        'owner': definition.owner,
        'status': status,
        'version': version,
        'started_at': started_at,
        'ended_at': ended_at,
        'duration_seconds': duration_seconds,
        'duration_display': _duration_display(duration_seconds),
        'target_hours': definition.target_hours,
        'is_current': is_current,
        'is_stalled': is_current and exceeded_target,
        'exceeded_target': exceeded_target,
    }


def _task_stage(task: WorkflowConfirmation) -> str:
    if task.document_type == WorkflowConfirmation.DOCUMENT_PURCHASE_REQUEST:
        return 'manager_review' if task.stage == WorkflowConfirmation.STAGE_TECHNICAL else 'finance_review'
    if task.document_type == WorkflowConfirmation.DOCUMENT_STOCK_ISSUE:
        return 'admin_stock_approval' if task.stage == WorkflowConfirmation.STAGE_STOCK else 'storekeeper_issue'
    if task.document_type == WorkflowConfirmation.DOCUMENT_PURCHASE_ORDER:
        return 'finance_review'
    if task.document_type == WorkflowConfirmation.DOCUMENT_PO_DISPATCH:
        return 'supplier_delivery'
    if task.document_type == WorkflowConfirmation.DOCUMENT_SITE_RECEIPT:
        return 'site_receipt'
    if task.document_type == WorkflowConfirmation.DOCUMENT_WAREHOUSE_RECEIPT:
        return 'warehouse_receipt'
    return 'procurement_progress'


def _task_status(task: WorkflowConfirmation) -> str:
    return {
        WorkflowConfirmation.STATUS_PENDING: 'CURRENT',
        WorkflowConfirmation.STATUS_CONFIRMED: 'COMPLETED',
        WorkflowConfirmation.STATUS_RETURNED: 'RETURNED',
        WorkflowConfirmation.STATUS_CANCELLED: 'CANCELLED',
    }.get(task.status, task.status)


def material_request_stage_tracking(material_request: PurchaseRequest) -> dict:
    """Return an auditable timeline and the request's current follow-up age."""
    orders = list(material_request.purchase_orders.all())
    order_ids = [str(order.pk) for order in orders]
    request_id = str(material_request.pk)
    tasks = list(
        WorkflowConfirmation.objects.filter(company=material_request.company).filter(
            # Generic workflow references are strings; keep request and PO ids
            # scoped by document type to avoid collisions.
            _workflow_query(request_id, order_ids)
        ).order_by('submitted_at', 'id')
    )

    history = [
        _stage_payload(
            key=_task_stage(task),
            started_at=task.submitted_at,
            ended_at=task.decided_at,
            status=_task_status(task),
            version=task.version,
        )
        for task in tasks
    ]
    history.extend(_legacy_stage_history(material_request, orders, history))
    history.sort(key=lambda entry: entry['started_at'])
    pending = [entry for entry in history if entry['is_current']]
    if pending:
        current = pending[-1]
    else:
        key, started_at = _inferred_current_stage(material_request, orders, tasks)
        current = _stage_payload(key=key, started_at=started_at) if key else None
        if current:
            history.append(current)

    return {
        'current_stage': current,
        'history': history,
        'total_age_seconds': max(0, int((timezone.now() - material_request.created_at).total_seconds())),
        'total_age_display': _duration_display((timezone.now() - material_request.created_at).total_seconds()),
    }


def _legacy_stage_history(material_request, orders, recorded_history):
    """Fill older records that predate WorkflowConfirmation from audited timestamps."""
    inferred = []
    recorded_keys = {entry['key'] for entry in recorded_history}
    events = list(FinanceAuditEvent.objects.filter(
        company=material_request.company,
        object_type='PurchaseRequest',
        object_id=str(material_request.pk),
    ).order_by('created_at', 'id'))

    if 'manager_review' not in recorded_keys and material_request.status != PurchaseRequest.STATUS_PENDING:
        manager_event = next((event for event in events if event.action in {
            'purchase_request.technical_approved',
            'purchase_request.returned_for_correction',
            'purchase_request.rejected',
            'warehouse_replenishment.technical_approved',
        }), None)
        if manager_event:
            inferred.append(_stage_payload(
                key='manager_review', started_at=material_request.created_at,
                ended_at=manager_event.created_at, status='COMPLETED',
            ))

    order = orders[-1] if orders else None
    if order and 'procurement_decision' not in recorded_keys:
        manager_end = next((
            entry['ended_at'] for entry in reversed(inferred + recorded_history)
            if entry['key'] == 'manager_review' and entry['ended_at']
        ), material_request.created_at)
        inferred.append(_stage_payload(
            key='procurement_decision', started_at=manager_end,
            ended_at=order.created_at, status='COMPLETED',
        ))

    if 'finance_review' not in recorded_keys:
        approval = BudgetApproval.objects.filter(
            company=material_request.company,
            purchase_request=material_request,
        ).first()
        if approval and approval.submitted_at:
            is_pending = approval.status in {BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD}
            inferred.append(_stage_payload(
                key='finance_review', started_at=approval.submitted_at,
                ended_at=None if is_pending else approval.reviewed_at,
                status='CURRENT' if is_pending else 'COMPLETED',
            ))

    if order and order.received_at and not {'site_receipt', 'warehouse_receipt'} & recorded_keys:
        key = 'site_receipt' if order.delivery_destination == PurchaseOrder.DELIVERY_SITE else 'warehouse_receipt'
        inferred.append(_stage_payload(
            key=key,
            started_at=order.dispatch_confirmed_at or order.created_at,
            ended_at=order.received_at,
            status='COMPLETED',
        ))

    if order:
        invoices = list(order.supplier_invoices.all())
        latest_invoice = max(invoices, key=lambda invoice: invoice.pk) if invoices else None
        if latest_invoice and latest_invoice.status == latest_invoice.STATUS_PAID:
            inferred.append(_stage_payload(
                key='invoice_payment', started_at=latest_invoice.created_at,
                ended_at=latest_invoice.updated_at, status='COMPLETED',
            ))
    return inferred


def _workflow_query(request_id: str, order_ids: list[str]):
    from django.db.models import Q

    query = Q(
        document_type__in=[
            WorkflowConfirmation.DOCUMENT_PURCHASE_REQUEST,
            WorkflowConfirmation.DOCUMENT_STOCK_ISSUE,
        ],
        object_id=request_id,
    )
    if order_ids:
        query |= Q(
            document_type__in=[
                WorkflowConfirmation.DOCUMENT_PURCHASE_ORDER,
                WorkflowConfirmation.DOCUMENT_PO_DISPATCH,
                WorkflowConfirmation.DOCUMENT_WAREHOUSE_RECEIPT,
                WorkflowConfirmation.DOCUMENT_SITE_RECEIPT,
            ],
            object_id__in=order_ids,
        )
    return query


def _inferred_current_stage(material_request, orders, tasks):
    last_decision = next((task.decided_at for task in reversed(tasks) if task.decided_at), None)
    stage_started = last_decision or material_request.updated_at or material_request.created_at
    if material_request.status == PurchaseRequest.STATUS_PENDING:
        return 'manager_review', material_request.created_at
    if material_request.status == PurchaseRequest.STATUS_RETURNED:
        return 'requester_correction', stage_started
    if material_request.status == PurchaseRequest.STATUS_APPROVED:
        return 'procurement_decision', stage_started
    if material_request.status == PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED:
        return 'storekeeper_issue', stage_started
    if material_request.status == PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED:
        return 'procurement_decision', material_request.updated_at
    if material_request.status == PurchaseRequest.STATUS_STOCK_ISSUED:
        return None, None
    if material_request.status == PurchaseRequest.STATUS_REJECTED:
        return None, None
    if material_request.status == PurchaseRequest.STATUS_PO_CREATED:
        order = orders[-1] if orders else None
        if order is None:
            return 'procurement_progress', material_request.updated_at
        if order.status in {PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING}:
            return 'procurement_progress', stage_started
        if order.status == PurchaseOrder.STATUS_ORDERED:
            return 'supplier_delivery', stage_started
        if order.status == PurchaseOrder.STATUS_DISPATCH_CONFIRMED:
            key = 'site_receipt' if order.delivery_destination == PurchaseOrder.DELIVERY_SITE else 'warehouse_receipt'
            return key, order.dispatch_confirmed_at or stage_started
        if order.status in {PurchaseOrder.STATUS_PARTIAL, PurchaseOrder.STATUS_RECEIVED}:
            invoices = list(order.supplier_invoices.all())
            latest_invoice = max(invoices, key=lambda invoice: invoice.pk) if invoices else None
            if latest_invoice and latest_invoice.status == latest_invoice.STATUS_PAID:
                return None, None
            return 'invoice_payment', order.received_at or order.updated_at
    return None, None
