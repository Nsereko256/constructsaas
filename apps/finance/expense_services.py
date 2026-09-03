from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from . import services
from apps.api.upload_validation import validate_image_upload
from .budget_services import budget_line_summary
from .configuration_services import (
    ensure_finance_settings,
    record_finance_audit_event,
    validate_exchange_rate,
)
from .models import (
    Account,
    AdvanceRetirement,
    BudgetLine,
    BudgetTransaction,
    CashAccount,
    ExpenseApproval,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseItem,
    ExpenseReceiptAttachment,
    FinanceDocumentSequence,
    JournalEntry,
    PettyCashTransaction,
    ProjectBudget,
    StaffAdvance,
)


ZERO = Decimal('0.00')


def _approval(*, user, action, claim=None, advance=None, transaction_record=None, comments='', key=''):
    return services._save(ExpenseApproval(
        company=user.company,
        expense_claim=claim,
        staff_advance=advance,
        petty_cash_transaction=transaction_record,
        action=action,
        comments=comments,
        acted_by=user,
        idempotency_key=key,
    ))


def _audit(*, user, action, instance, message='', metadata=None, key=''):
    record_finance_audit_event(
        company=user.company,
        actor=user,
        action=action,
        object_type=instance.__class__.__name__,
        object_id=instance.pk,
        message=message,
        metadata=metadata,
        correlation_id=key,
    )


def _destination_project(record):
    if isinstance(record, AdvanceRetirement):
        record = record.advance
    if record.project_id:
        return record.project
    if record.cost_centre_id:
        return record.cost_centre.project
    return None


def _check_approval_controls(record, user, base_amount):
    settings = ensure_finance_settings(user.company)
    if settings.maker_checker_enforced and record.created_by_id == user.id:
        raise ValidationError({'non_field_errors': ['Maker-checker control prevents self-approval.']})
    threshold = settings.finance_manager_approval_threshold
    if user.role != user.ROLE_ADMIN and threshold > ZERO and services.money(base_amount) > threshold:
        raise ValidationError({
            'amount': ['This amount exceeds the Finance Manager threshold and requires Company Administrator approval.'],
        })


def _cash_balance(cash_account):
    effect = PettyCashTransaction.objects.filter(cash_account=cash_account).aggregate(
        total=Sum('balance_effect'),
    )['total'] or ZERO
    return services.money(cash_account.opening_balance + effect)


def _locked_cash(cash_account, company):
    return CashAccount.objects.select_for_update().select_related('account', 'currency').get(
        pk=cash_account.pk,
        company=company,
    )


def _require_cash(cash_account, amount):
    balance = _cash_balance(cash_account)
    if services.money(amount) > balance:
        raise ValidationError({'amount': [f'Insufficient cash balance. Available balance is {balance}.']})


def _approved_project_budget(project, company):
    if not project:
        return None
    return ProjectBudget.objects.select_for_update().filter(
        company=company,
        project=project,
        status=ProjectBudget.STATUS_APPROVED,
    ).first()


def _require_project_budget(record, user):
    """Fail closed for project-linked cash expenditure."""
    project = _destination_project(record)
    if project and not _approved_project_budget(project, user.company):
        raise ValidationError({
            'project': ['An approved Finance project budget is required before project expenditure can be posted.'],
        })


def _validate_budget_category(record, category, user):
    project = _destination_project(record)
    if not project:
        return
    budget = _approved_project_budget(project, user.company)
    if not category.budget_category_id:
        raise ValidationError({
            'category': [f'Expense category {category.code} is not mapped to a project budget category.'],
        })
    line = BudgetLine.objects.filter(
        company=user.company,
        budget=budget,
        category=category.budget_category,
    ).first() if budget else None
    if not line:
        raise ValidationError({
            'category': [f'No approved budget line exists for expense category {category.code}.'],
        })


def _record_budget_actual(*, record, category, amount, user, key, description, reversal=False):
    project = _destination_project(record)
    if not project:
        return None
    _validate_budget_category(record, category, user)
    budget = _approved_project_budget(project, user.company)
    line = BudgetLine.objects.select_for_update().filter(
        company=user.company,
        budget=budget,
        category=category.budget_category,
    ).first()
    if not line:
        raise ValidationError({
            'category': [f'No approved budget line exists for expense category {category.code}.'],
        })
    existing = BudgetTransaction.objects.filter(company=user.company, idempotency_key=key).first()
    if existing:
        return existing
    amount = services.money(amount)
    if not reversal and amount > budget_line_summary(line)['available_balance']:
        raise ValidationError({'amount': [f'Expense would exceed the available {category.code} budget.']})
    transaction_record = BudgetTransaction(
        company=user.company,
        budget=budget,
        budget_line=line,
        transaction_type=(
            BudgetTransaction.TYPE_ACTUAL_REVERSAL if reversal else BudgetTransaction.TYPE_ACTUAL
        ),
        amount=-amount if reversal else amount,
        description=description,
        idempotency_key=key,
        created_by=user,
    )
    if isinstance(record, ExpenseClaim):
        transaction_record.expense_claim = record
    else:
        transaction_record.advance_retirement = record
    return services._save(transaction_record)


