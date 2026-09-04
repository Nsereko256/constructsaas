from decimal import Decimal
from pathlib import Path

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .configuration_services import record_finance_audit_event, validate_exchange_rate
from apps.api.upload_validation import validate_image_upload
from .models import (
    Account,
    FinanceDocumentSequence,
    FinanceSettings,
    InvoiceReversal,
    JournalEntry,
    Payment,
    PaymentAllocation,
    PaymentApproval,
    PaymentAttachment,
    PaymentReversal,
    ProjectCost,
    SupplierAdvance,
    SupplierCreditNote,
    SupplierInvoice,
)
from .services import (
    ZERO,
    _create_journal,
    _next_number,
    _reverse_lines,
    _save,
    base_money,
    ensure_system_accounts,
    money,
)


BALANCE_ALLOCATION_STATUSES = [PaymentAllocation.STATUS_APPROVED, PaymentAllocation.STATUS_POSTED]


def approved_allocations(invoice, *, exclude_payment=None):
    queryset = invoice.payment_allocations.filter(
        status__in=BALANCE_ALLOCATION_STATUSES, payment__reversal__isnull=True,
    )
    if exclude_payment:
        queryset = queryset.exclude(payment=exclude_payment)
    return money(queryset.aggregate(total=Sum('amount'))['total'] or ZERO)


def approved_credit_notes(invoice):
    return money(invoice.credit_notes.filter(status=SupplierCreditNote.STATUS_POSTED).aggregate(
        total=Sum('total_amount'),
    )['total'] or ZERO)


def invoice_balance(invoice, *, exclude_payment=None):
    return money(max(
        invoice.total_amount - approved_allocations(invoice, exclude_payment=exclude_payment)
        - approved_credit_notes(invoice), ZERO,
    ))


def invoice_balance_totals(invoices):
    """Resolve balances for a list in two aggregate queries instead of per invoice."""
    invoices = list(invoices)
    invoice_ids = [invoice.pk for invoice in invoices]
    allocations = dict(PaymentAllocation.objects.filter(
        invoice_id__in=invoice_ids,
        status__in=BALANCE_ALLOCATION_STATUSES,
        payment__reversal__isnull=True,
    ).values_list('invoice_id').annotate(total=Sum('amount')))
    credits = dict(SupplierCreditNote.objects.filter(
        invoice_id__in=invoice_ids,
        status=SupplierCreditNote.STATUS_POSTED,
    ).values_list('invoice_id').annotate(total=Sum('total_amount')))
    return {
        invoice.pk: {
            'payments': money(allocations.get(invoice.pk, ZERO)),
            'credits': money(credits.get(invoice.pk, ZERO)),
            'balance': money(max(
                invoice.total_amount
                - allocations.get(invoice.pk, ZERO)
                - credits.get(invoice.pk, ZERO),
                ZERO,
            )),
        }
        for invoice in invoices
    }


def _refresh_invoice(invoice):
    allocated = approved_allocations(invoice)
    balance = invoice_balance(invoice)
    status = SupplierInvoice.STATUS_POSTED
    if allocated > ZERO:
        status = SupplierInvoice.STATUS_PAID if balance == ZERO else SupplierInvoice.STATUS_PARTIALLY_PAID
    SupplierInvoice.objects.filter(pk=invoice.pk).update(status=status, updated_at=timezone.now())


def _action(payment, user, action, comments='', idempotency_key=''):
    approval = PaymentApproval(
        company=user.company, payment=payment, action=action, comments=comments,
        acted_by=user, idempotency_key=idempotency_key,
    )
    _save(approval)
    record_finance_audit_event(
        company=user.company, actor=user, action=f'payment.{action.lower()}',
        object_type='Payment', object_id=payment.pk, message=comments,
        correlation_id=idempotency_key,
    )
    return approval


