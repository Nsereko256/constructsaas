from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Company, User


def invoice_attachment_path(instance, filename):
    extension = Path(filename).suffix.lower()[:10]
    return f'finance/invoices/{instance.company_id}/{uuid4().hex}{extension}'


def payment_attachment_path(instance, filename):
    extension = Path(filename).suffix.lower()[:10]
    return f'finance/payments/{instance.company_id}/{uuid4().hex}{extension}'


def expense_receipt_path(instance, filename):
    extension = Path(filename).suffix.lower()[:10]
    return f'finance/expenses/{instance.company_id}/{uuid4().hex}{extension}'


def default_financial_year_start():
    today = timezone.localdate()
    financial_year_start = today.replace(month=7, day=1)
    if financial_year_start > today:
        return financial_year_start.replace(year=today.year - 1)
    return financial_year_start


class CompanyScopedQuerySet(models.QuerySet):
    def for_company(self, company):
        if company is None:
            return self.none()
        return self.filter(company=company)


class CompanyScopedManager(models.Manager.from_queryset(CompanyScopedQuerySet)):
    pass


class OfflineDraftMixin(models.Model):
    client_uuid = models.UUIDField(null=True, blank=True)
    version = models.PositiveBigIntegerField(default=1, editable=False)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and not self._state.adding:
            self.version += 1
            update_fields = kwargs.get('update_fields')
            if update_fields is not None:
                kwargs['update_fields'] = set(update_fields) | {'version'}
        return super().save(*args, **kwargs)


class AppendOnlyAuditQuerySet(CompanyScopedQuerySet):
    def update(self, **kwargs):
        raise ValidationError('Finance audit events are append-only.')

    def delete(self):
        raise ValidationError('Finance audit events cannot be deleted.')


class AppendOnlySyncQuerySet(CompanyScopedQuerySet):
    def update(self, **kwargs):
        raise ValidationError('Finance synchronization receipts are immutable.')

    def delete(self):
        raise ValidationError('Finance synchronization receipts cannot be deleted.')


class Currency(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_currencies')
    code = models.CharField(max_length=3)
    name = models.CharField(max_length=100)
    symbol = models.CharField(max_length=10, blank=True)
    decimal_places = models.PositiveSmallIntegerField(default=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(fields=['company', 'code'], name='unique_company_currency_code'),
            models.CheckConstraint(condition=Q(decimal_places__lte=6), name='currency_decimal_places_max_six'),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class FinanceSettings(models.Model):
    NEGATIVE_STOCK_PREVENT = 'PREVENT'
    NEGATIVE_STOCK_WARN = 'WARN'
    NEGATIVE_STOCK_ALLOW = 'ALLOW'
    NEGATIVE_STOCK_CHOICES = [
        (NEGATIVE_STOCK_PREVENT, 'Prevent'),
        (NEGATIVE_STOCK_WARN, 'Warn'),
        (NEGATIVE_STOCK_ALLOW, 'Allow'),
    ]

    company = models.OneToOneField(Company, on_delete=models.PROTECT, related_name='finance_settings')
    base_currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='base_for_settings')
    financial_year_start = models.DateField(default=default_financial_year_start)
    quantity_matching_tolerance = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    price_matching_tolerance = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    finance_officer_approval_threshold = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    finance_manager_approval_threshold = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    maker_checker_enforced = models.BooleanField(default=True)
    negative_stock_policy = models.CharField(
        max_length=10,
        choices=NEGATIVE_STOCK_CHOICES,
        default=NEGATIVE_STOCK_PREVENT,
    )
    document_retention_years = models.PositiveSmallIntegerField(default=7)
    require_invoice_attachment = models.BooleanField(default=False)
    require_payment_attachment = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        verbose_name_plural = 'finance settings'
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_matching_tolerance__gte=0),
                name='finance_quantity_tolerance_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(price_matching_tolerance__gte=0),
                name='finance_price_tolerance_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(finance_officer_approval_threshold__gte=0),
                name='finance_officer_threshold_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(finance_manager_approval_threshold__gte=0),
                name='finance_manager_threshold_nonnegative',
            ),
            models.CheckConstraint(
                condition=Q(document_retention_years__gte=1),
                name='finance_document_retention_minimum_one_year',
            ),
        ]

    def clean(self):
        if self.base_currency_id and self.base_currency.company_id != self.company_id:
            raise ValidationError({'base_currency': 'Base currency must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Finance settings for {self.company}'


class ApprovalMatrixRule(models.Model):
    """Company-configurable route for operational approvals."""
    DOCUMENT_PR = 'PURCHASE_REQUEST'
    DOCUMENT_PO = 'PURCHASE_ORDER'
    DOCUMENT_INVOICE = 'SUPPLIER_INVOICE'
    DOCUMENT_PAYMENT = 'PAYMENT'
    DOCUMENT_BUDGET = 'BUDGET'
    DOCUMENT_JOURNAL = 'JOURNAL'
    DOCUMENT_CHOICES = [(DOCUMENT_PR, 'Purchase request'), (DOCUMENT_PO, 'Purchase order'), (DOCUMENT_INVOICE, 'Supplier invoice'), (DOCUMENT_PAYMENT, 'Payment'), (DOCUMENT_BUDGET, 'Budget'), (DOCUMENT_JOURNAL, 'Journal')]
    STAGE_TECHNICAL = 'TECHNICAL'
    STAGE_FINANCE = 'FINANCE'
    STAGE_FINAL = 'FINAL'
    STAGE_CHOICES = [(STAGE_TECHNICAL, 'Technical approval'), (STAGE_FINANCE, 'Finance review'), (STAGE_FINAL, 'Final approval')]
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='approval_matrix_rules')
    document_type = models.CharField(max_length=30, choices=DOCUMENT_CHOICES)
    stage = models.CharField(max_length=20, choices=STAGE_CHOICES)
    approver_role = models.CharField(max_length=30, choices=User.ROLE_CHOICES)
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='approval_matrix_rules')
    budget_category = models.ForeignKey('finance.BudgetCategory', on_delete=models.PROTECT, null=True, blank=True, related_name='approval_matrix_rules')
    minimum_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    maximum_amount = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    due_hours = models.PositiveIntegerField(default=24)
    escalation_hours = models.PositiveIntegerField(default=48)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['document_type', 'stage', 'minimum_amount']

    def clean(self):
        if self.maximum_amount is not None and self.maximum_amount < self.minimum_amount:
            raise ValidationError({'maximum_amount': 'Maximum amount cannot be below minimum amount.'})
        if self.project_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Project must belong to this company.'})


class TaxCode(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_tax_codes')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=100)
    rate_percent = models.DecimalField(max_digits=7, decimal_places=4)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(fields=['company', 'code'], name='unique_company_tax_code'),
            models.CheckConstraint(condition=Q(rate_percent__gte=0), name='tax_rate_nonnegative'),
            models.CheckConstraint(condition=Q(rate_percent__lte=100), name='tax_rate_max_hundred'),
        ]

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} ({self.rate_percent}%)'