def _expense_amounts_by_category(claim):
    totals = defaultdict(lambda: ZERO)
    categories = {}
    for item in claim.items.select_related('category', 'category__budget_category'):
        categories[item.category_id] = item.category
        totals[item.category_id] += services.money(item.amount * claim.exchange_rate)
    return [(categories[category_id], services.money(amount)) for category_id, amount in totals.items()]


def _recalculate_claim(claim):
    total = claim.items.aggregate(total=Sum('amount'))['total'] or ZERO
    claim.total_amount = services.money(total)
    claim.base_total_amount = services.money(claim.total_amount * claim.exchange_rate)
    services._save(claim, update_fields=['total_amount', 'base_total_amount', 'updated_at'])
    return claim


@transaction.atomic
def create_expense_claim(*, user, items, idempotency_key, **values):
    existing = ExpenseClaim.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    currency = values['currency']
    if currency.company_id != user.company_id or not currency.is_active:
        raise ValidationError({'currency': ['Select an active company currency.']})
    values['exchange_rate'] = validate_exchange_rate(
        company=user.company,
        currency=currency,
        exchange_rate=values.get('exchange_rate', Decimal('1')),
    )
    number = services._next_number(
        user.company, FinanceDocumentSequence.TYPE_EXPENSE, 'EXP', ExpenseClaim,
    )
    claim = services._save(ExpenseClaim(
        company=user.company,
        number=number,
        created_by=user,
        idempotency_key=idempotency_key,
        **values,
    ))
    for item in items:
        services._save(ExpenseItem(company=user.company, claim=claim, **item))
    _recalculate_claim(claim)
    _audit(user=user, action='expense.created', instance=claim, key=idempotency_key)
    return claim


@transaction.atomic
def update_draft_expense_claim(*, claim, user, values, items=None):
    locked = ExpenseClaim.objects.select_for_update().get(pk=claim.pk, company=user.company)
    if locked.status != ExpenseClaim.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft expense claims can be edited.']})
    for field, value in values.items():
        setattr(locked, field, value)
    if locked.currency.company_id != user.company_id or not locked.currency.is_active:
        raise ValidationError({'currency': ['Select an active company currency.']})
    locked.exchange_rate = validate_exchange_rate(
        company=user.company, currency=locked.currency, exchange_rate=locked.exchange_rate,
    )
    services._save(locked)
    if items is not None:
        locked.items.all().delete()
        for item in items:
            services._save(ExpenseItem(company=user.company, claim=locked, **item))
    _recalculate_claim(locked)
    _audit(user=user, action='expense.updated', instance=locked)
    return locked


@transaction.atomic
def submit_expense_claim(*, claim, user, comments=''):
    locked = ExpenseClaim.objects.select_for_update().get(pk=claim.pk, company=user.company)
    if locked.status != ExpenseClaim.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft expense claims can be submitted.']})
    _recalculate_claim(locked)
    if locked.total_amount <= ZERO:
        raise ValidationError({'items': ['At least one expense item is required.']})
    locked.status = ExpenseClaim.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    services._save(locked, update_fields=['status', 'submitted_at', 'updated_at'])
    _approval(user=user, action=ExpenseApproval.ACTION_SUBMIT, claim=locked, comments=comments)
    _audit(user=user, action='expense.submitted', instance=locked, message=comments)
    return locked


@transaction.atomic
def approve_expense_claim(*, claim, user, comments=''):
    locked = ExpenseClaim.objects.select_for_update().prefetch_related(
        'items__category__budget_category',
    ).get(pk=claim.pk, company=user.company)
    if locked.status not in {ExpenseClaim.STATUS_SUBMITTED, ExpenseClaim.STATUS_REVIEWED}:
        raise ValidationError({'status': ['Only submitted expense claims can be approved.']})
    _check_approval_controls(locked, user, locked.base_total_amount)
    _require_project_budget(locked, user)
    for category, _amount in _expense_amounts_by_category(locked):
        _validate_budget_category(locked, category, user)
    locked.status = ExpenseClaim.STATUS_APPROVED
    locked.reviewed_by = user
    locked.reviewed_at = timezone.now()
    locked.approved_by = user
    locked.approved_at = locked.reviewed_at
    services._save(locked, update_fields=[
        'status', 'reviewed_by', 'reviewed_at', 'approved_by', 'approved_at', 'updated_at',
    ])
    _approval(user=user, action=ExpenseApproval.ACTION_APPROVE, claim=locked, comments=comments)
    _audit(user=user, action='expense.approved', instance=locked, message=comments)
    return locked