@transaction.atomic
def create_payment(
    *, user, supplier, source_account, currency, amount, payment_date, method,
    reference='', voucher_reference='', notes='', exchange_rate=Decimal('1'), idempotency_key,
    client_uuid=None,
):
    existing = Payment.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.supplier_id != supplier.pk or existing.amount != money(amount):
            raise ValidationError({'idempotency_key': ['This key was used for a different payment.']})
        return existing
    for field, value in [('supplier', supplier), ('source_account', source_account), ('currency', currency)]:
        if value.company_id != user.company_id:
            raise ValidationError({field: ['Selection must belong to your company.']})
    if not source_account.is_active or source_account.account_type != Account.TYPE_ASSET or not currency.is_active:
        raise ValidationError({'non_field_errors': ['Payment account must be an active asset account and currency must be active.']})
    amount = money(amount)
    exchange_rate = validate_exchange_rate(
        company=user.company, currency=currency, exchange_rate=exchange_rate,
    )
    if amount <= ZERO:
        raise ValidationError({'amount': ['Amount must be greater than zero.']})
    reference = reference.strip()
    if reference and Payment.objects.filter(
        company=user.company, source_account=source_account, reference=reference,
    ).exists():
        raise ValidationError({'reference': ['This transaction reference already exists for the selected account.']})
    payment = Payment(
        company=user.company, supplier=supplier, source_account=source_account,
        currency=currency, exchange_rate=exchange_rate,
        number=_next_number(user.company, FinanceDocumentSequence.TYPE_PAYMENT, 'PAY', Payment),
        amount=amount, payment_date=payment_date, method=method, reference=reference,
        voucher_reference=voucher_reference.strip(), notes=notes, idempotency_key=idempotency_key,
        client_uuid=client_uuid,
        created_by=user, status=Payment.STATUS_DRAFT,
    )
    return _save(payment)


@transaction.atomic
def update_draft_payment(*, payment, user, values):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status != Payment.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft payments can be edited.']})
    for field in ('source_account', 'currency', 'exchange_rate', 'amount', 'payment_date', 'method',
                  'reference', 'voucher_reference', 'notes'):
        if field in values:
            setattr(locked, field, values[field])
    if (
        not locked.source_account_id
        or locked.source_account.company_id != user.company_id
        or not locked.source_account.is_active
        or locked.source_account.account_type != Account.TYPE_ASSET
    ):
        raise ValidationError({'source_account': ['Select an active company asset account.']})
    if (
        not locked.currency_id
        or locked.currency.company_id != user.company_id
        or not locked.currency.is_active
    ):
        raise ValidationError({'currency': ['Select an active company currency.']})
    locked.amount = money(locked.amount)
    locked.exchange_rate = validate_exchange_rate(
        company=user.company, currency=locked.currency, exchange_rate=locked.exchange_rate,
    )
    if locked.amount <= ZERO:
        raise ValidationError({'amount': ['Amount must be greater than zero.']})
    locked.reference = locked.reference.strip()
    if locked.reference and Payment.objects.filter(
        company=user.company,
        source_account=locked.source_account,
        reference=locked.reference,
    ).exclude(pk=locked.pk).exists():
        raise ValidationError({'reference': ['This transaction reference already exists for the selected account.']})
    if locked.allocated_amount > locked.amount:
        raise ValidationError({'amount': ['Amount cannot be less than existing allocations.']})
    return _save(locked)


@transaction.atomic
def allocate_payment(*, payment, user, invoice, amount):
    # Lock the payment without joining nullable account/currency relations.
    # PostgreSQL rejects FOR UPDATE when a nullable-side outer join is present.
    locked = Payment.objects.select_for_update().get(
        pk=payment.pk, company=user.company,
    )
    if locked.status != Payment.STATUS_DRAFT:
        raise ValidationError({'status': ['Allocations can only change while payment is draft.']})
    invoice = SupplierInvoice.objects.select_for_update().get(pk=invoice.pk, company=user.company)
    if invoice.supplier_id != locked.supplier_id or invoice.status not in {
        SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID,
    } or hasattr(invoice, 'reversal'):
        raise ValidationError({'invoice': ['Select an active posted invoice for this supplier.']})
    if locked.currency.code != invoice.currency:
        raise ValidationError({
            'invoice': ['Payment and invoice currencies must match; use a separate payment per currency.'],
        })
    amount = money(amount)
    if amount <= ZERO:
        raise ValidationError({'amount': ['Allocation must be greater than zero.']})
    existing = PaymentAllocation.objects.filter(payment=locked, invoice=invoice).first()
    existing_amount = existing.amount if existing else ZERO
    if money(locked.allocated_amount - existing_amount + amount) > locked.amount:
        raise ValidationError({'amount': ['Allocations cannot exceed the payment amount.']})
    if amount > invoice_balance(invoice):
        raise ValidationError({'amount': [f'Allocation exceeds the invoice balance of {invoice_balance(invoice)}.']})
    if existing:
        existing.amount = amount
        _save(existing)
        allocation = existing
    else:
        allocation = PaymentAllocation(
            company=user.company, payment=locked, invoice=invoice, amount=amount, created_by=user,
        )
        _save(allocation)
    if not locked.invoice_id and locked.allocations.count() == 1:
        Payment.objects.filter(pk=locked.pk).update(invoice=invoice)
    _action(locked, user, PaymentApproval.ACTION_ALLOCATE, comments=f'{invoice.internal_number}: {amount}')
    return allocation


