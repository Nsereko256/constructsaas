from decimal import Decimal

from rest_framework import serializers

from apps.procurement.models import GoodsReceivedNote, PurchaseOrder, PurchaseOrderItem, PurchaseRequest
from apps.accounts.models import User
from apps.projects.models import Project
from apps.suppliers.models import Supplier
from apps.api.upload_validation import validate_image_upload

from . import services
from . import configuration_services
from . import budget_services
from . import budget_approval_services
from . import payment_services
from . import landed_cost_services
from . import expense_services
from . import ledger_services
from .models import (
    Account,
    AccountMapping,
    AdvanceRetirement,
    BudgetApproval,
    BudgetCategory,
    BudgetLine,
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
    FinancialApproval,
    InvoiceApproval,
    InvoiceAttachment,
    InvoiceMatchItemResult,
    InvoiceMatchRun,
    InvoiceReversal,
    JournalEntry,
    JournalLine,
    JournalReversal,
    LandedCostAllocation,
    LandedCostApproval,
    LandedCostDocument,
    LandedCostItem,
    ExpenseApproval,
    ExpenseCategory,
    ExpenseClaim,
    ExpenseItem,
    ExpenseReceiptAttachment,
    Payment,
    PaymentBatch,
    PaymentBatchItem,
    PaymentAllocation,
    PaymentApproval,
    PaymentAttachment,
    PaymentReversal,
    PettyCashTransaction,
    PostingRule,
    ProjectCost,
    ProjectBudget,
    SupplierInvoice,
    SupplierInvoiceItem,
    SupplierInvoiceItemTax,
    SupplierCreditNote,
    SupplierCreditNoteItem,
    SupplierAdvance,
    StaffAdvance,
    TaxCode,
    ThreeWayMatch,
)


ZERO = Decimal('0.00')


class CompanyScopedSerializer(serializers.ModelSerializer):
    def company_queryset(self, model, **filters):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        return model.objects.filter(company_id=company_id, **filters)

    def validate(self, attrs):
        if self.instance is not None and 'client_uuid' in attrs:
            current = getattr(self.instance, 'client_uuid', None)
            if current is not None and attrs['client_uuid'] != current:
                raise serializers.ValidationError({'client_uuid': 'Client UUID is immutable once assigned.'})
        return super().validate(attrs)