@transaction.atomic
def reject_expense_claim(*, claim, user, reason):
    locked = ExpenseClaim.objects.select_for_update().get(pk=claim.pk, company=user.company)
    if locked.status not in {ExpenseClaim.STATUS_SUBMITTED, ExpenseClaim.STATUS_REVIEWED}:
        raise ValidationError({'status': ['Only submitted expense claims can be rejected.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A rejection reason is required.']})
    locked.status = ExpenseClaim.STATUS_REJECTED
    locked.rejection_reason = reason
    services._save(locked, update_fields=['status', 'rejection_reason', 'updated_at'])
    _approval(user=user, action=ExpenseApproval.ACTION_REJECT, claim=locked, comments=reason)
    _audit(user=user, action='expense.rejected', instance=locked, message=reason)
    return locked


@transaction.atomic
def pay_expense_claim(*, claim, user, cash_account, payment_reference, idempotency_key, payment_date=None):
    existing = PettyCashTransaction.objects.filter(
        company=user.company, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.expense_claim_id != claim.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another transaction.']})
        return ExpenseClaim.objects.get(pk=claim.pk)
    locked = ExpenseClaim.objects.select_for_update().prefetch_related(
        'items__category__budget_category',
    ).get(pk=claim.pk, company=user.company)
    if locked.status != ExpenseClaim.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved expense claims can be paid.']})
    cash = _locked_cash(cash_account, user.company)
    if cash.currency_id != locked.currency_id:
        raise ValidationError({'cash_account': ['Cash account currency must match the claim currency.']})
    payment_reference = payment_reference.strip()
    if not payment_reference:
        raise ValidationError({'payment_reference': ['Payment reference is required.']})
    _require_cash(cash, locked.total_amount)
    for category, amount in _expense_amounts_by_category(locked):
        _record_budget_actual(
            record=locked,
            category=category,
            amount=amount,
            user=user,
            key=f'expense:{locked.pk}:category:{category.pk}:actual',
            description=f'Expense reimbursement {locked.number}',
        )
    project = _destination_project(locked)
    debit_lines = [{
        'account': category.expense_account,
        'project': project,
        'supplier': None,
        'description': locked.number,
        'debit': amount,
        'credit': ZERO,
    } for category, amount in _expense_amounts_by_category(locked)]
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=payment_date or timezone.localdate(),
        description=f'Pay expense claim {locked.number}',
        source_type=JournalEntry.SOURCE_EXPENSE,
        source_object_id=locked.pk,
        lines=debit_lines + [{
            'account': cash.account,
            'project': project,
            'supplier': None,
            'description': payment_reference,
            'debit': ZERO,
            'credit': locked.base_total_amount,
        }],
    )
    cash_transaction = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_DISBURSEMENT,
        amount=locked.total_amount,
        balance_effect=-locked.total_amount,
        exchange_rate=locked.exchange_rate,
        transaction_date=payment_date or timezone.localdate(),
        reference=payment_reference,
        reason=f'Expense reimbursement {locked.number}',
        expense_claim=locked,
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    locked.status = ExpenseClaim.STATUS_PAID
    locked.cash_account = cash
    locked.payment_reference = payment_reference
    locked.posting_idempotency_key = idempotency_key
    locked.amount_paid = locked.total_amount
    locked.journal_entry = entry
    locked.paid_by = user
    locked.paid_at = timezone.now()
    services._save(locked, update_fields=[
        'status', 'cash_account', 'payment_reference', 'posting_idempotency_key', 'amount_paid',
        'journal_entry', 'paid_by', 'paid_at', 'updated_at',
    ])
    _approval(
        user=user, action=ExpenseApproval.ACTION_PAY, claim=locked,
        comments=payment_reference, key=f'action:{idempotency_key}',
    )
    _audit(
        user=user, action='expense.paid', instance=locked,
        metadata={'cash_transaction': cash_transaction.pk}, key=idempotency_key,
    )
    return locked