class CostCentre(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_cost_centres')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='cost_centres',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['company', 'code'], name='unique_company_cost_centre')]

    def clean(self):
        if self.project_id and self.project.company_id != self.company_id:
            raise ValidationError({'project': 'Project must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} - {self.name}'


class BudgetCategory(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_budget_categories')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    cost_centre = models.ForeignKey(
        CostCentre,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='budget_categories',
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['code']
        constraints = [models.UniqueConstraint(fields=['company', 'code'], name='unique_company_budget_category')]

    def clean(self):
        if self.cost_centre_id and self.cost_centre.company_id != self.company_id:
            raise ValidationError({'cost_centre': 'Cost centre must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} - {self.name}'


class ProjectBudget(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='project_budgets')
    project = models.OneToOneField(
        'projects.Project',
        on_delete=models.PROTECT,
        related_name='finance_budget',
    )
    name = models.CharField(max_length=150)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_project_budgets',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_project_budgets',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['project__name']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'],
                condition=Q(client_uuid__isnull=False),
                name='unique_company_budget_client_uuid',
            ),
        ]

    def clean(self):
        for field in ('project', 'created_by', 'approved_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = ProjectBudget.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous == self.STATUS_APPROVED:
                raise ValidationError('Approved budgets are immutable; use revisions or transfers.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def _transaction_total(self, transaction_types):
        return self.transactions.filter(transaction_type__in=transaction_types).aggregate(
            total=models.Sum('amount'),
        )['total'] or Decimal('0.00')

    @property
    def original_budget(self):
        return self.lines.aggregate(total=models.Sum('original_amount'))['total'] or Decimal('0.00')

    @property
    def approved_revisions(self):
        return self.revisions.filter(status=BudgetRevision.STATUS_APPROVED).aggregate(
            total=models.Sum('amount'),
        )['total'] or Decimal('0.00')

    @property
    def revised_budget(self):
        return self.original_budget + self.approved_revisions

    @property
    def open_commitments(self):
        return self._transaction_total([
            BudgetTransaction.TYPE_COMMITMENT,
            BudgetTransaction.TYPE_COMMITMENT_RELEASE,
        ])

    @property
    def actual_expenditure(self):
        return self._transaction_total([
            BudgetTransaction.TYPE_ACTUAL,
            BudgetTransaction.TYPE_ACTUAL_REVERSAL,
        ])

    @property
    def available_balance(self):
        return self.revised_budget - self.open_commitments - self.actual_expenditure

    def __str__(self):
        return f'{self.project.code} - {self.name}'


class BudgetLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_lines')
    budget = models.ForeignKey(ProjectBudget, on_delete=models.PROTECT, related_name='lines')
    category = models.ForeignKey(BudgetCategory, on_delete=models.PROTECT, related_name='budget_lines')
    description = models.CharField(max_length=255, blank=True)
    original_amount = models.DecimalField(max_digits=16, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['category__code']
        constraints = [
            models.UniqueConstraint(fields=['budget', 'category'], name='unique_budget_category_line'),
            models.CheckConstraint(condition=Q(original_amount__gte=0), name='budget_line_amount_nonnegative'),
        ]

    def clean(self):
        for field in ('budget', 'category'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        if self.budget_id and self.budget.status != ProjectBudget.STATUS_DRAFT:
            raise ValidationError('Budget lines can only change while the budget is draft.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.budget.status != ProjectBudget.STATUS_DRAFT:
            raise ValidationError('Budget lines can only be deleted while the budget is draft.')
        return super().delete(*args, **kwargs)

    def __str__(self):
        return f'{self.budget} - {self.category.code}'


class BudgetRevision(models.Model):
    STATUS_APPROVED = 'APPROVED'

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_revisions')
    budget = models.ForeignKey(ProjectBudget, on_delete=models.PROTECT, related_name='revisions')
    budget_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name='revisions')
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    comments = models.TextField()
    status = models.CharField(max_length=20, default=STATUS_APPROVED, editable=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='approved_budget_revisions',
    )
    approved_at = models.DateTimeField(default=timezone.now)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-approved_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(amount__gt=0) | Q(amount__lt=0),
                name='budget_revision_amount_nonzero',
            )
        ]

    def clean(self):
        for field in ('budget', 'budget_line', 'approved_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.budget_line_id and self.budget_line.budget_id != self.budget_id:
            raise ValidationError({'budget_line': 'Budget line must belong to the budget.'})

    def save(self, *args, **kwargs):
        if self.pk and BudgetRevision.objects.filter(pk=self.pk).exists():
            raise ValidationError('Budget revisions are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Budget revisions cannot be deleted.')


class BudgetTransfer(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_transfers')
    budget = models.ForeignKey(ProjectBudget, on_delete=models.PROTECT, related_name='transfers')
    from_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name='outgoing_transfers')
    to_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name='incoming_transfers')
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    comments = models.TextField()
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='authorized_budget_transfers',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-created_at']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='budget_transfer_amount_positive')]

    def clean(self):
        if self.from_line_id == self.to_line_id:
            raise ValidationError({'to_line': 'Transfer destination must differ from source.'})
        for field in ('budget', 'from_line', 'to_line', 'authorized_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.from_line_id and self.from_line.budget_id != self.budget_id:
            raise ValidationError({'from_line': 'Source line must belong to the budget.'})
        if self.to_line_id and self.to_line.budget_id != self.budget_id:
            raise ValidationError({'to_line': 'Destination line must belong to the budget.'})

    def save(self, *args, **kwargs):
        if self.pk and BudgetTransfer.objects.filter(pk=self.pk).exists():
            raise ValidationError('Budget transfers are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Budget transfers cannot be deleted.')


class BudgetTransaction(models.Model):
    TYPE_REVISION = 'REVISION'
    TYPE_TRANSFER_IN = 'TRANSFER_IN'
    TYPE_TRANSFER_OUT = 'TRANSFER_OUT'
    TYPE_COMMITMENT = 'COMMITMENT'
    TYPE_COMMITMENT_RELEASE = 'COMMITMENT_RELEASE'
    TYPE_ACTUAL = 'ACTUAL'
    TYPE_ACTUAL_REVERSAL = 'ACTUAL_REVERSAL'
    TYPE_CHOICES = [
        (TYPE_REVISION, 'Revision'),
        (TYPE_TRANSFER_IN, 'Transfer In'),
        (TYPE_TRANSFER_OUT, 'Transfer Out'),
        (TYPE_COMMITMENT, 'Commitment'),
        (TYPE_COMMITMENT_RELEASE, 'Commitment Release'),
        (TYPE_ACTUAL, 'Actual Expenditure'),
        (TYPE_ACTUAL_REVERSAL, 'Actual Reversal'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_transactions')
    budget = models.ForeignKey(ProjectBudget, on_delete=models.PROTECT, related_name='transactions')
    budget_line = models.ForeignKey(BudgetLine, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.PROTECT, null=True, blank=True, related_name='budget_transactions',
    )
    supplier_invoice = models.ForeignKey(
        'finance.SupplierInvoice', on_delete=models.PROTECT, null=True, blank=True, related_name='budget_transactions',
    )
    revision = models.ForeignKey(
        BudgetRevision, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )
    transfer = models.ForeignKey(
        BudgetTransfer, on_delete=models.PROTECT, null=True, blank=True, related_name='transactions',
    )
    expense_claim = models.ForeignKey(
        'finance.ExpenseClaim', on_delete=models.PROTECT, null=True, blank=True, related_name='budget_transactions',
    )
    advance_retirement = models.ForeignKey(
        'finance.AdvanceRetirement', on_delete=models.PROTECT, null=True, blank=True,
        related_name='budget_transactions',
    )
    stock_movement = models.ForeignKey(
        'warehouse.StockMovement', on_delete=models.PROTECT, null=True, blank=True,
        related_name='budget_transactions',
    )
    description = models.CharField(max_length=500)
    idempotency_key = models.CharField(max_length=150, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_budget_transactions',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                condition=~Q(idempotency_key=''),
                name='unique_company_budget_transaction_key',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0) | Q(amount__lt=0),
                name='budget_transaction_amount_nonzero',
            ),
        ]

    def clean(self):
        for field in (
            'budget', 'budget_line', 'purchase_order', 'supplier_invoice', 'revision', 'transfer',
            'expense_claim', 'advance_retirement', 'stock_movement', 'created_by',
        ):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.budget_line_id and self.budget_line.budget_id != self.budget_id:
            raise ValidationError({'budget_line': 'Budget line must belong to the budget.'})

    def save(self, *args, **kwargs):
        if self.pk and BudgetTransaction.objects.filter(pk=self.pk).exists():
            raise ValidationError('Budget transactions are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Budget transactions cannot be deleted.')


class FinanceAuditEvent(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_audit_events')
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='finance_audit_events',
    )
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100, blank=True)
    message = models.CharField(max_length=500, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    correlation_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager.from_queryset(AppendOnlyAuditQuerySet)()

    class Meta:
        ordering = ['-created_at', '-id']
        indexes = [
            models.Index(fields=['company', 'created_at'], name='finance_audit_company_time'),
            models.Index(fields=['company', 'object_type', 'object_id'], name='finance_audit_object'),
        ]

    def clean(self):
        if self.actor_id and self.actor.company_id != self.company_id:
            raise ValidationError({'actor': 'Actor must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk and FinanceAuditEvent.objects.filter(pk=self.pk).exists():
            raise ValidationError('Finance audit events are append-only.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Finance audit events cannot be deleted.')


class FinanceSyncReceipt(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_sync_receipts')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='finance_sync_receipts',
    )
    client_uuid = models.UUIDField()
    record_type = models.CharField(max_length=50)
    idempotency_key = models.CharField(max_length=150)
    request_hash = models.CharField(max_length=64)
    response_data = models.JSONField(default=dict)
    response_status = models.PositiveSmallIntegerField(default=200)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = models.Manager.from_queryset(AppendOnlySyncQuerySet)()

    class Meta:
        ordering = ['-created_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_finance_sync_company_key',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and FinanceSyncReceipt.objects.filter(pk=self.pk).exists():
            raise ValidationError('Finance synchronization receipts are immutable.')
        if self.user_id and self.user.company_id != self.company_id:
            raise ValidationError({'user': 'User must belong to the receipt company.'})
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Finance synchronization receipts cannot be deleted.')


class FinanceDocumentSequence(models.Model):
    TYPE_INVOICE = 'INV'
    TYPE_PAYMENT = 'PAY'
    TYPE_JOURNAL = 'JE'
    TYPE_EXPENSE = 'EXP'
    TYPE_STAFF_ADVANCE = 'SADV'

    TYPE_CHOICES = [
        (TYPE_INVOICE, 'Supplier Invoice'),
        (TYPE_PAYMENT, 'Payment'),
        (TYPE_JOURNAL, 'Journal Entry'),
        (TYPE_EXPENSE, 'Expense Claim'),
        (TYPE_STAFF_ADVANCE, 'Staff Advance'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='finance_sequences')
    document_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    last_value = models.PositiveBigIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'document_type'],
                name='unique_company_finance_sequence',
            )
        ]


class BudgetApproval(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_RETURNED = 'RETURNED'
    STATUS_HOLD = 'HOLD'
    STATUS_OVERRIDDEN = 'OVERRIDDEN'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_RETURNED, 'Returned'),
        (STATUS_HOLD, 'On Hold'),
        (STATUS_OVERRIDDEN, 'Approved with Override'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='budget_approvals')
    purchase_request = models.OneToOneField(
        'procurement.PurchaseRequest',
        on_delete=models.PROTECT,
        related_name='budget_approval',
    )
    project_budget = models.ForeignKey(
        ProjectBudget,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='financial_approvals',
    )
    budget_line = models.ForeignKey(
        BudgetLine,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='financial_approvals',
    )
    requested_amount = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    review_reason = models.TextField(blank=True)
    return_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_budget_approvals',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reviewed_budget_approvals',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=Q(requested_amount__gte=0),
                name='budget_requested_amount_nonnegative',
            )
        ]

    def clean(self):
        if self.purchase_request_id and self.purchase_request.company_id != self.company_id:
            raise ValidationError({'purchase_request': 'Purchase request must belong to the same company.'})
        if self.created_by_id and self.created_by.company_id != self.company_id:
            raise ValidationError({'created_by': 'User must belong to the same company.'})
        if self.reviewed_by_id and self.reviewed_by.company_id != self.company_id:
            raise ValidationError({'reviewed_by': 'Reviewer must belong to the same company.'})
        if self.project_budget_id and self.project_budget.company_id != self.company_id:
            raise ValidationError({'project_budget': 'Budget must belong to the same company.'})
        if self.budget_line_id and self.budget_line.company_id != self.company_id:
            raise ValidationError({'budget_line': 'Budget line must belong to the same company.'})
        if self.budget_line_id and self.project_budget_id and self.budget_line.budget_id != self.project_budget_id:
            raise ValidationError({'budget_line': 'Budget line must belong to the selected budget.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = BudgetApproval.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_APPROVED, self.STATUS_REJECTED, self.STATUS_OVERRIDDEN}:
                raise ValidationError('Reviewed budget approvals are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)


class FinancialApproval(BudgetApproval):
    class Meta:
        proxy = True
        verbose_name = 'financial approval'
        verbose_name_plural = 'financial approvals'


class Account(models.Model):
    TYPE_ASSET = 'ASSET'
    TYPE_LIABILITY = 'LIABILITY'
    TYPE_EQUITY = 'EQUITY'
    TYPE_REVENUE = 'REVENUE'
    TYPE_EXPENSE = 'EXPENSE'
    TYPE_CHOICES = [
        (TYPE_ASSET, 'Asset'),
        (TYPE_LIABILITY, 'Liability'),
        (TYPE_EQUITY, 'Equity'),
        (TYPE_REVENUE, 'Revenue'),
        (TYPE_EXPENSE, 'Expense'),
    ]

    SYSTEM_CASH = 'CASH'
    SYSTEM_ACCOUNTS_PAYABLE = 'ACCOUNTS_PAYABLE'
    SYSTEM_INVENTORY = 'INVENTORY'
    SYSTEM_PROJECT_COST = 'PROJECT_COST'
    SYSTEM_SUPPLIER_ADVANCE = 'SUPPLIER_ADVANCE'
    SYSTEM_STAFF_ADVANCE = 'STAFF_ADVANCE'
    SYSTEM_GRN_CLEARING = 'GRN_CLEARING'
    SYSTEM_INVENTORY_ADJUSTMENT = 'INVENTORY_ADJUSTMENT'
    SYSTEM_INVENTORY_WRITE_OFF = 'INVENTORY_WRITE_OFF'
    SYSTEM_LANDED_COST_CLEARING = 'LANDED_COST_CLEARING'
    SYSTEM_REALIZED_FX = 'REALIZED_FX'
    SYSTEM_RECOVERABLE_VAT = 'RECOVERABLE_VAT'
    SYSTEM_WITHHOLDING_TAX_PAYABLE = 'WITHHOLDING_TAX_PAYABLE'
    SYSTEM_KEY_CHOICES = [
        (SYSTEM_CASH, 'Cash/Bank'),
        (SYSTEM_ACCOUNTS_PAYABLE, 'Accounts Payable'),
        (SYSTEM_INVENTORY, 'Inventory'),
        (SYSTEM_PROJECT_COST, 'Project Cost'),
        (SYSTEM_SUPPLIER_ADVANCE, 'Supplier Advance'),
        (SYSTEM_STAFF_ADVANCE, 'Staff Advance'),
        (SYSTEM_GRN_CLEARING, 'GRN Clearing'),
        (SYSTEM_INVENTORY_ADJUSTMENT, 'Inventory Adjustment'),
        (SYSTEM_INVENTORY_WRITE_OFF, 'Inventory Write-off'),
        (SYSTEM_LANDED_COST_CLEARING, 'Landed Cost Clearing'),
        (SYSTEM_REALIZED_FX, 'Realized Foreign Exchange Gain/Loss'),
        (SYSTEM_RECOVERABLE_VAT, 'Recoverable VAT'),
        (SYSTEM_WITHHOLDING_TAX_PAYABLE, 'Withholding Tax Payable'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_accounts')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    parent = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='children',
    )
    description = models.TextField(blank=True)
    account_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    system_key = models.CharField(max_length=40, choices=SYSTEM_KEY_CHOICES, blank=True)
    is_active = models.BooleanField(default=True)
    allow_manual_posting = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['code']
        constraints = [
            models.UniqueConstraint(fields=['company', 'code'], name='unique_company_account_code'),
            models.UniqueConstraint(
                fields=['company', 'system_key'],
                condition=~Q(system_key=''),
                name='unique_company_system_account',
            ),
        ]

    def clean(self):
        if self.parent_id and self.parent.company_id != self.company_id:
            raise ValidationError({'parent': 'Parent account must belong to the same company.'})
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({'parent': 'An account cannot be its own parent.'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} - {self.name}'


class ChartOfAccount(Account):
    class Meta:
        proxy = True
        verbose_name = 'chart of account'
        verbose_name_plural = 'chart of accounts'


class SupplierInvoice(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_MATCHED = 'MATCHED'
    STATUS_MATCH_EXCEPTION = 'MATCH_EXCEPTION'
    STATUS_VERIFIED = 'VERIFIED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_POSTED = 'POSTED'
    STATUS_PARTIALLY_PAID = 'PARTIALLY_PAID'
    STATUS_PAID = 'PAID'
    STATUS_REVERSED = 'REVERSED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_MATCHED, 'Matched'),
        (STATUS_MATCH_EXCEPTION, 'Match exception'),
        (STATUS_VERIFIED, 'Verified'),
        (STATUS_APPROVED, 'Approved'),
        (STATUS_POSTED, 'Posted'),
        (STATUS_PARTIALLY_PAID, 'Partially paid'),
        (STATUS_PAID, 'Paid'),
        (STATUS_REVERSED, 'Reversed'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_invoices')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='invoices')
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder',
        on_delete=models.PROTECT,
        related_name='supplier_invoices',
    )
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='supplier_invoices',
    )
    work_order = models.ForeignKey(
        'workorders.WorkOrder', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_invoices',
    )
    work_order_site = models.ForeignKey(
        'workorders.WorkOrderSite', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='supplier_invoices',
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.PROTECT, null=True, blank=True, related_name='supplier_invoices',
    )
    internal_number = models.CharField(max_length=50)
    invoice_number = models.CharField(max_length=100)
    invoice_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='UGX')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    freight_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    other_charges_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    withholding_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True)
    posting_idempotency_key = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_supplier_invoices',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='approved_supplier_invoices',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_supplier_invoices',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-invoice_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_invoice_client_uuid',
            ),
            models.UniqueConstraint(
                fields=['company', 'internal_number'],
                name='unique_company_internal_invoice_number',
            ),
            models.UniqueConstraint(
                fields=['company', 'supplier', 'invoice_number'],
                name='unique_company_supplier_invoice_number',
            ),
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                condition=~Q(idempotency_key=''),
                name='unique_company_invoice_idempotency',
            ),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name='invoice_subtotal_nonnegative'),
            models.CheckConstraint(condition=Q(discount_amount__gte=0), name='invoice_discount_nonnegative'),
            models.CheckConstraint(condition=Q(freight_amount__gte=0), name='invoice_freight_nonnegative'),
            models.CheckConstraint(condition=Q(other_charges_amount__gte=0), name='invoice_other_charges_nonnegative'),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name='invoice_tax_nonnegative'),
            models.CheckConstraint(condition=Q(withholding_amount__gte=0), name='invoice_withholding_nonnegative'),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name='invoice_total_nonnegative'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='invoice_exchange_rate_positive'),
            models.UniqueConstraint(
                fields=['company', 'posting_idempotency_key'], condition=~Q(posting_idempotency_key=''),
                name='unique_company_invoice_posting_key',
            ),
        ]

    def clean(self):
        related = ('supplier', 'purchase_order', 'project', 'cost_centre', 'created_by', 'approved_by', 'posted_by')
        for field in related:
            if not getattr(self, f'{field}_id', None):
                continue
            value = getattr(self, field)
            if value.company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.purchase_order_id and self.supplier_id:
            if self.purchase_order.supplier_id and self.purchase_order.supplier_id != self.supplier_id:
                raise ValidationError({'supplier': 'Supplier must match the purchase order supplier.'})
        if self.purchase_order_id and self.project_id and self.purchase_order.project_id:
            if self.purchase_order.project_id != self.project_id:
                raise ValidationError({'project': 'Project must match the purchase order project.'})
        if self.work_order_id:
            if self.work_order.company_id != self.company_id:
                raise ValidationError({'work_order': 'Work order must belong to the same company.'})
            if self.work_order.project_id and self.project_id != self.work_order.project_id:
                raise ValidationError({'work_order': 'Work order must match the invoice project.'})
        if self.work_order_site_id:
            if self.work_order_site.work_order_id != self.work_order_id or self.project_id != self.work_order_site.project_id:
                raise ValidationError({'work_order_site': 'Site package must match the invoice work order and project.'})
        if self.due_date and self.invoice_date and self.due_date < self.invoice_date:
            raise ValidationError({'due_date': 'Due date cannot be earlier than invoice date.'})
        if self.discount_amount > self.subtotal:
            raise ValidationError({'discount_amount': 'Discount cannot exceed subtotal.'})
        expected = (
            self.subtotal - self.discount_amount + self.freight_amount + self.other_charges_amount
            + self.tax_amount - self.withholding_amount
        )
        if expected < 0:
            raise ValidationError({'withholding_amount': 'Withholding cannot make the invoice total negative.'})
        if self.total_amount != expected:
            raise ValidationError({
                'total_amount': 'Total must equal subtotal minus discount plus freight, other charges and tax, minus withholding.',
            })

    @property
    def amount_paid(self):
        return self.payment_allocations.filter(
            status__in=[PaymentAllocation.STATUS_APPROVED, PaymentAllocation.STATUS_POSTED],
            payment__reversal__isnull=True,
        ).aggregate(total=models.Sum('amount'))['total'] or Decimal('0.00')

    @property
    def credit_amount(self):
        return self.credit_notes.filter(status=SupplierCreditNote.STATUS_POSTED).aggregate(
            total=models.Sum('total_amount'),
        )['total'] or Decimal('0.00')

    @property
    def balance(self):
        return max(self.total_amount - self.amount_paid - self.credit_amount, Decimal('0.00'))

    def save(self, *args, **kwargs):
        # Supplier invoice references are business identifiers, not free text.
        # Normalization makes the database uniqueness rule case- and
        # whitespace-insensitive for the same supplier.
        self.invoice_number = self.invoice_number.strip().upper()
        if self.pk:
            previous = SupplierInvoice.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_POSTED, self.STATUS_PARTIALLY_PAID, self.STATUS_PAID, self.STATUS_REVERSED}:
                raise ValidationError('Posted supplier invoices are immutable; use a reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError('Only draft supplier invoices can be deleted.')
        return super().delete(*args, **kwargs)


class SupplierInvoiceItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_invoice_items')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.CASCADE, related_name='items')
    purchase_order_item = models.ForeignKey(
        'procurement.PurchaseOrderItem',
        on_delete=models.PROTECT,
        related_name='supplier_invoice_items',
    )
    material = models.ForeignKey('materials.Material', on_delete=models.PROTECT, related_name='supplier_invoice_items')
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['invoice', 'purchase_order_item'],
                name='unique_po_item_per_supplier_invoice',
            ),
            models.CheckConstraint(condition=Q(quantity__gt=0), name='invoice_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='invoice_item_price_nonnegative'),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name='invoice_item_tax_nonnegative'),
        ]

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def total(self):
        return self.subtotal + self.tax_amount

    def clean(self):
        if self.invoice_id and self.invoice.company_id != self.company_id:
            raise ValidationError({'invoice': 'Invoice must belong to the same company.'})
        if self.purchase_order_item_id:
            if self.purchase_order_item.purchase_order.company_id != self.company_id:
                raise ValidationError({'purchase_order_item': 'PO item must belong to the same company.'})
            if self.invoice_id and self.purchase_order_item.purchase_order_id != self.invoice.purchase_order_id:
                raise ValidationError({'purchase_order_item': 'PO item must belong to the invoice purchase order.'})
            if self.purchase_order_item.material_id != self.material_id:
                raise ValidationError({'material': 'Material must match the purchase order item.'})
        if self.material_id and self.material.company_id != self.company_id:
            raise ValidationError({'material': 'Material must belong to the same company.'})
        if self.invoice_id and self.invoice.status != SupplierInvoice.STATUS_DRAFT:
            raise ValidationError('Only draft invoice items may be changed.')

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class SupplierInvoiceItemTax(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_invoice_item_taxes')
    invoice_item = models.ForeignKey(SupplierInvoiceItem, on_delete=models.CASCADE, related_name='taxes')
    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, related_name='supplier_invoice_item_taxes')
    taxable_amount = models.DecimalField(max_digits=16, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['invoice_item', 'tax_code'], name='unique_tax_per_invoice_item'),
            models.CheckConstraint(condition=Q(taxable_amount__gte=0), name='invoice_item_taxable_nonnegative'),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name='invoice_item_tax_value_nonnegative'),
        ]

    def clean(self):
        if self.invoice_item_id and self.invoice_item.company_id != self.company_id:
            raise ValidationError({'invoice_item': 'Invoice item must belong to the same company.'})
        if self.tax_code_id and self.tax_code.company_id != self.company_id:
            raise ValidationError({'tax_code': 'Tax code must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class InvoiceAttachment(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoice_attachments')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='attachments')
    file = models.FileField(upload_to=invoice_attachment_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='invoice_attachments')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        for field in ('invoice', 'uploaded_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.full_clean(exclude=['file'] if not self.file else None)
        return super().save(*args, **kwargs)


class InvoiceApproval(models.Model):
    ACTION_SUBMIT = 'SUBMIT'
    ACTION_WITHDRAW = 'WITHDRAW'
    ACTION_VERIFY = 'VERIFY'
    ACTION_APPROVE = 'APPROVE'
    ACTION_REJECT = 'REJECT'
    ACTION_POST = 'POST'
    ACTION_REVERSE = 'REVERSE'
    ACTION_CREDIT_NOTE = 'CREDIT_NOTE'
    ACTION_APPROVE_EXCEPTION = 'APPROVE_EXCEPTION'
    ACTION_REJECT_EXCEPTION = 'REJECT_EXCEPTION'
    ACTION_CHOICES = [
        (ACTION_SUBMIT, 'Submit'), (ACTION_WITHDRAW, 'Withdraw'), (ACTION_VERIFY, 'Verify'),
        (ACTION_APPROVE, 'Approve'), (ACTION_REJECT, 'Reject'), (ACTION_POST, 'Post'),
        (ACTION_REVERSE, 'Reverse'), (ACTION_CREDIT_NOTE, 'Create credit note'),
        (ACTION_APPROVE_EXCEPTION, 'Approve match exception'),
        (ACTION_REJECT_EXCEPTION, 'Reject match exception'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoice_approvals')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='approvals')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='invoice_approvals')
    idempotency_key = models.CharField(max_length=100, blank=True)
    acted_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-acted_at', '-id']
        constraints = [models.UniqueConstraint(
            fields=['company', 'idempotency_key'], condition=~Q(idempotency_key=''),
            name='unique_company_invoice_approval_key',
        )]

    def save(self, *args, **kwargs):
        if self.pk and InvoiceApproval.objects.filter(pk=self.pk).exists():
            raise ValidationError('Invoice approvals are append-only.')
        if self.invoice_id and self.invoice.company_id != self.company_id:
            raise ValidationError({'invoice': 'Invoice must belong to the same company.'})
        if self.acted_by_id and self.acted_by.company_id != self.company_id:
            raise ValidationError({'acted_by': 'User must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Invoice approvals cannot be deleted.')


class SupplierCreditNote(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_POSTED, 'Posted'), (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_credit_notes')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='credit_notes')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='credit_notes')
    credit_note_number = models.CharField(max_length=100)
    credit_note_date = models.DateField()
    currency = models.CharField(max_length=3, default='UGX')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    idempotency_key = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_supplier_credit_notes',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='posted_supplier_credit_notes',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-credit_note_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'supplier', 'credit_note_number'], name='unique_company_supplier_credit_note',
            ),
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_company_credit_note_key'),
            models.CheckConstraint(condition=Q(subtotal__gte=0), name='credit_note_subtotal_nonnegative'),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name='credit_note_tax_nonnegative'),
            models.CheckConstraint(condition=Q(total_amount__gt=0), name='credit_note_total_positive'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='credit_note_exchange_rate_positive'),
        ]

    def clean(self):
        for field in ('supplier', 'invoice', 'created_by', 'posted_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        if self.invoice_id and self.supplier_id and self.invoice.supplier_id != self.supplier_id:
            raise ValidationError({'supplier': 'Supplier must match the invoice.'})
        if self.total_amount != self.subtotal + self.tax_amount:
            raise ValidationError({'total_amount': 'Total must equal subtotal plus tax.'})

    def save(self, *args, **kwargs):
        if self.pk and SupplierCreditNote.objects.filter(pk=self.pk, status=self.STATUS_POSTED).exists():
            raise ValidationError('Posted credit notes are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError('Posted credit notes cannot be deleted.')
        return super().delete(*args, **kwargs)


class SupplierCreditNoteItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_credit_note_items')
    credit_note = models.ForeignKey(SupplierCreditNote, on_delete=models.CASCADE, related_name='items')
    invoice_item = models.ForeignKey(
        SupplierInvoiceItem, on_delete=models.PROTECT, null=True, blank=True, related_name='credit_note_items',
    )
    material = models.ForeignKey('materials.Material', on_delete=models.PROTECT, related_name='supplier_credit_note_items')
    tax_code = models.ForeignKey(TaxCode, on_delete=models.PROTECT, null=True, blank=True, related_name='credit_note_items')
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=2)
    unit_price = models.DecimalField(max_digits=16, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name='credit_note_item_quantity_positive'),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name='credit_note_item_price_nonnegative'),
            models.CheckConstraint(condition=Q(tax_amount__gte=0), name='credit_note_item_tax_nonnegative'),
        ]

    @property
    def subtotal(self):
        return self.quantity * self.unit_price

    @property
    def total(self):
        return self.subtotal + self.tax_amount

    def clean(self):
        for field in ('credit_note', 'invoice_item', 'material', 'tax_code'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.invoice_item_id and self.credit_note_id and self.invoice_item.invoice_id != self.credit_note.invoice_id:
            raise ValidationError({'invoice_item': 'Invoice item must belong to the credited invoice.'})

    def save(self, *args, **kwargs):
        if self.credit_note_id and self.credit_note.status != SupplierCreditNote.STATUS_DRAFT:
            raise ValidationError('Posted credit note items are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)


class ThreeWayMatch(models.Model):
    STATUS_MATCHED = 'MATCHED'
    STATUS_EXCEPTION = 'EXCEPTION'
    STATUS_CHOICES = [(STATUS_MATCHED, 'Matched'), (STATUS_EXCEPTION, 'Exception')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='three_way_matches')
    invoice = models.OneToOneField(SupplierInvoice, on_delete=models.PROTECT, related_name='three_way_match')
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder',
        on_delete=models.PROTECT,
        related_name='three_way_matches',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    tolerance = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    po_total = models.DecimalField(max_digits=16, decimal_places=2)
    invoice_total = models.DecimalField(max_digits=16, decimal_places=2)
    received_total = models.DecimalField(max_digits=16, decimal_places=2)
    quantity_variance = models.DecimalField(max_digits=16, decimal_places=2)
    amount_variance = models.DecimalField(max_digits=16, decimal_places=2)
    exceptions = models.JSONField(default=list, blank=True)
    idempotency_key = models.CharField(max_length=100, blank=True)
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='performed_three_way_matches',
    )
    matched_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-matched_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                condition=~Q(idempotency_key=''),
                name='unique_company_match_idempotency',
            ),
            models.CheckConstraint(condition=Q(tolerance__gte=0), name='match_tolerance_nonnegative'),
        ]

    def clean(self):
        if self.invoice_id and self.invoice.company_id != self.company_id:
            raise ValidationError({'invoice': 'Invoice must belong to the same company.'})
        if self.purchase_order_id and self.purchase_order.company_id != self.company_id:
            raise ValidationError({'purchase_order': 'Purchase order must belong to the same company.'})
        if self.matched_by_id and self.matched_by.company_id != self.company_id:
            raise ValidationError({'matched_by': 'User must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk and ThreeWayMatch.objects.filter(pk=self.pk).exists():
            raise ValidationError('Three-way match records are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)


class InvoiceMatchRun(models.Model):
    STATUS_MATCHED = 'MATCHED'
    STATUS_WITHIN_TOLERANCE = 'WITHIN_TOLERANCE'
    STATUS_EXCEPTION = 'EXCEPTION'
    STATUS_BLOCKED = 'BLOCKED'
    STATUS_CHOICES = [
        (STATUS_MATCHED, 'Matched'), (STATUS_WITHIN_TOLERANCE, 'Within tolerance'),
        (STATUS_EXCEPTION, 'Exception'), (STATUS_BLOCKED, 'Blocked'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoice_match_runs')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='match_runs')
    purchase_order = models.ForeignKey(
        'procurement.PurchaseOrder', on_delete=models.PROTECT, related_name='invoice_match_runs',
    )
    status = models.CharField(max_length=25, choices=STATUS_CHOICES)
    explanation = models.TextField(blank=True)
    subtotal = models.DecimalField(max_digits=16, decimal_places=2)
    freight_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    other_charges_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    credit_note_amount = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    quantity_tolerance = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    price_tolerance = models.DecimalField(max_digits=14, decimal_places=4, default=0)
    idempotency_key = models.CharField(max_length=100, blank=True)
    exception_reason = models.TextField(blank=True)
    exception_approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_invoice_match_exceptions',
    )
    exception_approved_at = models.DateTimeField(null=True, blank=True)
    exception_rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='rejected_invoice_match_exceptions',
    )
    exception_rejected_at = models.DateTimeField(null=True, blank=True)
    run_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='invoice_match_runs')
    run_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-run_at', '-id']
        constraints = [models.UniqueConstraint(
            fields=['company', 'idempotency_key'], condition=~Q(idempotency_key=''),
            name='unique_company_invoice_match_run_key',
        )]

    @property
    def exception_is_approved(self):
        return self.exception_approved_by_id is not None and self.exception_rejected_by_id is None

    def clean(self):
        for field in ('invoice', 'purchase_order', 'run_by', 'exception_approved_by', 'exception_rejected_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.invoice_id and self.purchase_order_id and self.invoice.purchase_order_id != self.purchase_order_id:
            raise ValidationError({'purchase_order': 'Purchase order must match the invoice.'})

    def save(self, *args, **kwargs):
        if self.pk and InvoiceMatchRun.objects.filter(pk=self.pk).exists():
            raise ValidationError('Match runs are immutable except through controlled exception actions.')
        self.full_clean()
        return super().save(*args, **kwargs)


class InvoiceMatchItemResult(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoice_match_item_results')
    match_run = models.ForeignKey(InvoiceMatchRun, on_delete=models.PROTECT, related_name='item_results')
    invoice_item = models.ForeignKey(SupplierInvoiceItem, on_delete=models.PROTECT, related_name='match_results')
    purchase_order_item = models.ForeignKey(
        'procurement.PurchaseOrderItem', on_delete=models.PROTECT, related_name='invoice_match_results',
    )
    ordered_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    accepted_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    rejected_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    damaged_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    previously_invoiced_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    current_invoice_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    remaining_invoiceable_quantity = models.DecimalField(max_digits=14, decimal_places=2)
    po_price = models.DecimalField(max_digits=16, decimal_places=2)
    invoice_price = models.DecimalField(max_digits=16, decimal_places=2)
    quantity_variance = models.DecimalField(max_digits=14, decimal_places=2)
    price_variance = models.DecimalField(max_digits=16, decimal_places=2)
    price_variance_percent = models.DecimalField(max_digits=14, decimal_places=4)
    status = models.CharField(max_length=25, choices=InvoiceMatchRun.STATUS_CHOICES)
    explanation = models.TextField(blank=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(
            fields=['match_run', 'invoice_item'], name='unique_invoice_item_per_match_run',
        )]

    def save(self, *args, **kwargs):
        if self.pk and InvoiceMatchItemResult.objects.filter(pk=self.pk).exists():
            raise ValidationError('Match item results are immutable.')
        for field in ('match_run', 'invoice_item'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class FiscalPeriod(models.Model):
    STATUS_OPEN = 'OPEN'
    STATUS_CLOSED = 'CLOSED'
    STATUS_CHOICES = [(STATUS_OPEN, 'Open'), (STATUS_CLOSED, 'Closed')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='fiscal_periods')
    name = models.CharField(max_length=100)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_OPEN)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='closed_fiscal_periods',
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-start_date']
        constraints = [
            models.UniqueConstraint(fields=['company', 'name'], name='unique_company_fiscal_period_name'),
            models.CheckConstraint(condition=Q(end_date__gte=models.F('start_date')), name='fiscal_period_dates_valid'),
        ]

    def clean(self):
        if self.closed_by_id and self.closed_by.company_id != self.company_id:
            raise ValidationError({'closed_by': 'User must belong to the same company.'})
        overlap = FiscalPeriod.objects.filter(
            company_id=self.company_id,
            start_date__lte=self.end_date,
            end_date__gte=self.start_date,
        ).exclude(pk=self.pk)
        if self.company_id and self.start_date and self.end_date and overlap.exists():
            raise ValidationError({'non_field_errors': ['Fiscal periods cannot overlap.']})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class PostingRule(models.Model):
    EVENT_GRN_RECEIPT = 'GRN_RECEIPT'
    EVENT_SUPPLIER_INVOICE = 'SUPPLIER_INVOICE'
    EVENT_SUPPLIER_PAYMENT = 'SUPPLIER_PAYMENT'
    EVENT_PROJECT_ISSUE = 'PROJECT_ISSUE'
    EVENT_INVENTORY_ADJUSTMENT = 'INVENTORY_ADJUSTMENT'
    EVENT_INVENTORY_WRITE_OFF = 'INVENTORY_WRITE_OFF'
    EVENT_SUPPLIER_RETURN = 'SUPPLIER_RETURN'
    EVENT_CREDIT_NOTE = 'CREDIT_NOTE'
    EVENT_LANDED_COST = 'LANDED_COST'
    EVENT_PROJECT_EXPENSE = 'PROJECT_EXPENSE'
    EVENT_PETTY_CASH = 'PETTY_CASH'
    EVENT_CHOICES = [
        (EVENT_GRN_RECEIPT, 'GRN inventory receipt'),
        (EVENT_SUPPLIER_INVOICE, 'Supplier invoice'),
        (EVENT_SUPPLIER_PAYMENT, 'Supplier payment'),
        (EVENT_PROJECT_ISSUE, 'Material issue to project'),
        (EVENT_INVENTORY_ADJUSTMENT, 'Inventory adjustment'),
        (EVENT_INVENTORY_WRITE_OFF, 'Inventory write-off'),
        (EVENT_SUPPLIER_RETURN, 'Supplier return'),
        (EVENT_CREDIT_NOTE, 'Credit note'),
        (EVENT_LANDED_COST, 'Landed cost'),
        (EVENT_PROJECT_EXPENSE, 'Project expense'),
        (EVENT_PETTY_CASH, 'Petty-cash transaction'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='posting_rules')
    event_type = models.CharField(max_length=40, choices=EVENT_CHOICES)
    name = models.CharField(max_length=150)
    debit_mapping_key = models.CharField(max_length=50)
    credit_mapping_key = models.CharField(max_length=50)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['event_type']
        constraints = [models.UniqueConstraint(
            fields=['company', 'event_type'], name='unique_company_posting_rule_event',
        )]

    def save(self, *args, **kwargs):
        self.debit_mapping_key = self.debit_mapping_key.upper()
        self.credit_mapping_key = self.credit_mapping_key.upper()
        self.full_clean()
        return super().save(*args, **kwargs)


class AccountMapping(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='account_mappings')
    mapping_key = models.CharField(max_length=50)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='account_mappings')
    description = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['mapping_key']
        constraints = [models.UniqueConstraint(
            fields=['company', 'mapping_key'], name='unique_company_account_mapping_key',
        )]

    def clean(self):
        if self.account_id and self.account.company_id != self.company_id:
            raise ValidationError({'account': 'Mapped account must belong to the same company.'})

    def save(self, *args, **kwargs):
        self.mapping_key = self.mapping_key.upper()
        self.full_clean()
        return super().save(*args, **kwargs)


class JournalEntry(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_POSTED, 'Posted'), (STATUS_REVERSED, 'Reversed'),
    ]
    SOURCE_INVOICE = 'INVOICE'
    SOURCE_PAYMENT = 'PAYMENT'
    SOURCE_INVOICE_REVERSAL = 'INVOICE_REVERSAL'
    SOURCE_PAYMENT_REVERSAL = 'PAYMENT_REVERSAL'
    SOURCE_CREDIT_NOTE = 'CREDIT_NOTE'
    SOURCE_EXPENSE = 'EXPENSE'
    SOURCE_STAFF_ADVANCE = 'STAFF_ADVANCE'
    SOURCE_ADVANCE_RETIREMENT = 'ADVANCE_RETIREMENT'
    SOURCE_ADVANCE_RETIREMENT_REVERSAL = 'ADVANCE_RETIREMENT_REVERSAL'
    SOURCE_PETTY_CASH = 'PETTY_CASH'
    SOURCE_PETTY_CASH_REVERSAL = 'PETTY_CASH_REVERSAL'
    SOURCE_EXPENSE_REVERSAL = 'EXPENSE_REVERSAL'
    SOURCE_ADVANCE_REVERSAL = 'ADVANCE_REVERSAL'
    SOURCE_MANUAL = 'MANUAL'
    SOURCE_GRN = 'GRN'
    SOURCE_STOCK_MOVEMENT = 'STOCK_MOVEMENT'
    SOURCE_LANDED_COST = 'LANDED_COST'
    SOURCE_JOURNAL_REVERSAL = 'JOURNAL_REVERSAL'
    SOURCE_CHOICES = [
        (SOURCE_INVOICE, 'Supplier Invoice'),
        (SOURCE_PAYMENT, 'Payment'),
        (SOURCE_INVOICE_REVERSAL, 'Invoice Reversal'),
        (SOURCE_PAYMENT_REVERSAL, 'Payment Reversal'),
        (SOURCE_CREDIT_NOTE, 'Supplier Credit Note'),
        (SOURCE_EXPENSE, 'Expense Claim'),
        (SOURCE_STAFF_ADVANCE, 'Staff Advance'),
        (SOURCE_ADVANCE_RETIREMENT, 'Advance Retirement'),
        (SOURCE_ADVANCE_RETIREMENT_REVERSAL, 'Advance Retirement Reversal'),
        (SOURCE_PETTY_CASH, 'Petty Cash'),
        (SOURCE_PETTY_CASH_REVERSAL, 'Petty Cash Reversal'),
        (SOURCE_EXPENSE_REVERSAL, 'Expense Reversal'),
        (SOURCE_ADVANCE_REVERSAL, 'Staff Advance Reversal'),
        (SOURCE_MANUAL, 'Manual Journal'),
        (SOURCE_GRN, 'Goods Received Note'),
        (SOURCE_STOCK_MOVEMENT, 'Stock Movement'),
        (SOURCE_LANDED_COST, 'Landed Cost'),
        (SOURCE_JOURNAL_REVERSAL, 'Journal Reversal'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='journal_entries')
    number = models.CharField(max_length=50)
    date = models.DateField()
    description = models.CharField(max_length=500)
    source_type = models.CharField(max_length=30, choices=SOURCE_CHOICES)
    source_object_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_reference = models.CharField(max_length=100, blank=True)
    fiscal_period = models.ForeignKey(
        FiscalPeriod, on_delete=models.PROTECT, null=True, blank=True, related_name='journal_entries',
    )
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    reversal_of = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversal_entry',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='created_journal_entries',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='posted_journal_entries',
    )
    posted_at = models.DateTimeField(null=True, blank=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-date', '-posted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_journal_client_uuid',
            ),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_journal_number'),
            models.UniqueConstraint(
                fields=['company', 'source_type', 'source_object_id'],
                condition=Q(source_object_id__isnull=False),
                name='unique_finance_source_journal',
            ),
        ]

    def save(self, *args, **kwargs):
        previous = JournalEntry.objects.filter(pk=self.pk).values_list('status', flat=True).first() if self.pk else None
        if previous in {self.STATUS_POSTED, self.STATUS_REVERSED}:
            raise ValidationError('Posted journal entries are immutable; use a reversal.')
        if not self.pk and self.status != self.STATUS_DRAFT:
            raise ValidationError('New journals must be created as drafts and posted through the ledger service.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def clean(self):
        for field in ('created_by', 'posted_by', 'fiscal_period'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.reversal_of_id and self.reversal_of.company_id != self.company_id:
            raise ValidationError({'reversal_of': 'Reversed entry must belong to the same company.'})

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError('Posted journal entries cannot be deleted.')
        return super().delete(*args, **kwargs)


class JournalLine(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='journal_lines')
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='lines')
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='journal_lines')
    project = models.ForeignKey(
        'projects.Project',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_lines',
    )
    supplier = models.ForeignKey(
        'suppliers.Supplier',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='journal_lines',
    )
    description = models.CharField(max_length=500, blank=True)
    debit = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=16, decimal_places=2, default=0)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [
            models.CheckConstraint(
                condition=(Q(debit__gt=0, credit=0) | Q(credit__gt=0, debit=0)),
                name='journal_line_single_positive_side',
            )
        ]

    def clean(self):
        for field in ('entry', 'account', 'project', 'supplier'):
            if not getattr(self, f'{field}_id', None):
                continue
            value = getattr(self, field)
            if value.company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.entry_id and self.entry.status != JournalEntry.STATUS_DRAFT:
            raise ValidationError('Posted journal lines are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.entry.status != JournalEntry.STATUS_DRAFT:
            raise ValidationError('Posted journal lines cannot be deleted.')
        return super().delete(*args, **kwargs)


class JournalReversal(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='journal_reversals')
    original_journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name='reversal_record',
    )
    reversal_journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, related_name='reverses_record',
    )
    reason = models.TextField()
    idempotency_key = models.CharField(max_length=100)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='journal_reversals',
    )
    reversed_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-reversed_at']
        constraints = [models.UniqueConstraint(
            fields=['company', 'idempotency_key'], name='unique_company_journal_reversal_key',
        )]

    def save(self, *args, **kwargs):
        if self.pk and JournalReversal.objects.filter(pk=self.pk).exists():
            raise ValidationError('Journal reversal records are immutable.')
        for field in ('original_journal', 'reversal_journal', 'reversed_by'):
            if getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.original_journal_id == self.reversal_journal_id:
            raise ValidationError({'reversal_journal': 'A journal cannot reverse itself.'})
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Journal reversal records cannot be deleted.')


