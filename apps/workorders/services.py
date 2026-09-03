from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User
from apps.finance.configuration_services import record_finance_audit_event
from apps.notifications.helpers import send_notification
from apps.notifications.models import Notification
from .models import WorkOrder, WorkOrderAuditLog, WorkOrderTask

TRANSITIONS = {
    WorkOrder.STATUS_DRAFT: {WorkOrder.STATUS_SUBMITTED, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_SUBMITTED: {WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_REJECTED, WorkOrder.STATUS_ON_HOLD, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_APPROVED: {WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_ON_HOLD, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_ASSIGNED: {WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_ON_HOLD, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_IN_PROGRESS: {WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_ON_HOLD, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_COMPLETED: {WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_IN_PROGRESS},
    WorkOrder.STATUS_VERIFIED: {WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_IN_PROGRESS},
    WorkOrder.STATUS_ON_HOLD: {WorkOrder.STATUS_SUBMITTED, WorkOrder.STATUS_APPROVED, WorkOrder.STATUS_ASSIGNED, WorkOrder.STATUS_IN_PROGRESS, WorkOrder.STATUS_CANCELLED},
    WorkOrder.STATUS_REJECTED: {WorkOrder.STATUS_DRAFT, WorkOrder.STATUS_CANCELLED},
}


def generate_work_order_number(company):
    year = timezone.localdate().year
    prefix = f'WO-{year}-'
    latest = WorkOrder.objects.filter(company=company, number__startswith=prefix).order_by('-number').values_list('number', flat=True).first()
    sequence = int(latest.rsplit('-', 1)[-1]) + 1 if latest else 1
    return f'{prefix}{sequence:04d}'


def _notify(users, work_order, title, message, level=Notification.LEVEL_INFO):
    for user in {user for user in users if user and user.is_active and user.company_id == work_order.company_id}:
        send_notification(user, Notification.TYPE_SYSTEM, level, title, message, f'/work-orders/{work_order.pk}')


@transaction.atomic
def transition_work_order(*, work_order, actor, target_status, comments=''):
    work_order = WorkOrder.objects.select_for_update().get(pk=work_order.pk)
    if target_status not in TRANSITIONS.get(work_order.status, set()):
        raise ValidationError({'status': f'{work_order.get_status_display()} cannot move to {target_status.replace("_", " ").title()}.'})
    if target_status == WorkOrder.STATUS_CLOSED and work_order.site_packages.exclude(
        status__in=[WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED],
    ).exists():
        raise ValidationError({'status': 'Every site package must be verified, closed, or cancelled before the master work order can close.'})
    if target_status == WorkOrder.STATUS_IN_PROGRESS and work_order.assignment_status != WorkOrder.ASSIGNMENT_ACCEPTED:
        raise ValidationError({'assignment': 'The assigned internal owner must accept the work before it can start.'})
    if target_status == WorkOrder.STATUS_ASSIGNED and work_order.estimated_cost > 0 and not work_order.finance_reviewed_at:
        raise ValidationError({'finance_review': 'Finance must confirm budget availability before paid work can be assigned.'})
    if target_status == WorkOrder.STATUS_COMPLETED:
        active_sites = work_order.site_packages.exclude(status=WorkOrder.STATUS_CANCELLED)
        if active_sites.exists() and active_sites.exclude(status__in=[WorkOrder.STATUS_COMPLETED, WorkOrder.STATUS_VERIFIED, WorkOrder.STATUS_CLOSED]).exists():
            raise ValidationError({'status': 'Every active site package must be completed before the master work order can complete.'})
        if work_order.tasks.exclude(status=WorkOrderTask.STATUS_COMPLETED).exists():
            raise ValidationError({'status': 'Complete or cancel every master-level task before completing the work order.'})
    before = work_order.status
    work_order.status = target_status
    if target_status == WorkOrder.STATUS_APPROVED:
        work_order.approved_by = actor
    if target_status == WorkOrder.STATUS_VERIFIED:
        work_order.verified_by = actor
    if target_status == WorkOrder.STATUS_COMPLETED:
        work_order.actual_completion_date = timezone.localdate()
    if target_status == WorkOrder.STATUS_REJECTED:
        work_order.rejection_reason = comments
    if target_status == WorkOrder.STATUS_ON_HOLD:
        work_order.hold_reason = comments
    work_order.save()
    WorkOrderAuditLog.objects.create(work_order=work_order, actor=actor, action='status_changed', from_status=before, to_status=target_status, message=comments)
    record_finance_audit_event(company=work_order.company, actor=actor, action='work_order.status_changed', object_type='WorkOrder', object_id=work_order.pk, message=comments, metadata={'number': work_order.number, 'from': before, 'to': target_status})
    recipients = [work_order.requester, work_order.responsible_person]
    if work_order.project_id and work_order.project.manager_id:
        recipients.append(work_order.project.manager)
    _notify(recipients, work_order, f'{work_order.number}: {work_order.get_status_display()}', comments or f'Work order status changed to {work_order.get_status_display()}.', Notification.LEVEL_WARNING if target_status in {WorkOrder.STATUS_REJECTED, WorkOrder.STATUS_ON_HOLD} else Notification.LEVEL_SUCCESS)
    return work_order
