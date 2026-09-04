from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AccountViewSet,
    AccountMappingViewSet,
    AdvanceRetirementViewSet,
    ApprovalMatrixRuleViewSet,
    BudgetApprovalViewSet,
    BudgetCategoryViewSet,
    BudgetRevisionViewSet,
    BudgetTransactionViewSet,
    BudgetTransferViewSet,
    ChartOfAccountViewSet,
    CostCentreViewSet,
    CashAccountViewSet,
    BankStatementLineViewSet,
    CurrencyViewSet,
    FinanceAuditEventViewSet,
    FinanceSettingsViewSet,
    FiscalPeriodViewSet,
    ExpenseApprovalViewSet,
    ExpenseCategoryViewSet,
    ExpenseClaimViewSet,
    ExpenseReceiptAttachmentViewSet,
    FinancialApprovalViewSet,
    JournalEntryViewSet,
    JournalReversalViewSet,
    LandedCostDocumentViewSet,
    InvoiceApprovalViewSet,
    InvoiceAttachmentViewSet,
    PaymentViewSet,
    PaymentBatchViewSet,
    PettyCashTransactionViewSet,
    PostingRuleViewSet,
    PaymentApprovalViewSet,
    PaymentAttachmentViewSet,
    ProjectCostViewSet,
    ProjectBudgetViewSet,
    SupplierInvoiceViewSet,
    SupplierCreditNoteViewSet,
    SupplierAdvanceViewSet,
    StaffAdvanceViewSet,
    DraftJournalViewSet,
    SupplierOutstandingBalanceAPIView,
    SupplierStatementAPIView,
    TaxCodeViewSet,
    ThreeWayMatchViewSet,
)
from .report_services import REPORTS
from .report_views import (
    FinanceDashboardAPIView,
    FinanceReportAPIView,
    FinanceReportDownloadAPIView,
)
from .sync_views import FinanceDeadlineCheckAPIView, FinanceDraftSyncAPIView


app_name = 'finance_api'

router = DefaultRouter()
router.register('settings', FinanceSettingsViewSet, basename='settings')
router.register('approval-matrix-rules', ApprovalMatrixRuleViewSet, basename='approval-matrix-rule')
router.register('currencies', CurrencyViewSet, basename='currency')
router.register('tax-codes', TaxCodeViewSet, basename='tax-code')
router.register('cost-centres', CostCentreViewSet, basename='cost-centre')
router.register('budget-categories', BudgetCategoryViewSet, basename='budget-category')
router.register('audit-events', FinanceAuditEventViewSet, basename='audit-event')
router.register('budgets', ProjectBudgetViewSet, basename='budget')
router.register('budget-revisions', BudgetRevisionViewSet, basename='budget-revision')
router.register('budget-transfers', BudgetTransferViewSet, basename='budget-transfer')
router.register('budget-transactions', BudgetTransactionViewSet, basename='budget-transaction')
router.register('financial-approvals', FinancialApprovalViewSet, basename='financial-approval')
router.register('budget-approvals', BudgetApprovalViewSet, basename='budget-approval')
router.register('accounts', AccountViewSet, basename='account')
router.register('supplier-invoices', SupplierInvoiceViewSet, basename='supplier-invoice')
router.register('invoice-attachments', InvoiceAttachmentViewSet, basename='invoice-attachment')
router.register('invoice-approvals', InvoiceApprovalViewSet, basename='invoice-approval')
router.register('supplier-credit-notes', SupplierCreditNoteViewSet, basename='supplier-credit-note')
router.register('three-way-matches', ThreeWayMatchViewSet, basename='three-way-match')
router.register('payments', PaymentViewSet, basename='payment')
router.register('payment-batches', PaymentBatchViewSet, basename='payment-batch')
router.register('payment-attachments', PaymentAttachmentViewSet, basename='payment-attachment')
router.register('payment-approvals', PaymentApprovalViewSet, basename='payment-approval')
router.register('supplier-advances', SupplierAdvanceViewSet, basename='supplier-advance')
router.register('journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register('project-costs', ProjectCostViewSet, basename='project-cost')
router.register('landed-costs', LandedCostDocumentViewSet, basename='landed-cost')
router.register('expense-categories', ExpenseCategoryViewSet, basename='expense-category')
router.register('cash-accounts', CashAccountViewSet, basename='cash-account')
router.register('bank-statement-lines', BankStatementLineViewSet, basename='bank-statement-line')
router.register('expense-claims', ExpenseClaimViewSet, basename='expense-claim')
router.register('expense-receipts', ExpenseReceiptAttachmentViewSet, basename='expense-receipt')
router.register('staff-advances', StaffAdvanceViewSet, basename='staff-advance')
router.register('advance-retirements', AdvanceRetirementViewSet, basename='advance-retirement')
router.register('petty-cash-transactions', PettyCashTransactionViewSet, basename='petty-cash-transaction')
router.register('expense-approvals', ExpenseApprovalViewSet, basename='expense-approval')
router.register('chart-of-accounts', ChartOfAccountViewSet, basename='chart-of-account')
router.register('fiscal-periods', FiscalPeriodViewSet, basename='fiscal-period')
router.register('posting-rules', PostingRuleViewSet, basename='posting-rule')
router.register('account-mappings', AccountMappingViewSet, basename='account-mapping')
router.register('journals', DraftJournalViewSet, basename='journal')
router.register('journal-reversals', JournalReversalViewSet, basename='journal-reversal')

urlpatterns = [
    path('dashboard/', FinanceDashboardAPIView.as_view(), name='finance-dashboard'),
    path('sync/drafts/', FinanceDraftSyncAPIView.as_view(), name='finance-draft-sync'),
    path(
        'notification-checks/deadlines/',
        FinanceDeadlineCheckAPIView.as_view(),
        name='finance-deadline-check',
    ),
    path('suppliers/<int:supplier_id>/statement/', SupplierStatementAPIView.as_view(), name='supplier-statement'),
    path(
        'suppliers/<int:supplier_id>/outstanding-balance/',
        SupplierOutstandingBalanceAPIView.as_view(),
        name='supplier-outstanding-balance',
    ),
    path('', include(router.urls)),
]

for report_slug in REPORTS:
    route_name = report_slug.replace('-', '_')
    urlpatterns.extend([
        path(
            f'reports/{report_slug}/',
            FinanceReportAPIView.as_view(report_slug=report_slug),
            name=f'report-{route_name}',
        ),
        path(
            f'reports/{report_slug}/download/csv/',
            FinanceReportDownloadAPIView.as_view(report_slug=report_slug, file_format='csv'),
            name=f'report-{route_name}-csv',
        ),
        path(
            f'reports/{report_slug}/download/xlsx/',
            FinanceReportDownloadAPIView.as_view(report_slug=report_slug, file_format='xlsx'),
            name=f'report-{route_name}-xlsx',
        ),
        path(
            f'reports/{report_slug}/download/pdf/',
            FinanceReportDownloadAPIView.as_view(report_slug=report_slug, file_format='pdf'),
            name=f'report-{route_name}-pdf',
        ),
    ])