class Payment(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_POSTED = 'POSTED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'), (STATUS_POSTED, 'Posted'),
        (STATUS_REJECTED, 'Rejected'), (STATUS_REVERSED, 'Reversed'),
    ]

    METHOD_BANK = 'BANK'
    METHOD_MOBILE_MONEY = 'MOBILE_MONEY'
    METHOD_CHEQUE = 'CHEQUE'
    METHOD_CASH = 'CASH'
    METHOD_CHOICES = [
        (METHOD_BANK, 'Bank Transfer'),
        (METHOD_MOBILE_MONEY, 'Mobile Money'),
        (METHOD_CHEQUE, 'Cheque'),
        (METHOD_CASH, 'Cash'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_payments')
    supplier = models.ForeignKey(
        'suppliers.Supplier', on_delete=models.PROTECT, null=True, blank=True, related_name='finance_payments',
    )
    invoice = models.ForeignKey(
        SupplierInvoice, on_delete=models.PROTECT, null=True, blank=True, related_name='payments',
    )
    source_account = models.ForeignKey(
        Account, on_delete=models.PROTECT, null=True, blank=True, related_name='supplier_payments',
    )
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, null=True, blank=True, related_name='supplier_payments',
    )
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    number = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    payment_date = models.DateField()
    method = models.CharField(max_length=30, choices=METHOD_CHOICES)
    reference = models.CharField(max_length=100, blank=True)
    voucher_reference = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    idempotency_key = models.CharField(max_length=100)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_finance_payments',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_finance_payments',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='posted_finance_payments',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment',
    )

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-payment_date', '-posted_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_payment_client_uuid',
            ),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_payment_number'),
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_company_payment_idempotency',
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_amount_positive'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='payment_exchange_rate_positive'),
            models.UniqueConstraint(
                fields=['company', 'source_account', 'reference'], condition=~Q(reference=''),
                name='unique_payment_account_reference',
            ),
        ]

    def clean(self):
        for field in (
            'supplier', 'invoice', 'source_account', 'currency', 'created_by',
            'approved_by', 'posted_by', 'journal_entry',
        ):
            if not getattr(self, f'{field}_id', None):
                continue
            value = getattr(self, field)
            if value.company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.invoice_id and self.supplier_id and self.invoice.supplier_id != self.supplier_id:
            raise ValidationError({'invoice': 'Invoice supplier must match the payment supplier.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = Payment.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_POSTED, self.STATUS_REVERSED}:
                raise ValidationError('Posted payments are immutable; use a reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError('Only draft payments can be deleted.')
        return super().delete(*args, **kwargs)

    @property
    def allocated_amount(self):
        return self.allocations.exclude(status=PaymentAllocation.STATUS_REVERSED).aggregate(
            total=models.Sum('amount'),
        )['total'] or Decimal('0.00')

    @property
    def unallocated_amount(self):
        return max(self.amount - self.allocated_amount, Decimal('0.00'))


class PaymentAllocation(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_APPROVED = 'APPROVED'
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_APPROVED, 'Approved'),
        (STATUS_POSTED, 'Posted'), (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_allocations')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='allocations')
    invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='payment_allocations')
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_payment_allocations',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(fields=['payment', 'invoice'], name='unique_invoice_per_payment'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='payment_allocation_positive'),
        ]

    def clean(self):
        for field in ('payment', 'invoice', 'created_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        if self.payment_id and self.invoice_id and self.payment.supplier_id != self.invoice.supplier_id:
            raise ValidationError({'invoice': 'Invoice supplier must match the payment supplier.'})

    def save(self, *args, **kwargs):
        if self.pk and PaymentAllocation.objects.filter(
            pk=self.pk, status__in=[self.STATUS_POSTED, self.STATUS_REVERSED],
        ).exists():
            raise ValidationError('Posted allocations are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)


class PaymentApproval(models.Model):
    ACTION_SUBMIT = 'SUBMIT'
    ACTION_APPROVE = 'APPROVE'
    ACTION_REJECT = 'REJECT'
    ACTION_POST = 'POST'
    ACTION_REVERSE = 'REVERSE'
    ACTION_ALLOCATE = 'ALLOCATE'
    ACTION_UNALLOCATE = 'UNALLOCATE'
    ACTION_CHOICES = [
        (ACTION_SUBMIT, 'Submit'), (ACTION_APPROVE, 'Approve'), (ACTION_REJECT, 'Reject'),
        (ACTION_POST, 'Post'), (ACTION_REVERSE, 'Reverse'),
        (ACTION_ALLOCATE, 'Allocate'), (ACTION_UNALLOCATE, 'Unallocate'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_approvals')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='approvals')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    acted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_approvals')
    idempotency_key = models.CharField(max_length=100, blank=True)
    acted_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-acted_at', '-id']
        constraints = [models.UniqueConstraint(
            fields=['company', 'idempotency_key'], condition=~Q(idempotency_key=''),
            name='unique_company_payment_approval_key',
        )]

    def save(self, *args, **kwargs):
        if self.pk and PaymentApproval.objects.filter(pk=self.pk).exists():
            raise ValidationError('Payment approvals are append-only.')
        for field in ('payment', 'acted_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class PaymentAttachment(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_attachments')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='attachments')
    file = models.FileField(upload_to=payment_attachment_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payment_attachments')
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    def save(self, *args, **kwargs):
        for field in ('payment', 'uploaded_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        self.full_clean(exclude=['file'] if not self.file else None)
        return super().save(*args, **kwargs)


class SupplierAdvance(models.Model):
    STATUS_AUTHORIZED = 'AUTHORIZED'
    STATUS_APPLIED = 'APPLIED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_AUTHORIZED, 'Authorized'), (STATUS_APPLIED, 'Applied'), (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='supplier_advances')
    supplier = models.ForeignKey('suppliers.Supplier', on_delete=models.PROTECT, related_name='advances')
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='supplier_advance')
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AUTHORIZED)
    reason = models.TextField()
    authorized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='authorized_supplier_advances',
    )
    authorized_at = models.DateTimeField(default=timezone.now)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-authorized_at']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='supplier_advance_positive')]

    def save(self, *args, **kwargs):
        if self.pk and SupplierAdvance.objects.filter(pk=self.pk).exists():
            raise ValidationError('Supplier advances are immutable except through controlled application or reversal.')
        for field in ('supplier', 'payment', 'authorized_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        if self.payment_id and self.supplier_id and self.payment.supplier_id != self.supplier_id:
            raise ValidationError({'payment': 'Payment supplier must match the advance supplier.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class ProjectCost(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='finance_project_costs')
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, related_name='finance_costs')
    supplier_invoice = models.ForeignKey(SupplierInvoice, on_delete=models.PROTECT, related_name='project_costs')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='project_costs')
    journal_entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='project_costs')
    amount = models.DecimalField(max_digits=16, decimal_places=2)
    date = models.DateField()
    description = models.CharField(max_length=500)
    is_reversal = models.BooleanField(default=False)
    reversal_of = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reversal_cost',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['payment', 'supplier_invoice'],
                condition=Q(is_reversal=False),
                name='unique_project_cost_per_payment_invoice',
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name='project_cost_amount_positive'),
            models.CheckConstraint(
                condition=(Q(is_reversal=False, reversal_of__isnull=True) | Q(is_reversal=True, reversal_of__isnull=False)),
                name='project_cost_reversal_consistency',
            ),
        ]

    def clean(self):
        for field in ('project', 'supplier_invoice', 'payment', 'journal_entry', 'reversal_of'):
            if not getattr(self, f'{field}_id', None):
                continue
            value = getattr(self, field)
            if value.company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.payment_id and self.supplier_invoice_id:
            is_legacy_invoice = self.payment.invoice_id == self.supplier_invoice_id
            is_allocated = self.payment.allocations.filter(invoice_id=self.supplier_invoice_id).exists()
            if not (is_legacy_invoice or is_allocated):
                raise ValidationError({'payment': 'Payment must be allocated to the supplier invoice.'})

    def save(self, *args, **kwargs):
        if self.pk and ProjectCost.objects.filter(pk=self.pk).exists():
            raise ValidationError('Project costs are immutable; use a reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Project costs cannot be deleted.')


class InvoiceReversal(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='invoice_reversals')
    invoice = models.OneToOneField(SupplierInvoice, on_delete=models.PROTECT, related_name='reversal')
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name='invoice_reversal')
    reason = models.TextField()
    idempotency_key = models.CharField(max_length=100)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reversed_supplier_invoices',
    )
    reversed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_company_invoice_reversal_idempotency',
            )
        ]

    def clean(self):
        for field in ('invoice', 'journal_entry', 'reversed_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk and InvoiceReversal.objects.filter(pk=self.pk).exists():
            raise ValidationError('Invoice reversal records are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Invoice reversal records cannot be deleted.')


class PaymentReversal(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_reversals')
    payment = models.OneToOneField(Payment, on_delete=models.PROTECT, related_name='reversal')
    journal_entry = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, related_name='payment_reversal')
    project_cost = models.OneToOneField(
        ProjectCost,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='payment_reversal',
    )
    reason = models.TextField()
    idempotency_key = models.CharField(max_length=100)
    reversed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reversed_finance_payments',
    )
    reversed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'],
                name='unique_company_payment_reversal_idempotency',
            )
        ]

    def clean(self):
        for field in ('payment', 'journal_entry', 'project_cost', 'reversed_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk and PaymentReversal.objects.filter(pk=self.pk).exists():
            raise ValidationError('Payment reversal records are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Payment reversal records cannot be deleted.')


class LandedCostDocument(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'), (STATUS_POSTED, 'Posted'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    ALLOCATION_QUANTITY = 'QUANTITY'
    ALLOCATION_WEIGHT = 'WEIGHT'
    ALLOCATION_VALUE = 'MATERIAL_VALUE'
    ALLOCATION_EQUAL = 'EQUAL'
    ALLOCATION_MANUAL = 'MANUAL'
    ALLOCATION_CHOICES = [
        (ALLOCATION_QUANTITY, 'Quantity'), (ALLOCATION_WEIGHT, 'Weight'),
        (ALLOCATION_VALUE, 'Material value'), (ALLOCATION_EQUAL, 'Equal distribution'),
        (ALLOCATION_MANUAL, 'Manual allocation'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='landed_cost_documents')
    number = models.CharField(max_length=50)
    description = models.TextField(blank=True)
    allocation_method = models.CharField(max_length=25, choices=ALLOCATION_CHOICES)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='landed_cost_documents')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    base_total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    goods_received_notes = models.ManyToManyField(
        'procurement.GoodsReceivedNote', related_name='landed_cost_documents', blank=True,
    )
    reversal_of = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal_document',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_landed_cost_documents',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_landed_cost_documents',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='posted_landed_cost_documents',
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_landed_client_uuid',
            ),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_landed_cost_number'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='landed_cost_exchange_rate_positive'),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name='landed_cost_total_nonnegative'),
            models.CheckConstraint(condition=Q(base_total_amount__gte=0), name='landed_cost_base_total_nonnegative'),
        ]

    def clean(self):
        for field in ('currency', 'created_by', 'approved_by', 'posted_by', 'reversal_of'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = LandedCostDocument.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_APPROVED, self.STATUS_POSTED, self.STATUS_REVERSED}:
                raise ValidationError('Approved and posted landed-cost documents are immutable; use a reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != self.STATUS_DRAFT:
            raise ValidationError('Only draft landed-cost documents can be deleted.')
        return super().delete(*args, **kwargs)


class LandedCostItem(models.Model):
    COST_TRANSPORT = 'TRANSPORT'
    COST_LOADING = 'LOADING_OFFLOADING'
    COST_INSURANCE = 'INSURANCE'
    COST_HANDLING = 'HANDLING'
    COST_NON_REFUNDABLE_TAX = 'NON_REFUNDABLE_TAX'
    COST_OTHER = 'OTHER'
    COST_TYPE_CHOICES = [
        (COST_TRANSPORT, 'Transport'), (COST_LOADING, 'Loading and offloading'),
        (COST_INSURANCE, 'Insurance'), (COST_HANDLING, 'Handling'),
        (COST_NON_REFUNDABLE_TAX, 'Non-refundable tax'), (COST_OTHER, 'Other approved cost'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='landed_cost_items')
    document = models.ForeignKey(LandedCostDocument, on_delete=models.PROTECT, related_name='items')
    cost_type = models.CharField(max_length=30, choices=COST_TYPE_CHOICES)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    tax_code = models.ForeignKey(
        TaxCode, on_delete=models.PROTECT, null=True, blank=True, related_name='landed_cost_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='landed_cost_item_amount_positive')]

    def clean(self):
        for field in ('document', 'tax_code'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.document_id and self.document.status != LandedCostDocument.STATUS_DRAFT:
            raise ValidationError('Landed-cost items can only be changed while the document is draft.')
        self.full_clean()
        return super().save(*args, **kwargs)


class LandedCostAllocation(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_POSTED, 'Posted'), (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='landed_cost_allocations')
    document = models.ForeignKey(LandedCostDocument, on_delete=models.PROTECT, related_name='allocations')
    goods_received_note_item = models.ForeignKey(
        'procurement.GoodsReceivedNoteItem', on_delete=models.PROTECT, related_name='landed_cost_allocations',
    )
    receipt_movement = models.ForeignKey(
        'warehouse.StockMovement', on_delete=models.PROTECT, related_name='landed_cost_allocations',
    )
    basis_quantity = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    basis_weight = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    basis_value = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    allocated_amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    valuation_movement = models.OneToOneField(
        'warehouse.StockMovement', on_delete=models.PROTECT, null=True, blank=True,
        related_name='landed_cost_valuation_allocation',
    )
    reverses = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal_allocation',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [
            models.UniqueConstraint(
                fields=['document', 'goods_received_note_item'], name='unique_landed_cost_grn_item_allocation',
            ),
            models.CheckConstraint(condition=Q(allocated_amount__gte=0), name='landed_cost_allocation_nonnegative'),
            models.CheckConstraint(condition=Q(basis_quantity__gte=0), name='landed_cost_basis_quantity_nonnegative'),
            models.CheckConstraint(condition=Q(basis_weight__gte=0), name='landed_cost_basis_weight_nonnegative'),
            models.CheckConstraint(condition=Q(basis_value__gte=0), name='landed_cost_basis_value_nonnegative'),
        ]

    def clean(self):
        for field in (
            'document', 'goods_received_note_item', 'receipt_movement',
            'valuation_movement', 'reverses',
        ):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.receipt_movement_id and self.goods_received_note_item_id:
            if self.receipt_movement.goods_received_note_item_id != self.goods_received_note_item_id:
                raise ValidationError({'receipt_movement': 'Receipt movement must match the GRN item.'})

    def save(self, *args, **kwargs):
        if self.pk and LandedCostAllocation.objects.filter(
            pk=self.pk, status__in=[self.STATUS_POSTED, self.STATUS_REVERSED],
        ).exists():
            raise ValidationError('Posted landed-cost allocations are immutable.')
        self.full_clean()
        return super().save(*args, **kwargs)


class LandedCostApproval(models.Model):
    ACTION_SUBMIT = 'SUBMIT'
    ACTION_APPROVE = 'APPROVE'
    ACTION_POST = 'POST'
    ACTION_REVERSE = 'REVERSE'
    ACTION_CHOICES = [
        (ACTION_SUBMIT, 'Submit'), (ACTION_APPROVE, 'Approve'),
        (ACTION_POST, 'Post'), (ACTION_REVERSE, 'Reverse'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='landed_cost_approvals')
    document = models.ForeignKey(LandedCostDocument, on_delete=models.PROTECT, related_name='approvals')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='landed_cost_approvals',
    )
    idempotency_key = models.CharField(max_length=100, blank=True)
    acted_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-acted_at', '-id']
        constraints = [models.UniqueConstraint(
            fields=['company', 'idempotency_key'], condition=~Q(idempotency_key=''),
            name='unique_company_landed_cost_action_key',
        )]

    def save(self, *args, **kwargs):
        if self.pk and LandedCostApproval.objects.filter(pk=self.pk).exists():
            raise ValidationError('Landed-cost approvals are append-only.')
        for field in ('document', 'acted_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class ExpenseCategory(models.Model):
    TYPE_TRANSPORT = 'TRANSPORT'
    TYPE_LOADING = 'LOADING_OFFLOADING'
    TYPE_EQUIPMENT_HIRE = 'EQUIPMENT_HIRE'
    TYPE_FUEL = 'FUEL'
    TYPE_SITE_CONSUMABLES = 'SITE_CONSUMABLES'
    TYPE_EMERGENCY_MATERIALS = 'EMERGENCY_MATERIALS'
    TYPE_ACCOMMODATION = 'ACCOMMODATION'
    TYPE_MISCELLANEOUS = 'MISCELLANEOUS'
    TYPE_CHOICES = [
        (TYPE_TRANSPORT, 'Transport'), (TYPE_LOADING, 'Loading and offloading'),
        (TYPE_EQUIPMENT_HIRE, 'Equipment hire'), (TYPE_FUEL, 'Fuel'),
        (TYPE_SITE_CONSUMABLES, 'Site consumables'),
        (TYPE_EMERGENCY_MATERIALS, 'Emergency material purchases'),
        (TYPE_ACCOMMODATION, 'Accommodation'),
        (TYPE_MISCELLANEOUS, 'Miscellaneous project expenses'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='expense_categories')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    category_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    expense_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='expense_categories')
    budget_category = models.ForeignKey(
        BudgetCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='expense_categories',
    )
    is_overhead = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['name']
        constraints = [models.UniqueConstraint(fields=['company', 'code'], name='unique_company_expense_category')]

    def clean(self):
        for field in ('expense_account', 'budget_category'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.expense_account_id and self.expense_account.account_type != Account.TYPE_EXPENSE:
            raise ValidationError({'expense_account': 'Expense category requires an expense account.'})

    def save(self, *args, **kwargs):
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)


class CashAccount(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='cash_accounts')
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=150)
    account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='cash_accounts')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='cash_accounts')
    opening_balance = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_petty_cash = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['company', 'code'], name='unique_company_cash_account_code'),
            models.UniqueConstraint(fields=['company', 'account'], name='unique_company_cash_ledger_account'),
            models.CheckConstraint(condition=Q(opening_balance__gte=0), name='cash_opening_balance_nonnegative'),
        ]

    def clean(self):
        for field in ('account', 'currency'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})
        if self.account_id and self.account.account_type != Account.TYPE_ASSET:
            raise ValidationError({'account': 'Cash account requires an asset ledger account.'})

    def save(self, *args, **kwargs):
        if self.pk and PettyCashTransaction.objects.filter(cash_account_id=self.pk).exists():
            previous = CashAccount.objects.get(pk=self.pk)
            protected = ('company_id', 'account_id', 'currency_id', 'opening_balance', 'is_petty_cash')
            if any(getattr(previous, field) != getattr(self, field) for field in protected):
                raise ValidationError('Posted cash-account values are immutable; use transactions and reversals.')
        self.code = self.code.upper()
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def current_balance(self):
        effect = self.transactions.aggregate(total=models.Sum('balance_effect'))['total'] or Decimal('0.00')
        return self.opening_balance + effect