@transaction.atomic
def reverse_expense_claim(*, claim, user, reason, idempotency_key, reversal_date=None):
    existing = PettyCashTransaction.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.expense_claim_id != claim.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another transaction.']})
        return existing
    locked = ExpenseClaim.objects.select_for_update().select_related(
        'cash_account__account', 'journal_entry',
    ).get(pk=claim.pk, company=user.company)
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    if locked.status not in {ExpenseClaim.STATUS_PAID, ExpenseClaim.STATUS_CLOSED}:
        raise ValidationError({'status': ['Only paid expense claims can be reversed.']})
    original = PettyCashTransaction.objects.select_for_update().get(
        company=user.company, expense_claim=locked, transaction_type=PettyCashTransaction.TYPE_DISBURSEMENT,
    )
    cash = _locked_cash(locked.cash_account, user.company)
    for actual in locked.budget_transactions.select_related('budget', 'budget_line').filter(
        transaction_type=BudgetTransaction.TYPE_ACTUAL,
    ):
        services._save(BudgetTransaction(
            company=user.company,
            budget=actual.budget,
            budget_line=actual.budget_line,
            transaction_type=BudgetTransaction.TYPE_ACTUAL_REVERSAL,
            amount=-actual.amount,
            expense_claim=locked,
            description=f'Reverse expense {locked.number}: {reason}',
            idempotency_key=f'{actual.idempotency_key}:reversal',
            created_by=user,
        ))
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=reversal_date or timezone.localdate(),
        description=f'Reverse expense claim {locked.number}: {reason}',
        source_type=JournalEntry.SOURCE_EXPENSE_REVERSAL,
        source_object_id=locked.pk,
        reversal_of=locked.journal_entry,
        lines=services._reverse_lines(locked.journal_entry),
    )
    reversal = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_REVERSAL,
        amount=original.amount,
        balance_effect=original.amount,
        exchange_rate=original.exchange_rate,
        transaction_date=reversal_date or timezone.localdate(),
        reference=original.reference,
        reason=reason,
        expense_claim=locked,
        original_transaction=original,
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    PettyCashTransaction.objects.filter(pk=original.pk).update(status=PettyCashTransaction.STATUS_REVERSED)
    ExpenseClaim.objects.filter(pk=locked.pk).update(status=ExpenseClaim.STATUS_REVERSED, updated_at=timezone.now())
    _approval(
        user=user, action=ExpenseApproval.ACTION_REVERSE, transaction_record=reversal,
        comments=reason, key=f'action:{idempotency_key}',
    )
    _audit(user=user, action='expense.reversed', instance=locked, message=reason, key=idempotency_key)
    return reversal


@transaction.atomic
def create_staff_advance(*, user, idempotency_key, **values):
    existing = StaffAdvance.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    currency = values['currency']
    if currency.company_id != user.company_id or not currency.is_active:
        raise ValidationError({'currency': ['Select an active company currency.']})
    amount = services.money(values['amount'])
    exchange_rate = validate_exchange_rate(
        company=user.company,
        currency=currency,
        exchange_rate=values.get('exchange_rate', Decimal('1')),
    )
    values['amount'] = amount
    values['exchange_rate'] = exchange_rate
    advance = services._save(StaffAdvance(
        company=user.company,
        number=services._next_number(
            user.company, FinanceDocumentSequence.TYPE_STAFF_ADVANCE, 'SADV', StaffAdvance,
        ),
        base_amount=services.money(amount * exchange_rate),
        created_by=user,
        idempotency_key=idempotency_key,
        **values,
    ))
    _audit(user=user, action='staff_advance.created', instance=advance, key=idempotency_key)
    return advance


@transaction.atomic
def update_draft_staff_advance(*, advance, user, values):
    locked = StaffAdvance.objects.select_for_update().get(pk=advance.pk, company=user.company)
    if locked.status != StaffAdvance.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft staff advances can be edited.']})
    for field, value in values.items():
        setattr(locked, field, value)
    if locked.currency.company_id != user.company_id or not locked.currency.is_active:
        raise ValidationError({'currency': ['Select an active company currency.']})
    locked.exchange_rate = validate_exchange_rate(
        company=user.company, currency=locked.currency, exchange_rate=locked.exchange_rate,
    )
    locked.base_amount = services.money(locked.amount * locked.exchange_rate)
    services._save(locked)
    _audit(user=user, action='staff_advance.updated', instance=locked)
    return locked


@transaction.atomic
def submit_staff_advance(*, advance, user, comments=''):
    locked = StaffAdvance.objects.select_for_update().get(pk=advance.pk, company=user.company)
    if locked.status != StaffAdvance.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft staff advances can be submitted.']})
    locked.status = StaffAdvance.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    services._save(locked, update_fields=['status', 'submitted_at', 'updated_at'])
    _approval(user=user, action=ExpenseApproval.ACTION_SUBMIT, advance=locked, comments=comments)
    _audit(user=user, action='staff_advance.submitted', instance=locked, message=comments)
    return locked