@transaction.atomic
def unallocate_payment(*, payment, user, invoice):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status != Payment.STATUS_DRAFT:
        raise ValidationError({'status': ['Allocations cannot be removed after submission.']})
    allocation = PaymentAllocation.objects.select_for_update().filter(
        payment=locked, invoice=invoice, company=user.company,
    ).first()
    if not allocation:
        raise ValidationError({'invoice': ['This invoice is not allocated to the payment.']})
    amount = allocation.amount
    PaymentAllocation.objects.filter(pk=allocation.pk).delete()
    _action(locked, user, PaymentApproval.ACTION_UNALLOCATE, comments=f'{invoice.internal_number}: {amount}')


@transaction.atomic
def submit_payment(*, payment, user):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status != Payment.STATUS_DRAFT:
        raise ValidationError({'status': ['Only draft payments can be submitted.']})
    settings = FinanceSettings.objects.select_for_update().get(company=user.company)
    if settings.require_payment_attachment and not locked.attachments.exists():
        raise ValidationError({'attachments': ['Attach payment support before submitting the voucher.']})
    locked.status = Payment.STATUS_SUBMITTED
    locked.submitted_at = timezone.now()
    _save(locked, update_fields=['status', 'submitted_at'])
    _action(locked, user, PaymentApproval.ACTION_SUBMIT)
    from .notification_services import payment_awaiting_approval

    transaction.on_commit(lambda: payment_awaiting_approval(locked))
    return locked


@transaction.atomic
def approve_payment(*, payment, user, authorize_advance=False, advance_reason=''):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status != Payment.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted payments can be approved.']})
    settings = FinanceSettings.objects.select_for_update().get(company=user.company)
    if settings.maker_checker_enforced and locked.created_by_id == user.pk:
        raise ValidationError({'non_field_errors': ['Maker-checker policy prevents self-approval.']})
    from .approval_routing_services import require_approver
    require_approver(
        user=user, company=locked.company,
        document_type='PAYMENT', amount=locked.amount,
        project=locked.invoice.project if locked.invoice_id else None,
    )
    allocations = list(locked.allocations.select_for_update().select_related('invoice').order_by('invoice_id'))
    invoices = {invoice.pk: invoice for invoice in SupplierInvoice.objects.select_for_update().filter(
        pk__in=[allocation.invoice_id for allocation in allocations], company=user.company,
    ).order_by('pk')}
    for allocation in allocations:
        invoice = invoices[allocation.invoice_id]
        balance = invoice_balance(invoice, exclude_payment=locked)
        if allocation.amount > balance:
            raise ValidationError({'allocations': [{invoice.pk: [f'Allocation exceeds balance of {balance}.']}]})
    unallocated = money(locked.amount - sum((item.amount for item in allocations), ZERO))
    if unallocated > ZERO:
        if not authorize_advance:
            raise ValidationError({'advance': [f'{unallocated} is unallocated; authorize it as a supplier advance.']})
        if not advance_reason.strip():
            raise ValidationError({'advance_reason': ['A reason is required for a supplier advance.']})
        _save(SupplierAdvance(
            company=user.company, supplier=locked.supplier, payment=locked, amount=unallocated,
            reason=advance_reason.strip(), authorized_by=user,
        ))
    PaymentAllocation.objects.filter(payment=locked).update(status=PaymentAllocation.STATUS_APPROVED)
    locked.status = Payment.STATUS_APPROVED
    locked.approved_by = user
    locked.approved_at = timezone.now()
    _save(locked, update_fields=['status', 'approved_by', 'approved_at'])
    for invoice in invoices.values():
        _refresh_invoice(invoice)
    _action(locked, user, PaymentApproval.ACTION_APPROVE, comments=advance_reason)
    from .notification_services import payment_decided

    transaction.on_commit(lambda: payment_decided(locked, True))
    return locked