class BankStatementLine(models.Model):
    """A bank or cash-statement transaction awaiting independent reconciliation.

    A positive amount increases the cash account; a negative amount is a debit
    from it.  The line deliberately does not alter the ledger: it is evidence
    that a separately-posted payment or receipt actually cleared.
    """

    STATUS_UNRECONCILED = 'UNRECONCILED'
    STATUS_MATCHED = 'MATCHED'
    STATUS_IGNORED = 'IGNORED'
    STATUS_CHOICES = [
        (STATUS_UNRECONCILED, 'Unreconciled'),
        (STATUS_MATCHED, 'Matched'),
        (STATUS_IGNORED, 'Ignored'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='bank_statement_lines')
    cash_account = models.ForeignKey(CashAccount, on_delete=models.PROTECT, related_name='statement_lines')
    statement_date = models.DateField()
    reference = models.CharField(max_length=100)
    description = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment = models.OneToOneField(
        Payment, on_delete=models.PROTECT, null=True, blank=True, related_name='reconciliation_line',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNRECONCILED)
    match_notes = models.TextField(blank=True)
    imported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='imported_bank_statement_lines',
    )
    matched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='matched_bank_statement_lines',
    )
    matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-statement_date', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['cash_account', 'statement_date', 'reference'],
                name='unique_statement_line_reference_per_account_date',
            ),
            models.CheckConstraint(
                condition=Q(amount__gt=0) | Q(amount__lt=0),
                name='bank_statement_line_amount_nonzero',
            ),
        ]

    def clean(self):
        if self.cash_account_id and self.cash_account.company_id != self.company_id:
            raise ValidationError({'cash_account': 'Cash account must belong to the same company.'})
        for field in ('payment', 'imported_by', 'matched_by'):
            value = getattr(self, field, None)
            if value is not None and value.company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.payment_id:
            if self.payment.status != Payment.STATUS_POSTED:
                raise ValidationError({'payment': 'Only posted payments can be reconciled.'})
            if self.payment.source_account_id != self.cash_account.account_id:
                raise ValidationError({'payment': 'Payment source account must match the selected cash account.'})
            if self.amount != -self.payment.amount:
                raise ValidationError({'amount': 'Statement debit must equal the posted payment amount.'})
        if self.status == self.STATUS_MATCHED and not self.payment_id:
            raise ValidationError({'payment': 'A matched statement line requires a posted payment.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = BankStatementLine.objects.get(pk=self.pk)
            protected = ('company_id', 'cash_account_id', 'statement_date', 'reference', 'amount', 'imported_by_id')
            if any(getattr(previous, field) != getattr(self, field) for field in protected):
                raise ValidationError('Imported statement evidence is immutable; create a correcting line instead.')
        self.reference = self.reference.strip()
        self.full_clean()
        return super().save(*args, **kwargs)


class PaymentBatch(models.Model):
    """A controlled run of already-approved supplier payment vouchers."""

    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_RELEASED = 'RELEASED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_APPROVED, 'Approved'), (STATUS_RELEASED, 'Released to ledger'),
        (STATUS_CANCELLED, 'Cancelled'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_batches')
    number = models.CharField(max_length=50)
    source_account = models.ForeignKey(Account, on_delete=models.PROTECT, related_name='payment_batches')
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='payment_batches')
    payment_date = models.DateField(default=timezone.localdate)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_payment_batches')
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='approved_payment_batches')
    approved_at = models.DateTimeField(null=True, blank=True)
    released_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='released_payment_batches')
    released_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-payment_date', '-id']
        constraints = [models.UniqueConstraint(fields=['company', 'number'], name='unique_company_payment_batch_number')]

    def clean(self):
        for field in ('source_account', 'currency', 'created_by', 'approved_by', 'released_by'):
            value = getattr(self, field, None)
            if value is not None and value.company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})

    @property
    def total_amount(self):
        return self.items.aggregate(total=models.Sum('payment__amount'))['total'] or Decimal('0.00')


class PaymentBatchItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='payment_batch_items')
    batch = models.ForeignKey(PaymentBatch, on_delete=models.PROTECT, related_name='items')
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='batch_items')
    added_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [models.UniqueConstraint(fields=['batch', 'payment'], name='unique_payment_per_batch')]

    def clean(self):
        if self.batch_id and self.batch.company_id != self.company_id:
            raise ValidationError({'batch': 'Batch must belong to the same company.'})
        if self.payment_id:
            if self.payment.company_id != self.company_id:
                raise ValidationError({'payment': 'Payment must belong to the same company.'})
            if self.batch_id and (
                self.payment.source_account_id != self.batch.source_account_id
                or self.payment.currency_id != self.batch.currency_id
            ):
                raise ValidationError({'payment': 'Payment account and currency must match the batch.'})


class ExpenseClaim(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_REVIEWED = 'REVIEWED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_PAID = 'PAID'
    STATUS_CLOSED = 'CLOSED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_REVIEWED, 'Reviewed'), (STATUS_APPROVED, 'Approved'),
        (STATUS_PAID, 'Paid'), (STATUS_CLOSED, 'Closed'),
        (STATUS_REJECTED, 'Rejected'), (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='expense_claims')
    number = models.CharField(max_length=50)
    claimant = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='expense_claims',
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='expense_claims',
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.PROTECT, null=True, blank=True, related_name='expense_claims',
    )
    overhead_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='overhead_claims',
    )
    purpose = models.TextField()
    claim_date = models.DateField(default=timezone.localdate)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='expense_claims')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    base_total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    rejection_reason = models.TextField(blank=True)
    cash_account = models.ForeignKey(
        CashAccount, on_delete=models.PROTECT, null=True, blank=True, related_name='expense_claims',
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=100)
    posting_idempotency_key = models.CharField(max_length=100, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='expense_claim',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_expense_claims',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_expense_claims',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_expense_claims',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='paid_expense_claims',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-claim_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_expense_client_uuid',
            ),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_expense_claim_number'),
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_company_expense_claim_key'),
            models.UniqueConstraint(
                fields=['company', 'cash_account', 'payment_reference'], condition=~Q(payment_reference=''),
                name='unique_expense_reimbursement_reference',
            ),
            models.UniqueConstraint(
                fields=['company', 'posting_idempotency_key'], condition=~Q(posting_idempotency_key=''),
                name='unique_expense_posting_key',
            ),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='expense_exchange_rate_positive'),
            models.CheckConstraint(condition=Q(total_amount__gte=0), name='expense_total_nonnegative'),
            models.CheckConstraint(condition=Q(base_total_amount__gte=0), name='expense_base_total_nonnegative'),
            models.CheckConstraint(condition=Q(amount_paid__gte=0), name='expense_amount_paid_nonnegative'),
            models.CheckConstraint(
                condition=Q(project__isnull=False) | Q(cost_centre__isnull=False) | Q(overhead_category__isnull=False),
                name='expense_claim_has_destination',
            ),
        ]

    def clean(self):
        for field in (
            'claimant', 'project', 'cost_centre', 'overhead_category', 'currency',
            'cash_account', 'created_by', 'reviewed_by', 'approved_by', 'paid_by', 'journal_entry',
        ):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if not (self.project_id or self.cost_centre_id or self.overhead_category_id):
            raise ValidationError('Project, cost centre, or approved overhead category is required.')
        if self.overhead_category_id and not (
            self.overhead_category.is_overhead and self.overhead_category.is_approved
        ):
            raise ValidationError({'overhead_category': 'Select an approved overhead category.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = ExpenseClaim.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_PAID, self.STATUS_CLOSED, self.STATUS_REVERSED}:
                raise ValidationError('Posted expense claims are immutable; use a reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)


class ExpenseItem(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='expense_items')
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.PROTECT, related_name='items')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expense_items')
    expense_date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['id']
        constraints = [models.CheckConstraint(condition=Q(amount__gt=0), name='expense_item_amount_positive')]

    def clean(self):
        for field in ('claim', 'category'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.title()} must belong to the same company.'})

    def save(self, *args, **kwargs):
        if self.claim_id and self.claim.status != ExpenseClaim.STATUS_DRAFT:
            raise ValidationError('Expense items can only be changed while the claim is draft.')
        self.full_clean()
        return super().save(*args, **kwargs)


class ExpenseReceiptAttachment(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='expense_receipts')
    claim = models.ForeignKey(ExpenseClaim, on_delete=models.PROTECT, related_name='receipts')
    expense_item = models.ForeignKey(
        ExpenseItem, on_delete=models.PROTECT, null=True, blank=True, related_name='receipts',
    )
    file = models.FileField(upload_to=expense_receipt_path)
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=150)
    size = models.PositiveBigIntegerField()
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='expense_receipts',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    def save(self, *args, **kwargs):
        for field in ('claim', 'expense_item', 'uploaded_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.expense_item_id and self.expense_item.claim_id != self.claim_id:
            raise ValidationError({'expense_item': 'Expense item must belong to the claim.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class StaffAdvance(OfflineDraftMixin):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_REVIEWED = 'REVIEWED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_PAID = 'PAID'
    STATUS_RETIRED = 'RETIRED'
    STATUS_CLOSED = 'CLOSED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'),
        (STATUS_REVIEWED, 'Reviewed'), (STATUS_APPROVED, 'Approved'),
        (STATUS_PAID, 'Paid'), (STATUS_RETIRED, 'Retired'),
        (STATUS_CLOSED, 'Closed'), (STATUS_REJECTED, 'Rejected'),
        (STATUS_REVERSED, 'Reversed'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='staff_advances')
    number = models.CharField(max_length=50)
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='staff_advances',
    )
    project = models.ForeignKey(
        'projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='staff_advances',
    )
    cost_centre = models.ForeignKey(
        CostCentre, on_delete=models.PROTECT, null=True, blank=True, related_name='staff_advances',
    )
    overhead_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, null=True, blank=True, related_name='overhead_advances',
    )
    purpose = models.TextField()
    advance_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)
    currency = models.ForeignKey(Currency, on_delete=models.PROTECT, related_name='staff_advances')
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    base_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    rejection_reason = models.TextField(blank=True)
    cash_account = models.ForeignKey(
        CashAccount, on_delete=models.PROTECT, null=True, blank=True, related_name='staff_advances',
    )
    payment_reference = models.CharField(max_length=100, blank=True)
    idempotency_key = models.CharField(max_length=100)
    posting_idempotency_key = models.CharField(max_length=100, blank=True)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='staff_advance',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_staff_advances',
    )
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_staff_advances',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='paid_staff_advances',
    )
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-advance_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'client_uuid'], condition=Q(client_uuid__isnull=False),
                name='unique_company_advance_client_uuid',
            ),
            models.UniqueConstraint(fields=['company', 'number'], name='unique_company_staff_advance_number'),
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_company_staff_advance_key'),
            models.UniqueConstraint(
                fields=['company', 'cash_account', 'payment_reference'], condition=~Q(payment_reference=''),
                name='unique_staff_advance_payment_reference',
            ),
            models.UniqueConstraint(
                fields=['company', 'posting_idempotency_key'], condition=~Q(posting_idempotency_key=''),
                name='unique_staff_advance_posting_key',
            ),
            models.CheckConstraint(condition=Q(amount__gt=0), name='staff_advance_amount_positive'),
            models.CheckConstraint(condition=Q(base_amount__gte=0), name='staff_advance_base_nonnegative'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='staff_advance_exchange_rate_positive'),
            models.CheckConstraint(
                condition=Q(project__isnull=False) | Q(cost_centre__isnull=False) | Q(overhead_category__isnull=False),
                name='staff_advance_has_destination',
            ),
        ]

    def clean(self):
        for field in (
            'staff', 'project', 'cost_centre', 'overhead_category', 'currency',
            'cash_account', 'created_by', 'approved_by', 'paid_by', 'journal_entry',
        ):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if not (self.project_id or self.cost_centre_id or self.overhead_category_id):
            raise ValidationError('Project, cost centre, or approved overhead category is required.')
        if self.overhead_category_id and not (
            self.overhead_category.is_overhead and self.overhead_category.is_approved
        ):
            raise ValidationError({'overhead_category': 'Select an approved overhead category.'})
        if self.due_date and self.due_date < self.advance_date:
            raise ValidationError({'due_date': 'Due date cannot be earlier than advance date.'})

    def save(self, *args, **kwargs):
        if self.pk:
            previous = StaffAdvance.objects.filter(pk=self.pk).values_list('status', flat=True).first()
            if previous in {self.STATUS_PAID, self.STATUS_RETIRED, self.STATUS_CLOSED, self.STATUS_REVERSED}:
                raise ValidationError('Posted staff advances are immutable; use retirement or reversal.')
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def retired_amount(self):
        retired = self.retirements.filter(is_reversal=False).aggregate(
            total=models.Sum('total_retired'),
        )['total'] or Decimal('0.00')
        reversed_amount = self.retirements.filter(is_reversal=True).aggregate(
            total=models.Sum('total_retired'),
        )['total'] or Decimal('0.00')
        return retired - reversed_amount

    @property
    def outstanding_amount(self):
        return max(self.amount - self.retired_amount, Decimal('0.00'))

    @property
    def outstanding_base_amount(self):
        return (self.outstanding_amount * self.exchange_rate).quantize(Decimal('0.01'))


