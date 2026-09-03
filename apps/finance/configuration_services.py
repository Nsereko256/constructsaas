from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import ValidationError

from .models import Currency, FinanceAuditEvent, FinanceSettings


def _error_detail(exc):
    return getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}


def _save(instance, **kwargs):
    try:
        instance.save(**kwargs)
    except DjangoValidationError as exc:
        raise ValidationError(_error_detail(exc)) from exc
    except IntegrityError as exc:
        raise ValidationError({'non_field_errors': ['A finance record with these values already exists.']}) from exc
    return instance


def _json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, 'pk'):
        return value.pk
    return value


def record_finance_audit_event(
    *, company, actor, action, object_type, object_id='', message='', metadata=None, correlation_id='',
):
    return _save(FinanceAuditEvent(
        company=company,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id or ''),
        message=message,
        metadata=_json_value(metadata or {}),
        correlation_id=correlation_id,
    ))


@transaction.atomic
def ensure_finance_settings(company):
    currency, _ = Currency.objects.get_or_create(
        company=company,
        code='UGX',
        defaults={'name': 'Uganda Shilling', 'symbol': 'UGX', 'decimal_places': 0},
    )
    settings, _ = FinanceSettings.objects.get_or_create(
        company=company,
        defaults={'base_currency': currency},
    )
    return settings


def validate_exchange_rate(*, company, currency, exchange_rate):
    """Validate and normalize a transaction-to-base-currency exchange rate."""
    try:
        rate = Decimal(str(exchange_rate))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError({'exchange_rate': ['Enter a valid exchange rate.']}) from exc
    if rate <= 0:
        raise ValidationError({'exchange_rate': ['Exchange rate must be greater than zero.']})
    settings = ensure_finance_settings(company)
    currency_code = getattr(currency, 'code', str(currency)).upper()
    if currency_code == settings.base_currency.code and rate != Decimal('1'):
        raise ValidationError({'exchange_rate': ['The base currency exchange rate must be 1.']})
    return rate


@transaction.atomic
def update_finance_settings(*, instance, user, values):
    locked = FinanceSettings.objects.select_for_update().get(pk=instance.pk, company=user.company)
    before = {field: getattr(locked, field) for field in values}
    for field, value in values.items():
        setattr(locked, field, value)
    _save(locked)
    record_finance_audit_event(
        company=user.company,
        actor=user,
        action='settings.updated',
        object_type='FinanceSettings',
        object_id=locked.pk,
        metadata={'before': before, 'after': values},
    )
    return locked


@transaction.atomic
def create_reference_record(*, model, user, values):
    instance = model(company=user.company, **values)
    _save(instance)
    record_finance_audit_event(
        company=user.company,
        actor=user,
        action=f'{model.__name__}.created'.lower(),
        object_type=model.__name__,
        object_id=instance.pk,
        metadata={'values': values},
    )
    return instance


@transaction.atomic
def update_reference_record(*, instance, user, values):
    locked = type(instance).objects.select_for_update().get(pk=instance.pk, company=user.company)
    before = {field: getattr(locked, field) for field in values}
    for field, value in values.items():
        setattr(locked, field, value)
    _save(locked)
    record_finance_audit_event(
        company=user.company,
        actor=user,
        action=f'{type(instance).__name__}.updated'.lower(),
        object_type=type(instance).__name__,
        object_id=locked.pk,
        metadata={'before': before, 'after': values},
    )
    return locked
