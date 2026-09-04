from django.db.models import Q

from apps.procurement.models import GoodsReceivedNote, SupplierClaim

from .models import BankStatementLine, JournalEntry, Payment, SupplierInvoice


def checklist(*, company, period):
    """Return the period-close control pack and the blockers that must be cleared."""
    in_period = Q(receipt_date__gte=period.start_date, receipt_date__lte=period.end_date)
    grns = GoodsReceivedNote.objects.filter(company=company, status=GoodsReceivedNote.STATUS_ACCEPTED).filter(in_period)
    unmatched_grns = grns.exclude(purchase_order__supplier_invoices__status__in=[
        SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID,
    ]).distinct()
    unmatched_invoices = SupplierInvoice.objects.filter(
        company=company, invoice_date__gte=period.start_date, invoice_date__lte=period.end_date,
        status__in=[
            SupplierInvoice.STATUS_SUBMITTED, SupplierInvoice.STATUS_MATCHED,
            SupplierInvoice.STATUS_MATCH_EXCEPTION, SupplierInvoice.STATUS_VERIFIED,
            SupplierInvoice.STATUS_APPROVED,
        ],
    )
    pending_payments = Payment.objects.filter(
        company=company, payment_date__gte=period.start_date, payment_date__lte=period.end_date,
        status__in=[Payment.STATUS_DRAFT, Payment.STATUS_SUBMITTED, Payment.STATUS_APPROVED],
    )
    unreconciled = BankStatementLine.objects.filter(
        company=company, statement_date__gte=period.start_date, statement_date__lte=period.end_date,
        status=BankStatementLine.STATUS_UNRECONCILED,
    )
    open_claims = SupplierClaim.objects.filter(
        company=company, created_at__date__gte=period.start_date, created_at__date__lte=period.end_date,
    ).exclude(status__in=[SupplierClaim.STATUS_RESOLVED, SupplierClaim.STATUS_CANCELLED])
    draft_journals = JournalEntry.objects.filter(
        company=company, date__gte=period.start_date, date__lte=period.end_date,
        status=JournalEntry.STATUS_DRAFT,
    )
    checks = [
        {'key': 'unmatched_grns', 'label': 'Received goods without a posted supplier invoice', 'count': unmatched_grns.count(), 'blocking': True},
        {'key': 'unmatched_invoices', 'label': 'Invoices awaiting matching, approval, or posting', 'count': unmatched_invoices.count(), 'blocking': True},
        {'key': 'pending_payments', 'label': 'Draft, submitted, or approved payments not yet posted', 'count': pending_payments.count(), 'blocking': True},
        {'key': 'unreconciled_cash', 'label': 'Unreconciled bank or cash statement lines', 'count': unreconciled.count(), 'blocking': True},
        {'key': 'open_supplier_claims', 'label': 'Unresolved supplier claims raised in the period', 'count': open_claims.count(), 'blocking': True},
        # Draft journals are surfaced for month-end follow-up, but do not stop
        # period closure by themselves; the posting guard still prevents them
        # from being posted after the period is closed.
        {'key': 'draft_journals', 'label': 'Draft journals dated in the period', 'count': draft_journals.count(), 'blocking': False},
    ]
    return {
        'period': {'id': period.pk, 'name': period.name, 'start_date': period.start_date, 'end_date': period.end_date},
        'checks': checks,
        'is_ready': not any(check['blocking'] and check['count'] for check in checks),
    }
