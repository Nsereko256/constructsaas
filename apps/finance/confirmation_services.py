import json

from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User

from .configuration_services import ensure_finance_settings, record_finance_audit_event
from .models import WorkflowConfirmation


def _normalise_object_id(value):
    return str(value)


def _json_safe(value):
    """Return an immutable JSON-safe copy for audit snapshots."""
    return json.loads(json.dumps(value or {}, cls=DjangoJSONEncoder))


def role_can_confirm(user_role, required_role):
    """Allow an accountable senior role to cover its own operational function."""
    if user_role == User.ROLE_ADMIN:
        return True
    if required_role == User.ROLE_FINANCE_OFFICER:
        return user_role in {User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER}
    return user_role == required_role


def _notify_responsible_users(task):
    from apps.notifications.helpers import send_notification
    from apps.notifications.models import Notification

    recipients = User.objects.filter(company=task.company, is_active=True)
    if task.assigned_to_id:
        recipients = recipients.filter(pk=task.assigned_to_id)
    elif task.required_role == User.ROLE_FINANCE_OFFICER:
        recipients = recipients.filter(role__in=[User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN])
    else:
        recipients = recipients.filter(role__in=[task.required_role, User.ROLE_ADMIN])
    for recipient in recipients.exclude(pk=task.submitted_by_id):
        send_notification(
            recipient,
            Notification.TYPE_SYSTEM,
            Notification.LEVEL_WARNING,
            f'Confirmation required: {task.object_label}',
            f'{task.get_stage_display()} is assigned to {task.assigned_to.get_full_name() or task.assigned_to.username if task.assigned_to_id else task.get_required_role_display()}.',
            task.action_url or '/confirmations',
        )


@transaction.atomic
def submit_confirmation(
    *, company, document_type, object_id, object_label, stage, required_role,
    submitted_by, snapshot=None, action_url='', assigned_to=None,
):
    object_id = _normalise_object_id(object_id)
    existing = WorkflowConfirmation.objects.select_for_update().filter(
        company=company, document_type=document_type, object_id=object_id,
        stage=stage, status=WorkflowConfirmation.STATUS_PENDING,
    ).first()
    if existing:
        return existing
    latest_version = WorkflowConfirmation.objects.filter(
        company=company, document_type=document_type, object_id=object_id, stage=stage,
    ).order_by('-version').values_list('version', flat=True).first() or 0
    task = WorkflowConfirmation.objects.create(
        company=company, document_type=document_type, object_id=object_id,
        object_label=object_label, action_url=action_url, stage=stage,
        required_role=required_role, assigned_to=assigned_to,
        submitted_by=submitted_by, submitted_snapshot=_json_safe(snapshot),
        version=latest_version + 1,
    )
    record_finance_audit_event(
        company=company, actor=submitted_by, action='workflow.confirmation_requested',
        object_type=document_type, object_id=object_id,
        message=f'{object_label} submitted for {task.get_stage_display().lower()}.',
        metadata={'confirmation_id': task.pk, 'required_role': required_role, 'version': task.version},
    )
    transaction.on_commit(lambda: _notify_responsible_users(task), robust=True)
    return task


def _check_checker(task, user, override_reason=''):
    if user.company_id != task.company_id:
        raise PermissionDenied('This confirmation belongs to another company.')
    is_admin_override = user.role == User.ROLE_ADMIN and user.role != task.required_role
    if task.assigned_to_id and task.assigned_to_id != user.id and not is_admin_override:
        raise PermissionDenied('This confirmation is assigned to another responsible person.')
    if not role_can_confirm(user.role, task.required_role):
        raise PermissionDenied(f'Only a {task.get_required_role_display()} can confirm this step.')
    settings = ensure_finance_settings(task.company)
    self_confirmation = task.submitted_by_id == user.id
    if settings.maker_checker_enforced and self_confirmation and user.role != User.ROLE_ADMIN:
        raise PermissionDenied('The person who prepared this record cannot confirm it. Assign it to another responsible user.')
    if settings.maker_checker_enforced and self_confirmation and len(override_reason.strip()) < 10:
        raise ValidationError({'override_reason': 'Enter at least 10 characters explaining this controlled Admin override.'})
    return is_admin_override or self_confirmation


