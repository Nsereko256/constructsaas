import django_filters

from .models import (
    BudgetApproval,
    BudgetCategory,
    BudgetRevision,
    BudgetTransaction,
    BudgetTransfer,
    BankStatementLine,
    AccountMapping,
    ChartOfAccount,
    CostCentre,
    CashAccount,
    Currency,
    FinanceAuditEvent,
    FiscalPeriod,
    ExpenseCategory,
    ExpenseClaim,
    JournalEntry,
    JournalReversal,
    LandedCostDocument,
    Payment,
    PettyCashTransaction,
    PostingRule,
    ProjectCost,
    ProjectBudget,
    SupplierInvoice,
    SupplierCreditNote,
    StaffAdvance,
    TaxCode,
)


class BankStatementLineFilter(django_filters.FilterSet):
    statement_date_from = django_filters.DateFilter(field_name='statement_date', lookup_expr='gte')
    statement_date_to = django_filters.DateFilter(field_name='statement_date', lookup_expr='lte')

    class Meta:
        model = BankStatementLine
        fields = ['cash_account', 'status', 'payment', 'statement_date_from', 'statement_date_to']


class ProjectBudgetFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    project_site = django_filters.NumberFilter(field_name='project__sites__id')

    class Meta:
        model = ProjectBudget
        fields = ['project', 'project_site', 'status', 'created_by', 'approved_by', 'created_from', 'created_to']


class BudgetRevisionFilter(django_filters.FilterSet):
    approved_from = django_filters.DateFilter(field_name='approved_at', lookup_expr='date__gte')
    approved_to = django_filters.DateFilter(field_name='approved_at', lookup_expr='date__lte')

    class Meta:
        model = BudgetRevision
        fields = ['budget', 'budget_line', 'approved_by', 'approved_from', 'approved_to']


class BudgetTransferFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = BudgetTransfer
        fields = ['budget', 'from_line', 'to_line', 'authorized_by', 'created_from', 'created_to']


class BudgetTransactionFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = BudgetTransaction
        fields = [
            'budget', 'budget_line', 'transaction_type', 'purchase_order', 'supplier_invoice',
            'created_by', 'created_from', 'created_to',
        ]


class CurrencyFilter(django_filters.FilterSet):
    class Meta:
        model = Currency
        fields = ['is_active', 'decimal_places']


class TaxCodeFilter(django_filters.FilterSet):
    rate_from = django_filters.NumberFilter(field_name='rate_percent', lookup_expr='gte')
    rate_to = django_filters.NumberFilter(field_name='rate_percent', lookup_expr='lte')

    class Meta:
        model = TaxCode
        fields = ['is_active', 'rate_from', 'rate_to']


class CostCentreFilter(django_filters.FilterSet):
    class Meta:
        model = CostCentre
        fields = ['project', 'is_active']


class BudgetCategoryFilter(django_filters.FilterSet):
    class Meta:
        model = BudgetCategory
        fields = ['cost_centre', 'is_active']


class FinanceAuditEventFilter(django_filters.FilterSet):
    created_from = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='gte')
    created_to = django_filters.IsoDateTimeFilter(field_name='created_at', lookup_expr='lte')

    class Meta:
        model = FinanceAuditEvent
        fields = ['actor', 'action', 'object_type', 'object_id', 'correlation_id', 'created_from', 'created_to']


class BudgetApprovalFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')

    class Meta:
        model = BudgetApproval
        fields = ['status', 'purchase_request', 'purchase_request__project', 'created_from', 'created_to']


class SupplierInvoiceFilter(django_filters.FilterSet):
    invoice_date_from = django_filters.DateFilter(field_name='invoice_date', lookup_expr='gte')
    invoice_date_to = django_filters.DateFilter(field_name='invoice_date', lookup_expr='lte')
    due_date_from = django_filters.DateFilter(field_name='due_date', lookup_expr='gte')
    due_date_to = django_filters.DateFilter(field_name='due_date', lookup_expr='lte')

    class Meta:
        model = SupplierInvoice
        fields = [
            'status', 'supplier', 'project', 'purchase_order',
            'invoice_date_from', 'invoice_date_to', 'due_date_from', 'due_date_to',
        ]


class SupplierCreditNoteFilter(django_filters.FilterSet):
    credit_note_date_from = django_filters.DateFilter(field_name='credit_note_date', lookup_expr='gte')
    credit_note_date_to = django_filters.DateFilter(field_name='credit_note_date', lookup_expr='lte')

    class Meta:
        model = SupplierCreditNote
        fields = [
            'status', 'supplier', 'invoice', 'credit_note_date_from', 'credit_note_date_to',
        ]