class AdvanceRetirement(models.Model):
    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='advance_retirements')
    advance = models.ForeignKey(StaffAdvance, on_delete=models.PROTECT, related_name='retirements')
    expense_category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name='advance_retirements',
    )
    amount_spent = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    amount_refunded = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    total_retired = models.DecimalField(max_digits=18, decimal_places=2)
    retirement_date = models.DateField(default=timezone.localdate)
    reason = models.TextField()
    idempotency_key = models.CharField(max_length=100)
    is_reversal = models.BooleanField(default=False)
    reversal_of = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal',
    )
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='advance_retirement',
    )
    retired_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='advance_retirements',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-retirement_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'], name='unique_company_advance_retirement_key',
            ),
            models.CheckConstraint(condition=Q(amount_spent__gte=0), name='advance_spent_nonnegative'),
            models.CheckConstraint(condition=Q(amount_refunded__gte=0), name='advance_refund_nonnegative'),
            models.CheckConstraint(condition=Q(total_retired__gt=0), name='advance_retired_positive'),
            models.CheckConstraint(
                condition=Q(is_reversal=False, reversal_of__isnull=True) | Q(is_reversal=True, reversal_of__isnull=False),
                name='advance_retirement_reversal_consistency',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and AdvanceRetirement.objects.filter(pk=self.pk).exists():
            raise ValidationError('Advance retirement records are immutable; use a reversal.')
        for field in ('advance', 'expense_category', 'reversal_of', 'journal_entry', 'retired_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        if self.total_retired != self.amount_spent + self.amount_refunded:
            raise ValidationError({'total_retired': 'Total retired must equal spent plus refunded amount.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class PettyCashTransaction(models.Model):
    TYPE_DISBURSEMENT = 'DISBURSEMENT'
    TYPE_ADVANCE = 'ADVANCE'
    TYPE_REFUND = 'REFUND'
    TYPE_REPLENISHMENT = 'REPLENISHMENT'
    TYPE_REVERSAL = 'REVERSAL'
    TYPE_CHOICES = [
        (TYPE_DISBURSEMENT, 'Expense disbursement'), (TYPE_ADVANCE, 'Staff advance'),
        (TYPE_REFUND, 'Advance refund'), (TYPE_REPLENISHMENT, 'Replenishment'),
        (TYPE_REVERSAL, 'Reversal'),
    ]
    STATUS_POSTED = 'POSTED'
    STATUS_REVERSED = 'REVERSED'
    STATUS_CHOICES = [(STATUS_POSTED, 'Posted'), (STATUS_REVERSED, 'Reversed')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='petty_cash_transactions')
    cash_account = models.ForeignKey(CashAccount, on_delete=models.PROTECT, related_name='transactions')
    transaction_type = models.CharField(max_length=25, choices=TYPE_CHOICES)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    balance_effect = models.DecimalField(max_digits=18, decimal_places=2)
    exchange_rate = models.DecimalField(max_digits=18, decimal_places=6, default=1)
    transaction_date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=100, blank=True)
    reason = models.TextField()
    expense_claim = models.ForeignKey(
        ExpenseClaim, on_delete=models.PROTECT, null=True, blank=True, related_name='petty_cash_transactions',
    )
    staff_advance = models.ForeignKey(
        StaffAdvance, on_delete=models.PROTECT, null=True, blank=True, related_name='petty_cash_transactions',
    )
    advance_retirement = models.ForeignKey(
        AdvanceRetirement, on_delete=models.PROTECT, null=True, blank=True, related_name='petty_cash_transactions',
    )
    original_transaction = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='reversal_transaction',
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_POSTED)
    idempotency_key = models.CharField(max_length=100)
    journal_entry = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='petty_cash_transaction',
    )
    posted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='petty_cash_transactions',
    )
    posted_at = models.DateTimeField(default=timezone.now)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-transaction_date', '-posted_at']
        constraints = [
            models.UniqueConstraint(fields=['company', 'idempotency_key'], name='unique_company_petty_cash_key'),
            models.CheckConstraint(condition=Q(amount__gt=0), name='petty_cash_amount_positive'),
            models.CheckConstraint(condition=Q(exchange_rate__gt=0), name='petty_cash_exchange_rate_positive'),
            models.CheckConstraint(
                condition=Q(balance_effect__gt=0) | Q(balance_effect__lt=0),
                name='petty_cash_effect_nonzero',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and PettyCashTransaction.objects.filter(pk=self.pk).exists():
            raise ValidationError('Posted petty-cash transactions are immutable; use a reversal.')
        for field in (
            'cash_account', 'expense_claim', 'staff_advance', 'advance_retirement',
            'original_transaction', 'journal_entry', 'posted_by',
        ):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)


class ExpenseApproval(models.Model):
    ACTION_SUBMIT = 'SUBMIT'
    ACTION_APPROVE = 'APPROVE'
    ACTION_REJECT = 'REJECT'
    ACTION_PAY = 'PAY'
    ACTION_RETIRE = 'RETIRE'
    ACTION_REPLENISH = 'REPLENISH'
    ACTION_REVERSE = 'REVERSE'
    ACTION_CHOICES = [
        (ACTION_SUBMIT, 'Submit'), (ACTION_APPROVE, 'Approve'),
        (ACTION_REJECT, 'Reject'), (ACTION_PAY, 'Pay'),
        (ACTION_RETIRE, 'Retire'), (ACTION_REPLENISH, 'Replenish'),
        (ACTION_REVERSE, 'Reverse'),
    ]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='expense_approvals')
    expense_claim = models.ForeignKey(
        ExpenseClaim, on_delete=models.PROTECT, null=True, blank=True, related_name='approvals',
    )
    staff_advance = models.ForeignKey(
        StaffAdvance, on_delete=models.PROTECT, null=True, blank=True, related_name='approvals',
    )
    petty_cash_transaction = models.ForeignKey(
        PettyCashTransaction, on_delete=models.PROTECT, null=True, blank=True, related_name='approvals',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    comments = models.TextField(blank=True)
    acted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='expense_approvals',
    )
    idempotency_key = models.CharField(max_length=100, blank=True)
    acted_at = models.DateTimeField(auto_now_add=True)

    objects = CompanyScopedManager()

    class Meta:
        ordering = ['-acted_at', '-id']
        constraints = [
            models.UniqueConstraint(
                fields=['company', 'idempotency_key'], condition=~Q(idempotency_key=''),
                name='unique_company_expense_approval_key',
            ),
            models.CheckConstraint(
                condition=(
                    Q(expense_claim__isnull=False, staff_advance__isnull=True, petty_cash_transaction__isnull=True)
                    | Q(expense_claim__isnull=True, staff_advance__isnull=False, petty_cash_transaction__isnull=True)
                    | Q(expense_claim__isnull=True, staff_advance__isnull=True, petty_cash_transaction__isnull=False)
                ),
                name='expense_approval_one_target',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and ExpenseApproval.objects.filter(pk=self.pk).exists():
            raise ValidationError('Expense approvals are append-only.')
        for field in ('expense_claim', 'staff_advance', 'petty_cash_transaction', 'acted_by'):
            if getattr(self, f'{field}_id', None) and getattr(self, field).company_id != self.company_id:
                raise ValidationError({field: f'{field.replace("_", " ").title()} must belong to the same company.'})
        self.full_clean()
        return super().save(*args, **kwargs)