@transaction.atomic
def approve_staff_advance(*, advance, user, comments=''):
    locked = StaffAdvance.objects.select_for_update().get(pk=advance.pk, company=user.company)
    if locked.status not in {StaffAdvance.STATUS_SUBMITTED, StaffAdvance.STATUS_REVIEWED}:
        raise ValidationError({'status': ['Only submitted staff advances can be approved.']})
    _check_approval_controls(locked, user, locked.base_amount)
    _require_project_budget(locked, user)
    locked.status = StaffAdvance.STATUS_APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    services._save(locked, update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    _approval(user=user, action=ExpenseApproval.ACTION_APPROVE, advance=locked, comments=comments)
    _audit(user=user, action='staff_advance.approved', instance=locked, message=comments)
    return locked


@transaction.atomic
def reject_staff_advance(*, advance, user, reason):
    locked = StaffAdvance.objects.select_for_update().get(pk=advance.pk, company=user.company)
    if locked.status not in {StaffAdvance.STATUS_SUBMITTED, StaffAdvance.STATUS_REVIEWED}:
        raise ValidationError({'status': ['Only submitted staff advances can be rejected.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A rejection reason is required.']})
    locked.status = StaffAdvance.STATUS_REJECTED
    locked.rejection_reason = reason
    services._save(locked, update_fields=['status', 'rejection_reason', 'updated_at'])
    _approval(user=user, action=ExpenseApproval.ACTION_REJECT, advance=locked, comments=reason)
    _audit(user=user, action='staff_advance.rejected', instance=locked, message=reason)
    return locked


@transaction.atomic
def pay_staff_advance(*, advance, user, cash_account, payment_reference, idempotency_key, payment_date=None):
    existing = PettyCashTransaction.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.staff_advance_id != advance.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another transaction.']})
        return StaffAdvance.objects.get(pk=advance.pk)
    locked = StaffAdvance.objects.select_for_update().get(pk=advance.pk, company=user.company)
    if locked.status != StaffAdvance.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved staff advances can be paid.']})
    cash = _locked_cash(cash_account, user.company)
    if cash.currency_id != locked.currency_id:
        raise ValidationError({'cash_account': ['Cash account currency must match the advance currency.']})
    payment_reference = payment_reference.strip()
    if not payment_reference:
        raise ValidationError({'payment_reference': ['Payment reference is required.']})
    _require_cash(cash, locked.amount)
    from .ledger_services import resolve_mapping

    staff_advance_account = resolve_mapping(company=user.company, mapping_key='STAFF_ADVANCE')
    project = _destination_project(locked)
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=payment_date or timezone.localdate(),
        description=f'Pay staff advance {locked.number}',
        source_type=JournalEntry.SOURCE_STAFF_ADVANCE,
        source_object_id=locked.pk,
        lines=[
            {
                'account': staff_advance_account, 'project': project, 'supplier': None,
                'description': locked.number, 'debit': locked.base_amount, 'credit': ZERO,
            },
            {
                'account': cash.account, 'project': project, 'supplier': None,
                'description': payment_reference, 'debit': ZERO, 'credit': locked.base_amount,
            },
        ],
    )
    cash_transaction = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_ADVANCE,
        amount=locked.amount,
        balance_effect=-locked.amount,
        exchange_rate=locked.exchange_rate,
        transaction_date=payment_date or timezone.localdate(),
        reference=payment_reference,
        reason=f'Staff advance {locked.number}',
        staff_advance=locked,
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    locked.status = StaffAdvance.STATUS_PAID
    locked.cash_account = cash
    locked.payment_reference = payment_reference
    locked.posting_idempotency_key = idempotency_key
    locked.journal_entry = entry
    locked.paid_by = user
    locked.paid_at = timezone.now()
    services._save(locked, update_fields=[
        'status', 'cash_account', 'payment_reference', 'posting_idempotency_key', 'journal_entry',
        'paid_by', 'paid_at', 'updated_at',
    ])
    _approval(
        user=user, action=ExpenseApproval.ACTION_PAY, advance=locked,
        comments=payment_reference, key=f'action:{idempotency_key}',
    )
    _audit(
        user=user, action='staff_advance.paid', instance=locked,
        metadata={'cash_transaction': cash_transaction.pk}, key=idempotency_key,
    )
    if locked.due_date and locked.due_date < timezone.localdate():
        from .notification_services import check_finance_deadlines_for_company

        transaction.on_commit(lambda: check_finance_deadlines_for_company(user.company))
    return locked