class FinanceSettingsSerializer(CompanyScopedSerializer):
    base_currency_code = serializers.CharField(source='base_currency.code', read_only=True)

    class Meta:
        model = FinanceSettings
        fields = [
            'id', 'company', 'base_currency', 'base_currency_code', 'financial_year_start',
            'quantity_matching_tolerance', 'price_matching_tolerance',
            'finance_officer_approval_threshold', 'finance_manager_approval_threshold',
            'maker_checker_enforced', 'negative_stock_policy', 'document_retention_years',
            'require_invoice_attachment', 'require_payment_attachment', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['base_currency'].queryset = self.company_queryset(Currency, is_active=True)

    def update(self, instance, validated_data):
        return configuration_services.update_finance_settings(
            instance=instance,
            user=self.context['request'].user,
            values=validated_data,
        )


class ReferenceConfigurationSerializer(CompanyScopedSerializer):
    def create(self, validated_data):
        return configuration_services.create_reference_record(
            model=self.Meta.model,
            user=self.context['request'].user,
            values=validated_data,
        )

    def update(self, instance, validated_data):
        return configuration_services.update_reference_record(
            instance=instance,
            user=self.context['request'].user,
            values=validated_data,
        )


class CurrencySerializer(ReferenceConfigurationSerializer):
    class Meta:
        model = Currency
        fields = ['id', 'company', 'code', 'name', 'symbol', 'decimal_places', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class TaxCodeSerializer(ReferenceConfigurationSerializer):
    class Meta:
        model = TaxCode
        fields = [
            'id', 'company', 'code', 'name', 'rate_percent', 'description',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class CostCentreSerializer(ReferenceConfigurationSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = CostCentre
        fields = [
            'id', 'company', 'code', 'name', 'project', 'project_name', 'description',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'project_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = self.company_queryset(Project)


class BudgetCategorySerializer(ReferenceConfigurationSerializer):
    cost_centre_name = serializers.CharField(source='cost_centre.name', read_only=True)

    class Meta:
        model = BudgetCategory
        fields = [
            'id', 'company', 'code', 'name', 'cost_centre', 'cost_centre_name', 'description',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'cost_centre_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cost_centre'].queryset = self.company_queryset(CostCentre)


class FinanceAuditEventSerializer(serializers.ModelSerializer):
    actor_username = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = FinanceAuditEvent
        fields = [
            'id', 'company', 'actor', 'actor_username', 'action', 'object_type', 'object_id',
            'message', 'metadata', 'correlation_id', 'created_at',
        ]
        read_only_fields = fields


class BudgetLineSerializer(CompanyScopedSerializer):
    category_code = serializers.CharField(source='category.code', read_only=True)
    category_name = serializers.CharField(source='category.name', read_only=True)
    original_budget = serializers.SerializerMethodField()
    approved_revisions = serializers.SerializerMethodField()
    transfer_adjustment = serializers.SerializerMethodField()
    revised_budget = serializers.SerializerMethodField()
    open_commitments = serializers.SerializerMethodField()
    actual_expenditure = serializers.SerializerMethodField()
    available_balance = serializers.SerializerMethodField()

    class Meta:
        model = BudgetLine
        fields = [
            'id', 'category', 'category_code', 'category_name', 'description', 'original_amount',
            'original_budget', 'approved_revisions', 'transfer_adjustment', 'revised_budget',
            'open_commitments', 'actual_expenditure', 'available_balance', 'created_at',
        ]
        read_only_fields = [
            'id', 'category_code', 'category_name', 'original_budget', 'approved_revisions',
            'transfer_adjustment', 'revised_budget', 'open_commitments', 'actual_expenditure',
            'available_balance', 'created_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = self.company_queryset(BudgetCategory, is_active=True)

    def _summary(self, obj):
        return budget_services.budget_line_summary(obj)

    def get_original_budget(self, obj) -> Decimal:
        return self._summary(obj)['original_budget']

    def get_approved_revisions(self, obj) -> Decimal:
        return self._summary(obj)['approved_revisions']

    def get_transfer_adjustment(self, obj) -> Decimal:
        return self._summary(obj)['transfer_adjustment']

    def get_revised_budget(self, obj) -> Decimal:
        return self._summary(obj)['revised_budget']

    def get_open_commitments(self, obj) -> Decimal:
        return self._summary(obj)['open_commitments']

    def get_actual_expenditure(self, obj) -> Decimal:
        return self._summary(obj)['actual_expenditure']

    def get_available_balance(self, obj) -> Decimal:
        return self._summary(obj)['available_balance']


class ProjectBudgetSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_code = serializers.CharField(source='project.code', read_only=True)
    lines = BudgetLineSerializer(many=True)
    original_budget = serializers.SerializerMethodField()
    approved_revisions = serializers.SerializerMethodField()
    revised_budget = serializers.SerializerMethodField()
    open_commitments = serializers.SerializerMethodField()
    actual_expenditure = serializers.SerializerMethodField()
    available_balance = serializers.SerializerMethodField()

    class Meta:
        model = ProjectBudget
        fields = [
            'id', 'company', 'client_uuid', 'version', 'project', 'project_name', 'project_code',
            'name', 'status', 'lines',
            'original_budget', 'approved_revisions', 'revised_budget', 'open_commitments',
            'actual_expenditure', 'available_balance', 'created_by', 'submitted_at',
            'approved_by', 'approved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'project_name', 'project_code', 'status', 'original_budget',
            'approved_revisions', 'revised_budget', 'open_commitments', 'actual_expenditure',
            'available_balance', 'created_by', 'submitted_at', 'approved_by', 'approved_at',
            'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['project'].queryset = self.company_queryset(Project, finance_budget__isnull=True)
        company_id = getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None)
        self.fields['lines'].child.fields['category'].queryset = BudgetCategory.objects.filter(
            company_id=company_id, is_active=True,
        )

    def _summary(self, obj):
        return budget_services.project_budget_summary(obj)

    def get_original_budget(self, obj) -> Decimal:
        return self._summary(obj)['original_budget']

    def get_approved_revisions(self, obj) -> Decimal:
        return self._summary(obj)['approved_revisions']

    def get_revised_budget(self, obj) -> Decimal:
        return self._summary(obj)['revised_budget']

    def get_open_commitments(self, obj) -> Decimal:
        return self._summary(obj)['open_commitments']

    def get_actual_expenditure(self, obj) -> Decimal:
        return self._summary(obj)['actual_expenditure']

    def get_available_balance(self, obj) -> Decimal:
        return self._summary(obj)['available_balance']

    def validate(self, attrs):
        if any(field in getattr(self, 'initial_data', {}) for field in (
            'original_budget', 'approved_revisions', 'revised_budget',
            'open_commitments', 'actual_expenditure', 'available_balance',
        )):
            raise serializers.ValidationError({'non_field_errors': ['Calculated budget totals are read-only.']})
        return super().validate(attrs)

    def create(self, validated_data):
        lines = validated_data.pop('lines')
        return budget_services.create_project_budget(
            user=self.context['request'].user, lines=lines, **validated_data,
        )


class BudgetRevisionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetRevision
        fields = [
            'id', 'company', 'budget', 'budget_line', 'amount', 'comments',
            'status', 'approved_by', 'approved_at',
        ]
        read_only_fields = fields


class BudgetTransferSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetTransfer
        fields = [
            'id', 'company', 'budget', 'from_line', 'to_line', 'amount',
            'comments', 'authorized_by', 'created_at',
        ]
        read_only_fields = fields


class BudgetTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BudgetTransaction
        fields = [
            'id', 'company', 'budget', 'budget_line', 'transaction_type', 'amount',
            'purchase_order', 'supplier_invoice', 'revision', 'transfer', 'description',
            'created_by', 'created_at',
        ]
        read_only_fields = fields


class FinancialApprovalSerializer(serializers.ModelSerializer):
    purchase_request_number = serializers.CharField(source='purchase_request.number', read_only=True)
    project_name = serializers.CharField(source='purchase_request.project.name', read_only=True)

    class Meta:
        model = FinancialApproval
        fields = [
            'id', 'company', 'purchase_request', 'purchase_request_number', 'project_name',
            'project_budget', 'budget_line', 'requested_amount', 'status', 'review_reason',
            'created_by', 'submitted_at', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = fields


class CommentsSerializer(serializers.Serializer):
    comments = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)


class RequiredCommentsSerializer(serializers.Serializer):
    comments = serializers.CharField(allow_blank=False, trim_whitespace=True)


class FinanceSubmissionSerializer(CommentsSerializer):
    budget_line = serializers.PrimaryKeyRelatedField(
        queryset=BudgetLine.objects.none(), required=False, allow_null=True,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company_id = getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None)
        self.fields['budget_line'].queryset = BudgetLine.objects.filter(company_id=company_id)


class FinanceDecisionSerializer(CommentsSerializer):
    override = serializers.BooleanField(default=False)


class BudgetRevisionRequestSerializer(serializers.Serializer):
    budget_line = serializers.PrimaryKeyRelatedField(queryset=BudgetLine.objects.none())
    amount = serializers.DecimalField(max_digits=16, decimal_places=2)
    comments = serializers.CharField(allow_blank=False, trim_whitespace=True)
    override = serializers.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company_id = getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None)
        self.fields['budget_line'].queryset = BudgetLine.objects.filter(company_id=company_id)


class BudgetTransferRequestSerializer(serializers.Serializer):
    from_line = serializers.PrimaryKeyRelatedField(queryset=BudgetLine.objects.none())
    to_line = serializers.PrimaryKeyRelatedField(queryset=BudgetLine.objects.none())
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'))
    comments = serializers.CharField(allow_blank=False, trim_whitespace=True)
    override = serializers.BooleanField(default=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company_id = getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None)
        queryset = BudgetLine.objects.filter(company_id=company_id)
        self.fields['from_line'].queryset = queryset
        self.fields['to_line'].queryset = queryset


class BudgetApprovalSerializer(CompanyScopedSerializer):
    purchase_request_number = serializers.CharField(source='purchase_request.number', read_only=True)
    project_name = serializers.CharField(source='purchase_request.project.name', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.username', read_only=True)

    class Meta:
        model = BudgetApproval
        fields = [
            'id', 'company', 'purchase_request', 'purchase_request_number', 'project_name',
            'requested_amount', 'status', 'review_reason', 'created_by', 'created_by_name',
            'submitted_at', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'requested_amount', 'status', 'review_reason', 'created_by',
            'submitted_at', 'reviewed_by', 'reviewed_at', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['purchase_request'].queryset = self.company_queryset(
            PurchaseRequest,
            status=PurchaseRequest.STATUS_APPROVED,
            budget_approval__isnull=True,
        )

    def create(self, validated_data):
        return budget_approval_services.create_budget_approval(
            purchase_request=validated_data['purchase_request'],
            user=self.context['request'].user,
        )


class AccountSerializer(CompanyScopedSerializer):
    class Meta:
        model = Account
        fields = [
            'id', 'company', 'code', 'name', 'parent', 'description', 'account_type',
            'system_key', 'allow_manual_posting', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']
        extra_kwargs = {'system_key': {'required': False, 'allow_blank': True}}

    def create(self, validated_data):
        request = self.context['request']
        return services.create_account(company=request.user.company, user=request.user, **validated_data)


class SupplierInvoiceItemTaxSerializer(serializers.ModelSerializer):
    tax_code_name = serializers.CharField(source='tax_code.name', read_only=True)
    rate_percent = serializers.DecimalField(
        source='tax_code.rate_percent', max_digits=7, decimal_places=4, read_only=True,
    )

    class Meta:
        model = SupplierInvoiceItemTax
        fields = ['id', 'tax_code', 'tax_code_name', 'rate_percent', 'taxable_amount', 'tax_amount']
        read_only_fields = ['id', 'tax_code_name', 'rate_percent', 'taxable_amount', 'tax_amount']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['tax_code'].queryset = TaxCode.objects.filter(company_id=company_id, is_active=True)


class SupplierInvoiceItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_code = serializers.CharField(source='material.code', read_only=True)
    subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    taxes = SupplierInvoiceItemTaxSerializer(many=True, required=False)

    class Meta:
        model = SupplierInvoiceItem
        fields = [
            'id', 'purchase_order_item', 'material', 'material_name', 'material_code',
            'description', 'quantity', 'unit_price', 'tax_amount', 'subtotal', 'total', 'taxes',
        ]
        read_only_fields = [
            'id', 'material', 'material_name', 'material_code', 'tax_amount', 'subtotal', 'total',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['purchase_order_item'].queryset = PurchaseOrderItem.objects.filter(
            purchase_order__company_id=company_id,
        )


class SupplierInvoiceSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    items = SupplierInvoiceItemSerializer(many=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    purchase_order_number = serializers.CharField(source='purchase_order.number', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    work_order_number = serializers.CharField(source='work_order.number', read_only=True)
    work_order_site_name = serializers.CharField(source='work_order_site.project_site.name', read_only=True)
    cost_centre_name = serializers.CharField(source='cost_centre.name', read_only=True)
    amount_paid = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    credit_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    paid_amount = serializers.DecimalField(source='amount_paid', max_digits=16, decimal_places=2, read_only=True)
    outstanding_amount = serializers.DecimalField(source='balance', max_digits=16, decimal_places=2, read_only=True)
    is_reversed = serializers.SerializerMethodField()

    class Meta:
        model = SupplierInvoice
        fields = [
            'id', 'company', 'client_uuid', 'version', 'supplier', 'supplier_name',
            'purchase_order', 'purchase_order_number',
            'project', 'project_name', 'work_order', 'work_order_number', 'work_order_site', 'work_order_site_name',
            'cost_centre', 'cost_centre_name', 'internal_number',
            'invoice_number', 'invoice_date', 'due_date', 'currency', 'exchange_rate',
            'subtotal', 'discount_amount', 'freight_amount', 'other_charges_amount',
            'tax_amount', 'withholding_amount', 'total_amount',
            'amount_paid', 'credit_amount', 'balance', 'status', 'notes', 'rejection_reason',
            'idempotency_key', 'items', 'paid_amount', 'outstanding_amount', 'is_reversed', 'created_by', 'submitted_at',
            'approved_by', 'approved_at', 'posted_by', 'posted_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'project', 'internal_number', 'subtotal', 'tax_amount', 'total_amount',
            'amount_paid', 'credit_amount', 'balance',
            'status', 'rejection_reason', 'created_by', 'submitted_at', 'approved_by', 'approved_at',
            'posted_by', 'posted_at', 'created_at', 'updated_at',
        ]
        extra_kwargs = {'idempotency_key': {'write_only': True, 'required': False, 'allow_blank': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = self.company_queryset(Supplier, is_active=True)
        self.fields['purchase_order'].queryset = self.company_queryset(PurchaseOrder).filter(
            supplier__isnull=False,
        )
        self.fields['cost_centre'].queryset = self.company_queryset(CostCentre, is_active=True)
        from apps.workorders.models import WorkOrder
        self.fields['work_order'].queryset = WorkOrder.objects.filter(company_id=getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None))
        from apps.workorders.models import WorkOrderSite
        self.fields['work_order_site'].queryset = WorkOrderSite.objects.filter(work_order__company_id=getattr(getattr(self.context.get('request'), 'user', None), 'company_id', None))
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['items'].child.fields['purchase_order_item'].queryset = PurchaseOrderItem.objects.filter(
            purchase_order__company_id=company_id,
        )
        self.fields['items'].child.fields['taxes'].child.fields['tax_code'].queryset = TaxCode.objects.filter(
            company_id=company_id, is_active=True,
        )

    def get_is_reversed(self, obj) -> bool:
        return hasattr(obj, 'reversal')

    def validate(self, attrs):
        if 'status' in getattr(self, 'initial_data', {}):
            raise serializers.ValidationError({
                'status': 'Financial workflow status can only change through a dedicated action.',
            })
        return super().validate(attrs)

    def create(self, validated_data):
        items = validated_data.pop('items')
        request = self.context['request']
        return services.create_supplier_invoice(
            company=request.user.company,
            user=request.user,
            items=items,
            **validated_data,
        )

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        return services.update_draft_invoice(
            invoice=instance,
            user=self.context['request'].user,
            values=validated_data,
            items=items,
        )


class InvoiceAttachmentSerializer(CompanyScopedSerializer):
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = InvoiceAttachment
        fields = [
            'id', 'invoice', 'file', 'original_name', 'content_type', 'size',
            'uploaded_by', 'created_at', 'download_url',
        ]
        read_only_fields = [
            'id', 'original_name', 'content_type', 'size', 'uploaded_by', 'created_at', 'download_url',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['invoice'].queryset = self.company_queryset(SupplierInvoice)

    def get_download_url(self, obj) -> str:
        request = self.context.get('request')
        path = f'/api/v1/finance/invoice-attachments/{obj.pk}/download/'
        return request.build_absolute_uri(path) if request else path

    def validate_file(self, value):
        return validate_image_upload(value)

    def create(self, validated_data):
        return services.create_invoice_attachment(
            invoice=validated_data['invoice'], user=self.context['request'].user,
            uploaded_file=validated_data['file'],
        )


class InvoiceApprovalSerializer(serializers.ModelSerializer):
    acted_by_name = serializers.CharField(source='acted_by.get_full_name', read_only=True)

    class Meta:
        model = InvoiceApproval
        fields = ['id', 'invoice', 'action', 'comments', 'acted_by', 'acted_by_name', 'acted_at']
        read_only_fields = fields


class SupplierCreditNoteItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    total = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = SupplierCreditNoteItem
        fields = [
            'id', 'invoice_item', 'material', 'tax_code', 'description', 'quantity',
            'unit_price', 'tax_amount', 'subtotal', 'total',
        ]
        read_only_fields = fields


class SupplierCreditNoteSerializer(serializers.ModelSerializer):
    items = SupplierCreditNoteItemSerializer(many=True, read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = SupplierCreditNote
        fields = [
            'id', 'company', 'supplier', 'supplier_name', 'invoice', 'credit_note_number',
            'credit_note_date', 'currency', 'exchange_rate', 'subtotal', 'tax_amount',
            'total_amount', 'reason', 'status', 'created_by', 'posted_by', 'posted_at',
            'created_at', 'items',
        ]
        read_only_fields = fields


class ThreeWayMatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ThreeWayMatch
        fields = [
            'id', 'company', 'invoice', 'purchase_order', 'status', 'tolerance', 'po_total',
            'invoice_total', 'received_total', 'quantity_variance', 'amount_variance',
            'exceptions', 'matched_by', 'matched_at',
        ]
        read_only_fields = fields


class InvoiceMatchItemResultSerializer(serializers.ModelSerializer):
    material = serializers.IntegerField(source='invoice_item.material_id', read_only=True)
    material_code = serializers.CharField(source='invoice_item.material.code', read_only=True)

    class Meta:
        model = InvoiceMatchItemResult
        fields = [
            'id', 'invoice_item', 'purchase_order_item', 'material', 'material_code',
            'ordered_quantity', 'accepted_quantity', 'rejected_quantity', 'damaged_quantity',
            'previously_invoiced_quantity', 'current_invoice_quantity',
            'remaining_invoiceable_quantity', 'po_price', 'invoice_price',
            'quantity_variance', 'price_variance', 'price_variance_percent',
            'status', 'explanation',
        ]
        read_only_fields = fields


class InvoiceMatchRunSerializer(serializers.ModelSerializer):
    item_results = InvoiceMatchItemResultSerializer(many=True, read_only=True)
    exception_is_approved = serializers.BooleanField(read_only=True)

    class Meta:
        model = InvoiceMatchRun
        fields = [
            'id', 'invoice', 'purchase_order', 'status', 'explanation', 'subtotal',
            'freight_amount', 'other_charges_amount', 'tax_amount', 'credit_note_amount',
            'quantity_tolerance', 'price_tolerance', 'exception_reason',
            'exception_is_approved', 'exception_approved_by', 'exception_approved_at',
            'exception_rejected_by', 'exception_rejected_at', 'run_by', 'run_at',
            'item_results',
        ]
        read_only_fields = fields


class JournalLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = JournalLine
        fields = [
            'id', 'account', 'account_code', 'account_name', 'project', 'project_name',
            'supplier', 'supplier_name', 'description', 'debit', 'credit',
        ]
        read_only_fields = fields


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalLineSerializer(many=True, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'company', 'number', 'date', 'description', 'source_type', 'source_object_id',
            'source_reference', 'fiscal_period', 'status', 'reversal_of', 'created_by',
            'posted_by', 'posted_at', 'lines',
        ]
        read_only_fields = fields


class PaymentAllocationSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source='invoice.invoice_number', read_only=True)
    invoice_balance = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAllocation
        fields = ['id', 'invoice', 'invoice_number', 'amount', 'status', 'created_by', 'created_at', 'invoice_balance']
        read_only_fields = fields

    def get_invoice_balance(self, obj) -> Decimal:
        return payment_services.invoice_balance(obj.invoice)


class PaymentSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    invoice_number = serializers.CharField(source='invoice.internal_number', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    source_account_name = serializers.CharField(source='source_account.name', read_only=True)
    allocated_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    unallocated_amount = serializers.DecimalField(max_digits=16, decimal_places=2, read_only=True)
    allocations = PaymentAllocationSerializer(many=True, read_only=True)
    is_reversed = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = [
            'id', 'company', 'client_uuid', 'version', 'supplier', 'supplier_name',
            'invoice', 'invoice_number',
            'source_account', 'source_account_name', 'currency', 'currency_code', 'exchange_rate',
            'number', 'amount', 'allocated_amount', 'unallocated_amount', 'payment_date',
            'method', 'reference', 'voucher_reference', 'notes', 'status', 'rejection_reason',
            'idempotency_key', 'created_by', 'submitted_at', 'approved_by', 'approved_at',
            'posted_by', 'posted_at', 'journal_entry', 'allocations', 'is_reversed',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'invoice', 'number', 'allocated_amount', 'unallocated_amount',
            'status', 'rejection_reason', 'created_by', 'submitted_at', 'approved_by',
            'approved_at', 'posted_by', 'posted_at', 'journal_entry', 'allocations', 'is_reversed',
        ]
        extra_kwargs = {'idempotency_key': {'write_only': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['supplier'].queryset = self.company_queryset(Supplier, is_active=True)
        self.fields['source_account'].queryset = self.company_queryset(Account, is_active=True)
        self.fields['currency'].queryset = self.company_queryset(Currency, is_active=True)

    def validate(self, attrs):
        if 'status' in getattr(self, 'initial_data', {}):
            raise serializers.ValidationError({'status': 'Use a dedicated payment workflow action.'})
        return super().validate(attrs)

    def create(self, validated_data):
        return payment_services.create_payment(user=self.context['request'].user, **validated_data)

    def update(self, instance, validated_data):
        return payment_services.update_draft_payment(
            payment=instance, user=self.context['request'].user, values=validated_data,
        )

    def get_is_reversed(self, obj) -> bool:
        return hasattr(obj, 'reversal')


class PaymentApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentApproval
        fields = ['id', 'payment', 'action', 'comments', 'acted_by', 'acted_at']
        read_only_fields = fields


class PaymentBatchItemSerializer(serializers.ModelSerializer):
    payment_number = serializers.CharField(source='payment.number', read_only=True)
    supplier_name = serializers.CharField(source='payment.supplier.name', read_only=True)
    amount = serializers.DecimalField(source='payment.amount', max_digits=16, decimal_places=2, read_only=True)

    class Meta:
        model = PaymentBatchItem
        fields = ['id', 'payment', 'payment_number', 'supplier_name', 'amount', 'added_at']
        read_only_fields = fields


class PaymentBatchSerializer(CompanyScopedSerializer):
    source_account_name = serializers.CharField(source='source_account.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    items = PaymentBatchItemSerializer(many=True, read_only=True)
    payment_ids = serializers.PrimaryKeyRelatedField(
        queryset=Payment.objects.all(), many=True, write_only=True, required=True,
    )

    class Meta:
        model = PaymentBatch
        fields = [
            'id', 'company', 'number', 'source_account', 'source_account_name', 'currency', 'currency_code',
            'payment_date', 'status', 'notes', 'total_amount', 'items', 'payment_ids', 'created_by',
            'submitted_at', 'approved_by', 'approved_at', 'released_by', 'released_at',
            'cancellation_reason', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'number', 'source_account_name', 'currency_code', 'status', 'total_amount',
            'items', 'created_by', 'submitted_at', 'approved_by', 'approved_at', 'released_by',
            'released_at', 'cancellation_reason', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['source_account'].queryset = self.company_queryset(Account, account_type=Account.TYPE_ASSET, is_active=True)
        self.fields['currency'].queryset = self.company_queryset(Currency, is_active=True)
        self.fields['payment_ids'].child_relation.queryset = self.company_queryset(Payment, status=Payment.STATUS_APPROVED)

    def create(self, validated_data):
        from . import payment_batch_services
        payment_ids = [payment.pk for payment in validated_data.pop('payment_ids')]
        return payment_batch_services.create_batch(user=self.context['request'].user, payment_ids=payment_ids, **validated_data)


class PaymentBatchCancelSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, allow_blank=False)


class PaymentAttachmentSerializer(CompanyScopedSerializer):
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAttachment
        fields = [
            'id', 'payment', 'file', 'original_name', 'content_type', 'size',
            'uploaded_by', 'created_at', 'download_url',
        ]
        read_only_fields = ['id', 'original_name', 'content_type', 'size', 'uploaded_by', 'created_at', 'download_url']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['payment'].queryset = self.company_queryset(Payment)

    def get_download_url(self, obj) -> str:
        request = self.context.get('request')
        path = f'/api/v1/finance/payment-attachments/{obj.pk}/download/'
        return request.build_absolute_uri(path) if request else path

    def validate_file(self, value):
        return validate_image_upload(value)

    def create(self, validated_data):
        return payment_services.create_payment_attachment(
            payment=validated_data['payment'], user=self.context['request'].user,
            uploaded_file=validated_data['file'],
        )


class SupplierAdvanceSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)

    class Meta:
        model = SupplierAdvance
        fields = [
            'id', 'supplier', 'supplier_name', 'payment', 'amount', 'status',
            'reason', 'authorized_by', 'authorized_at',
        ]
        read_only_fields = fields


class ProjectCostSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    invoice_number = serializers.CharField(source='supplier_invoice.internal_number', read_only=True)
    payment_number = serializers.CharField(source='payment.number', read_only=True)

    class Meta:
        model = ProjectCost
        fields = [
            'id', 'company', 'project', 'project_name', 'supplier_invoice', 'invoice_number',
            'payment', 'payment_number', 'journal_entry', 'amount', 'date', 'description',
            'is_reversal', 'reversal_of', 'created_at',
        ]
        read_only_fields = fields


class InvoiceReversalSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceReversal
        fields = ['id', 'company', 'invoice', 'journal_entry', 'reason', 'reversed_by', 'reversed_at']
        read_only_fields = fields


class PaymentReversalSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentReversal
        fields = ['id', 'company', 'payment', 'journal_entry', 'project_cost', 'reason', 'reversed_by', 'reversed_at']
        read_only_fields = fields


class ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(trim_whitespace=True)


class MatchRequestSerializer(serializers.Serializer):
    tolerance = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.00'), default=Decimal('0.00'))
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class VerifyRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class RunMatchRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class PostRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100, required=False, allow_blank=True)


class CreditNoteItemRequestSerializer(serializers.Serializer):
    invoice_item = serializers.PrimaryKeyRelatedField(queryset=SupplierInvoiceItem.objects.none())
    quantity = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal('0.01'))
    unit_price = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.00'), required=False)
    tax_code = serializers.PrimaryKeyRelatedField(queryset=TaxCode.objects.none(), required=False, allow_null=True)
    description = serializers.CharField(max_length=255, required=False, allow_blank=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['invoice_item'].queryset = SupplierInvoiceItem.objects.filter(company_id=company_id)
        self.fields['tax_code'].queryset = TaxCode.objects.filter(company_id=company_id, is_active=True)


class CreditNoteRequestSerializer(serializers.Serializer):
    credit_note_number = serializers.CharField(max_length=100, trim_whitespace=True)
    credit_note_date = serializers.DateField()
    reason = serializers.CharField(trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)
    items = CreditNoteItemRequestSerializer(many=True, allow_empty=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        child = self.fields['items'].child
        child.fields['invoice_item'].queryset = SupplierInvoiceItem.objects.filter(company_id=company_id)
        child.fields['tax_code'].queryset = TaxCode.objects.filter(company_id=company_id, is_active=True)


class PaymentRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'))
    payment_date = serializers.DateField()
    method = serializers.ChoiceField(choices=Payment.METHOD_CHOICES)
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)
    notes = serializers.CharField(required=False, allow_blank=True)
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)


class PaymentAllocationRequestSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=SupplierInvoice.objects.none())
    amount = serializers.DecimalField(max_digits=16, decimal_places=2, min_value=Decimal('0.01'))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['invoice'].queryset = SupplierInvoice.objects.filter(company_id=company_id)


class PaymentUnallocationRequestSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=SupplierInvoice.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['invoice'].queryset = SupplierInvoice.objects.filter(company_id=company_id)


class PaymentApproveRequestSerializer(serializers.Serializer):
    authorize_advance = serializers.BooleanField(default=False)
    advance_reason = serializers.CharField(required=False, allow_blank=True)


class PaymentPostRequestSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)


class ReversalRequestSerializer(ReasonSerializer):
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)
    reversal_date = serializers.DateField(required=False)


class LandedCostItemSerializer(serializers.ModelSerializer):
    tax_code_name = serializers.CharField(source='tax_code.name', read_only=True)

    class Meta:
        model = LandedCostItem
        fields = ['id', 'cost_type', 'description', 'amount', 'tax_code', 'tax_code_name']
        read_only_fields = ['id', 'tax_code_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['tax_code'].queryset = TaxCode.objects.filter(company_id=company_id, is_active=True)


class LandedCostAllocationSerializer(serializers.ModelSerializer):
    grn_number = serializers.CharField(source='goods_received_note_item.goods_received_note.number', read_only=True)
    material = serializers.IntegerField(source='receipt_movement.material_id', read_only=True)
    material_code = serializers.CharField(source='receipt_movement.material.code', read_only=True)
    material_name = serializers.CharField(source='receipt_movement.material.name', read_only=True)
    warehouse = serializers.IntegerField(source='receipt_movement.warehouse_id', read_only=True)
    warehouse_name = serializers.CharField(source='receipt_movement.warehouse.name', read_only=True)

    class Meta:
        model = LandedCostAllocation
        fields = [
            'id', 'goods_received_note_item', 'grn_number', 'receipt_movement',
            'material', 'material_code', 'material_name', 'warehouse', 'warehouse_name',
            'basis_quantity', 'basis_weight', 'basis_value', 'allocated_amount',
            'status', 'valuation_movement', 'reverses',
        ]
        read_only_fields = fields


class LandedCostApprovalSerializer(serializers.ModelSerializer):
    acted_by_username = serializers.CharField(source='acted_by.username', read_only=True)

    class Meta:
        model = LandedCostApproval
        fields = [
            'id', 'action', 'comments', 'acted_by', 'acted_by_username',
            'idempotency_key', 'acted_at',
        ]
        read_only_fields = fields


class LandedCostDocumentSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    items = LandedCostItemSerializer(many=True)
    goods_received_notes = serializers.PrimaryKeyRelatedField(
        many=True, queryset=GoodsReceivedNote.objects.none(), allow_empty=False,
    )
    allocations = LandedCostAllocationSerializer(many=True, read_only=True)
    approvals = LandedCostApprovalSerializer(many=True, read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    reversal_document = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = LandedCostDocument
        fields = [
            'id', 'company', 'client_uuid', 'version', 'number', 'description', 'allocation_method',
            'currency', 'currency_code', 'exchange_rate', 'total_amount',
            'base_total_amount', 'status', 'goods_received_notes', 'items',
            'allocations', 'approvals', 'reversal_of', 'reversal_document',
            'created_by', 'submitted_at', 'approved_by', 'approved_at',
            'posted_by', 'posted_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'currency_code', 'total_amount', 'base_total_amount',
            'status', 'allocations', 'approvals', 'reversal_of', 'reversal_document',
            'created_by', 'submitted_at', 'approved_by', 'approved_at',
            'posted_by', 'posted_at', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['currency'].queryset = Currency.objects.filter(company_id=company_id, is_active=True)
        self.fields['goods_received_notes'].child_relation.queryset = GoodsReceivedNote.objects.filter(
            company_id=company_id, status=GoodsReceivedNote.STATUS_ACCEPTED,
        )
        self.fields['items'].child.fields['tax_code'].queryset = TaxCode.objects.filter(
            company_id=company_id, is_active=True,
        )

    def create(self, validated_data):
        request = self.context['request']
        items = validated_data.pop('items')
        grns = validated_data.pop('goods_received_notes')
        return landed_cost_services.create_document(
            user=request.user, values=validated_data, items=items,
            goods_received_notes=grns,
        )

    def update(self, instance, validated_data):
        request = self.context['request']
        items = validated_data.pop('items', None)
        grns = validated_data.pop('goods_received_notes', None)
        return landed_cost_services.update_draft_document(
            document=instance, user=request.user, values=validated_data,
            items=items, goods_received_notes=grns,
        )


class LandedCostAllocationInputSerializer(serializers.Serializer):
    goods_received_note_item = serializers.IntegerField(min_value=1)
    weight_per_unit = serializers.DecimalField(
        max_digits=18, decimal_places=6, min_value=Decimal('0.000001'), required=False,
    )
    manual_amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal('0'), required=False,
    )


class LandedCostPreviewRequestSerializer(serializers.Serializer):
    inputs = LandedCostAllocationInputSerializer(many=True, required=False, default=list)


class ExpenseCategorySerializer(ReferenceConfigurationSerializer):
    expense_account_name = serializers.CharField(source='expense_account.name', read_only=True)
    budget_category_name = serializers.CharField(source='budget_category.name', read_only=True)

    class Meta:
        model = ExpenseCategory
        fields = [
            'id', 'company', 'code', 'name', 'category_type', 'expense_account',
            'expense_account_name', 'budget_category', 'budget_category_name',
            'is_overhead', 'is_approved', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'expense_account_name', 'budget_category_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['expense_account'].queryset = self.company_queryset(
            Account, account_type=Account.TYPE_EXPENSE, is_active=True,
        )
        self.fields['budget_category'].queryset = self.company_queryset(BudgetCategory, is_active=True)


class CashAccountSerializer(ReferenceConfigurationSerializer):
    account_name = serializers.CharField(source='account.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    current_balance = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = CashAccount
        fields = [
            'id', 'company', 'code', 'name', 'account', 'account_name', 'currency',
            'currency_code', 'opening_balance', 'current_balance', 'is_petty_cash',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'account_name', 'currency_code', 'current_balance', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = self.company_queryset(
            Account, account_type=Account.TYPE_ASSET, is_active=True,
        )
        self.fields['currency'].queryset = self.company_queryset(Currency, is_active=True)


class BankStatementLineSerializer(CompanyScopedSerializer):
    cash_account_name = serializers.CharField(source='cash_account.name', read_only=True)
    cash_account_ledger = serializers.IntegerField(source='cash_account.account_id', read_only=True)
    currency_code = serializers.CharField(source='cash_account.currency.code', read_only=True)
    payment_number = serializers.CharField(source='payment.number', read_only=True)
    payment_reference = serializers.CharField(source='payment.reference', read_only=True)
    imported_by_name = serializers.SerializerMethodField()
    matched_by_name = serializers.SerializerMethodField()

    class Meta:
        model = BankStatementLine
        fields = [
            'id', 'company', 'cash_account', 'cash_account_name', 'cash_account_ledger', 'currency_code',
            'statement_date', 'reference', 'description', 'amount', 'payment',
            'payment_number', 'payment_reference', 'status', 'match_notes',
            'imported_by', 'imported_by_name', 'matched_by', 'matched_by_name',
            'matched_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'payment', 'payment_number', 'payment_reference', 'status',
            'imported_by', 'imported_by_name', 'matched_by', 'matched_by_name',
            'matched_at', 'created_at', 'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['cash_account'].queryset = self.company_queryset(CashAccount, is_active=True)

    def create(self, validated_data):
        return BankStatementLine.objects.create(
            company=self.context['request'].user.company,
            imported_by=self.context['request'].user,
            **validated_data,
        )

    @staticmethod
    def _display_name(user):
        return (user.get_full_name() or user.username) if user else None

    def get_imported_by_name(self, obj):
        return self._display_name(obj.imported_by)

    def get_matched_by_name(self, obj):
        return self._display_name(obj.matched_by)


class ReconcileStatementLineSerializer(serializers.Serializer):
    payment = serializers.PrimaryKeyRelatedField(queryset=Payment.objects.all())
    match_notes = serializers.CharField(required=False, allow_blank=True, max_length=2000)

    def validate_payment(self, payment):
        request = self.context['request']
        if payment.company_id != request.user.company_id:
            raise serializers.ValidationError('Payment must belong to your company.')
        return payment


class StatementLineReasonSerializer(serializers.Serializer):
    match_notes = serializers.CharField(required=True, allow_blank=False, max_length=2000)


class ExpenseItemSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)

    class Meta:
        model = ExpenseItem
        fields = ['id', 'category', 'category_name', 'expense_date', 'description', 'amount']
        read_only_fields = ['id', 'category_name']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['category'].queryset = ExpenseCategory.objects.filter(
            company_id=company_id, is_active=True, is_approved=True,
        )


class ExpenseReceiptAttachmentSerializer(CompanyScopedSerializer):
    file = serializers.FileField(write_only=True)
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ExpenseReceiptAttachment
        fields = [
            'id', 'claim', 'expense_item', 'file', 'original_name', 'content_type',
            'size', 'uploaded_by', 'created_at', 'download_url',
        ]
        read_only_fields = [
            'id', 'original_name', 'content_type', 'size', 'uploaded_by',
            'created_at', 'download_url',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['claim'].queryset = self.company_queryset(ExpenseClaim)
        self.fields['expense_item'].queryset = self.company_queryset(ExpenseItem)

    def get_download_url(self, obj) -> str:
        request = self.context.get('request')
        path = f'/api/v1/finance/expense-receipts/{obj.pk}/download/'
        return request.build_absolute_uri(path) if request else path

    def validate_file(self, value):
        return validate_image_upload(value)

    def create(self, validated_data):
        return expense_services.create_expense_receipt(
            claim=validated_data['claim'],
            expense_item=validated_data.get('expense_item'),
            uploaded_file=validated_data['file'],
            user=self.context['request'].user,
        )


class ExpenseApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseApproval
        fields = [
            'id', 'expense_claim', 'staff_advance', 'petty_cash_transaction',
            'action', 'comments', 'acted_by', 'idempotency_key', 'acted_at',
        ]
        read_only_fields = fields


class ExpenseClaimSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    claimant_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    cost_centre_name = serializers.CharField(source='cost_centre.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    items = ExpenseItemSerializer(many=True, allow_empty=False)
    receipts = ExpenseReceiptAttachmentSerializer(many=True, read_only=True)
    approvals = ExpenseApprovalSerializer(many=True, read_only=True)

    class Meta:
        model = ExpenseClaim
        fields = [
            'id', 'company', 'client_uuid', 'version', 'number', 'claimant', 'claimant_name', 'project',
            'project_name', 'cost_centre', 'cost_centre_name', 'overhead_category',
            'purpose', 'claim_date', 'currency', 'currency_code', 'exchange_rate',
            'total_amount', 'base_total_amount', 'amount_paid', 'status',
            'rejection_reason', 'cash_account', 'payment_reference', 'idempotency_key',
            'journal_entry', 'created_by', 'submitted_at', 'reviewed_by', 'reviewed_at',
            'approved_by', 'approved_at', 'paid_by', 'paid_at', 'created_at',
            'updated_at', 'items', 'receipts', 'approvals',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'number', 'claimant_name', 'project_name', 'cost_centre_name',
            'currency_code', 'total_amount', 'base_total_amount', 'amount_paid', 'status',
            'rejection_reason', 'cash_account', 'payment_reference', 'journal_entry',
            'created_by', 'submitted_at', 'reviewed_by', 'reviewed_at', 'approved_by',
            'approved_at', 'paid_by', 'paid_at', 'created_at', 'updated_at',
            'receipts', 'approvals',
        ]
        extra_kwargs = {'idempotency_key': {'write_only': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['claimant'].queryset = self.company_queryset(User, is_active=True)
        self.fields['project'].queryset = self.company_queryset(Project)
        self.fields['cost_centre'].queryset = self.company_queryset(CostCentre, is_active=True)
        self.fields['overhead_category'].queryset = self.company_queryset(
            ExpenseCategory, is_active=True, is_approved=True, is_overhead=True,
        )
        self.fields['currency'].queryset = self.company_queryset(Currency, is_active=True)
        self.fields['items'].child.fields['category'].queryset = self.company_queryset(
            ExpenseCategory, is_active=True, is_approved=True,
        )

    def validate(self, attrs):
        if 'status' in getattr(self, 'initial_data', {}):
            raise serializers.ValidationError({'status': 'Use a dedicated expense workflow action.'})
        project = attrs.get('project', getattr(self.instance, 'project', None))
        cost_centre = attrs.get('cost_centre', getattr(self.instance, 'cost_centre', None))
        overhead = attrs.get('overhead_category', getattr(self.instance, 'overhead_category', None))
        if not (project or cost_centre or overhead):
            raise serializers.ValidationError({'non_field_errors': ['Project, cost centre, or approved overhead category is required.']})
        return attrs

    def create(self, validated_data):
        items = validated_data.pop('items')
        key = validated_data.pop('idempotency_key')
        return expense_services.create_expense_claim(
            user=self.context['request'].user, items=items, idempotency_key=key, **validated_data,
        )

    def update(self, instance, validated_data):
        items = validated_data.pop('items', None)
        validated_data.pop('idempotency_key', None)
        return expense_services.update_draft_expense_claim(
            claim=instance, user=self.context['request'].user, values=validated_data, items=items,
        )

    def get_claimant_name(self, obj) -> str:
        return obj.claimant.get_full_name() or obj.claimant.username


class AdvanceRetirementSerializer(serializers.ModelSerializer):
    expense_category_name = serializers.CharField(source='expense_category.name', read_only=True)

    class Meta:
        model = AdvanceRetirement
        fields = [
            'id', 'advance', 'expense_category', 'expense_category_name', 'amount_spent',
            'amount_refunded', 'total_retired', 'retirement_date', 'reason', 'is_reversal',
            'reversal_of', 'journal_entry', 'retired_by', 'created_at',
        ]
        read_only_fields = fields


class StaffAdvanceSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    staff_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    currency_code = serializers.CharField(source='currency.code', read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    outstanding_base_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    retired_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    retirements = AdvanceRetirementSerializer(many=True, read_only=True)
    approvals = ExpenseApprovalSerializer(many=True, read_only=True)

    class Meta:
        model = StaffAdvance
        fields = [
            'id', 'company', 'client_uuid', 'version', 'number', 'staff', 'staff_name',
            'project', 'project_name', 'cost_centre', 'overhead_category', 'purpose',
            'advance_date', 'due_date', 'currency',
            'currency_code', 'exchange_rate', 'amount', 'base_amount', 'retired_amount',
            'outstanding_amount', 'outstanding_base_amount', 'status', 'rejection_reason',
            'cash_account', 'payment_reference', 'idempotency_key', 'journal_entry',
            'created_by', 'submitted_at', 'approved_by', 'approved_at', 'paid_by',
            'paid_at', 'created_at', 'updated_at', 'retirements', 'approvals',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'number', 'staff_name', 'project_name', 'currency_code',
            'base_amount', 'retired_amount', 'outstanding_amount', 'outstanding_base_amount',
            'status', 'rejection_reason', 'cash_account', 'payment_reference', 'journal_entry',
            'created_by', 'submitted_at', 'approved_by', 'approved_at', 'paid_by',
            'paid_at', 'created_at', 'updated_at', 'retirements', 'approvals',
        ]
        extra_kwargs = {'idempotency_key': {'write_only': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['staff'].queryset = self.company_queryset(User, is_active=True)
        self.fields['project'].queryset = self.company_queryset(Project)
        self.fields['cost_centre'].queryset = self.company_queryset(CostCentre, is_active=True)
        self.fields['overhead_category'].queryset = self.company_queryset(
            ExpenseCategory, is_active=True, is_approved=True, is_overhead=True,
        )
        self.fields['currency'].queryset = self.company_queryset(Currency, is_active=True)

    def validate(self, attrs):
        if 'status' in getattr(self, 'initial_data', {}):
            raise serializers.ValidationError({'status': 'Use a dedicated staff-advance workflow action.'})
        project = attrs.get('project', getattr(self.instance, 'project', None))
        cost_centre = attrs.get('cost_centre', getattr(self.instance, 'cost_centre', None))
        overhead = attrs.get('overhead_category', getattr(self.instance, 'overhead_category', None))
        if not (project or cost_centre or overhead):
            raise serializers.ValidationError({'non_field_errors': ['Project, cost centre, or approved overhead category is required.']})
        return attrs

    def create(self, validated_data):
        key = validated_data.pop('idempotency_key')
        return expense_services.create_staff_advance(
            user=self.context['request'].user, idempotency_key=key, **validated_data,
        )

    def update(self, instance, validated_data):
        validated_data.pop('idempotency_key', None)
        return expense_services.update_draft_staff_advance(
            advance=instance, user=self.context['request'].user, values=validated_data,
        )

    def get_staff_name(self, obj) -> str:
        return obj.staff.get_full_name() or obj.staff.username


class PettyCashTransactionSerializer(serializers.ModelSerializer):
    cash_account_name = serializers.CharField(source='cash_account.name', read_only=True)
    currency_code = serializers.CharField(source='cash_account.currency.code', read_only=True)

    class Meta:
        model = PettyCashTransaction
        fields = [
            'id', 'cash_account', 'cash_account_name', 'currency_code', 'transaction_type',
            'amount', 'balance_effect', 'exchange_rate', 'transaction_date', 'reference',
            'reason', 'expense_claim', 'staff_advance', 'advance_retirement',
            'original_transaction', 'status', 'journal_entry', 'posted_by', 'posted_at',
        ]
        read_only_fields = fields


class ExpensePayRequestSerializer(serializers.Serializer):
    cash_account = serializers.PrimaryKeyRelatedField(queryset=CashAccount.objects.none())
    payment_reference = serializers.CharField(max_length=100, trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)
    payment_date = serializers.DateField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['cash_account'].queryset = CashAccount.objects.filter(company_id=company_id, is_active=True)


class StaffAdvanceRetirementRequestSerializer(serializers.Serializer):
    expense_category = serializers.PrimaryKeyRelatedField(queryset=ExpenseCategory.objects.none())
    amount_spent = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.00'))
    amount_refunded = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.00'))
    retirement_date = serializers.DateField(required=False)
    reason = serializers.CharField(trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['expense_category'].queryset = ExpenseCategory.objects.filter(
            company_id=company_id, is_active=True, is_approved=True,
        )


class CashReplenishmentRequestSerializer(serializers.Serializer):
    source_account = serializers.PrimaryKeyRelatedField(queryset=Account.objects.none())
    amount = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    exchange_rate = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0.000001'), default=Decimal('1'))
    transaction_date = serializers.DateField(required=False)
    reference = serializers.CharField(max_length=100, trim_whitespace=True)
    reason = serializers.CharField(trim_whitespace=True)
    idempotency_key = serializers.CharField(max_length=100, allow_blank=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['source_account'].queryset = Account.objects.filter(
            company_id=company_id, account_type=Account.TYPE_ASSET, is_active=True,
        )


class ChartOfAccountSerializer(ReferenceConfigurationSerializer):
    parent_code = serializers.CharField(source='parent.code', read_only=True)

    class Meta:
        model = ChartOfAccount
        fields = [
            'id', 'company', 'code', 'name', 'parent', 'parent_code', 'description',
            'account_type', 'system_key', 'allow_manual_posting', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'parent_code', 'created_at', 'updated_at']
        extra_kwargs = {'system_key': {'required': False, 'allow_blank': True}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parent'].queryset = self.company_queryset(Account)


class FiscalPeriodSerializer(serializers.ModelSerializer):
    class Meta:
        model = FiscalPeriod
        fields = [
            'id', 'company', 'name', 'start_date', 'end_date', 'status',
            'closed_by', 'closed_at', 'created_at',
        ]
        read_only_fields = ['id', 'company', 'status', 'closed_by', 'closed_at', 'created_at']

    def create(self, validated_data):
        return ledger_services._save(FiscalPeriod(
            company=self.context['request'].user.company, **validated_data,
        ))

    def update(self, instance, validated_data):
        if instance.status == FiscalPeriod.STATUS_CLOSED:
            raise serializers.ValidationError({'status': 'Reopen the period before editing it.'})
        for field, value in validated_data.items():
            setattr(instance, field, value)
        return ledger_services._save(instance)


class PostingRuleSerializer(ReferenceConfigurationSerializer):
    class Meta:
        model = PostingRule
        fields = [
            'id', 'company', 'event_type', 'name', 'debit_mapping_key',
            'credit_mapping_key', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class AccountMappingSerializer(ReferenceConfigurationSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = AccountMapping
        fields = [
            'id', 'company', 'mapping_key', 'account', 'account_code', 'account_name',
            'description', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'account_code', 'account_name', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['account'].queryset = self.company_queryset(Account, is_active=True)


class DraftJournalLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = JournalLine
        fields = ['id', 'account', 'project', 'supplier', 'description', 'debit', 'credit']
        read_only_fields = ['id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['account'].queryset = Account.objects.filter(
            company_id=company_id, is_active=True, allow_manual_posting=True,
        )
        self.fields['project'].queryset = Project.objects.filter(company_id=company_id)
        self.fields['supplier'].queryset = Supplier.objects.filter(company_id=company_id)

    def validate(self, attrs):
        debit = attrs.get('debit', ZERO)
        credit = attrs.get('credit', ZERO)
        if not ((debit > ZERO and credit == ZERO) or (credit > ZERO and debit == ZERO)):
            raise serializers.ValidationError('Enter a positive debit or credit, but not both.')
        return attrs


class DraftJournalSerializer(CompanyScopedSerializer):
    client_uuid = serializers.UUIDField(required=False, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    lines = DraftJournalLineSerializer(many=True, allow_empty=False)
    debit_total = serializers.SerializerMethodField()
    credit_total = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'company', 'client_uuid', 'version', 'number', 'date', 'description', 'source_type',
            'source_reference', 'fiscal_period', 'status', 'created_by', 'posted_by',
            'posted_at', 'reversal_of', 'debit_total', 'credit_total', 'lines',
        ]
        read_only_fields = [
            'id', 'company', 'version', 'number', 'source_type', 'fiscal_period', 'status',
            'created_by', 'posted_by', 'posted_at', 'reversal_of', 'debit_total', 'credit_total',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        child = self.fields['lines'].child
        child.context.update(self.context)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        child.fields['account'].queryset = Account.objects.filter(
            company_id=company_id, is_active=True, allow_manual_posting=True,
        )
        child.fields['project'].queryset = Project.objects.filter(company_id=company_id)
        child.fields['supplier'].queryset = Supplier.objects.filter(company_id=company_id)

    def create(self, validated_data):
        lines = validated_data.pop('lines')
        return ledger_services.create_draft_journal(
            user=self.context['request'].user,
            entry_date=validated_data.pop('date'),
            lines=lines,
            **validated_data,
        )

    def update(self, instance, validated_data):
        lines = validated_data.pop('lines', None)
        return ledger_services.update_draft_journal(
            journal=instance,
            user=self.context['request'].user,
            values=validated_data,
            lines=lines,
        )

    def get_debit_total(self, obj) -> Decimal:
        return sum((line.debit for line in obj.lines.all()), ZERO)

    def get_credit_total(self, obj) -> Decimal:
        return sum((line.credit for line in obj.lines.all()), ZERO)


class JournalReversalSerializer(serializers.ModelSerializer):
    original_number = serializers.CharField(source='original_journal.number', read_only=True)
    reversal_number = serializers.CharField(source='reversal_journal.number', read_only=True)

    class Meta:
        model = JournalReversal
        fields = [
            'id', 'company', 'original_journal', 'original_number', 'reversal_journal',
            'reversal_number', 'reason', 'idempotency_key', 'reversed_by', 'reversed_at',
        ]
        read_only_fields = fields


class JournalPostRequestSerializer(serializers.Serializer):
    pass
