import hashlib
import json

from django.db import transaction
from rest_framework.exceptions import APIException, PermissionDenied

from apps.accounts.models import Company, User

from .models import (
    ExpenseClaim,
    FinanceSyncReceipt,
    JournalEntry,
    LandedCostDocument,
    Payment,
    ProjectBudget,
    StaffAdvance,
    SupplierInvoice,
)


class FinanceSyncConflict(APIException):
    status_code = 409
    default_code = 'finance_sync_conflict'

    def __init__(self, detail):
        self.detail = detail


SYNC_CONFIG = {
    'project_budget': (ProjectBudget, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, False),
    'supplier_invoice': (
        SupplierInvoice,
        {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN},
        True,
    ),
    'payment': (Payment, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, True),
    'landed_cost': (LandedCostDocument, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, True),
    'expense_claim': (ExpenseClaim, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, True),
    'staff_advance': (StaffAdvance, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, True),
    'journal_entry': (JournalEntry, {User.ROLE_FINANCE_OFFICER, User.ROLE_ADMIN}, True),
}


def request_hash(*, record_type, client_uuid, version, data):
    canonical = json.dumps({
        'record_type': record_type,
        'client_uuid': str(client_uuid),
        'version': version,
        'data': data,
    }, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _conflict(code, message, *, instance=None):
    server = None
    if instance is not None:
        server = {
            'id': instance.pk,
            'client_uuid': str(instance.client_uuid),
            'version': instance.version,
            'status': instance.status,
            'updated_at': getattr(instance, 'updated_at', None),
        }
    raise FinanceSyncConflict({
        'type': 'conflict',
        'code': code,
        'errors': {'non_field_errors': [message]},
        'server': server,
    })


def require_sync_permission(*, user, record_type):
    model, roles, can_update = SYNC_CONFIG[record_type]
    if not (
        user.is_authenticated
        and user.is_active
        and user.company_id
        and user.company.is_active
        and user.role in roles
    ):
        raise PermissionDenied('Your current company role cannot synchronize this finance draft.')
    return model, can_update


def begin_draft_sync(*, user, record_type, client_uuid, idempotency_key, version, data):
    current_user = User.objects.select_for_update().select_related('company').get(pk=user.pk)
    model, can_update = require_sync_permission(user=current_user, record_type=record_type)
    Company.objects.select_for_update().get(pk=current_user.company_id)
    digest = request_hash(
        record_type=record_type, client_uuid=client_uuid, version=version, data=data,
    )
    receipt = FinanceSyncReceipt.objects.select_for_update().filter(
        company=current_user.company, idempotency_key=idempotency_key,
    ).first()
    if receipt:
        if receipt.request_hash != digest:
            _conflict('idempotency_key_reused', 'The idempotency key was already used with different data.')
        return {
            'replay': receipt.response_data,
            'status': receipt.response_status,
            'user': current_user,
        }

    instance = model.objects.select_for_update().filter(
        company=current_user.company, client_uuid=client_uuid,
    ).first()
    if instance:
        if not can_update:
            _conflict('duplicate_client_uuid', 'This draft type can only be created once.', instance=instance)
        if version is None:
            _conflict(
                'version_required',
                'The current server version is required when updating an existing draft.',
                instance=instance,
            )
        if version != instance.version:
            _conflict('stale_version', 'The draft changed after the offline copy was made.', instance=instance)
        if instance.status != 'DRAFT':
            _conflict(
                'status_changed',
                'The record is no longer a draft and cannot be synchronized.',
                instance=instance,
            )
    elif version is not None:
        _conflict('record_missing', 'The draft no longer exists on the server.')
    return {'instance': instance, 'request_hash': digest, 'user': current_user}


def finish_draft_sync(
    *, user, record_type, client_uuid, idempotency_key, request_hash_value,
    response_data, response_status,
):
    FinanceSyncReceipt.objects.create(
        company=user.company,
        user=user,
        client_uuid=client_uuid,
        record_type=record_type,
        idempotency_key=idempotency_key,
        request_hash=request_hash_value,
        response_data=response_data,
        response_status=response_status,
    )


def atomic_sync():
    return transaction.atomic()