@transaction.atomic
def retire_staff_advance(
    *, advance, user, expense_category, amount_spent, amount_refunded, reason,
    idempotency_key, retirement_date=None,
):
    existing = AdvanceRetirement.objects.filter(
        company=user.company, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.advance_id != advance.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another retirement.']})
        return existing
    locked = StaffAdvance.objects.select_for_update().select_related(
        'project', 'cost_centre__project', 'cash_account__account',
    ).get(pk=advance.pk, company=user.company)
    if locked.status not in {StaffAdvance.STATUS_PAID, StaffAdvance.STATUS_RETIRED}:
        raise ValidationError({'status': ['Only paid staff advances can be retired.']})
    amount_spent = services.money(amount_spent)
    amount_refunded = services.money(amount_refunded)
    total = services.money(amount_spent + amount_refunded)
    if total <= ZERO:
        raise ValidationError({'amount_spent': ['Spent or refunded amount must be greater than zero.']})
    if total > locked.outstanding_amount:
        raise ValidationError({'amount_spent': [f'Retirement exceeds outstanding advance of {locked.outstanding_amount}.']})
    if expense_category.company_id != user.company_id or not expense_category.is_active:
        raise ValidationError({'expense_category': ['Select an active company expense category.']})
    if not reason.strip():
        raise ValidationError({'reason': ['A retirement reason is required.']})
    project = _destination_project(locked)
    base_spent = services.money(amount_spent * locked.exchange_rate)
    base_refunded = services.money(amount_refunded * locked.exchange_rate)
    from .ledger_services import resolve_mapping

    staff_advance_account = resolve_mapping(company=user.company, mapping_key='STAFF_ADVANCE')
    retirement = services._save(AdvanceRetirement(
        company=user.company,
        advance=locked,
        expense_category=expense_category,
        amount_spent=amount_spent,
        amount_refunded=amount_refunded,
        total_retired=total,
        retirement_date=retirement_date or timezone.localdate(),
        reason=reason.strip(),
        idempotency_key=idempotency_key,
        retired_by=user,
    ))
    if amount_spent > ZERO:
        _record_budget_actual(
            record=retirement,
            category=expense_category,
            amount=base_spent,
            user=user,
            key=f'advance-retirement:{retirement.pk}:actual',
            description=f'Retire staff advance {locked.number}',
        )
    lines = []
    if base_spent > ZERO:
        lines.append({
            'account': expense_category.expense_account, 'project': project, 'supplier': None,
            'description': locked.number, 'debit': base_spent, 'credit': ZERO,
        })
    if base_refunded > ZERO:
        lines.append({
            'account': locked.cash_account.account, 'project': project, 'supplier': None,
            'description': locked.number, 'debit': base_refunded, 'credit': ZERO,
        })
    lines.append({
        'account': staff_advance_account, 'project': project, 'supplier': None,
        'description': locked.number, 'debit': ZERO, 'credit': services.money(base_spent + base_refunded),
    })
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=retirement.retirement_date,
        description=f'Retire staff advance {locked.number}',
        source_type=JournalEntry.SOURCE_ADVANCE_RETIREMENT,
        source_object_id=retirement.pk,
        lines=lines,
    )
    AdvanceRetirement.objects.filter(pk=retirement.pk).update(journal_entry=entry)
    retirement.journal_entry = entry
    if amount_refunded > ZERO:
        cash = _locked_cash(locked.cash_account, user.company)
        services._save(PettyCashTransaction(
            company=user.company,
            cash_account=cash,
            transaction_type=PettyCashTransaction.TYPE_REFUND,
            amount=amount_refunded,
            balance_effect=amount_refunded,
            exchange_rate=locked.exchange_rate,
            transaction_date=retirement.retirement_date,
            reference=locked.payment_reference,
            reason=f'Refund for {locked.number}',
            staff_advance=locked,
            advance_retirement=retirement,
            idempotency_key=f'cash:{idempotency_key}',
            journal_entry=entry,
            posted_by=user,
        ))
    outstanding = services.money(locked.outstanding_amount - total)
    StaffAdvance.objects.filter(pk=locked.pk).update(
        status=StaffAdvance.STATUS_RETIRED if outstanding == ZERO else StaffAdvance.STATUS_PAID,
        updated_at=timezone.now(),
    )
    _approval(
        user=user, action=ExpenseApproval.ACTION_RETIRE, advance=locked,
        comments=reason.strip(), key=f'action:{idempotency_key}',
    )
    _audit(
        user=user, action='staff_advance.retired', instance=retirement,
        metadata={'spent': amount_spent, 'refunded': amount_refunded}, key=idempotency_key,
    )
    return retirement