@transaction.atomic
def confirm_confirmation(*, task, user, confirmation_data=None, comments='', override_reason=''):
    locked = WorkflowConfirmation.objects.select_for_update().get(pk=task.pk)
    if locked.status != WorkflowConfirmation.STATUS_PENDING:
        raise ValidationError({'status': 'This confirmation is no longer pending.'})
    used_override = _check_checker(locked, user, override_reason)
    locked.status = WorkflowConfirmation.STATUS_CONFIRMED
    locked.confirmed_by = user
    locked.confirmation_data = _json_safe(confirmation_data)
    locked.comments = comments.strip()
    locked.override_reason = override_reason.strip() if used_override else ''
    locked.decided_at = timezone.now()
    locked.save(update_fields=[
        'status', 'confirmed_by', 'confirmation_data', 'comments',
        'override_reason', 'decided_at', 'updated_at',
    ])
    record_finance_audit_event(
        company=locked.company, actor=user, action='workflow.confirmation_completed',
        object_type=locked.document_type, object_id=locked.object_id,
        message=f'{locked.object_label} confirmed by {user.get_role_display()}.',
        metadata={'confirmation_id': locked.pk, 'stage': locked.stage, 'override': used_override, 'version': locked.version},
    )
    return locked


@transaction.atomic
def return_confirmation(*, task, user, reason, override_reason=''):
    if len(reason.strip()) < 5:
        raise ValidationError({'reason': 'Explain what must be corrected.'})
    locked = WorkflowConfirmation.objects.select_for_update().get(pk=task.pk)
    if locked.status != WorkflowConfirmation.STATUS_PENDING:
        raise ValidationError({'status': 'This confirmation is no longer pending.'})
    used_override = _check_checker(locked, user, override_reason)
    locked.status = WorkflowConfirmation.STATUS_RETURNED
    locked.confirmed_by = user
    locked.return_reason = reason.strip()
    locked.override_reason = override_reason.strip() if used_override else ''
    locked.decided_at = timezone.now()
    locked.save(update_fields=['status', 'confirmed_by', 'return_reason', 'override_reason', 'decided_at', 'updated_at'])
    record_finance_audit_event(
        company=locked.company, actor=user, action='workflow.confirmation_returned',
        object_type=locked.document_type, object_id=locked.object_id,
        message=reason.strip(), metadata={'confirmation_id': locked.pk, 'stage': locked.stage, 'override': used_override, 'version': locked.version},
    )
    return locked


def pending_confirmation(*, company, document_type, object_id, stage):
    return WorkflowConfirmation.objects.filter(
        company=company, document_type=document_type, object_id=_normalise_object_id(object_id),
        stage=stage, status=WorkflowConfirmation.STATUS_PENDING,
    ).first()


def confirm_pending(*, company, document_type, object_id, stage, user, confirmation_data=None, comments='', override_reason=''):
    task = pending_confirmation(
        company=company, document_type=document_type, object_id=object_id, stage=stage,
    )
    if task is None:
        raise ValidationError({'confirmation': 'This action has not been submitted to the responsible confirmer.'})
    return confirm_confirmation(
        task=task, user=user, confirmation_data=confirmation_data,
        comments=comments, override_reason=override_reason,
    )


def return_pending(*, company, document_type, object_id, stage, user, reason, override_reason=''):
    task = pending_confirmation(
        company=company, document_type=document_type, object_id=object_id, stage=stage,
    )
    if task is None:
        raise ValidationError({'confirmation': 'This action has not been submitted to the responsible confirmer.'})
    return return_confirmation(task=task, user=user, reason=reason, override_reason=override_reason)


@transaction.atomic
def cancel_pending(*, company, document_type, object_id, stage, user, reason):
    task = pending_confirmation(
        company=company, document_type=document_type, object_id=object_id, stage=stage,
    )
    if task is None:
        return None
    locked = WorkflowConfirmation.objects.select_for_update().get(pk=task.pk)
    locked.status = WorkflowConfirmation.STATUS_CANCELLED
    locked.confirmed_by = user
    locked.comments = reason.strip()
    locked.decided_at = timezone.now()
    locked.save(update_fields=['status', 'confirmed_by', 'comments', 'decided_at', 'updated_at'])
    record_finance_audit_event(
        company=locked.company, actor=user, action='workflow.confirmation_cancelled',
        object_type=locked.document_type, object_id=locked.object_id,
        message=locked.comments, metadata={'confirmation_id': locked.pk, 'stage': locked.stage, 'version': locked.version},
    )
    return locked
