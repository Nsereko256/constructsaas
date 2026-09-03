from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import User

from .configuration_services import ensure_finance_settings, record_finance_audit_event
from .models import (
    Account,
    AccountMapping,
    FinanceDocumentSequence,
    FiscalPeriod,
    JournalEntry,
    JournalLine,
    JournalReversal,
    PostingRule,
)


ZERO = Decimal('0.00')
MONEY_PLACES = Decimal('0.01')


def money(value):
    return Decimal(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def _save(instance, **kwargs):
    try:
        instance.save(**kwargs)
    except DjangoValidationError as exc:
        detail = getattr(exc, 'message_dict', None) or {'non_field_errors': exc.messages}
        raise ValidationError(detail) from exc
    except IntegrityError as exc:
        raise ValidationError({'non_field_errors': ['The operation conflicts with an existing ledger record.']}) from exc
    return instance


DEFAULT_ACCOUNTS = (
    ('1000', 'Cash and Bank', Account.TYPE_ASSET, Account.SYSTEM_CASH),
    ('1200', 'Inventory', Account.TYPE_ASSET, Account.SYSTEM_INVENTORY),
    ('1300', 'Supplier Advances', Account.TYPE_ASSET, Account.SYSTEM_SUPPLIER_ADVANCE),
    ('1400', 'Staff Advances', Account.TYPE_ASSET, Account.SYSTEM_STAFF_ADVANCE),
    ('2100', 'GRN Clearing', Account.TYPE_LIABILITY, Account.SYSTEM_GRN_CLEARING),
    ('2000', 'Accounts Payable', Account.TYPE_LIABILITY, Account.SYSTEM_ACCOUNTS_PAYABLE),
    ('5100', 'Inventory Adjustments', Account.TYPE_EXPENSE, Account.SYSTEM_INVENTORY_ADJUSTMENT),
    ('5200', 'Inventory Write-offs', Account.TYPE_EXPENSE, Account.SYSTEM_INVENTORY_WRITE_OFF),
    ('5300', 'Landed Cost Clearing', Account.TYPE_LIABILITY, Account.SYSTEM_LANDED_COST_CLEARING),
    ('5000', 'Project Material Cost', Account.TYPE_EXPENSE, Account.SYSTEM_PROJECT_COST),
    ('5400', 'Realized Foreign Exchange Gain/Loss', Account.TYPE_EXPENSE, Account.SYSTEM_REALIZED_FX),
    ('1500', 'Recoverable VAT', Account.TYPE_ASSET, Account.SYSTEM_RECOVERABLE_VAT),
    ('2200', 'Withholding Tax Payable', Account.TYPE_LIABILITY, Account.SYSTEM_WITHHOLDING_TAX_PAYABLE),
)

MAPPING_SYSTEM_KEYS = {
    'CASH': Account.SYSTEM_CASH,
    'INVENTORY': Account.SYSTEM_INVENTORY,
    'SUPPLIER_ADVANCE': Account.SYSTEM_SUPPLIER_ADVANCE,
    'STAFF_ADVANCE': Account.SYSTEM_STAFF_ADVANCE,
    'GRN_CLEARING': Account.SYSTEM_GRN_CLEARING,
    'ACCOUNTS_PAYABLE': Account.SYSTEM_ACCOUNTS_PAYABLE,
    'PROJECT_MATERIAL_COST': Account.SYSTEM_PROJECT_COST,
    'INVENTORY_ADJUSTMENT': Account.SYSTEM_INVENTORY_ADJUSTMENT,
    'INVENTORY_WRITE_OFF': Account.SYSTEM_INVENTORY_WRITE_OFF,
    'LANDED_COST_CLEARING': Account.SYSTEM_LANDED_COST_CLEARING,
    'PROJECT_EXPENSE': Account.SYSTEM_PROJECT_COST,
    'PETTY_CASH': Account.SYSTEM_CASH,
    'REALIZED_FX_GAIN_LOSS': Account.SYSTEM_REALIZED_FX,
    'RECOVERABLE_VAT': Account.SYSTEM_RECOVERABLE_VAT,
    'WITHHOLDING_TAX_PAYABLE': Account.SYSTEM_WITHHOLDING_TAX_PAYABLE,
}

DEFAULT_RULES = (
    (PostingRule.EVENT_GRN_RECEIPT, 'GRN inventory receipt', 'INVENTORY', 'GRN_CLEARING'),
    (PostingRule.EVENT_SUPPLIER_INVOICE, 'Supplier invoice', 'GRN_CLEARING', 'ACCOUNTS_PAYABLE'),
    (PostingRule.EVENT_SUPPLIER_PAYMENT, 'Supplier payment', 'ACCOUNTS_PAYABLE', 'CASH'),
    (PostingRule.EVENT_PROJECT_ISSUE, 'Material issue to project', 'PROJECT_MATERIAL_COST', 'INVENTORY'),
    (PostingRule.EVENT_INVENTORY_ADJUSTMENT, 'Inventory adjustment', 'INVENTORY', 'INVENTORY_ADJUSTMENT'),
    (PostingRule.EVENT_INVENTORY_WRITE_OFF, 'Inventory write-off', 'INVENTORY_WRITE_OFF', 'INVENTORY'),
    (PostingRule.EVENT_SUPPLIER_RETURN, 'Supplier return', 'GRN_CLEARING', 'INVENTORY'),
    (PostingRule.EVENT_CREDIT_NOTE, 'Supplier credit note', 'ACCOUNTS_PAYABLE', 'INVENTORY'),
    (PostingRule.EVENT_LANDED_COST, 'Landed cost', 'INVENTORY', 'LANDED_COST_CLEARING'),
    (PostingRule.EVENT_PROJECT_EXPENSE, 'Project expense', 'PROJECT_EXPENSE', 'CASH'),
    (PostingRule.EVENT_PETTY_CASH, 'Petty-cash transaction', 'PETTY_CASH', 'CASH'),
)


@transaction.atomic
def ensure_ledger_configuration(company):
    accounts = {}
    for code, name, account_type, system_key in DEFAULT_ACCOUNTS:
        account = Account.objects.filter(company=company, system_key=system_key).first()
        if not account:
            available_code = code
            suffix = 1
            while Account.objects.filter(company=company, code=available_code).exists():
                suffix += 1
                available_code = f'{code}-L{suffix}'
            account = Account.objects.create(
                company=company, system_key=system_key, code=available_code,
                name=name, account_type=account_type,
            )
        accounts[system_key] = account
    for mapping_key, system_key in MAPPING_SYSTEM_KEYS.items():
        AccountMapping.objects.get_or_create(
            company=company,
            mapping_key=mapping_key,
            defaults={'account': accounts[system_key]},
        )
    for event_type, name, debit_key, credit_key in DEFAULT_RULES:
        PostingRule.objects.get_or_create(
            company=company,
            event_type=event_type,
            defaults={
                'name': name,
                'debit_mapping_key': debit_key,
                'credit_mapping_key': credit_key,
            },
        )
    return accounts


def resolve_mapping(*, company, mapping_key):
    ensure_ledger_configuration(company)
    mapping = AccountMapping.objects.select_related('account').filter(
        company=company,
        mapping_key=mapping_key.upper(),
        is_active=True,
        account__is_active=True,
    ).first()
    if not mapping:
        raise ValidationError({'account_mapping': [f'No active account mapping exists for {mapping_key}.']})
    return mapping.account


def resolve_rule_accounts(*, company, event_type):
    ensure_ledger_configuration(company)
    rule = PostingRule.objects.filter(company=company, event_type=event_type, is_active=True).first()
    if not rule:
        raise ValidationError({'posting_rule': [f'No active posting rule exists for {event_type}.']})
    return (
        resolve_mapping(company=company, mapping_key=rule.debit_mapping_key),
        resolve_mapping(company=company, mapping_key=rule.credit_mapping_key),
    )


def _number(company):
    today = timezone.localdate()
    sequence, _ = FinanceDocumentSequence.objects.select_for_update().get_or_create(
        company=company,
        document_type=FinanceDocumentSequence.TYPE_JOURNAL,
        defaults={'last_value': JournalEntry.objects.filter(company=company).count()},
    )
    sequence.last_value += 1
    sequence.save(update_fields=['last_value'])
    return f'JE-{today:%Y%m%d}-{sequence.last_value:05d}'


def _period_for_date(*, company, entry_date, lock=False, create=True):
    queryset = FiscalPeriod.objects
    if lock:
        queryset = queryset.select_for_update()
    period = queryset.filter(
        company=company, start_date__lte=entry_date, end_date__gte=entry_date,
    ).first()
    if period or not create:
        return period
    last_day = monthrange(entry_date.year, entry_date.month)[1]
    return _save(FiscalPeriod(
        company=company,
        name=f'{entry_date:%Y-%m}',
        start_date=entry_date.replace(day=1),
        end_date=entry_date.replace(day=last_day),
    ))


def _require_open_period(*, company, entry_date):
    period = _period_for_date(company=company, entry_date=entry_date, lock=True)
    if period.status != FiscalPeriod.STATUS_OPEN:
        raise ValidationError({'date': [f'Fiscal period {period.name} is closed.']})
    return period


def _line_totals(entry):
    totals = entry.lines.aggregate(debit=Sum('debit'), credit=Sum('credit'))
    return money(totals['debit'] or ZERO), money(totals['credit'] or ZERO)


@transaction.atomic
def create_draft_journal(*, user, entry_date, description, lines, source_reference='', client_uuid=None):
    period = _period_for_date(company=user.company, entry_date=entry_date, lock=True)
    entry = _save(JournalEntry(
        company=user.company,
        number=_number(user.company),
        date=entry_date,
        description=description,
        source_type=JournalEntry.SOURCE_MANUAL,
        source_reference=source_reference,
        fiscal_period=period,
        status=JournalEntry.STATUS_DRAFT,
        created_by=user,
        client_uuid=client_uuid,
        posted_at=None,
    ))
    JournalEntry.objects.filter(pk=entry.pk).update(source_object_id=entry.pk)
    entry.source_object_id = entry.pk
    for line in lines:
        account = line['account']
        if account.company_id != user.company_id or not account.allow_manual_posting:
            raise ValidationError({'lines': ['All accounts must permit manual posting within your company.']})
        _save(JournalLine(company=user.company, entry=entry, **line))
    record_finance_audit_event(
        company=user.company, actor=user, action='journal.draft_created',
        object_type='JournalEntry', object_id=entry.pk,
    )
    return entry


@transaction.atomic
def update_draft_journal(*, journal, user, values, lines=None):
    entry = JournalEntry.objects.select_for_update().get(pk=journal.pk, company=user.company)
    if entry.status != JournalEntry.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft journals can be edited.']})
    for field, value in values.items():
        setattr(entry, field, value)
    entry.fiscal_period = _period_for_date(company=user.company, entry_date=entry.date, lock=True)
    _save(entry)
    if lines is not None:
        entry.lines.all().delete()
        for line in lines:
            if line['account'].company_id != user.company_id or not line['account'].allow_manual_posting:
                raise ValidationError({'lines': ['All accounts must permit manual posting within your company.']})
            _save(JournalLine(company=user.company, entry=entry, **line))
    return entry


@transaction.atomic
def post_journal(*, journal, user, enforce_maker_checker=True, require_manager=True):
    entry = JournalEntry.objects.select_for_update().prefetch_related('lines').get(
        pk=journal.pk, company=user.company,
    )
    if entry.status == JournalEntry.STATUS_POSTED:
        return entry
    if entry.status != JournalEntry.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft journals can be posted.']})
    if require_manager and user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
        raise ValidationError({'non_field_errors': ['Finance Manager permission is required to post journals.']})
    settings = ensure_finance_settings(user.company)
    if enforce_maker_checker and settings.maker_checker_enforced and entry.created_by_id == user.id:
        raise ValidationError({'non_field_errors': ['Maker-checker control prevents posting your own journal.']})
    period = _require_open_period(company=user.company, entry_date=entry.date)
    debit, credit = _line_totals(entry)
    if debit <= ZERO or debit != credit:
        raise ValidationError({'lines': [f'Journal must balance. Debits: {debit}; credits: {credit}.']})
    JournalEntry.objects.filter(pk=entry.pk).update(
        status=JournalEntry.STATUS_POSTED,
        fiscal_period=period,
        posted_by=user,
        posted_at=timezone.now(),
    )
    entry.status = JournalEntry.STATUS_POSTED
    entry.fiscal_period = period
    entry.posted_by = user
    entry.posted_at = timezone.now()
    record_finance_audit_event(
        company=user.company, actor=user, action='journal.posted',
        object_type='JournalEntry', object_id=entry.pk,
        metadata={'debit': debit, 'credit': credit},
    )
    return entry


@transaction.atomic
def create_and_post_source_journal(
    *, company, user, entry_date, description, source_type, source_object_id,
    lines, source_reference='', reversal_of=None,
):
    existing = JournalEntry.objects.filter(
        company=company, source_type=source_type, source_object_id=source_object_id,
    ).first()
    if existing:
        expected_debit = money(sum((money(line.get('debit', ZERO)) for line in lines), ZERO))
        expected_credit = money(sum((money(line.get('credit', ZERO)) for line in lines), ZERO))
        actual_debit, actual_credit = _line_totals(existing)
        if expected_debit != actual_debit or expected_credit != actual_credit:
            raise ValidationError({
                'source': ['This source record was already posted with different journal values.'],
            })
        return existing
    period = _require_open_period(company=company, entry_date=entry_date)
    entry = _save(JournalEntry(
        company=company,
        number=_number(company),
        date=entry_date,
        description=description,
        source_type=source_type,
        source_object_id=source_object_id,
        source_reference=source_reference,
        fiscal_period=period,
        status=JournalEntry.STATUS_DRAFT,
        reversal_of=reversal_of,
        created_by=user,
        posted_at=None,
    ))
    for line in lines:
        _save(JournalLine(company=company, entry=entry, **line))
    return post_journal(
        journal=entry, user=user, enforce_maker_checker=False, require_manager=False,
    )


@transaction.atomic
def post_rule_event(
    *, company, user, event_type, entry_date, source_type, source_object_id,
    amount, description, source_reference='', project=None, supplier=None,
    debit_account=None, credit_account=None,
):
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({'amount': ['Posting amount must be greater than zero.']})
    ensure_ledger_configuration(company)
    rule = PostingRule.objects.select_for_update().filter(
        company=company, event_type=event_type, is_active=True,
    ).first()
    if not rule:
        raise ValidationError({'posting_rule': [f'No active posting rule exists for {event_type}.']})
    debit_account = debit_account or resolve_mapping(company=company, mapping_key=rule.debit_mapping_key)
    credit_account = credit_account or resolve_mapping(company=company, mapping_key=rule.credit_mapping_key)
    return create_and_post_source_journal(
        company=company,
        user=user,
        entry_date=entry_date,
        description=description,
        source_type=source_type,
        source_object_id=source_object_id,
        source_reference=source_reference,
        lines=[
            {
                'account': debit_account, 'project': project, 'supplier': supplier,
                'description': description, 'debit': amount, 'credit': ZERO,
            },
            {
                'account': credit_account, 'project': project, 'supplier': supplier,
                'description': description, 'debit': ZERO, 'credit': amount,
            },
        ],
    )


def post_inventory_movement(*, movement, user):
    from apps.warehouse.models import StockMovement

    # Transfers between company-controlled inventory locations do not change
    # total company inventory or create an expense. Their stock movements are
    # the subledger record; posting them as inventory adjustments would create
    # artificial P&L activity. This covers warehouse/site transfers in both
    # directions.
    if movement.transaction_type in {
        StockMovement.TRANSACTION_SITE_TRANSFER_OUT,
        StockMovement.TRANSACTION_SITE_TRANSFER_IN,
        StockMovement.TRANSACTION_SITE_RETURN_OUT,
        StockMovement.TRANSACTION_SITE_RETURN_IN,
    }:
        return None

    if movement.goods_received_note_item_id or movement.transaction_type in {
        StockMovement.TRANSACTION_LANDED_COST,
        StockMovement.TRANSACTION_LANDED_COST_REVERSAL,
    }:
        return None
    amount = money(abs(movement.value_effect))
    if amount <= ZERO:
        return None
    ensure_ledger_configuration(movement.company)
    inventory = resolve_mapping(company=movement.company, mapping_key='INVENTORY')
    project_cost = resolve_mapping(company=movement.company, mapping_key='PROJECT_MATERIAL_COST')
    adjustment = resolve_mapping(company=movement.company, mapping_key='INVENTORY_ADJUSTMENT')
    event_type = PostingRule.EVENT_INVENTORY_ADJUSTMENT
    debit_account, credit_account = inventory, adjustment
    if movement.transaction_type == StockMovement.TRANSACTION_PROJECT_ISSUE:
        event_type = PostingRule.EVENT_PROJECT_ISSUE
        debit_account, credit_account = project_cost, inventory
    elif movement.transaction_type == StockMovement.TRANSACTION_PROJECT_RETURN:
        event_type = PostingRule.EVENT_PROJECT_ISSUE
        debit_account, credit_account = inventory, project_cost
    elif movement.transaction_type == StockMovement.TRANSACTION_WRITE_OFF:
        event_type = PostingRule.EVENT_INVENTORY_WRITE_OFF
        debit_account = resolve_mapping(company=movement.company, mapping_key='INVENTORY_WRITE_OFF')
        credit_account = inventory
    elif movement.transaction_type == StockMovement.TRANSACTION_SUPPLIER_RETURN:
        event_type = PostingRule.EVENT_SUPPLIER_RETURN
        debit_account = resolve_mapping(company=movement.company, mapping_key='GRN_CLEARING')
        credit_account = inventory
    elif movement.value_effect < ZERO:
        debit_account, credit_account = adjustment, inventory
    return post_rule_event(
        company=movement.company,
        user=user,
        event_type=event_type,
        entry_date=movement.date,
        source_type=JournalEntry.SOURCE_STOCK_MOVEMENT,
        source_object_id=movement.pk,
        amount=amount,
        description=f'Inventory movement {movement.pk}: {movement.get_transaction_type_display()}',
        source_reference=str(movement.pk),
        project=movement.project,
        debit_account=debit_account,
        credit_account=credit_account,
    )


@transaction.atomic
def reverse_journal(*, journal, user, reason, idempotency_key, reversal_date=None):
    existing = JournalReversal.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.original_journal_id != journal.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another reversal.']})
        return existing
    original = JournalEntry.objects.select_for_update().prefetch_related('lines').get(
        pk=journal.pk, company=user.company,
    )
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    if original.status != JournalEntry.STATUS_POSTED or hasattr(original, 'reversal_record'):
        raise ValidationError({'status': ['Only an unreversed posted journal can be reversed.']})
    reversal_date = reversal_date or timezone.localdate()
    lines = [{
        'account': line.account,
        'project': line.project,
        'supplier': line.supplier,
        'description': f'Reversal: {line.description}',
        'debit': line.credit,
        'credit': line.debit,
    } for line in original.lines.select_related('account', 'project', 'supplier')]
    reversal_journal = create_and_post_source_journal(
        company=user.company,
        user=user,
        entry_date=reversal_date,
        description=f'Reverse {original.number}: {reason}',
        source_type=JournalEntry.SOURCE_JOURNAL_REVERSAL,
        source_object_id=original.pk,
        source_reference=original.number,
        reversal_of=original,
        lines=lines,
    )
    record = _save(JournalReversal(
        company=user.company,
        original_journal=original,
        reversal_journal=reversal_journal,
        reason=reason,
        idempotency_key=idempotency_key,
        reversed_by=user,
    ))
    JournalEntry.objects.filter(pk=original.pk).update(status=JournalEntry.STATUS_REVERSED)
    record_finance_audit_event(
        company=user.company, actor=user, action='journal.reversed',
        object_type='JournalEntry', object_id=original.pk,
        metadata={'reversal_journal': reversal_journal.pk, 'reason': reason},
        correlation_id=idempotency_key,
    )
    return record


@transaction.atomic
def set_period_status(*, period, user, status):
    locked = FiscalPeriod.objects.select_for_update().get(pk=period.pk, company=user.company)
    if status not in {FiscalPeriod.STATUS_OPEN, FiscalPeriod.STATUS_CLOSED}:
        raise ValidationError({'status': ['Invalid fiscal-period status.']})
    if status == FiscalPeriod.STATUS_CLOSED:
        from .month_end_services import checklist
        close_check = checklist(company=user.company, period=locked)
        if not close_check['is_ready']:
            blockers = [f"{row['label']} ({row['count']})" for row in close_check['checks'] if row['count']]
            raise ValidationError({'close_checklist': blockers})
    values = {'status': status, 'closed_by': None, 'closed_at': None}
    if status == FiscalPeriod.STATUS_CLOSED:
        values.update({'closed_by': user, 'closed_at': timezone.now()})
    FiscalPeriod.objects.filter(pk=locked.pk).update(**values)
    for field, value in values.items():
        setattr(locked, field, value)
    record_finance_audit_event(
        company=user.company, actor=user, action=f'fiscal_period.{status.lower()}',
        object_type='FiscalPeriod', object_id=locked.pk,
    )
    return locked
