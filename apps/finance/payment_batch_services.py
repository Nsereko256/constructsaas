from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .configuration_services import record_finance_audit_event
from .models import Payment, PaymentBatch, PaymentBatchItem
from .payment_services import post_payment


def _number(company):
    prefix = f'PBR-{timezone.localdate():%Y%m%d}'
    count = PaymentBatch.objects.filter(company=company, number__startswith=prefix).count() + 1
    return f'{prefix}-{count:03d}'


def _active_batch_for(payment_ids, company):
    return PaymentBatchItem.objects.filter(
        company=company, payment_id__in=payment_ids,
        batch__status__in=[PaymentBatch.STATUS_DRAFT, PaymentBatch.STATUS_SUBMITTED, PaymentBatch.STATUS_APPROVED],
    ).exists()


@transaction.atomic
def create_batch(*, user, source_account, currency, payment_date, payment_ids, notes=''):
    payments = list(Payment.objects.select_for_update().filter(pk__in=payment_ids, company=user.company))
    if not payments or len(payments) != len(set(payment_ids)):
        raise ValidationError({'payments': ['Select one or more valid payments.']})
    if _active_batch_for([payment.pk for payment in payments], user.company):
        raise ValidationError({'payments': ['A selected payment is already in an active payment batch.']})
    for payment in payments:
        if payment.status != Payment.STATUS_APPROVED:
            raise ValidationError({'payments': [f'{payment.number} must be approved before batching.']})
        if payment.source_account_id != source_account.pk or payment.currency_id != currency.pk:
            raise ValidationError({'payments': ['Every payment must use the selected account and currency.']})
    batch = PaymentBatch.objects.create(
        company=user.company, number=_number(user.company), source_account=source_account,
        currency=currency, payment_date=payment_date, notes=notes.strip(), created_by=user,
    )
    PaymentBatchItem.objects.bulk_create([
        PaymentBatchItem(company=user.company, batch=batch, payment=payment) for payment in payments
    ])
    record_finance_audit_event(
        company=user.company, actor=user, action='payment_batch.created', object_type='PaymentBatch',
        object_id=batch.pk, metadata={'payments': [payment.number for payment in payments]},
    )
    return batch


@transaction.atomic
def submit_batch(*, batch, user):
    locked = PaymentBatch.objects.select_for_update().get(pk=batch.pk, company=user.company)
    if locked.status != PaymentBatch.STATUS_DRAFT or not locked.items.exists():
        raise ValidationError({'status': ['Only a non-empty draft batch can be submitted.']})
    locked.status = PaymentBatch.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    locked.save(update_fields=['status', 'submitted_at', 'updated_at'])
    record_finance_audit_event(company=user.company, actor=user, action='payment_batch.submitted', object_type='PaymentBatch', object_id=locked.pk)
    return locked


@transaction.atomic
def approve_batch(*, batch, user):
    locked = PaymentBatch.objects.select_for_update().get(pk=batch.pk, company=user.company)
    if locked.status != PaymentBatch.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted batches can be approved.']})
    if locked.created_by_id == user.pk:
        raise ValidationError({'non_field_errors': ['Maker-checker policy prevents approving your own payment batch.']})
    locked.status = PaymentBatch.STATUS_APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    locked.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    record_finance_audit_event(company=user.company, actor=user, action='payment_batch.approved', object_type='PaymentBatch', object_id=locked.pk)
    return locked


@transaction.atomic
def release_batch(*, batch, user):
    locked = PaymentBatch.objects.select_for_update().prefetch_related('items__payment').get(pk=batch.pk, company=user.company)
    if locked.status != PaymentBatch.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved batches can be released.']})
    if locked.created_by_id == user.pk:
        raise ValidationError({'non_field_errors': ['Maker-checker policy prevents releasing your own payment batch.']})
    for item in locked.items.all():
        if item.payment.status != Payment.STATUS_APPROVED:
            raise ValidationError({'payments': [f'{item.payment.number} is no longer eligible for release.']})
        post_payment(payment=item.payment, user=user, idempotency_key=f'batch-{locked.pk}-{item.payment.pk}')
    locked.status = PaymentBatch.STATUS_RELEASED
    locked.released_by = user
    locked.released_at = timezone.now()
    locked.save(update_fields=['status', 'released_by', 'released_at', 'updated_at'])
    record_finance_audit_event(company=user.company, actor=user, action='payment_batch.released', object_type='PaymentBatch', object_id=locked.pk)
    return locked


@transaction.atomic
def cancel_batch(*, batch, user, reason):
    locked = PaymentBatch.objects.select_for_update().get(pk=batch.pk, company=user.company)
    if locked.status in {PaymentBatch.STATUS_RELEASED, PaymentBatch.STATUS_CANCELLED}:
        raise ValidationError({'status': ['Released or cancelled batches cannot be cancelled.']})
    if not reason.strip():
        raise ValidationError({'reason': ['A cancellation reason is required.']})
    locked.status = PaymentBatch.STATUS_CANCELLED
    locked.cancellation_reason = reason.strip()
    locked.save(update_fields=['status', 'cancellation_reason', 'updated_at'])
    record_finance_audit_event(company=user.company, actor=user, action='payment_batch.cancelled', object_type='PaymentBatch', object_id=locked.pk, message=reason.strip())
    return locked