@transaction.atomic
def reverse_advance_retirement(
    *, retirement, user, reason, idempotency_key, reversal_date=None,
):
    existing = AdvanceRetirement.objects.filter(
        company=user.company, idempotency_key=idempotency_key,
    ).first()
    if existing:
        if existing.reversal_of_id != retirement.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another retirement reversal.']})
        return existing
    original = AdvanceRetirement.objects.select_for_update().select_related(
        'advance__cash_account__account', 'advance__project', 'advance__cost_centre__project',
        'expense_category', 'journal_entry',
    ).get(pk=retirement.pk, company=user.company)
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    if original.is_reversal or hasattr(original, 'reversal'):
        raise ValidationError({'non_field_errors': ['This retirement cannot be reversed again.']})
    advance = StaffAdvance.objects.select_for_update().get(pk=original.advance_id, company=user.company)
    cash = _locked_cash(advance.cash_account, user.company)
    refund_transaction = original.petty_cash_transactions.select_for_update().first()
    if refund_transaction:
        _require_cash(cash, refund_transaction.amount)
    reversal = services._save(AdvanceRetirement(
        company=user.company,
        advance=advance,
        expense_category=original.expense_category,
        amount_spent=original.amount_spent,
        amount_refunded=original.amount_refunded,
        total_retired=original.total_retired,
        retirement_date=reversal_date or timezone.localdate(),
        reason=reason,
        idempotency_key=idempotency_key,
        is_reversal=True,
        reversal_of=original,
        retired_by=user,
    ))
    for actual in original.budget_transactions.select_related('budget', 'budget_line').filter(
        transaction_type=BudgetTransaction.TYPE_ACTUAL,
    ):
        services._save(BudgetTransaction(
            company=user.company,
            budget=actual.budget,
            budget_line=actual.budget_line,
            transaction_type=BudgetTransaction.TYPE_ACTUAL_REVERSAL,
            amount=-actual.amount,
            advance_retirement=reversal,
            description=f'Reverse retirement of {advance.number}: {reason}',
            idempotency_key=f'{actual.idempotency_key}:reversal',
            created_by=user,
        ))
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=reversal.retirement_date,
        description=f'Reverse retirement of {advance.number}: {reason}',
        source_type=JournalEntry.SOURCE_ADVANCE_RETIREMENT_REVERSAL,
        source_object_id=reversal.pk,
        reversal_of=original.journal_entry,
        lines=services._reverse_lines(original.journal_entry),
    )
    AdvanceRetirement.objects.filter(pk=reversal.pk).update(journal_entry=entry)
    reversal.journal_entry = entry
    if refund_transaction:
        cash_reversal = services._save(PettyCashTransaction(
            company=user.company,
            cash_account=cash,
            transaction_type=PettyCashTransaction.TYPE_REVERSAL,
            amount=refund_transaction.amount,
            balance_effect=-refund_transaction.amount,
            exchange_rate=refund_transaction.exchange_rate,
            transaction_date=reversal.retirement_date,
            reference=refund_transaction.reference,
            reason=reason,
            staff_advance=advance,
            advance_retirement=reversal,
            original_transaction=refund_transaction,
            idempotency_key=f'cash:{idempotency_key}',
            journal_entry=entry,
            posted_by=user,
        ))
        PettyCashTransaction.objects.filter(pk=refund_transaction.pk).update(
            status=PettyCashTransaction.STATUS_REVERSED,
        )
    StaffAdvance.objects.filter(pk=advance.pk).update(
        status=StaffAdvance.STATUS_PAID,
        updated_at=timezone.now(),
    )
    _approval(
        user=user, action=ExpenseApproval.ACTION_REVERSE, advance=advance,
        comments=reason, key=f'action:{idempotency_key}',
    )
    _audit(
        user=user, action='staff_advance.retirement_reversed', instance=reversal,
        message=reason, key=idempotency_key,
    )
    return reversal


@transaction.atomic
def reverse_staff_advance(*, advance, user, reason, idempotency_key, reversal_date=None):
    existing = PettyCashTransaction.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.staff_advance_id != advance.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another transaction.']})
        return existing
    locked = StaffAdvance.objects.select_for_update().select_related(
        'cash_account__account', 'journal_entry',
    ).get(pk=advance.pk, company=user.company)
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    if locked.status != StaffAdvance.STATUS_PAID or locked.retirements.exists():
        raise ValidationError({'status': ['Only an unretired paid advance can be reversed.']})
    original = PettyCashTransaction.objects.select_for_update().get(
        company=user.company, staff_advance=locked, transaction_type=PettyCashTransaction.TYPE_ADVANCE,
    )
    cash = _locked_cash(locked.cash_account, user.company)
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=reversal_date or timezone.localdate(),
        description=f'Reverse staff advance {locked.number}: {reason}',
        source_type=JournalEntry.SOURCE_ADVANCE_REVERSAL,
        source_object_id=locked.pk,
        reversal_of=locked.journal_entry,
        lines=services._reverse_lines(locked.journal_entry),
    )
    reversal = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_REVERSAL,
        amount=original.amount,
        balance_effect=original.amount,
        exchange_rate=original.exchange_rate,
        transaction_date=reversal_date or timezone.localdate(),
        reference=original.reference,
        reason=reason,
        staff_advance=locked,
        original_transaction=original,
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    PettyCashTransaction.objects.filter(pk=original.pk).update(status=PettyCashTransaction.STATUS_REVERSED)
    StaffAdvance.objects.filter(pk=locked.pk).update(status=StaffAdvance.STATUS_REVERSED, updated_at=timezone.now())
    _approval(
        user=user, action=ExpenseApproval.ACTION_REVERSE, transaction_record=reversal,
        comments=reason, key=f'action:{idempotency_key}',
    )
    _audit(user=user, action='staff_advance.reversed', instance=locked, message=reason, key=idempotency_key)
    return reversal