@transaction.atomic
def reject_payment(*, payment, user, reason):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status != Payment.STATUS_SUBMITTED:
        raise ValidationError({'status': ['Only submitted payments can be rejected.']})
    if not reason.strip():
        raise ValidationError({'reason': ['A rejection reason is required.']})
    locked.status = Payment.STATUS_REJECTED
    locked.rejection_reason = reason.strip()
    _save(locked, update_fields=['status', 'rejection_reason'])
    _action(locked, user, PaymentApproval.ACTION_REJECT, comments=reason.strip())
    from .notification_services import payment_decided

    transaction.on_commit(lambda: payment_decided(locked, False))
    return locked


@transaction.atomic
def post_payment(*, payment, user, idempotency_key):
    # Lock the voucher without joining nullable account/currency relations.
    locked = Payment.objects.select_for_update().get(
        pk=payment.pk, company=user.company,
    )
    existing = JournalEntry.objects.filter(
        company=user.company, source_type=JournalEntry.SOURCE_PAYMENT, source_object_id=locked.pk,
    ).first()
    if existing:
        return existing
    if locked.status != Payment.STATUS_APPROVED:
        raise ValidationError({'status': ['Only approved payments can be posted.']})
    if PaymentApproval.objects.filter(company=user.company, idempotency_key=f'post:{idempotency_key}').exists():
        raise ValidationError({'idempotency_key': ['This posting key has already been used.']})
    allocations = list(locked.allocations.select_for_update())
    from .ledger_services import resolve_mapping, resolve_rule_accounts
    from .models import PostingRule

    payment_debit, _ = resolve_rule_accounts(
        company=user.company, event_type=PostingRule.EVENT_SUPPLIER_PAYMENT,
    )
    lines = [{
        'account': payment_debit, 'project': allocation.invoice.project,
        'supplier': locked.supplier, 'description': allocation.invoice.internal_number,
        'debit': base_money(allocation.amount, allocation.invoice.exchange_rate), 'credit': ZERO,
    } for allocation in allocations]
    if hasattr(locked, 'supplier_advance'):
        lines.append({
            'account': resolve_mapping(company=user.company, mapping_key='SUPPLIER_ADVANCE'), 'project': None,
            'supplier': locked.supplier, 'description': locked.number,
            'debit': base_money(locked.supplier_advance.amount, locked.exchange_rate), 'credit': ZERO,
        })
    base_payment_amount = base_money(locked.amount, locked.exchange_rate)
    debit_total = money(sum((line['debit'] for line in lines), ZERO))
    fx_difference = money(base_payment_amount - debit_total)
    if fx_difference:
        fx_account = resolve_mapping(company=user.company, mapping_key='REALIZED_FX_GAIN_LOSS')
        lines.append({
            'account': fx_account,
            'project': None,
            'supplier': locked.supplier,
            'description': f'Exchange difference on {locked.number}',
            'debit': fx_difference if fx_difference > ZERO else ZERO,
            'credit': abs(fx_difference) if fx_difference < ZERO else ZERO,
        })
    lines.append({
        'account': locked.source_account, 'project': None, 'supplier': locked.supplier,
        'description': locked.reference or locked.number, 'debit': ZERO, 'credit': base_payment_amount,
    })
    entry = _create_journal(
        company=user.company, user=user, date=locked.payment_date,
        description=f'Post payment voucher {locked.number}', source_type=JournalEntry.SOURCE_PAYMENT,
        source_object_id=locked.pk, lines=lines,
    )
    for allocation in allocations:
        invoice = allocation.invoice
        if invoice.project_id:
            _save(ProjectCost(
                company=user.company, project=invoice.project, supplier_invoice=invoice,
                payment=locked, journal_entry=entry,
                amount=base_money(allocation.amount, invoice.exchange_rate),
                date=locked.payment_date, description=f'Paid cost for {invoice.internal_number}',
            ))
    PaymentAllocation.objects.filter(payment=locked).update(status=PaymentAllocation.STATUS_POSTED)
    locked.status = Payment.STATUS_POSTED
    locked.posted_by = user
    locked.posted_at = timezone.now()
    locked.journal_entry = entry
    _save(locked, update_fields=['status', 'posted_by', 'posted_at', 'journal_entry'])
    _action(locked, user, PaymentApproval.ACTION_POST, idempotency_key=f'post:{idempotency_key}')
    return entry


