"""Shared helpers for safe record lifecycle actions."""

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.finance.configuration_services import record_finance_audit_event


def require_draft(*, instance, allowed_statuses, actor, owner_id=None, owner_label='record'):
    if instance.status not in allowed_statuses:
        raise ValidationError({'status': f'Only {", ".join(allowed_statuses).lower()} {owner_label}s can be edited or deleted.'})
    if owner_id is not None and actor.role != getattr(actor, 'ROLE_ADMIN', 'ADMIN') and owner_id != actor.id:
        raise PermissionDenied(f'Only the record owner or an administrator can change this {owner_label}.')


def audit_lifecycle(*, instance, actor, action, message, metadata=None):
    return record_finance_audit_event(
        company=instance.company,
        actor=actor,
        action=action,
        object_type=instance.__class__.__name__,
        object_id=instance.pk,
        message=message,
        metadata=metadata or {},
    )
