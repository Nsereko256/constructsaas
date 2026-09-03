from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.accounts.models import Company


class WorkOrder(models.Model):
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_ASSIGNED = 'ASSIGNED'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_VERIFIED = 'VERIFIED'
    STATUS_CLOSED = 'CLOSED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CANCELLED = 'CANCELLED'
    STATUS_ON_HOLD = 'ON_HOLD'
    STATUS_CHOICES = [(value, value.replace('_', ' ').title()) for value in (
        STATUS_DRAFT, STATUS_SUBMITTED, STATUS_APPROVED, STATUS_ASSIGNED, STATUS_IN_PROGRESS,
        STATUS_COMPLETED, STATUS_VERIFIED, STATUS_CLOSED, STATUS_REJECTED, STATUS_CANCELLED, STATUS_ON_HOLD,
    )]
    PRIORITY_LOW = 'LOW'
    PRIORITY_NORMAL = 'NORMAL'
    PRIORITY_HIGH = 'HIGH'
    PRIORITY_URGENT = 'URGENT'
    PRIORITY_CHOICES = [(value, value.title()) for value in (PRIORITY_LOW, PRIORITY_NORMAL, PRIORITY_HIGH, PRIORITY_URGENT)]
    ASSIGNMENT_PENDING = 'PENDING'
    ASSIGNMENT_ACCEPTED = 'ACCEPTED'
    ASSIGNMENT_DECLINED = 'DECLINED'
    ASSIGNMENT_CHOICES = [(ASSIGNMENT_PENDING, 'Awaiting acceptance'), (ASSIGNMENT_ACCEPTED, 'Accepted'), (ASSIGNMENT_DECLINED, 'Declined')]

    company = models.ForeignKey(Company, on_delete=models.PROTECT, related_name='work_orders')
    number = models.CharField(max_length=50)
    # A work order is controlled within one project. It may have many physical
    # site packages, but cannot span projects without losing budget ownership.
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, null=True, blank=True, related_name='work_orders')
    site = models.ForeignKey('warehouse.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='work_orders')
    title = models.CharField(max_length=255)
    description = models.TextField()
    work_category = models.CharField(max_length=100, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default=PRIORITY_NORMAL)
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_work_orders')
    responsible_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='responsible_work_orders')
    responsible_team = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True, related_name='team_work_orders')
    contractor = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='work_orders')
    estimated_start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    scope_version = models.PositiveIntegerField(default=1)
    approved_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    assignment_status = models.CharField(max_length=12, choices=ASSIGNMENT_CHOICES, default=ASSIGNMENT_PENDING)
    assignment_response = models.TextField(blank=True)
    assignment_responded_at = models.DateTimeField(null=True, blank=True)
    finance_reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='finance_reviewed_work_orders')
    finance_reviewed_at = models.DateTimeField(null=True, blank=True)
    finance_review_notes = models.TextField(blank=True)
    hold_owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_work_order_holds')
    hold_recovery_date = models.DateField(null=True, blank=True)
    revised_due_date = models.DateField(null=True, blank=True)
    is_emergency = models.BooleanField(default=False)
    emergency_reason = models.TextField(blank=True)
    emergency_spend_cap = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    emergency_retrospectively_approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='retrospectively_approved_emergency_work_orders')
    emergency_retrospectively_approved_at = models.DateTimeField(null=True, blank=True)
    emergency_retrospective_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)
    hold_reason = models.TextField(blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_work_orders')
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verified_work_orders')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['company', 'number'], name='unique_company_work_order_number')]

    def clean(self):
        # New records must be tied to a project. Existing demonstration data
        # created before this control may still be submitted for correction,
        # but approval is blocked until a project is assigned.
        if not self.project_id and self._state.adding:
            raise ValidationError({'project': 'Every work order must have a project. Add physical sites as site packages under that project.'})
        for field in ('project', 'site', 'requester', 'responsible_person', 'contractor', 'approved_by', 'verified_by'):
            value = getattr(self, field, None)
            if value and getattr(value, 'company_id', self.company_id) != self.company_id:
                raise ValidationError({field: 'Selected record must belong to the same company.'})
        if self.site_id and self.project_id and self.site.project_id and self.site.project_id != self.project_id:
            raise ValidationError({'site': 'Site store must belong to the selected project.'})
        if self.due_date and self.estimated_start_date and self.due_date < self.estimated_start_date:
            raise ValidationError({'due_date': 'Due date cannot be before estimated start date.'})
        if self.is_emergency and not self.emergency_reason:
            raise ValidationError({'emergency_reason': 'Explain why emergency work is required.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WorkOrderSite(models.Model):
    """A separately accountable site package under a contractor work order."""
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='site_packages')
    project = models.ForeignKey('projects.Project', on_delete=models.PROTECT, related_name='work_order_site_packages')
    project_site = models.ForeignKey('projects.ProjectSite', on_delete=models.PROTECT, null=True, blank=True, related_name='work_order_packages')
    site = models.ForeignKey('warehouse.Warehouse', on_delete=models.PROTECT, null=True, blank=True, related_name='work_order_site_packages')
    title = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    responsible_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='site_work_orders')
    contractor = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='site_work_orders')
    estimated_start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    actual_completion_date = models.DateField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    progress_notes = models.TextField(blank=True)
    progress_updated_at = models.DateTimeField(null=True, blank=True)
    materials_reconciled = models.BooleanField(default=False)
    quality_checked = models.BooleanField(default=False)
    safety_checked = models.BooleanField(default=False)
    client_signed_off = models.BooleanField(default=False)
    closeout_notes = models.TextField(blank=True)
    hold_owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_site_work_holds')
    hold_recovery_date = models.DateField(null=True, blank=True)
    revised_due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=WorkOrder.STATUS_CHOICES, default=WorkOrder.STATUS_DRAFT)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['project__name', 'site__name', 'id']
        constraints = [models.UniqueConstraint(fields=['work_order', 'project_site'], name='unique_physical_site_package_per_work_order')]

    def clean(self):
        company_id = self.work_order.company_id
        if not self.project_site_id:
            raise ValidationError({'project_site': 'Select the physical project site accountable for this work package.'})
        if self.work_order.project_id != self.project_id:
            raise ValidationError({'project': 'Site packages must belong to the work order project.'})
        if self.project_id and self.project.company_id != company_id:
            raise ValidationError({'project': 'Project must belong to the work order company.'})
        if self.site_id:
            if self.site.company_id != company_id:
                raise ValidationError({'site': 'Site must belong to the work order company.'})
            if self.site.project_id and self.site.project_id != self.project_id:
                raise ValidationError({'site': 'Site store must belong to the selected project.'})
        if self.project_site_id:
            if self.project_site.project_id != self.project_id:
                raise ValidationError({'project_site': 'Physical site must belong to the selected project.'})
            if self.site_id and self.site.project_site_id and self.site.project_site_id != self.project_site_id:
                raise ValidationError({'site': 'Site store must belong to the selected physical site.'})
        for field in ('responsible_person', 'contractor'):
            value = getattr(self, field, None)
            if value and value.company_id != company_id:
                raise ValidationError({field: 'Selected record must belong to the work order company.'})
        if self.due_date and self.estimated_start_date and self.due_date < self.estimated_start_date:
            raise ValidationError({'due_date': 'Due date cannot be before estimated start date.'})
        if self.progress_percent > 100:
            raise ValidationError({'progress_percent': 'Progress cannot exceed 100%.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class WorkOrderTask(models.Model):
    STATUS_NOT_STARTED = 'NOT_STARTED'
    STATUS_IN_PROGRESS = 'IN_PROGRESS'
    STATUS_COMPLETED = 'COMPLETED'
    STATUS_CHOICES = [(STATUS_NOT_STARTED, 'Not started'), (STATUS_IN_PROGRESS, 'In progress'), (STATUS_COMPLETED, 'Completed')]
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='tasks')
    site_package = models.ForeignKey(WorkOrderSite, on_delete=models.CASCADE, null=True, blank=True, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='work_order_tasks')
    contractor = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='work_order_tasks')
    priority = models.CharField(max_length=10, choices=WorkOrder.PRIORITY_CHOICES, default=WorkOrder.PRIORITY_NORMAL)
    planned_start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    planned_hours = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    dependency = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='dependent_tasks')
    blocker = models.TextField(blank=True)
    completion_notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NOT_STARTED)
    completion_percent = models.PositiveSmallIntegerField(default=0)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'due_date', 'id']

    def clean(self):
        if self.completion_percent > 100:
            raise ValidationError({'completion_percent': 'Completion cannot exceed 100%.'})
        for field in ('assignee', 'contractor'):
            value = getattr(self, field, None)
            if value and value.company_id != self.work_order.company_id:
                raise ValidationError({field: 'Assignee must belong to the work order company.'})
        if self.site_package_id and self.site_package.work_order_id != self.work_order_id:
            raise ValidationError({'site_package': 'Task site package must belong to this work order.'})
        if self.dependency_id and self.dependency.work_order_id != self.work_order_id:
            raise ValidationError({'dependency': 'A task dependency must belong to this work order.'})
        if self.due_date and self.planned_start_date and self.due_date < self.planned_start_date:
            raise ValidationError({'due_date': 'Task due date cannot be before its planned start date.'})