@transaction.atomic
def reverse_posted_payment(*, payment, user, reason, idempotency_key, reversal_date=None):
    existing = PaymentReversal.objects.filter(company=user.company, idempotency_key=idempotency_key).first()
    if existing:
        if existing.payment_id != payment.pk:
            raise ValidationError({'idempotency_key': ['This key was used for another reversal.']})
        return existing
    locked = Payment.objects.select_for_update().select_related('journal_entry').get(
        pk=payment.pk, company=user.company,
    )
    if locked.status != Payment.STATUS_POSTED or hasattr(locked, 'reversal'):
        raise ValidationError({'status': ['Only an active posted payment can be reversed.']})
    if not reason.strip():
        raise ValidationError({'reason': ['A reversal reason is required.']})
    allocations = list(locked.allocations.select_for_update().select_related('invoice').order_by('invoice_id'))
    list(SupplierInvoice.objects.select_for_update().filter(
        pk__in=[item.invoice_id for item in allocations], company=user.company,
    ).order_by('pk'))
    entry = _create_journal(
        company=user.company, user=user, date=reversal_date or timezone.localdate(),
        description=f'Reverse payment {locked.number}: {reason.strip()}',
        source_type=JournalEntry.SOURCE_PAYMENT_REVERSAL, source_object_id=locked.pk,
        reversal_of=locked.journal_entry, lines=_reverse_lines(locked.journal_entry),
    )
    reversal = PaymentReversal(
        company=user.company, payment=locked, journal_entry=entry, reason=reason.strip(),
        idempotency_key=idempotency_key, reversed_by=user,
    )
    reversal_costs = []
    for original in locked.project_costs.filter(is_reversal=False):
        cost = ProjectCost(
            company=user.company, project=original.project, supplier_invoice=original.supplier_invoice,
            payment=locked, journal_entry=entry, amount=original.amount, date=entry.date,
            description=f'Reversal of {original.description}', is_reversal=True, reversal_of=original,
        )
        _save(cost)
        reversal_costs.append(cost)
    if reversal_costs:
        reversal.project_cost = reversal_costs[0]
    _save(reversal)
    PaymentAllocation.objects.filter(payment=locked).update(status=PaymentAllocation.STATUS_REVERSED)
    if hasattr(locked, 'supplier_advance'):
        SupplierAdvance.objects.filter(pk=locked.supplier_advance.pk).update(status=SupplierAdvance.STATUS_REVERSED)
    Payment.objects.filter(pk=locked.pk).update(status=Payment.STATUS_REVERSED)
    for allocation in allocations:
        _refresh_invoice(allocation.invoice)
    _action(locked, user, PaymentApproval.ACTION_REVERSE, comments=reason.strip())
    return reversal


@transaction.atomic
def create_payment_attachment(*, payment, user, uploaded_file):
    locked = Payment.objects.select_for_update().get(pk=payment.pk, company=user.company)
    if locked.status in {Payment.STATUS_POSTED, Payment.STATUS_REVERSED}:
        raise ValidationError({'status': ['Posted payment attachments cannot be changed.']})
    if uploaded_file.size > 10 * 1024 * 1024:
        raise ValidationError({'file': ['Attachments cannot exceed 10 MB.']})
    validate_image_upload(uploaded_file)
    content_type = getattr(uploaded_file, 'content_type', '')
    if content_type not in {'application/pdf', 'image/jpeg', 'image/png', 'image/webp'}:
        raise ValidationError({'file': ['Only PDF, JPEG, PNG, and WebP files are allowed.']})
    return _save(PaymentAttachment(
        company=user.company, payment=locked, file=uploaded_file,
        original_name=Path(uploaded_file.name).name[:255], content_type=content_type,
        size=uploaded_file.size, uploaded_by=user,
    ))