@transaction.atomic
def replenish_cash_account(
    *, cash_account, user, source_account, amount, exchange_rate, reference,
    reason, idempotency_key, transaction_date=None,
):
    existing = PettyCashTransaction.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.cash_account_id != cash_account.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another transaction.']})
        return existing
    cash = _locked_cash(cash_account, user.company)
    if source_account.company_id != user.company_id or source_account.account_type != Account.TYPE_ASSET:
        raise ValidationError({'source_account': ['Select a company asset account.']})
    if source_account.pk == cash.account_id:
        raise ValidationError({'source_account': ['Source account must differ from the cash account.']})
    amount = services.money(amount)
    exchange_rate = validate_exchange_rate(
        company=user.company, currency=cash.currency, exchange_rate=exchange_rate,
    )
    base_amount = services.money(amount * exchange_rate)
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=transaction_date or timezone.localdate(),
        description=f'Replenish {cash.name}: {reason}',
        source_type=JournalEntry.SOURCE_PETTY_CASH,
        source_object_id=cash.pk,
        lines=[
            {
                'account': cash.account, 'project': None, 'supplier': None,
                'description': reference, 'debit': base_amount, 'credit': ZERO,
            },
            {
                'account': source_account, 'project': None, 'supplier': None,
                'description': reference, 'debit': ZERO, 'credit': base_amount,
            },
        ],
    )
    record = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_REPLENISHMENT,
        amount=amount,
        balance_effect=amount,
        exchange_rate=exchange_rate,
        transaction_date=transaction_date or timezone.localdate(),
        reference=reference.strip(),
        reason=reason.strip(),
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    _approval(
        user=user, action=ExpenseApproval.ACTION_REPLENISH, transaction_record=record,
        comments=reason, key=f'action:{idempotency_key}',
    )
    _audit(user=user, action='petty_cash.replenished', instance=record, key=idempotency_key)
    return record


@transaction.atomic
def reverse_petty_cash_transaction(*, transaction_record, user, reason, idempotency_key, reversal_date=None):
    existing = PettyCashTransaction.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        return existing
    original = PettyCashTransaction.objects.select_for_update().select_related(
        'cash_account__account', 'journal_entry',
    ).get(pk=transaction_record.pk, company=user.company)
    if original.status == PettyCashTransaction.STATUS_REVERSED or hasattr(original, 'reversal_transaction'):
        raise ValidationError({'non_field_errors': ['This petty-cash transaction is already reversed.']})
    if original.transaction_type not in {PettyCashTransaction.TYPE_REPLENISHMENT}:
        raise ValidationError({'transaction_type': ['Reverse linked expenses or advances through their own endpoint.']})
    reason = reason.strip()
    if not reason:
        raise ValidationError({'reason': ['A reversal reason is required.']})
    cash = _locked_cash(original.cash_account, user.company)
    if original.balance_effect > ZERO:
        _require_cash(cash, original.amount)
    entry = services._create_journal(
        company=user.company,
        user=user,
        date=reversal_date or timezone.localdate(),
        description=f'Reverse petty cash transaction {original.pk}: {reason}',
        source_type=JournalEntry.SOURCE_PETTY_CASH_REVERSAL,
        source_object_id=original.pk,
        reversal_of=original.journal_entry,
        lines=services._reverse_lines(original.journal_entry),
    )
    reversal = services._save(PettyCashTransaction(
        company=user.company,
        cash_account=cash,
        transaction_type=PettyCashTransaction.TYPE_REVERSAL,
        amount=original.amount,
        balance_effect=-original.balance_effect,
        exchange_rate=original.exchange_rate,
        transaction_date=reversal_date or timezone.localdate(),
        reference=original.reference,
        reason=reason,
        original_transaction=original,
        idempotency_key=idempotency_key,
        journal_entry=entry,
        posted_by=user,
    ))
    PettyCashTransaction.objects.filter(pk=original.pk).update(status=PettyCashTransaction.STATUS_REVERSED)
    _approval(
        user=user, action=ExpenseApproval.ACTION_REVERSE, transaction_record=reversal,
        comments=reason, key=f'action:{idempotency_key}',
    )
    _audit(user=user, action='petty_cash.reversed', instance=original, message=reason, key=idempotency_key)
    return reversal


@transaction.atomic
def create_expense_receipt(*, claim, user, uploaded_file, expense_item=None):
    locked = ExpenseClaim.objects.select_for_update().get(pk=claim.pk, company=user.company)
    if locked.status in {ExpenseClaim.STATUS_PAID, ExpenseClaim.STATUS_CLOSED, ExpenseClaim.STATUS_REVERSED}:
        raise ValidationError({'claim': ['Receipts cannot be added to a posted claim.']})
    if expense_item and (expense_item.company_id != user.company_id or expense_item.claim_id != locked.pk):
        raise ValidationError({'expense_item': ['Expense item must belong to this company claim.']})
    if uploaded_file.size > 10 * 1024 * 1024:
        raise ValidationError({'file': ['Attachments cannot exceed 10 MB.']})
    validate_image_upload(uploaded_file)
    content_type = getattr(uploaded_file, 'content_type', '')
    if content_type not in {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}:
        raise ValidationError({'file': ['Only PDF, JPEG, PNG, and WebP files are allowed.']})
    receipt = services._save(ExpenseReceiptAttachment(
        company=user.company,
        claim=locked,
        expense_item=expense_item,
        file=uploaded_file,
        original_name=Path(uploaded_file.name).name[:255],
        content_type=content_type,
        size=uploaded_file.size,
        uploaded_by=user,
    ))
    _audit(user=user, action='expense.receipt_added', instance=receipt)
    return receipt
