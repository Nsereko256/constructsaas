"""Reusable Finance read query definitions."""

from .models import (
    BudgetApproval,
    ExpenseClaim,
    Payment,
    PaymentBatch,
    StaffAdvance,
    SupplierInvoice,
)


def supplier_invoice_queryset():
    return SupplierInvoice.objects.select_related(
        'supplier', 'purchase_order', 'project', 'created_by',
    ).prefetch_related('items__material', 'items__purchase_order_item', 'payments')


def payment_queryset():
    return Payment.objects.select_related(
        'supplier', 'invoice', 'source_account', 'currency', 'created_by',
        'approved_by', 'posted_by', 'journal_entry',
    ).prefetch_related('allocations__invoice', 'approvals')


def payment_batch_queryset():
    return PaymentBatch.objects.select_related(
        'source_account', 'currency', 'created_by', 'approved_by', 'released_by',
    ).prefetch_related('items__payment__supplier')


def expense_claim_queryset():
    return ExpenseClaim.objects.select_related(
        'claimant', 'project', 'cost_centre', 'overhead_category', 'currency',
        'cash_account', 'created_by', 'reviewed_by', 'approved_by', 'paid_by',
    ).prefetch_related('items__category', 'receipts', 'approvals')


def submitted_budget_approvals(company):
    return BudgetApproval.objects.for_company(company).filter(
        status=BudgetApproval.STATUS_SUBMITTED,
    )


def submitted_payments(company):
    return Payment.objects.for_company(company).filter(status=Payment.STATUS_SUBMITTED)


def pending_expense_claims(company):
    return ExpenseClaim.objects.for_company(company).filter(
        status__in=[ExpenseClaim.STATUS_SUBMITTED, ExpenseClaim.STATUS_REVIEWED],
    )


def pending_staff_advances(company):
    return StaffAdvance.objects.for_company(company).filter(
        status__in=[StaffAdvance.STATUS_SUBMITTED, StaffAdvance.STATUS_REVIEWED],
    )
