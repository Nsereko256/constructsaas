from csv import DictReader
from io import TextIOWrapper

from drf_spectacular.utils import extend_schema, extend_schema_view
from django.http import FileResponse
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from decimal import Decimal
from rest_framework import status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.pdf_exports import pdf_table_response
from .report_exports import xlsx_response
from rest_framework.views import APIView
from apps.suppliers.models import Supplier
from apps.dashboard.helpers import push_dashboard_update
from apps.api.lifecycle import audit_lifecycle

from . import services
from . import invoice_services
from . import budget_approval_services
from . import budget_services
from . import matching_services
from . import payment_services
from . import payment_batch_services
from . import landed_cost_services
from . import expense_services
from . import expense_claim_services, staff_advance_services, cash_services
from . import ledger_workflow_services, month_end_workflow_services
from . import ledger_services
from . import month_end_services
from .selectors import expense_claim_queryset, payment_batch_queryset, payment_queryset, supplier_invoice_queryset
from .filters import (
    BudgetApprovalFilter,
    AccountMappingFilter,
    BudgetCategoryFilter,
    BudgetRevisionFilter,
    BudgetTransactionFilter,
    BudgetTransferFilter,
    BankStatementLineFilter,
    ChartOfAccountFilter,
    CostCentreFilter,
    CashAccountFilter,
    CurrencyFilter,
    FinanceAuditEventFilter,
    FiscalPeriodFilter,
    ExpenseCategoryFilter,
    ExpenseClaimFilter,
    JournalEntryFilter,
    JournalReversalFilter,
    LandedCostDocumentFilter,
    PaymentFilter,
    PettyCashTransactionFilter,
    PostingRuleFilter,
    ProjectCostFilter,
    ProjectBudgetFilter,
    SupplierInvoiceFilter,
    SupplierCreditNoteFilter,
    StaffAdvanceFilter,
    TaxCodeFilter,
)
from .models import (
    Account,
    AccountMapping,
    AdvanceRetirement,
    BudgetApproval,
    BudgetCategory,
    BudgetRevision,
    BudgetTransaction,
    BudgetTransfer,
    BankStatementLine,
    ChartOfAccount,
    CostCentre,
    CashAccount,
    Currency,
    FinanceAuditEvent,
    FinanceSettings,
    FiscalPeriod,
    ExpenseApproval,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseReceiptAttachment,
    FinancialApproval,
    InvoiceApproval,
    InvoiceAttachment,
    JournalEntry,
    JournalLine,
    JournalReversal,
    LandedCostDocument,
    Payment,
    PaymentBatch,
    PaymentApproval,
    PaymentAttachment,
    PettyCashTransaction,
    PostingRule,
    ProjectCost,
    ProjectBudget,
    SupplierInvoice,
    SupplierCreditNote,
    SupplierAdvance,
    StaffAdvance,
    TaxCode,
    ThreeWayMatch,
)


def _finance_export(*, kind, title, filename, columns, rows, totals):
    report = {
        'title': title,
        'columns': [{'key': key, 'label': label} for key, label in columns],
        'rows': rows,
        'totals': totals,
    }
    if kind == 'xlsx':
        return xlsx_response(report, filename)
    return pdf_table_response(
        title=title, filename=filename, columns=columns, rows=rows,
        totals=totals, subtitle='Company-scoped finance export using the active record filters.',
    )


class DraftDeletionMixin:
    """Permit deletion only for unsubmitted finance preparation records."""

    def perform_destroy(self, instance):
        if getattr(instance, 'status', None) != 'DRAFT':
            raise ValidationError({'status': 'Only draft finance records can be deleted. Use the correction or reversal workflow for submitted records.'})
        audit_lifecycle(instance=instance, actor=self.request.user, action=f'{instance.__class__.__name__.lower()}.deleted', message='Draft finance record deleted.')
        instance.delete()
from .permissions import (
    FinanceAdminPermission,
    FinanceManagerOnlyPermission,
    FinanceCompanyPermission,
    FinanceFoundationPermission,
    FinancePreparationPermission,
    FinanceProcurementWritePermission,
)
from .serializers import (
    AccountSerializer,
    AccountMappingSerializer,
    AdvanceRetirementSerializer,
    BudgetApprovalSerializer,
    BudgetCategorySerializer,
    BudgetRevisionRequestSerializer,
    BudgetRevisionSerializer,
    BudgetTransactionSerializer,
    BudgetTransferRequestSerializer,
    BudgetTransferSerializer,
    ChartOfAccountSerializer,
    CommentsSerializer,
    CostCentreSerializer,
    CashAccountSerializer,
    BankStatementLineSerializer,
    CashReplenishmentRequestSerializer,
    ReconcileStatementLineSerializer,
    StatementLineReasonSerializer,
    CurrencySerializer,
    FinanceAuditEventSerializer,
    FinanceSettingsSerializer,
    FiscalPeriodSerializer,
    ExpenseApprovalSerializer,
    ExpenseCategorySerializer,
    ExpenseClaimSerializer,
    ExpensePayRequestSerializer,
    ExpenseReceiptAttachmentSerializer,
    FinancialApprovalSerializer,
    InvoiceReversalSerializer,
    InvoiceApprovalSerializer,
    InvoiceAttachmentSerializer,
    InvoiceMatchRunSerializer,
    JournalEntrySerializer,
    JournalPostRequestSerializer,
    JournalReversalSerializer,
    LandedCostDocumentSerializer,
    LandedCostPreviewRequestSerializer,
    MatchRequestSerializer,
    PaymentRequestSerializer,
    PaymentAllocationRequestSerializer,
    PaymentAllocationSerializer,
    PaymentApproveRequestSerializer,
    PaymentPostRequestSerializer,
    PaymentUnallocationRequestSerializer,
    PaymentApprovalSerializer,
    PaymentAttachmentSerializer,
    PaymentReversalSerializer,
    PaymentSerializer,
    PaymentBatchSerializer,
    PaymentBatchCancelSerializer,
    PettyCashTransactionSerializer,
    PostingRuleSerializer,
    ProjectCostSerializer,
    ProjectBudgetSerializer,
    RequiredCommentsSerializer,
    ReasonSerializer,
    ReversalRequestSerializer,
    SupplierInvoiceSerializer,
    SupplierCreditNoteSerializer,
    SupplierAdvanceSerializer,
    StaffAdvanceSerializer,
    StaffAdvanceRetirementRequestSerializer,
    TaxCodeSerializer,
    ThreeWayMatchSerializer,
    CreditNoteRequestSerializer,
    PostRequestSerializer,
    VerifyRequestSerializer,
    RunMatchRequestSerializer,
    DraftJournalSerializer,
)


class CompanyScopedMixin:
    permission_classes = [FinanceCompanyPermission]

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated or not user.company_id:
            return self.queryset.none()
        return self.queryset.filter(company_id=user.company_id)


class FoundationConfigurationViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    permission_classes = [FinanceFoundationPermission]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Settings'], summary='Retrieve company finance settings'),
    retrieve=extend_schema(tags=['Finance - Settings'], summary='Retrieve company finance settings'),
    partial_update=extend_schema(tags=['Finance - Settings'], summary='Update company finance settings'),
)
class FinanceSettingsViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = FinanceSettings.objects.select_related('base_currency')
    serializer_class = FinanceSettingsSerializer
    permission_classes = [FinanceFoundationPermission]
    http_method_names = ['get', 'patch', 'head', 'options']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Currencies'], summary='List company currencies'),
    retrieve=extend_schema(tags=['Finance - Currencies'], summary='Retrieve a company currency'),
    create=extend_schema(tags=['Finance - Currencies'], summary='Create a company currency'),
    partial_update=extend_schema(tags=['Finance - Currencies'], summary='Update a company currency'),
)
class CurrencyViewSet(FoundationConfigurationViewSet):
    queryset = Currency.objects.all()
    serializer_class = CurrencySerializer
    filterset_class = CurrencyFilter
    search_fields = ['code', 'name', 'symbol']
    ordering_fields = ['code', 'name', 'decimal_places', 'is_active', 'created_at']
    ordering = ['code']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Tax Codes'], summary='List configurable company tax codes'),
    retrieve=extend_schema(tags=['Finance - Tax Codes'], summary='Retrieve a tax code'),
    create=extend_schema(tags=['Finance - Tax Codes'], summary='Create a configurable tax code'),
    partial_update=extend_schema(tags=['Finance - Tax Codes'], summary='Update a configurable tax code'),
)
class TaxCodeViewSet(FoundationConfigurationViewSet):
    queryset = TaxCode.objects.all()
    serializer_class = TaxCodeSerializer
    filterset_class = TaxCodeFilter
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'rate_percent', 'is_active', 'created_at']
    ordering = ['code']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Cost Centres'], summary='List company cost centres'),
    retrieve=extend_schema(tags=['Finance - Cost Centres'], summary='Retrieve a cost centre'),
    create=extend_schema(tags=['Finance - Cost Centres'], summary='Create a cost centre'),
    partial_update=extend_schema(tags=['Finance - Cost Centres'], summary='Update a cost centre'),
)
class CostCentreViewSet(FoundationConfigurationViewSet):
    queryset = CostCentre.objects.select_related('project')
    serializer_class = CostCentreSerializer
    filterset_class = CostCentreFilter
    search_fields = ['code', 'name', 'project__name', 'project__code', 'description']
    ordering_fields = ['code', 'name', 'project__name', 'is_active', 'created_at']
    ordering = ['code']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budget Categories'], summary='List company budget categories'),
    retrieve=extend_schema(tags=['Finance - Budget Categories'], summary='Retrieve a budget category'),
    create=extend_schema(tags=['Finance - Budget Categories'], summary='Create a budget category'),
    partial_update=extend_schema(tags=['Finance - Budget Categories'], summary='Update a budget category'),
)
class BudgetCategoryViewSet(FoundationConfigurationViewSet):
    queryset = BudgetCategory.objects.select_related('cost_centre')
    serializer_class = BudgetCategorySerializer
    filterset_class = BudgetCategoryFilter
    search_fields = ['code', 'name', 'cost_centre__code', 'cost_centre__name', 'description']
    ordering_fields = ['code', 'name', 'cost_centre__code', 'is_active', 'created_at']
    ordering = ['code']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Audit'], summary='List append-only finance audit events'),
    retrieve=extend_schema(tags=['Finance - Audit'], summary='Retrieve a finance audit event'),
)
class FinanceAuditEventViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = FinanceAuditEvent.objects.select_related('actor')
    serializer_class = FinanceAuditEventSerializer
    permission_classes = [FinanceFoundationPermission]
    filterset_class = FinanceAuditEventFilter
    search_fields = ['action', 'object_type', 'object_id', 'message', 'correlation_id', 'actor__username']
    ordering_fields = ['created_at', 'action', 'object_type', 'actor__username']
    ordering = ['-created_at', '-id']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budgets'], summary='List project budgets with calculated summaries'),
    retrieve=extend_schema(tags=['Finance - Budgets'], summary='Retrieve a project budget and lines'),
    create=extend_schema(tags=['Finance - Budgets'], summary='Create a draft project budget with lines'),
)
class ProjectBudgetViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = (
        ProjectBudget.objects.select_related('project', 'created_by', 'approved_by')
        .prefetch_related('lines__category', 'revisions', 'transactions')
    )
    serializer_class = ProjectBudgetSerializer
    filterset_class = ProjectBudgetFilter
    search_fields = ['name', 'project__name', 'project__code']
    ordering_fields = ['name', 'project__name', 'status', 'created_at', 'approved_at']
    ordering = ['project__name']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve'}:
            permission = FinanceCompanyPermission
        elif self.action in {'approve', 'reject', 'revise', 'transfer'}:
            permission = FinanceAdminPermission
        else:
            permission = FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Budgets'], request=None, responses=ProjectBudgetSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        budget = budget_services.submit_project_budget(budget=self.get_object(), user=request.user)
        return Response(self.get_serializer(budget).data)

    @extend_schema(tags=['Finance - Budgets'], request=CommentsSerializer, responses=ProjectBudgetSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        budget = budget_services.approve_project_budget(
            budget=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(budget).data)

    @extend_schema(tags=['Finance - Budgets'], request=RequiredCommentsSerializer, responses=ProjectBudgetSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = RequiredCommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        budget = budget_services.reject_project_budget(
            budget=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(budget).data)

    @extend_schema(tags=['Finance - Budgets'], request=BudgetRevisionRequestSerializer, responses=BudgetRevisionSerializer)
    @action(detail=True, methods=['post'])
    def revise(self, request, pk=None):
        payload = BudgetRevisionRequestSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        revision = budget_services.revise_project_budget(
            budget=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(BudgetRevisionSerializer(revision).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Budgets'], request=BudgetTransferRequestSerializer, responses=BudgetTransferSerializer)
    @action(detail=True, methods=['post'])
    def transfer(self, request, pk=None):
        payload = BudgetTransferRequestSerializer(data=request.data, context=self.get_serializer_context())
        payload.is_valid(raise_exception=True)
        transfer = budget_services.transfer_project_budget(
            budget=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(BudgetTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budgets'], summary='List immutable budget revisions'),
    retrieve=extend_schema(tags=['Finance - Budgets'], summary='Retrieve a budget revision'),
)
class BudgetRevisionViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = BudgetRevision.objects.select_related('budget', 'budget_line', 'approved_by')
    serializer_class = BudgetRevisionSerializer
    filterset_class = BudgetRevisionFilter
    search_fields = ['budget__name', 'comments', 'budget__project__name', 'budget__project__code']
    ordering_fields = ['amount', 'approved_at']
    ordering = ['-approved_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budgets'], summary='List immutable budget transfers'),
    retrieve=extend_schema(tags=['Finance - Budgets'], summary='Retrieve a budget transfer'),
)
class BudgetTransferViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = BudgetTransfer.objects.select_related('budget', 'from_line', 'to_line', 'authorized_by')
    serializer_class = BudgetTransferSerializer
    filterset_class = BudgetTransferFilter
    search_fields = ['budget__name', 'comments', 'budget__project__name', 'budget__project__code']
    ordering_fields = ['amount', 'created_at']
    ordering = ['-created_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budgets'], summary='List immutable budget ledger transactions'),
    retrieve=extend_schema(tags=['Finance - Budgets'], summary='Retrieve a budget ledger transaction'),
)
class BudgetTransactionViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = BudgetTransaction.objects.select_related(
        'budget', 'budget_line', 'purchase_order', 'supplier_invoice', 'created_by',
    )
    serializer_class = BudgetTransactionSerializer
    filterset_class = BudgetTransactionFilter
    search_fields = ['budget__name', 'description', 'purchase_order__number', 'supplier_invoice__internal_number']
    ordering_fields = ['amount', 'transaction_type', 'created_at']
    ordering = ['-created_at', '-id']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Approvals'], summary='List purchase-request financial approvals'),
    retrieve=extend_schema(tags=['Finance - Approvals'], summary='Retrieve a financial approval'),
)
class FinancialApprovalViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = FinancialApproval.objects.select_related(
        'purchase_request__project', 'project_budget', 'budget_line', 'created_by', 'reviewed_by',
    )
    serializer_class = FinancialApprovalSerializer
    filterset_fields = ['status', 'project_budget', 'budget_line', 'purchase_request__project', 'reviewed_by']
    search_fields = ['purchase_request__number', 'purchase_request__title', 'purchase_request__project__name']
    ordering_fields = ['requested_amount', 'status', 'submitted_at', 'reviewed_at', 'created_at']
    ordering = ['-created_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Budget'], summary='List budget approvals'),
    retrieve=extend_schema(tags=['Finance - Budget'], summary='Retrieve a budget approval'),
    create=extend_schema(tags=['Finance - Budget'], summary='Start budget approval for a technically approved PR'),
)
class BudgetApprovalViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = BudgetApproval.objects.select_related(
        'purchase_request__project', 'created_by', 'reviewed_by',
    )
    serializer_class = BudgetApprovalSerializer
    filterset_class = BudgetApprovalFilter
    search_fields = ['purchase_request__number', 'purchase_request__title', 'purchase_request__project__name']
    ordering_fields = ['requested_amount', 'status', 'created_at', 'reviewed_at']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        permission = FinanceAdminPermission if self.action in {'approve', 'reject'} else FinanceProcurementWritePermission
        if self.action in {'list', 'retrieve'}:
            permission = FinanceCompanyPermission
        return [permission()]

    @extend_schema(tags=['Finance - Budget'], request=None, responses=BudgetApprovalSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        approval = budget_approval_services.submit_budget_approval(approval=self.get_object(), user=request.user)
        return Response(self.get_serializer(approval).data)

    @extend_schema(tags=['Finance - Budget'], request=None, responses=BudgetApprovalSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        approval = budget_approval_services.review_budget_approval(
            approval=self.get_object(), user=request.user, approve=True,
        )
        return Response(self.get_serializer(approval).data)

    @extend_schema(tags=['Finance - Budget'], request=ReasonSerializer, responses=BudgetApprovalSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = budget_approval_services.review_budget_approval(
            approval=self.get_object(), user=request.user, approve=False,
            reason=payload.validated_data['reason'],
        )
        return Response(self.get_serializer(approval).data)


@extend_schema_view(
    list=extend_schema(tags=['Finance - Accounts'], summary='List chart-of-account records'),
    retrieve=extend_schema(tags=['Finance - Accounts'], summary='Retrieve an account'),
    create=extend_schema(tags=['Finance - Accounts'], summary='Create an account'),
)
class AccountViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = Account.objects.all()
    serializer_class = AccountSerializer
    permission_classes = [FinanceAdminPermission]
    filterset_fields = ['account_type', 'system_key', 'is_active']
    search_fields = ['code', 'name']
    ordering_fields = ['code', 'name', 'account_type', 'created_at']
    ordering = ['code']
    http_method_names = ['get', 'post', 'head', 'options']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Invoices'], summary='List supplier invoices'),
    retrieve=extend_schema(tags=['Finance - Invoices'], summary='Retrieve a supplier invoice'),
    create=extend_schema(tags=['Finance - Invoices'], summary='Create a draft supplier invoice'),
    partial_update=extend_schema(tags=['Finance - Invoices'], summary='Edit non-line fields on a draft invoice'),
)
class SupplierInvoiceViewSet(DraftDeletionMixin, CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = supplier_invoice_queryset()
    serializer_class = SupplierInvoiceSerializer
    filterset_class = SupplierInvoiceFilter
    search_fields = ['internal_number', 'invoice_number', 'supplier__name', 'purchase_order__number', 'project__name']
    ordering_fields = ['internal_number', 'invoice_date', 'due_date', 'total_amount', 'status', 'created_at']
    ordering = ['-invoice_date', '-created_at']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'match_results', 'download_pdf'}:
            permission = FinanceCompanyPermission
        elif self.action in {'approve_exception', 'reject_exception'}:
            permission = FinanceManagerOnlyPermission
        elif self.action in {
            'approve', 'reject', 'post', 'pay', 'reverse', 'create_credit_note',
        }:
            permission = FinanceAdminPermission
        else:
            # Invoice capture, matching and submission are finance preparation
            # activities. Procurement can still read invoice progress, but cannot
            # create or alter a payable through a direct API call.
            permission = FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Invoices'], request=None, responses=SupplierInvoiceSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        invoice = invoice_services.submit_invoice(invoice=self.get_object(), user=request.user)
        return Response(self.get_serializer(invoice).data)

    @extend_schema(tags=['Finance - Invoices'], request=None, responses=SupplierInvoiceSerializer)
    @action(detail=True, methods=['post'], url_path='withdraw-submission')
    def withdraw_submission(self, request, pk=None):
        invoice = invoice_services.withdraw_invoice(invoice=self.get_object(), user=request.user)
        return Response(self.get_serializer(invoice).data)

    @extend_schema(tags=['Finance - Invoices'], request=VerifyRequestSerializer, responses=ThreeWayMatchSerializer)
    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        payload = VerifyRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = invoice_services.verify_invoice(invoice=self.get_object(), user=request.user, **payload.validated_data)
        return Response(ThreeWayMatchSerializer(result).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Finance - Matching'], request=RunMatchRequestSerializer,
        responses=InvoiceMatchRunSerializer,
    )
    @action(detail=True, methods=['post'], url_path='run-match')
    def run_match(self, request, pk=None):
        payload = RunMatchRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = matching_services.run_invoice_match(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(InvoiceMatchRunSerializer(result).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Matching'], responses=InvoiceMatchRunSerializer(many=True))
    @action(detail=True, methods=['get'], url_path='match-results')
    def match_results(self, request, pk=None):
        invoice = self.get_object()
        results = invoice.match_runs.select_related(
            'exception_approved_by', 'exception_rejected_by', 'run_by',
        ).prefetch_related(
            'item_results__invoice_item__material', 'item_results__purchase_order_item',
        )
        return Response(InvoiceMatchRunSerializer(results, many=True).data)

    @extend_schema(tags=['Finance - Invoices'], summary='Download invoice record as PDF', responses={200: bytes})
    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        invoice = self.get_object()
        rows = [{
            'material': f'{item.material.code} / {item.material.name}',
            'description': item.description or '-',
            'quantity': item.quantity,
            'unit_price': f'{invoice.currency} {item.unit_price:,.2f}',
            'tax': f'{invoice.currency} {item.tax_amount:,.2f}',
            'total': f'{invoice.currency} {item.total:,.2f}',
        } for item in invoice.items.select_related('material')]
        totals = {
            'Status': invoice.get_status_display(),
            'Invoice total': f'{invoice.currency} {invoice.total_amount:,.2f}',
            'Paid / credited': f'{invoice.currency} {invoice.amount_paid:,.2f} / {invoice.credit_amount:,.2f}',
            'Outstanding balance': f'{invoice.currency} {invoice.balance:,.2f}',
        }
        subtitle = ' | '.join(filter(None, [
            f'Supplier: {invoice.supplier.name}', f'Supplier reference: {invoice.invoice_number}',
            f'PO: {invoice.purchase_order.number}', f'Invoice date: {invoice.invoice_date.isoformat()}',
            f'Due: {invoice.due_date.isoformat() if invoice.due_date else "-"}',
        ]))
        return pdf_table_response(
            title=f'Invoice record - {invoice.internal_number}', filename=invoice.internal_number,
            columns=[('material', 'Material'), ('description', 'Description'), ('quantity', 'Quantity'), ('unit_price', 'Unit price'), ('tax', 'Tax'), ('total', 'Line total')],
            rows=rows, totals=totals, subtitle=subtitle,
        )

    @extend_schema(tags=['Finance - Matching'], request=ReasonSerializer, responses=InvoiceMatchRunSerializer)
    @action(detail=True, methods=['post'], url_path='approve-exception')
    def approve_exception(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = matching_services.approve_match_exception(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(InvoiceMatchRunSerializer(result).data)

    @extend_schema(tags=['Finance - Matching'], request=ReasonSerializer, responses=InvoiceMatchRunSerializer)
    @action(detail=True, methods=['post'], url_path='reject-exception')
    def reject_exception(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = matching_services.reject_match_exception(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(InvoiceMatchRunSerializer(result).data)

    @extend_schema(tags=['Finance - Invoices'], request=MatchRequestSerializer, responses=ThreeWayMatchSerializer)
    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        payload = MatchRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        result = invoice_services.match_invoice(invoice=self.get_object(), user=request.user, **payload.validated_data)
        return Response(ThreeWayMatchSerializer(result).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Invoices'], request=None, responses=SupplierInvoiceSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        invoice = invoice_services.approve_invoice(invoice=self.get_object(), user=request.user)
        return Response(self.get_serializer(invoice).data)

    @extend_schema(tags=['Finance - Invoices'], request=ReasonSerializer, responses=SupplierInvoiceSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        invoice = invoice_services.reject_invoice(
            invoice=self.get_object(), user=request.user, reason=payload.validated_data['reason'],
        )
        return Response(self.get_serializer(invoice).data)

    @extend_schema(tags=['Finance - Invoices'], request=PostRequestSerializer, responses=JournalEntrySerializer)
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        payload = PostRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        entry = invoice_services.post_invoice(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(JournalEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Invoices'], request=PaymentRequestSerializer, responses=PaymentSerializer)
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        payload = PaymentRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        payment = invoice_services.pay_invoice(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Invoices'], request=ReversalRequestSerializer, responses=InvoiceReversalSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reversal = invoice_services.reverse_invoice(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(InvoiceReversalSerializer(reversal).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        tags=['Finance - Invoices'], request=CreditNoteRequestSerializer,
        responses=SupplierCreditNoteSerializer,
    )
    @action(detail=True, methods=['post'], url_path='create-credit-note')
    def create_credit_note(self, request, pk=None):
        payload = CreditNoteRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        note = invoice_services.create_supplier_credit_note(
            invoice=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(SupplierCreditNoteSerializer(note).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=['Finance - Invoice Attachments'], summary='List company-secured invoice attachments'),
    create=extend_schema(tags=['Finance - Invoice Attachments'], summary='Upload a private invoice attachment'),
    retrieve=extend_schema(tags=['Finance - Invoice Attachments'], summary='Retrieve attachment metadata'),
)
class InvoiceAttachmentViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = InvoiceAttachment.objects.select_related('invoice', 'uploaded_by')
    serializer_class = InvoiceAttachmentSerializer
    filterset_fields = ['invoice', 'content_type', 'uploaded_by']
    ordering_fields = ['created_at', 'size', 'original_name']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        permission = FinanceCompanyPermission if self.action in {'list', 'retrieve', 'download'} else FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Invoice Attachments'], responses={(200, 'application/octet-stream'): bytes})
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        attachment = self.get_object()
        return FileResponse(
            attachment.file.open('rb'), as_attachment=True, filename=attachment.original_name,
            content_type=attachment.content_type,
        )


@extend_schema_view(
    list=extend_schema(tags=['Finance - Invoice Approvals'], summary='List append-only invoice decisions'),
    retrieve=extend_schema(tags=['Finance - Invoice Approvals'], summary='Retrieve an invoice decision'),
)
class InvoiceApprovalViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InvoiceApproval.objects.select_related('invoice', 'acted_by')
    serializer_class = InvoiceApprovalSerializer
    filterset_fields = ['invoice', 'action', 'acted_by']
    ordering_fields = ['acted_at', 'action']
    ordering = ['-acted_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Credit Notes'], summary='List posted supplier credit notes'),
    retrieve=extend_schema(tags=['Finance - Credit Notes'], summary='Retrieve a supplier credit note'),
)
class SupplierCreditNoteViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SupplierCreditNote.objects.select_related('supplier', 'invoice', 'created_by', 'posted_by').prefetch_related('items')
    serializer_class = SupplierCreditNoteSerializer
    filterset_class = SupplierCreditNoteFilter
    search_fields = ['credit_note_number', 'supplier__name', 'invoice__invoice_number', 'reason']
    ordering_fields = ['credit_note_date', 'total_amount', 'status', 'created_at']
    ordering = ['-credit_note_date', '-created_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Matching'], summary='List immutable three-way match results'),
    retrieve=extend_schema(tags=['Finance - Matching'], summary='Retrieve a three-way match result'),
)
class ThreeWayMatchViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ThreeWayMatch.objects.select_related('invoice', 'purchase_order', 'matched_by')
    serializer_class = ThreeWayMatchSerializer
    filterset_fields = ['status', 'invoice', 'purchase_order', 'matched_by']
    ordering_fields = ['matched_at', 'amount_variance', 'quantity_variance']
    ordering = ['-matched_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Payments'], summary='List supplier payments'),
    retrieve=extend_schema(tags=['Finance - Payments'], summary='Retrieve a supplier payment'),
    create=extend_schema(tags=['Finance - Payments'], summary='Prepare a supplier payment'),
    partial_update=extend_schema(tags=['Finance - Payments'], summary='Edit a draft supplier payment'),
)
class PaymentViewSet(DraftDeletionMixin, CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = payment_queryset()
    serializer_class = PaymentSerializer
    filterset_class = PaymentFilter
    search_fields = ['number', 'reference', 'invoice__internal_number', 'invoice__invoice_number', 'invoice__supplier__name']
    ordering_fields = ['number', 'amount', 'payment_date', 'status', 'posted_at', 'created_by']
    ordering = ['-payment_date', '-id']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'voucher', 'download'}:
            permission = FinanceCompanyPermission
        elif self.action in {'approve', 'reject', 'post', 'reverse'}:
            permission = FinanceAdminPermission
        else:
            permission = FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Payments'], request=None, responses=PaymentSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        payment = payment_services.submit_payment(payment=self.get_object(), user=request.user)
        return Response(self.get_serializer(payment).data)

    @extend_schema(tags=['Finance - Payments'], request=PaymentApproveRequestSerializer, responses=PaymentSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payload = PaymentApproveRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        payment = payment_services.approve_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(payment).data)

    @extend_schema(tags=['Finance - Payments'], request=ReasonSerializer, responses=PaymentSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        payment = payment_services.reject_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(payment).data)

    @extend_schema(tags=['Finance - Payments'], request=PaymentPostRequestSerializer, responses=JournalEntrySerializer)
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        payload = PaymentPostRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        entry = payment_services.post_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(JournalEntrySerializer(entry).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Payments'], request=PaymentAllocationRequestSerializer, responses=PaymentAllocationSerializer)
    @action(detail=True, methods=['post'])
    def allocate(self, request, pk=None):
        payload = PaymentAllocationRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        allocation = payment_services.allocate_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PaymentAllocationSerializer(allocation).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Payments'], request=PaymentUnallocationRequestSerializer, responses=None)
    @action(detail=True, methods=['post'])
    def unallocate(self, request, pk=None):
        payload = PaymentUnallocationRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        payment_services.unallocate_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=['Finance - Payments'], request=ReversalRequestSerializer, responses=PaymentReversalSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reversal = payment_services.reverse_posted_payment(
            payment=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PaymentReversalSerializer(reversal).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Payments'], responses=PaymentSerializer)
    @action(detail=True, methods=['get'])
    def voucher(self, request, pk=None):
        payment = self.get_object()
        return Response({
            'voucher_number': payment.number,
            'voucher_reference': payment.voucher_reference,
            'payment_date': payment.payment_date,
            'supplier': {'id': payment.supplier_id, 'name': payment.supplier.name},
            'method': payment.method,
            'account': {'id': payment.source_account_id, 'name': payment.source_account.name},
            'currency': payment.currency.code,
            'exchange_rate': payment.exchange_rate,
            'amount': payment.amount,
            'reference': payment.reference,
            'status': payment.status,
            'allocations': PaymentAllocationSerializer(payment.allocations.all(), many=True).data,
            'prepared_by': payment.created_by.get_full_name() or payment.created_by.username,
            'approved_by': payment.approved_by.get_full_name() if payment.approved_by else None,
            'posted_at': payment.posted_at,
        })

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        payment = self.get_object()
        rows = [{
            'payment': payment.number,
            'supplier': payment.supplier.name if payment.supplier_id else 'Supplier advance',
            'invoice': payment.invoice.internal_number if payment.invoice_id else '-',
            'date': payment.payment_date,
            'method': payment.get_method_display(),
            'currency': payment.currency.code,
            'amount': payment.amount,
            'reference': payment.reference,
            'status': payment.get_status_display(),
            'prepared_by': payment.created_by.get_full_name() or payment.created_by.username,
            'approved_by': payment.approved_by.get_full_name() if payment.approved_by else '-',
        }]
        return _finance_export(
            kind=kind, title=f'Payment voucher - {payment.number}', filename=payment.number,
            columns=[('payment', 'Payment'), ('supplier', 'Supplier'), ('invoice', 'Invoice'), ('date', 'Payment date'), ('method', 'Method'), ('currency', 'Currency'), ('amount', 'Amount'), ('reference', 'Reference'), ('status', 'Status'), ('prepared_by', 'Prepared by'), ('approved_by', 'Approved by')],
            rows=rows, totals={'Total': payment.amount, 'Status': payment.get_status_display()},
        )


class PaymentBatchViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = payment_batch_queryset()
    serializer_class = PaymentBatchSerializer
    filterset_fields = ['status', 'source_account', 'currency', 'payment_date']
    search_fields = ['number', 'notes']
    ordering_fields = ['number', 'payment_date', 'status', 'created_at']
    ordering = ['-payment_date', '-id']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        if self.action in {'approve', 'release', 'cancel'}:
            permission = FinanceAdminPermission
        elif self.action == 'submit':
            permission = FinancePreparationPermission
        elif self.action == 'create':
            permission = FinancePreparationPermission
        else:
            permission = FinanceCompanyPermission
        return [permission()]

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        batch = payment_batch_services.submit_batch(batch=self.get_object(), user=request.user)
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        batch = payment_batch_services.approve_batch(batch=self.get_object(), user=request.user)
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        batch = payment_batch_services.release_batch(batch=self.get_object(), user=request.user)
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        payload = PaymentBatchCancelSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        batch = payment_batch_services.cancel_batch(batch=self.get_object(), user=request.user, **payload.validated_data)
        return Response(self.get_serializer(batch).data)

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        batch = self.get_object()
        rows = [{
            'batch': batch.number,
            'payment': item.payment.number,
            'supplier': item.payment.supplier.name if item.payment.supplier_id else 'Supplier advance',
            'date': batch.payment_date,
            'currency': batch.currency.code,
            'amount': item.payment.amount,
            'status': batch.get_status_display(),
        } for item in batch.items.all()]
        return _finance_export(
            kind=kind, title=f'Payment batch - {batch.number}', filename=batch.number,
            columns=[('batch', 'Batch'), ('payment', 'Payment'), ('supplier', 'Supplier'), ('date', 'Payment date'), ('currency', 'Currency'), ('amount', 'Amount'), ('status', 'Batch status')],
            rows=rows, totals={'Payments': len(rows), 'Batch total': batch.total_amount, 'Status': batch.get_status_display()},
        )


class PaymentAttachmentViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = PaymentAttachment.objects.select_related('payment', 'uploaded_by')
    serializer_class = PaymentAttachmentSerializer
    filterset_fields = ['payment', 'content_type', 'uploaded_by']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        permission = FinanceCompanyPermission if self.action in {'list', 'retrieve', 'download'} else FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Payment Attachments'], responses={(200, 'application/octet-stream'): bytes})
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        attachment = self.get_object()
        return FileResponse(
            attachment.file.open('rb'), as_attachment=True, filename=attachment.original_name,
            content_type=attachment.content_type,
        )


class PaymentApprovalViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PaymentApproval.objects.select_related('payment', 'acted_by')
    serializer_class = PaymentApprovalSerializer
    filterset_fields = ['payment', 'action', 'acted_by']
    ordering = ['-acted_at']


class SupplierAdvanceViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = SupplierAdvance.objects.select_related('supplier', 'payment', 'authorized_by')
    serializer_class = SupplierAdvanceSerializer
    filterset_fields = ['supplier', 'payment', 'status']
    ordering_fields = ['amount', 'authorized_at', 'status']
    ordering = ['-authorized_at']


class SupplierOutstandingBalanceAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]

    @extend_schema(tags=['Finance - Supplier Statements'], responses=dict)
    def get(self, request, supplier_id):
        supplier = Supplier.objects.filter(pk=supplier_id, company=request.user.company).first()
        if not supplier:
            return Response({'detail': 'Supplier not found.'}, status=status.HTTP_404_NOT_FOUND)
        invoices = list(SupplierInvoice.objects.filter(
            company=request.user.company, supplier=supplier,
            status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID],
        ))
        totals = payment_services.invoice_balance_totals(invoices)
        rows = [{
            'invoice_id': invoice.pk, 'invoice_number': invoice.invoice_number,
            'invoice_date': invoice.invoice_date, 'due_date': invoice.due_date,
            'currency': invoice.currency, 'total': invoice.total_amount,
            'exchange_rate': invoice.exchange_rate,
            'balance': totals[invoice.pk]['balance'],
            'base_balance': services.base_money(totals[invoice.pk]['balance'], invoice.exchange_rate),
        } for invoice in invoices if totals[invoice.pk]['balance'] > 0]
        balances_by_currency = {}
        for row in rows:
            balances_by_currency[row['currency']] = services.money(
                balances_by_currency.get(row['currency'], services.ZERO) + row['balance'],
            )
        return Response({
            'supplier': {'id': supplier.pk, 'name': supplier.name},
            'outstanding_balance': sum((row['balance'] for row in rows), 0),
            'outstanding_balance_base': sum((row['base_balance'] for row in rows), services.ZERO),
            'balances_by_currency': balances_by_currency,
            'invoices': rows,
        })


class SupplierStatementAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]

    @extend_schema(tags=['Finance - Supplier Statements'], responses=dict)
    def get(self, request, supplier_id):
        supplier = Supplier.objects.filter(pk=supplier_id, company=request.user.company).first()
        if not supplier:
            return Response({'detail': 'Supplier not found.'}, status=status.HTTP_404_NOT_FOUND)
        invoices = list(SupplierInvoice.objects.filter(
            company=request.user.company, supplier=supplier,
        ).order_by('invoice_date'))
        totals = payment_services.invoice_balance_totals(invoices)
        payments = Payment.objects.filter(company=request.user.company, supplier=supplier).order_by('payment_date')
        return Response({
            'supplier': {'id': supplier.pk, 'name': supplier.name},
            'invoices': [{
                'id': invoice.pk, 'number': invoice.invoice_number, 'date': invoice.invoice_date,
                'total': invoice.total_amount, 'credits': totals[invoice.pk]['credits'],
                'payments': totals[invoice.pk]['payments'],
                'balance': totals[invoice.pk]['balance'],
                'base_balance': services.base_money(totals[invoice.pk]['balance'], invoice.exchange_rate),
            } for invoice in invoices],
            'payments': PaymentSerializer(payments, many=True, context={'request': request}).data,
            'advances': SupplierAdvanceSerializer(
                supplier.advances.filter(status=SupplierAdvance.STATUS_AUTHORIZED), many=True,
            ).data,
        })


@extend_schema_view(
    list=extend_schema(tags=['Finance - Ledger'], summary='List immutable journal entries'),
    retrieve=extend_schema(tags=['Finance - Ledger'], summary='Retrieve a journal entry and its lines'),
)
class JournalEntryViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = JournalEntry.objects.select_related('posted_by', 'reversal_of').prefetch_related(
        'lines__account', 'lines__project', 'lines__supplier',
    )
    serializer_class = JournalEntrySerializer
    filterset_class = JournalEntryFilter
    search_fields = ['number', 'description']
    ordering_fields = ['number', 'date', 'source_type', 'posted_at']
    ordering = ['-date', '-posted_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Project Costs'], summary='List project costs and reversals'),
    retrieve=extend_schema(tags=['Finance - Project Costs'], summary='Retrieve a project cost record'),
)
class ProjectCostViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ProjectCost.objects.select_related('project', 'supplier_invoice', 'payment', 'journal_entry')
    serializer_class = ProjectCostSerializer
    filterset_class = ProjectCostFilter
    search_fields = ['project__name', 'project__code', 'supplier_invoice__internal_number', 'payment__number']
    ordering_fields = ['date', 'amount', 'created_at']
    ordering = ['-date', '-created_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Landed Costs'], summary='List company landed-cost documents'),
    retrieve=extend_schema(tags=['Finance - Landed Costs'], summary='Retrieve landed-cost details and allocation preview'),
    create=extend_schema(tags=['Finance - Landed Costs'], summary='Prepare a draft landed-cost document'),
    partial_update=extend_schema(tags=['Finance - Landed Costs'], summary='Update an original draft landed-cost document'),
)
class LandedCostDocumentViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = LandedCostDocument.objects.select_related(
        'currency', 'created_by', 'approved_by', 'posted_by', 'reversal_of',
    ).prefetch_related(
        'goods_received_notes', 'items__tax_code', 'approvals__acted_by',
        'allocations__goods_received_note_item__goods_received_note',
        'allocations__receipt_movement__material',
        'allocations__receipt_movement__warehouse',
    )
    serializer_class = LandedCostDocumentSerializer
    filterset_class = LandedCostDocumentFilter
    search_fields = ['number', 'description', 'goods_received_notes__number']
    ordering_fields = ['number', 'status', 'total_amount', 'base_total_amount', 'created_at', 'posted_at']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in {'create', 'partial_update', 'preview', 'submit'}:
            permission_classes = [FinancePreparationPermission]
        elif self.action in {'approve', 'post', 'reverse'}:
            permission_classes = [FinanceAdminPermission]
        else:
            permission_classes = [FinanceCompanyPermission]
        return [permission() for permission in permission_classes]

    @extend_schema(
        tags=['Finance - Landed Costs'], request=LandedCostPreviewRequestSerializer,
        responses=LandedCostDocumentSerializer,
        summary='Calculate and persist an item-level allocation preview',
    )
    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        payload = LandedCostPreviewRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        document = landed_cost_services.preview_allocations(
            document=self.get_object(), user=request.user,
            inputs=payload.validated_data['inputs'],
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        tags=['Finance - Landed Costs'], request=CommentsSerializer,
        responses=LandedCostDocumentSerializer, summary='Submit a previewed landed cost',
    )
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        document = landed_cost_services.submit_document(
            document=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        tags=['Finance - Landed Costs'], request=CommentsSerializer,
        responses=LandedCostDocumentSerializer, summary='Approve a submitted landed cost',
    )
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        document = landed_cost_services.approve_document(
            document=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(document).data)

    @extend_schema(
        tags=['Finance - Landed Costs'], request=PaymentPostRequestSerializer,
        responses=LandedCostDocumentSerializer,
        summary='Post approved allocations into inventory valuation',
    )
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        payload = PaymentPostRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        document = landed_cost_services.post_document(
            document=self.get_object(), user=request.user,
            idempotency_key=payload.validated_data['idempotency_key'],
        )
        push_dashboard_update(document.company)
        return Response(self.get_serializer(document).data)

    @extend_schema(
        tags=['Finance - Landed Costs'], request=ReversalRequestSerializer,
        responses=LandedCostDocumentSerializer,
        summary='Reverse a posted landed cost through a new posted reversal document',
    )
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reversal = landed_cost_services.reverse_document(
            document=self.get_object(), user=request.user,
            reason=payload.validated_data['reason'],
            idempotency_key=payload.validated_data['idempotency_key'],
        )
        push_dashboard_update(reversal.company)
        return Response(self.get_serializer(reversal).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(tags=['Finance - Expenses'], summary='List company expense categories'),
    retrieve=extend_schema(tags=['Finance - Expenses'], summary='Retrieve an expense category'),
    create=extend_schema(tags=['Finance - Expenses'], summary='Create an expense category'),
    partial_update=extend_schema(tags=['Finance - Expenses'], summary='Update an expense category'),
)
class ExpenseCategoryViewSet(FoundationConfigurationViewSet):
    queryset = ExpenseCategory.objects.select_related('expense_account', 'budget_category')
    serializer_class = ExpenseCategorySerializer
    filterset_class = ExpenseCategoryFilter
    search_fields = ['code', 'name', 'expense_account__name', 'budget_category__name']
    ordering_fields = ['code', 'name', 'category_type', 'is_active', 'created_at']
    ordering = ['name']


@extend_schema_view(
    list=extend_schema(tags=['Finance - Petty Cash'], summary='List company cash accounts'),
    retrieve=extend_schema(tags=['Finance - Petty Cash'], summary='Retrieve a cash account and balance'),
    create=extend_schema(tags=['Finance - Petty Cash'], summary='Create a cash account'),
    partial_update=extend_schema(tags=['Finance - Petty Cash'], summary='Update an unposted cash account'),
)
class CashAccountViewSet(FoundationConfigurationViewSet):
    queryset = CashAccount.objects.select_related('account', 'currency')
    serializer_class = CashAccountSerializer
    filterset_class = CashAccountFilter
    search_fields = ['code', 'name', 'account__code', 'account__name']
    ordering_fields = ['code', 'name', 'opening_balance', 'is_active', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        permission = FinanceAdminPermission if self.action == 'replenish' else FinanceFoundationPermission
        return [permission()]

    @extend_schema(
        tags=['Finance - Petty Cash'], request=CashReplenishmentRequestSerializer,
        responses=PettyCashTransactionSerializer, summary='Post a petty-cash replenishment',
    )
    @action(detail=True, methods=['post'])
    def replenish(self, request, pk=None):
        payload = CashReplenishmentRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        record = cash_services.replenish_cash_account(
            cash_account=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PettyCashTransactionSerializer(record).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Petty Cash'], responses=CashAccountSerializer(many=True))
    @action(detail=False, methods=['get'])
    def balances(self, request):
        return Response(self.get_serializer(self.filter_queryset(self.get_queryset()), many=True).data)


class BankStatementLineViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    """Manual/imported bank evidence; matching is a manager-controlled action."""

    queryset = BankStatementLine.objects.select_related(
        'cash_account__currency', 'cash_account__account', 'payment', 'imported_by', 'matched_by',
    )
    serializer_class = BankStatementLineSerializer
    filterset_class = BankStatementLineFilter
    search_fields = ['reference', 'description', 'payment__number', 'payment__reference']
    ordering_fields = ['statement_date', 'amount', 'status', 'created_at', 'matched_at']
    ordering = ['-statement_date', '-id']
    http_method_names = ['get', 'post', 'patch', 'head', 'options']

    def get_permissions(self):
        if self.action in {'match', 'unmatch', 'ignore'}:
            permission = FinanceAdminPermission
        elif self.action in {'create', 'partial_update', 'import_csv'}:
            permission = FinancePreparationPermission
        else:
            permission = FinanceCompanyPermission
        return [permission()]

    def partial_update(self, request, *args, **kwargs):
        line = self.get_object()
        if line.status != BankStatementLine.STATUS_UNRECONCILED:
            return Response({'detail': 'Only unreconciled lines can be edited.'}, status=status.HTTP_400_BAD_REQUEST)
        return super().partial_update(request, *args, **kwargs)

    @extend_schema(tags=['Finance - Reconciliation'], request=None, responses=dict)
    @action(detail=False, methods=['post'], url_path='import-csv')
    def import_csv(self, request):
        """Import bank evidence using a small, auditable CSV contract.

        Required columns: statement_date, reference, amount.
        Optional column: description. Duplicate account/date/reference rows are
        reported as skipped rather than creating a second bank event.
        """
        cash_account_id = request.data.get('cash_account')
        uploaded = request.FILES.get('file')
        if not cash_account_id or not uploaded:
            return Response({'detail': 'cash_account and file are required.'}, status=status.HTTP_400_BAD_REQUEST)
        cash_account = CashAccount.objects.filter(
            pk=cash_account_id, company=request.user.company, is_active=True,
        ).first()
        if not cash_account:
            return Response({'cash_account': 'Select an active cash account from your company.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            reader = DictReader(TextIOWrapper(uploaded.file, encoding='utf-8-sig'))
            headers = {header.strip().lower() for header in (reader.fieldnames or []) if header}
            required = {'statement_date', 'reference', 'amount'}
            if not required.issubset(headers):
                return Response({'file': [f'CSV must contain columns: {", ".join(sorted(required))}.']}, status=status.HTTP_400_BAD_REQUEST)
            created = 0
            skipped = 0
            errors = []
            with transaction.atomic():
                for row_number, row in enumerate(reader, start=2):
                    try:
                        values = {
                            str(key).strip().lower(): value
                            for key, value in row.items()
                            if key is not None
                        }
                        statement_date = (values.get('statement_date') or '').strip()
                        reference = (values.get('reference') or '').strip()
                        amount = Decimal(str(values.get('amount') or '').replace(',', '').strip())
                        description = (values.get('description') or '').strip()
                        if not statement_date or not reference or not amount:
                            raise ValueError('statement_date, reference, and non-zero amount are required.')
                        if BankStatementLine.objects.filter(
                            cash_account=cash_account, statement_date=statement_date, reference=reference,
                        ).exists():
                            skipped += 1
                            continue
                        BankStatementLine.objects.create(
                            company=request.user.company, cash_account=cash_account,
                            statement_date=statement_date, reference=reference,
                            description=description, amount=amount, imported_by=request.user,
                        )
                        created += 1
                    except Exception as exc:
                        errors.append({'row': row_number, 'detail': str(exc)})
            return Response({'created': created, 'skipped_duplicates': skipped, 'errors': errors})
        except UnicodeDecodeError:
            return Response({'file': ['CSV must be UTF-8 encoded.']}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        lines = self.filter_queryset(self.get_queryset()).order_by('-statement_date', '-id')
        rows = [{
            'date': line.statement_date,
            'account': line.cash_account.name,
            'reference': line.reference,
            'description': line.description or '-',
            'amount': line.amount,
            'currency': line.cash_account.currency.code,
            'status': line.get_status_display(),
            'payment': line.payment.number if line.payment_id else '-',
            'imported_by': line.imported_by.get_full_name() if line.imported_by_id else '-',
        } for line in lines]
        return _finance_export(
            kind=kind, title='Bank and cash reconciliation register', filename='bank-reconciliation-register',
            columns=[('date', 'Statement date'), ('account', 'Cash account'), ('reference', 'Reference'), ('description', 'Description'), ('amount', 'Amount'), ('currency', 'Currency'), ('status', 'Status'), ('payment', 'Matched payment'), ('imported_by', 'Imported by')],
            rows=rows, totals={'Statement lines': len(rows), 'Unreconciled': sum(1 for line in lines if line.status == BankStatementLine.STATUS_UNRECONCILED)},
        )

    @action(detail=True, methods=['post'])
    def match(self, request, pk=None):
        line = self.get_object()
        if line.status != BankStatementLine.STATUS_UNRECONCILED:
            return Response({'detail': 'Only unreconciled statement lines can be matched.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = ReconcileStatementLineSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        payment = payload.validated_data['payment']
        if hasattr(payment, 'reconciliation_line'):
            return Response({'detail': 'This payment is already reconciled.'}, status=status.HTTP_400_BAD_REQUEST)
        line.payment = payment
        line.status = BankStatementLine.STATUS_MATCHED
        line.match_notes = payload.validated_data.get('match_notes', '')
        line.matched_by = request.user
        line.matched_at = timezone.now()
        line.save()
        return Response(self.get_serializer(line).data)

    @action(detail=True, methods=['post'])
    def unmatch(self, request, pk=None):
        line = self.get_object()
        if line.status != BankStatementLine.STATUS_MATCHED:
            return Response({'detail': 'Only matched statement lines can be unmatched.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = StatementLineReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        line.payment = None
        line.status = BankStatementLine.STATUS_UNRECONCILED
        line.match_notes = f"Unmatched: {payload.validated_data['match_notes']}"
        line.matched_by = request.user
        line.matched_at = timezone.now()
        line.save()
        return Response(self.get_serializer(line).data)

    @action(detail=True, methods=['post'])
    def ignore(self, request, pk=None):
        line = self.get_object()
        if line.status != BankStatementLine.STATUS_UNRECONCILED:
            return Response({'detail': 'Only unreconciled statement lines can be ignored.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = StatementLineReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        line.status = BankStatementLine.STATUS_IGNORED
        line.match_notes = payload.validated_data['match_notes']
        line.matched_by = request.user
        line.matched_at = timezone.now()
        line.save()
        return Response(self.get_serializer(line).data)
@extend_schema_view(
    list=extend_schema(tags=['Finance - Expense Claims'], summary='List company expense claims'),
    retrieve=extend_schema(tags=['Finance - Expense Claims'], summary='Retrieve an expense claim'),
    create=extend_schema(tags=['Finance - Expense Claims'], summary='Prepare an expense claim'),
    partial_update=extend_schema(tags=['Finance - Expense Claims'], summary='Edit a draft expense claim'),
)
class ExpenseClaimViewSet(DraftDeletionMixin, CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = expense_claim_queryset()
    serializer_class = ExpenseClaimSerializer
    filterset_class = ExpenseClaimFilter
    search_fields = ['number', 'purpose', 'payment_reference', 'claimant__username', 'project__name']
    ordering_fields = ['number', 'claim_date', 'total_amount', 'status', 'created_at', 'paid_at']
    ordering = ['-claim_date', '-id']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'voucher', 'summary', 'download'}:
            permission = FinanceCompanyPermission
        elif self.action in {'approve', 'reject', 'pay', 'reverse'}:
            permission = FinanceAdminPermission
        else:
            permission = FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Expense Claims'], request=CommentsSerializer, responses=ExpenseClaimSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        claim = expense_claim_services.submit_expense_claim(
            claim=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(claim).data)

    @extend_schema(tags=['Finance - Expense Claims'], request=CommentsSerializer, responses=ExpenseClaimSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        claim = expense_claim_services.approve_expense_claim(
            claim=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(claim).data)

    @extend_schema(tags=['Finance - Expense Claims'], request=ReasonSerializer, responses=ExpenseClaimSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        claim = expense_claim_services.reject_expense_claim(
            claim=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(claim).data)

    @extend_schema(tags=['Finance - Expense Claims'], request=ExpensePayRequestSerializer, responses=ExpenseClaimSerializer)
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        payload = ExpensePayRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        claim = expense_claim_services.pay_expense_claim(
            claim=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(claim).data)

    @extend_schema(tags=['Finance - Expense Claims'], request=ReversalRequestSerializer, responses=PettyCashTransactionSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        record = expense_claim_services.reverse_expense_claim(
            claim=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PettyCashTransactionSerializer(record).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Expense Claims'], responses=dict)
    @action(detail=True, methods=['get'])
    def voucher(self, request, pk=None):
        claim = self.get_object()
        return Response({
            'voucher_number': claim.number,
            'claim_date': claim.claim_date,
            'claimant': claim.claimant.get_full_name() or claim.claimant.username,
            'destination': {
                'project': claim.project.name if claim.project else None,
                'cost_centre': claim.cost_centre.name if claim.cost_centre else None,
                'overhead_category': claim.overhead_category.name if claim.overhead_category else None,
            },
            'purpose': claim.purpose,
            'currency': claim.currency.code,
            'total_amount': claim.total_amount,
            'status': claim.status,
            'payment_reference': claim.payment_reference,
            'items': ExpenseClaimSerializer(claim, context={'request': request}).data['items'],
            'prepared_by': claim.created_by.get_full_name() or claim.created_by.username,
            'approved_by': claim.approved_by.get_full_name() if claim.approved_by else None,
            'paid_by': claim.paid_by.get_full_name() if claim.paid_by else None,
            'paid_at': claim.paid_at,
        })

    @extend_schema(tags=['Finance - Expense Claims'], responses=dict)
    @action(detail=False, methods=['get'])
    def summary(self, request):
        claims = self.filter_queryset(self.get_queryset()).filter(
            status__in=[ExpenseClaim.STATUS_PAID, ExpenseClaim.STATUS_CLOSED],
        )
        claim_total = claims.aggregate(total=Sum('base_total_amount'))['total'] or 0
        retirement_query = AdvanceRetirement.objects.filter(
            company=request.user.company, is_reversal=False, reversal__isnull=True,
            advance__status__in=[StaffAdvance.STATUS_PAID, StaffAdvance.STATUS_RETIRED, StaffAdvance.STATUS_CLOSED],
        ).select_related('advance', 'expense_category')
        project_id = request.query_params.get('project')
        if project_id:
            retirement_query = retirement_query.filter(
                Q(advance__project_id=project_id) | Q(advance__cost_centre__project_id=project_id),
            )
        retired_spend = sum(
            (row.amount_spent * row.advance.exchange_rate for row in retirement_query), 0,
        )
        return Response({
            'posted_expense_claims': claims.count(),
            'expense_claim_total': claim_total,
            'retired_advance_expenditure': retired_spend,
            'total_expenditure': claim_total + retired_spend,
        })

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        claim = self.get_object()
        rows = [{
            'claim': claim.number,
            'claimant': claim.claimant.get_full_name() or claim.claimant.username,
            'date': claim.claim_date,
            'project': claim.project.name if claim.project_id else '-',
            'purpose': claim.purpose,
            'currency': claim.currency.code,
            'amount': claim.total_amount,
            'status': claim.get_status_display(),
            'payment_reference': claim.payment_reference or '-',
        }]
        return _finance_export(
            kind=kind, title=f'Expense claim - {claim.number}', filename=claim.number,
            columns=[('claim', 'Claim'), ('claimant', 'Claimant'), ('date', 'Claim date'), ('project', 'Project'), ('purpose', 'Purpose'), ('currency', 'Currency'), ('amount', 'Amount'), ('status', 'Status'), ('payment_reference', 'Payment reference')],
            rows=rows, totals={'Claim total': claim.total_amount, 'Status': claim.get_status_display()},
        )


class ExpenseReceiptAttachmentViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = ExpenseReceiptAttachment.objects.select_related('claim', 'expense_item', 'uploaded_by')
    serializer_class = ExpenseReceiptAttachmentSerializer
    filterset_fields = ['claim', 'expense_item', 'content_type', 'uploaded_by']
    ordering = ['-created_at']
    http_method_names = ['get', 'post', 'head', 'options']

    def get_permissions(self):
        permission = FinanceCompanyPermission if self.action in {'list', 'retrieve', 'download'} else FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Expense Receipts'], responses={(200, 'application/octet-stream'): bytes})
    @action(detail=True, methods=['get'])
    def download(self, request, pk=None):
        receipt = self.get_object()
        return FileResponse(
            receipt.file.open('rb'), as_attachment=True, filename=receipt.original_name,
            content_type=receipt.content_type,
        )


@extend_schema_view(
    list=extend_schema(tags=['Finance - Staff Advances'], summary='List company staff advances'),
    retrieve=extend_schema(tags=['Finance - Staff Advances'], summary='Retrieve a staff advance'),
    create=extend_schema(tags=['Finance - Staff Advances'], summary='Prepare a staff advance'),
    partial_update=extend_schema(tags=['Finance - Staff Advances'], summary='Edit a draft staff advance'),
)
class StaffAdvanceViewSet(DraftDeletionMixin, CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = StaffAdvance.objects.select_related(
        'staff', 'project', 'cost_centre', 'overhead_category', 'currency',
        'cash_account', 'created_by', 'approved_by', 'paid_by',
    ).prefetch_related('retirements__expense_category', 'approvals')
    serializer_class = StaffAdvanceSerializer
    filterset_class = StaffAdvanceFilter
    search_fields = ['number', 'purpose', 'payment_reference', 'staff__username', 'project__name']
    ordering_fields = ['number', 'advance_date', 'amount', 'status', 'created_at', 'paid_at']
    ordering = ['-advance_date', '-id']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'voucher', 'outstanding'}:
            permission = FinanceCompanyPermission
        elif self.action in {'approve', 'reject', 'pay', 'retire', 'reverse'}:
            permission = FinanceAdminPermission
        else:
            permission = FinancePreparationPermission
        return [permission()]

    @extend_schema(tags=['Finance - Staff Advances'], request=CommentsSerializer, responses=StaffAdvanceSerializer)
    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        advance = staff_advance_services.submit_staff_advance(
            advance=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(advance).data)

    @extend_schema(tags=['Finance - Staff Advances'], request=CommentsSerializer, responses=StaffAdvanceSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        payload = CommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        advance = staff_advance_services.approve_staff_advance(
            advance=self.get_object(), user=request.user,
            comments=payload.validated_data.get('comments', ''),
        )
        return Response(self.get_serializer(advance).data)

    @extend_schema(tags=['Finance - Staff Advances'], request=ReasonSerializer, responses=StaffAdvanceSerializer)
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        payload = ReasonSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        advance = staff_advance_services.reject_staff_advance(
            advance=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(advance).data)

    @extend_schema(tags=['Finance - Staff Advances'], request=ExpensePayRequestSerializer, responses=StaffAdvanceSerializer)
    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        payload = ExpensePayRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        advance = staff_advance_services.pay_staff_advance(
            advance=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(advance).data)

    @extend_schema(tags=['Finance - Staff Advances'], request=StaffAdvanceRetirementRequestSerializer, responses=AdvanceRetirementSerializer)
    @action(detail=True, methods=['post'])
    def retire(self, request, pk=None):
        payload = StaffAdvanceRetirementRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        retirement = staff_advance_services.retire_staff_advance(
            advance=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(AdvanceRetirementSerializer(retirement).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Staff Advances'], request=ReversalRequestSerializer, responses=PettyCashTransactionSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        record = staff_advance_services.reverse_staff_advance(
            advance=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(PettyCashTransactionSerializer(record).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Staff Advances'], responses=StaffAdvanceSerializer(many=True))
    @action(detail=False, methods=['get'])
    def outstanding(self, request):
        advances = self.filter_queryset(self.get_queryset()).filter(
            status__in=[StaffAdvance.STATUS_PAID, StaffAdvance.STATUS_RETIRED],
        )
        data = self.get_serializer(advances, many=True).data
        return Response([row for row in data if row['outstanding_amount'] != '0.00'])

    @extend_schema(tags=['Finance - Staff Advances'], responses=dict)
    @action(detail=True, methods=['get'])
    def voucher(self, request, pk=None):
        advance = self.get_object()
        return Response({
            'voucher_number': advance.number,
            'advance_date': advance.advance_date,
            'staff': advance.staff.get_full_name() or advance.staff.username,
            'purpose': advance.purpose,
            'project': advance.project.name if advance.project else None,
            'currency': advance.currency.code,
            'amount': advance.amount,
            'retired_amount': advance.retired_amount,
            'outstanding_amount': advance.outstanding_amount,
            'status': advance.status,
            'payment_reference': advance.payment_reference,
            'prepared_by': advance.created_by.get_full_name() or advance.created_by.username,
            'approved_by': advance.approved_by.get_full_name() if advance.approved_by else None,
            'paid_by': advance.paid_by.get_full_name() if advance.paid_by else None,
            'paid_at': advance.paid_at,
        })


class AdvanceRetirementViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = AdvanceRetirement.objects.select_related('advance', 'expense_category', 'retired_by')
    serializer_class = AdvanceRetirementSerializer
    filterset_fields = ['advance', 'expense_category', 'is_reversal', 'retired_by']
    ordering_fields = ['retirement_date', 'total_retired', 'created_at']
    ordering = ['-retirement_date', '-id']

    def get_permissions(self):
        permission = FinanceAdminPermission if self.action == 'reverse' else FinanceCompanyPermission
        return [permission()]

    @extend_schema(tags=['Finance - Staff Advances'], request=ReversalRequestSerializer, responses=AdvanceRetirementSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reversal = staff_advance_services.reverse_advance_retirement(
            retirement=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(reversal).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        advance = self.get_object()
        rows = [{
            'advance': advance.number,
            'staff': advance.staff.get_full_name() or advance.staff.username,
            'date': advance.advance_date,
            'due': advance.due_date or '-',
            'project': advance.project.name if advance.project_id else '-',
            'purpose': advance.purpose,
            'currency': advance.currency.code,
            'amount': advance.amount,
            'status': advance.get_status_display(),
        }]
        return _finance_export(
            kind=kind, title=f'Staff advance - {advance.number}', filename=advance.number,
            columns=[('advance', 'Advance'), ('staff', 'Staff member'), ('date', 'Advance date'), ('due', 'Retirement due'), ('project', 'Project'), ('purpose', 'Purpose'), ('currency', 'Currency'), ('amount', 'Amount'), ('status', 'Status')],
            rows=rows, totals={'Advance amount': advance.amount, 'Status': advance.get_status_display()},
        )


class PettyCashTransactionViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = PettyCashTransaction.objects.select_related(
        'cash_account__currency', 'expense_claim', 'staff_advance', 'advance_retirement',
        'original_transaction', 'journal_entry', 'posted_by',
    )
    serializer_class = PettyCashTransactionSerializer
    filterset_class = PettyCashTransactionFilter
    search_fields = ['reference', 'reason', 'expense_claim__number', 'staff_advance__number']
    ordering_fields = ['transaction_date', 'amount', 'transaction_type', 'status', 'posted_at']
    ordering = ['-transaction_date', '-id']

    def get_permissions(self):
        permission = FinanceAdminPermission if self.action == 'reverse' else FinanceCompanyPermission
        return [permission()]

    @extend_schema(tags=['Finance - Petty Cash'], request=ReversalRequestSerializer, responses=PettyCashTransactionSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        record = cash_services.reverse_petty_cash_transaction(
            transaction_record=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(self.get_serializer(record).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - Petty Cash'], responses=dict, summary='Return printable petty-cash voucher data')
    @action(detail=True, methods=['get'])
    def voucher(self, request, pk=None):
        record = self.get_object()
        return Response({
            'voucher_number': f'PC-{record.pk:06d}',
            'transaction_date': record.transaction_date,
            'cash_account': record.cash_account.name,
            'currency': record.cash_account.currency.code,
            'transaction_type': record.transaction_type,
            'amount': record.amount,
            'balance_effect': record.balance_effect,
            'reference': record.reference,
            'reason': record.reason,
            'status': record.status,
            'posted_by': record.posted_by.get_full_name() or record.posted_by.username,
            'posted_at': record.posted_at,
        })

    @action(detail=True, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, pk=None, kind=None):
        record = self.get_object()
        rows = [{
            'voucher': f'PC-{record.pk:06d}',
            'date': record.transaction_date,
            'account': record.cash_account.name,
            'currency': record.cash_account.currency.code,
            'type': record.get_transaction_type_display(),
            'amount': record.amount,
            'effect': record.balance_effect,
            'reference': record.reference,
            'reason': record.reason,
            'status': record.get_status_display(),
        }]
        return _finance_export(
            kind=kind, title=f'Petty cash voucher - PC-{record.pk:06d}', filename=f'petty-cash-PC-{record.pk:06d}',
            columns=[('voucher', 'Voucher'), ('date', 'Date'), ('account', 'Cash account'), ('currency', 'Currency'), ('type', 'Type'), ('amount', 'Amount'), ('effect', 'Balance effect'), ('reference', 'Reference'), ('reason', 'Reason'), ('status', 'Status')],
            rows=rows, totals={'Amount': record.amount, 'Balance effect': record.balance_effect},
        )


class ExpenseApprovalViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ExpenseApproval.objects.select_related(
        'expense_claim', 'staff_advance', 'petty_cash_transaction', 'acted_by',
    )
    serializer_class = ExpenseApprovalSerializer
    filterset_fields = ['expense_claim', 'staff_advance', 'petty_cash_transaction', 'action', 'acted_by']
    ordering = ['-acted_at']


@extend_schema_view(
    list=extend_schema(tags=['Finance - General Ledger'], summary='List chart-of-account records'),
    retrieve=extend_schema(tags=['Finance - General Ledger'], summary='Retrieve a chart-of-account record'),
    create=extend_schema(tags=['Finance - General Ledger'], summary='Create an account'),
    partial_update=extend_schema(tags=['Finance - General Ledger'], summary='Update an account'),
)
class ChartOfAccountViewSet(FoundationConfigurationViewSet):
    queryset = ChartOfAccount.objects.select_related('parent')
    serializer_class = ChartOfAccountSerializer
    filterset_class = ChartOfAccountFilter
    search_fields = ['code', 'name', 'description', 'parent__code', 'parent__name']
    ordering_fields = ['code', 'name', 'account_type', 'is_active', 'created_at']
    ordering = ['code']

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.company_id:
            ledger_workflow_services.ensure_ledger_configuration(self.request.user.company)
        return super().get_queryset()

    @extend_schema(tags=['Finance - General Ledger'], responses=dict, summary='Return the account ledger')
    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        account = self.get_object()
        lines = JournalLine.objects.filter(
            company=request.user.company,
            account=account,
            entry__status__in=[JournalEntry.STATUS_POSTED, JournalEntry.STATUS_REVERSED],
        ).select_related('entry', 'project', 'supplier').order_by('entry__date', 'entry_id', 'id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        project = request.query_params.get('project')
        supplier = request.query_params.get('supplier')
        if project:
            lines = lines.filter(project_id=project)
        if supplier:
            lines = lines.filter(supplier_id=supplier)
        opening_lines = lines.none()
        if date_from:
            opening_lines = lines.filter(entry__date__lt=date_from)
            lines = lines.filter(entry__date__gte=date_from)
        if date_to:
            lines = lines.filter(entry__date__lte=date_to)
        opening = opening_lines.aggregate(debit=Sum('debit'), credit=Sum('credit'))
        normal_debit = account.account_type in {Account.TYPE_ASSET, Account.TYPE_EXPENSE}
        opening_balance = Decimal(opening['debit'] or 0) - Decimal(opening['credit'] or 0)
        if not normal_debit:
            opening_balance = -opening_balance
        page = self.paginate_queryset(lines)
        selected = page if page is not None else list(lines)
        running = opening_balance
        if page is not None and self.paginator.page.start_index() > 1:
            prior_count = self.paginator.page.start_index() - 1
            prior_ids = list(lines.values_list('pk', flat=True)[:prior_count])
            prior = JournalLine.objects.filter(pk__in=prior_ids).aggregate(
                debit=Sum('debit'), credit=Sum('credit'),
            )
            prior_effect = Decimal(prior['debit'] or 0) - Decimal(prior['credit'] or 0)
            running += prior_effect if normal_debit else -prior_effect
        rows = []
        for line in selected:
            effect = line.debit - line.credit if normal_debit else line.credit - line.debit
            running += effect
            rows.append({
                'journal_id': line.entry_id,
                'journal_number': line.entry.number,
                'date': line.entry.date,
                'description': line.description or line.entry.description,
                'source_type': line.entry.source_type,
                'source_record': line.entry.source_object_id,
                'project': line.project_id,
                'supplier': line.supplier_id,
                'debit': line.debit,
                'credit': line.credit,
                'running_balance': running,
            })
        if page is not None:
            response = self.get_paginated_response(rows)
            response.data['account'] = {'id': account.pk, 'code': account.code, 'name': account.name}
            response.data['opening_balance'] = opening_balance
            return response
        return Response({
            'account': {'id': account.pk, 'code': account.code, 'name': account.name},
            'opening_balance': opening_balance,
            'results': rows,
        })


@extend_schema_view(
    list=extend_schema(tags=['Finance - Fiscal Periods'], summary='List company fiscal periods'),
    retrieve=extend_schema(tags=['Finance - Fiscal Periods'], summary='Retrieve a fiscal period'),
    create=extend_schema(tags=['Finance - Fiscal Periods'], summary='Create an open fiscal period'),
    partial_update=extend_schema(tags=['Finance - Fiscal Periods'], summary='Edit an open fiscal period'),
)
class FiscalPeriodViewSet(FoundationConfigurationViewSet):
    queryset = FiscalPeriod.objects.select_related('closed_by')
    serializer_class = FiscalPeriodSerializer
    filterset_class = FiscalPeriodFilter
    search_fields = ['name']
    ordering_fields = ['name', 'start_date', 'end_date', 'status', 'created_at']
    ordering = ['-start_date']

    @extend_schema(tags=['Finance - Month End'], responses=dict, summary='Return the period-close readiness checklist')
    @action(detail=True, methods=['get'])
    def checklist(self, request, pk=None):
        return Response(month_end_workflow_services.checklist(company=request.user.company, period=self.get_object()))

    @extend_schema(tags=['Finance - Fiscal Periods'], request=None, responses=FiscalPeriodSerializer)
    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        period = ledger_workflow_services.set_period_status(
            period=self.get_object(), user=request.user, status=FiscalPeriod.STATUS_CLOSED,
        )
        return Response(self.get_serializer(period).data)

    @extend_schema(tags=['Finance - Fiscal Periods'], request=None, responses=FiscalPeriodSerializer)
    @action(detail=True, methods=['post'])
    def open(self, request, pk=None):
        period = ledger_workflow_services.set_period_status(
            period=self.get_object(), user=request.user, status=FiscalPeriod.STATUS_OPEN,
        )
        return Response(self.get_serializer(period).data)


@extend_schema_view(
    list=extend_schema(tags=['Finance - Posting Configuration'], summary='List posting rules'),
    retrieve=extend_schema(tags=['Finance - Posting Configuration'], summary='Retrieve a posting rule'),
    create=extend_schema(tags=['Finance - Posting Configuration'], summary='Create a posting rule'),
    partial_update=extend_schema(tags=['Finance - Posting Configuration'], summary='Update a posting rule'),
)
class PostingRuleViewSet(FoundationConfigurationViewSet):
    queryset = PostingRule.objects.all()
    serializer_class = PostingRuleSerializer
    filterset_class = PostingRuleFilter
    search_fields = ['event_type', 'name', 'debit_mapping_key', 'credit_mapping_key']
    ordering_fields = ['event_type', 'name', 'is_active', 'created_at']
    ordering = ['event_type']

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.company_id:
            ledger_workflow_services.ensure_ledger_configuration(self.request.user.company)
        return super().get_queryset()


@extend_schema_view(
    list=extend_schema(tags=['Finance - Posting Configuration'], summary='List account mappings'),
    retrieve=extend_schema(tags=['Finance - Posting Configuration'], summary='Retrieve an account mapping'),
    create=extend_schema(tags=['Finance - Posting Configuration'], summary='Create an account mapping'),
    partial_update=extend_schema(tags=['Finance - Posting Configuration'], summary='Update an account mapping'),
)
class AccountMappingViewSet(FoundationConfigurationViewSet):
    queryset = AccountMapping.objects.select_related('account')
    serializer_class = AccountMappingSerializer
    filterset_class = AccountMappingFilter
    search_fields = ['mapping_key', 'description', 'account__code', 'account__name']
    ordering_fields = ['mapping_key', 'account__code', 'is_active', 'created_at']
    ordering = ['mapping_key']

    def get_queryset(self):
        if self.request.user.is_authenticated and self.request.user.company_id:
            ledger_workflow_services.ensure_ledger_configuration(self.request.user.company)
        return super().get_queryset()


@extend_schema_view(
    list=extend_schema(tags=['Finance - General Ledger'], summary='List company journals'),
    retrieve=extend_schema(tags=['Finance - General Ledger'], summary='Retrieve a journal'),
    create=extend_schema(tags=['Finance - General Ledger'], summary='Prepare a draft manual journal'),
    partial_update=extend_schema(tags=['Finance - General Ledger'], summary='Edit a draft manual journal'),
    destroy=extend_schema(tags=['Finance - General Ledger'], summary='Delete a draft manual journal'),
)
class DraftJournalViewSet(CompanyScopedMixin, viewsets.ModelViewSet):
    queryset = JournalEntry.objects.select_related(
        'fiscal_period', 'created_by', 'posted_by', 'reversal_of',
    ).prefetch_related('lines__account', 'lines__project', 'lines__supplier').distinct()
    serializer_class = DraftJournalSerializer
    filterset_class = JournalEntryFilter
    search_fields = ['number', 'description', 'source_reference']
    ordering_fields = ['number', 'date', 'status', 'source_type', 'posted_at']
    ordering = ['-date', '-id']
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'trial_balance'}:
            permission = FinanceCompanyPermission
        elif self.action in {'post', 'reverse'}:
            permission = FinanceAdminPermission
        else:
            permission = FinancePreparationPermission
        return [permission()]

    def perform_destroy(self, instance):
        if instance.status != JournalEntry.STATUS_DRAFT:
            from rest_framework.exceptions import ValidationError

            raise ValidationError({'status': ['Only draft journals can be deleted.']})
        instance.delete()

    @extend_schema(tags=['Finance - General Ledger'], request=JournalPostRequestSerializer, responses=DraftJournalSerializer)
    @action(detail=True, methods=['post'])
    def post(self, request, pk=None):
        journal = self.get_object()
        try:
            journal = ledger_workflow_services.post_journal(journal=journal, user=request.user)
        except Exception as exc:
            from .notification_services import journal_posting_failed

            try:
                detail = getattr(exc, 'detail', str(exc))
                journal_posting_failed(journal, str(detail))
            except Exception:
                pass
            raise
        return Response(self.get_serializer(journal).data)

    @extend_schema(tags=['Finance - General Ledger'], request=ReversalRequestSerializer, responses=JournalReversalSerializer)
    @action(detail=True, methods=['post'])
    def reverse(self, request, pk=None):
        payload = ReversalRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        record = ledger_workflow_services.reverse_journal(
            journal=self.get_object(), user=request.user, **payload.validated_data,
        )
        return Response(JournalReversalSerializer(record).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Finance - General Ledger'], responses=dict, summary='Return a company trial balance')
    @action(detail=False, methods=['get'], url_path='trial-balance')
    def trial_balance(self, request):
        accounts = Account.objects.filter(company=request.user.company).order_by('code')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        period = request.query_params.get('fiscal_period')
        rows = []
        total_debit = Decimal('0.00')
        total_credit = Decimal('0.00')
        for account in accounts:
            lines = account.journal_lines.filter(
                entry__status__in=[JournalEntry.STATUS_POSTED, JournalEntry.STATUS_REVERSED],
            )
            if date_from:
                lines = lines.filter(entry__date__gte=date_from)
            if date_to:
                lines = lines.filter(entry__date__lte=date_to)
            if period:
                lines = lines.filter(entry__fiscal_period_id=period)
            totals = lines.aggregate(debit=Sum('debit'), credit=Sum('credit'))
            debit = Decimal(totals['debit'] or 0)
            credit = Decimal(totals['credit'] or 0)
            debit_balance = max(debit - credit, Decimal('0.00'))
            credit_balance = max(credit - debit, Decimal('0.00'))
            if debit or credit:
                rows.append({
                    'account_id': account.pk, 'account_code': account.code,
                    'account_name': account.name, 'account_type': account.account_type,
                    'debit': debit_balance, 'credit': credit_balance,
                })
                total_debit += debit_balance
                total_credit += credit_balance
        page = self.paginator.paginate_queryset(rows, request, view=self)
        response = self.paginator.get_paginated_response(page)
        response.data['total_debit'] = total_debit
        response.data['total_credit'] = total_credit
        response.data['is_balanced'] = total_debit == total_credit
        return response


@extend_schema_view(
    list=extend_schema(tags=['Finance - General Ledger'], summary='List journal reversal records'),
    retrieve=extend_schema(tags=['Finance - General Ledger'], summary='Retrieve a journal reversal record'),
)
class JournalReversalViewSet(CompanyScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = JournalReversal.objects.select_related(
        'original_journal', 'reversal_journal', 'reversed_by',
    )
    serializer_class = JournalReversalSerializer
    filterset_class = JournalReversalFilter
    search_fields = ['original_journal__number', 'reversal_journal__number', 'reason']
    ordering_fields = ['reversed_at', 'original_journal__number']
    ordering = ['-reversed_at']