class WorkOrderChange(models.Model):
    """A controlled variation to approved work-order scope, cost, date, or contractor."""
    STATUS_DRAFT = 'DRAFT'
    STATUS_SUBMITTED = 'SUBMITTED'
    STATUS_APPROVED = 'APPROVED'
    STATUS_REJECTED = 'REJECTED'
    STATUS_CHOICES = [(STATUS_DRAFT, 'Draft'), (STATUS_SUBMITTED, 'Submitted'), (STATUS_APPROVED, 'Approved'), (STATUS_REJECTED, 'Rejected')]

    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='changes')
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_work_order_changes')
    reason = models.TextField()
    proposed_scope = models.TextField(blank=True)
    proposed_due_date = models.DateField(null=True, blank=True)
    proposed_estimated_cost = models.DecimalField(max_digits=16, decimal_places=2, null=True, blank=True)
    proposed_contractor = models.ForeignKey('suppliers.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='proposed_work_order_changes')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_work_order_changes')
    review_notes = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def clean(self):
        if self.proposed_contractor_id and not self.proposed_contractor.is_contractor:
            raise ValidationError({'proposed_contractor': 'Select a registered contractor.'})
        if self.proposed_contractor_id and self.proposed_contractor.company_id != self.work_order.company_id:
            raise ValidationError({'proposed_contractor': 'Contractor must belong to the work order company.'})


class WorkOrderAttachment(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='work-orders/%Y/%m/')
    name = models.CharField(max_length=255, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='work_order_attachments')
    created_at = models.DateTimeField(auto_now_add=True)


class WorkOrderAuditLog(models.Model):
    work_order = models.ForeignKey(WorkOrder, on_delete=models.PROTECT, related_name='audit_logs')
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    action = models.CharField(max_length=100)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20, blank=True)
    message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def save(self, *args, **kwargs):
        if self.pk and WorkOrderAuditLog.objects.filter(pk=self.pk).exists():
            raise ValidationError('Work order audit logs are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Work order audit logs cannot be deleted.')