class PaymentFilter(django_filters.FilterSet):
    payment_date_from = django_filters.DateFilter(field_name='payment_date', lookup_expr='gte')
    payment_date_to = django_filters.DateFilter(field_name='payment_date', lookup_expr='lte')

    class Meta:
        model = Payment
        fields = [
            'supplier', 'invoice', 'source_account', 'currency', 'status', 'method',
            'payment_date_from', 'payment_date_to',
        ]


class JournalEntryFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='date', lookup_expr='lte')
    account = django_filters.NumberFilter(field_name='lines__account')

    class Meta:
        model = JournalEntry
        fields = ['status', 'source_type', 'fiscal_period', 'account', 'date_from', 'date_to']


class ProjectCostFilter(django_filters.FilterSet):
    date_from = django_filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = django_filters.DateFilter(field_name='date', lookup_expr='lte')

    class Meta:
        model = ProjectCost
        fields = ['project', 'supplier_invoice', 'is_reversal', 'date_from', 'date_to']


class LandedCostDocumentFilter(django_filters.FilterSet):
    created_from = django_filters.DateFilter(field_name='created_at', lookup_expr='date__gte')
    created_to = django_filters.DateFilter(field_name='created_at', lookup_expr='date__lte')
    posted_from = django_filters.DateFilter(field_name='posted_at', lookup_expr='date__gte')
    posted_to = django_filters.DateFilter(field_name='posted_at', lookup_expr='date__lte')

    class Meta:
        model = LandedCostDocument
        fields = [
            'status', 'allocation_method', 'currency', 'goods_received_notes',
            'created_by', 'approved_by', 'created_from', 'created_to',
            'posted_from', 'posted_to',
        ]


class ExpenseCategoryFilter(django_filters.FilterSet):
    class Meta:
        model = ExpenseCategory
        fields = ['category_type', 'budget_category', 'is_overhead', 'is_approved', 'is_active']


class CashAccountFilter(django_filters.FilterSet):
    class Meta:
        model = CashAccount
        fields = ['currency', 'is_petty_cash', 'is_active']


class ExpenseClaimFilter(django_filters.FilterSet):
    claim_date_from = django_filters.DateFilter(field_name='claim_date', lookup_expr='gte')
    claim_date_to = django_filters.DateFilter(field_name='claim_date', lookup_expr='lte')

    class Meta:
        model = ExpenseClaim
        fields = [
            'status', 'claimant', 'project', 'cost_centre', 'overhead_category',
            'currency', 'claim_date_from', 'claim_date_to',
        ]


class StaffAdvanceFilter(django_filters.FilterSet):
    advance_date_from = django_filters.DateFilter(field_name='advance_date', lookup_expr='gte')
    advance_date_to = django_filters.DateFilter(field_name='advance_date', lookup_expr='lte')

    class Meta:
        model = StaffAdvance
        fields = [
            'status', 'staff', 'project', 'cost_centre', 'overhead_category',
            'currency', 'advance_date_from', 'advance_date_to',
        ]


class PettyCashTransactionFilter(django_filters.FilterSet):
    transaction_date_from = django_filters.DateFilter(field_name='transaction_date', lookup_expr='gte')
    transaction_date_to = django_filters.DateFilter(field_name='transaction_date', lookup_expr='lte')

    class Meta:
        model = PettyCashTransaction
        fields = [
            'cash_account', 'transaction_type', 'status', 'expense_claim',
            'staff_advance', 'transaction_date_from', 'transaction_date_to',
        ]


class ChartOfAccountFilter(django_filters.FilterSet):
    class Meta:
        model = ChartOfAccount
        fields = ['parent', 'account_type', 'system_key', 'allow_manual_posting', 'is_active']


class FiscalPeriodFilter(django_filters.FilterSet):
    class Meta:
        model = FiscalPeriod
        fields = ['status', 'start_date', 'end_date']


class PostingRuleFilter(django_filters.FilterSet):
    class Meta:
        model = PostingRule
        fields = ['event_type', 'is_active']


class AccountMappingFilter(django_filters.FilterSet):
    class Meta:
        model = AccountMapping
        fields = ['mapping_key', 'account', 'is_active']


class JournalReversalFilter(django_filters.FilterSet):
    reversed_from = django_filters.IsoDateTimeFilter(field_name='reversed_at', lookup_expr='gte')
    reversed_to = django_filters.IsoDateTimeFilter(field_name='reversed_at', lookup_expr='lte')

    class Meta:
        model = JournalReversal
        fields = ['original_journal', 'reversal_journal', 'reversed_by', 'reversed_from', 'reversed_to']
