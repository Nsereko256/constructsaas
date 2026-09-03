from django.db.models import Sum
from decimal import Decimal
from rest_framework import serializers
from django.db.models import Sum

from apps.procurement.models import PurchaseRequest, PurchaseRequestItem
from apps.finance.models import SupplierInvoice
from apps.api.upload_validation import validate_image_upload
from .models import WorkOrder, WorkOrderAttachment, WorkOrderAuditLog, WorkOrderChange, WorkOrderTask


class WorkOrderTaskSerializer(serializers.ModelSerializer):
    assignee_name = serializers.CharField(source='assignee.get_full_name', read_only=True)
    contractor_name = serializers.CharField(source='contractor.name', read_only=True)

    class Meta:
        model = WorkOrderTask
        fields = ['id', 'work_order', 'site_package', 'title', 'description', 'assignee', 'assignee_name', 'contractor', 'contractor_name', 'priority', 'planned_start_date', 'due_date', 'planned_hours', 'dependency', 'blocker', 'completion_notes', 'status', 'completion_percent', 'completed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'work_order', 'completed_at', 'created_at', 'updated_at']

    def validate(self, attrs):
        instance = self.instance
        work_order = getattr(instance, 'work_order', None)
        dependency = attrs.get('dependency', getattr(instance, 'dependency', None))
        if dependency and instance and dependency.pk == instance.pk:
            raise serializers.ValidationError({'dependency': 'A task cannot depend on itself.'})
        if dependency and work_order and dependency.work_order_id != work_order.id:
            raise serializers.ValidationError({'dependency': 'Dependency must belong to this work order.'})
        return attrs


class WorkOrderSiteSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_site_name = serializers.CharField(source='project_site.name', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    responsible_person_name = serializers.SerializerMethodField()
    contractor_name = serializers.CharField(source='contractor.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    tasks = WorkOrderTaskSerializer(many=True, read_only=True)
    material_cost = serializers.SerializerMethodField()
    invoice_cost = serializers.SerializerMethodField()
    total_actual_cost = serializers.SerializerMethodField()
    material_requests = serializers.SerializerMethodField()
    invoices = serializers.SerializerMethodField()
    task_progress_percent = serializers.SerializerMethodField()
    closeout_completion_percent = serializers.SerializerMethodField()
    committed_cost = serializers.SerializerMethodField()
    forecast_cost = serializers.SerializerMethodField()
    remaining_estimated_budget = serializers.SerializerMethodField()
    cost_variance = serializers.SerializerMethodField()

    class Meta:
        from .models import WorkOrderSite
        model = WorkOrderSite
        fields = ['id', 'work_order', 'project', 'project_name', 'project_site', 'project_site_name', 'site', 'site_name', 'title', 'description', 'responsible_person', 'responsible_person_name', 'contractor', 'contractor_name', 'estimated_start_date', 'due_date', 'revised_due_date', 'actual_completion_date', 'estimated_cost', 'actual_cost', 'material_cost', 'invoice_cost', 'total_actual_cost', 'committed_cost', 'forecast_cost', 'remaining_estimated_budget', 'cost_variance', 'progress_percent', 'task_progress_percent', 'closeout_completion_percent', 'progress_notes', 'progress_updated_at', 'materials_reconciled', 'quality_checked', 'safety_checked', 'client_signed_off', 'closeout_notes', 'hold_owner', 'hold_recovery_date', 'status', 'status_display', 'notes', 'tasks', 'material_requests', 'invoices', 'created_at', 'updated_at']
        read_only_fields = ['id', 'work_order', 'material_cost', 'invoice_cost', 'total_actual_cost', 'created_at', 'updated_at']
    def get_responsible_person_name(self, obj): return (obj.responsible_person.get_full_name() or obj.responsible_person.username) if obj.responsible_person else ''
    def get_material_cost(self, obj): return str(obj.stock_movements.aggregate(total=Sum('total_cost'))['total'] or 0)
    def get_invoice_cost(self, obj): return str(obj.supplier_invoices.filter(status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID]).aggregate(total=Sum('total_amount'))['total'] or 0)
    def get_total_actual_cost(self, obj): return str((obj.stock_movements.aggregate(total=Sum('total_cost'))['total'] or 0) + (obj.supplier_invoices.filter(status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID]).aggregate(total=Sum('total_amount'))['total'] or 0))
    def get_task_progress_percent(self, obj):
        tasks = list(obj.tasks.all())
        return round(sum(task.completion_percent for task in tasks) / len(tasks)) if tasks else 0
    def get_closeout_completion_percent(self, obj):
        checks = [obj.materials_reconciled, obj.quality_checked, obj.safety_checked, obj.client_signed_off]
        return round(sum(1 for checked in checks if checked) / len(checks) * 100)
    def get_committed_cost(self, obj):
        from apps.procurement.models import PurchaseOrderItem
        return str(sum((item.quantity * item.unit_price for item in PurchaseOrderItem.objects.filter(purchase_order__purchase_request__work_order_site=obj).exclude(purchase_order__status='CANCELLED')), Decimal('0')))
    def get_forecast_cost(self, obj):
        return str(max(Decimal(self.get_total_actual_cost(obj)), Decimal(self.get_committed_cost(obj))))
    def get_remaining_estimated_budget(self, obj):
        return str(Decimal(str(obj.estimated_cost or 0)) - Decimal(self.get_forecast_cost(obj)))
    def get_cost_variance(self, obj):
        return str(Decimal(self.get_forecast_cost(obj)) - Decimal(str(obj.estimated_cost or 0)))
    def get_material_requests(self, obj): return list(obj.purchase_requests.values('id', 'number', 'status', 'title'))
    def get_invoices(self, obj): return list(obj.supplier_invoices.values('id', 'internal_number', 'invoice_number', 'supplier__name', 'total_amount', 'currency', 'status'))

    def validate(self, attrs):
        contractor = attrs.get('contractor', getattr(self.instance, 'contractor', None))
        if contractor and not contractor.is_contractor:
            raise serializers.ValidationError({'contractor': 'Select a supplier registered as a contractor.'})
        return attrs


class WorkOrderAttachmentSerializer(serializers.ModelSerializer):
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    class Meta:
        model = WorkOrderAttachment
        fields = ['id', 'file', 'name', 'uploaded_by', 'uploaded_by_name', 'created_at']
        read_only_fields = ['id', 'uploaded_by', 'uploaded_by_name', 'created_at']

    def validate_file(self, value):
        return validate_image_upload(value)


class WorkOrderAuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    class Meta:
        model = WorkOrderAuditLog
        fields = ['id', 'actor', 'actor_name', 'action', 'from_status', 'to_status', 'message', 'metadata', 'created_at']
        read_only_fields = fields
    def get_actor_name(self, obj):
        return obj.actor.get_full_name() or obj.actor.username if obj.actor else 'System'


class WorkOrderChangeSerializer(serializers.ModelSerializer):
    requested_by_name = serializers.SerializerMethodField()
    reviewed_by_name = serializers.SerializerMethodField()
    proposed_contractor_name = serializers.CharField(source='proposed_contractor.name', read_only=True)

    class Meta:
        model = WorkOrderChange
        fields = ['id', 'work_order', 'requested_by', 'requested_by_name', 'reason', 'proposed_scope', 'proposed_due_date', 'proposed_estimated_cost', 'proposed_contractor', 'proposed_contractor_name', 'status', 'reviewed_by', 'reviewed_by_name', 'review_notes', 'reviewed_at', 'created_at', 'updated_at']
        read_only_fields = ['id', 'work_order', 'requested_by', 'requested_by_name', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at', 'updated_at']

    def _name(self, user):
        return (user.get_full_name() or user.username) if user else ''

    def get_requested_by_name(self, obj): return self._name(obj.requested_by)
    def get_reviewed_by_name(self, obj): return self._name(obj.reviewed_by)


class WorkOrderSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    requester_name = serializers.SerializerMethodField()
    responsible_person_name = serializers.SerializerMethodField()
    contractor_name = serializers.CharField(source='contractor.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    tasks = WorkOrderTaskSerializer(many=True, read_only=True)
    site_packages = WorkOrderSiteSerializer(many=True, read_only=True)
    attachments = WorkOrderAttachmentSerializer(many=True, read_only=True)
    audit_logs = WorkOrderAuditLogSerializer(many=True, read_only=True)
    material_requests = serializers.SerializerMethodField()
    actual_material_cost = serializers.SerializerMethodField()
    actual_cost = serializers.SerializerMethodField()
    committed_cost = serializers.SerializerMethodField()
    forecast_cost = serializers.SerializerMethodField()
    remaining_approved_budget = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    invoices = serializers.SerializerMethodField()
    changes = WorkOrderChangeSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = ['id', 'number', 'company', 'project', 'project_name', 'site', 'site_name', 'title', 'description', 'work_category', 'priority', 'priority_display', 'requester', 'requester_name', 'responsible_person', 'responsible_person_name', 'responsible_team', 'contractor', 'contractor_name', 'estimated_start_date', 'due_date', 'revised_due_date', 'actual_completion_date', 'estimated_cost', 'approved_cost', 'actual_cost', 'actual_material_cost', 'committed_cost', 'forecast_cost', 'remaining_approved_budget', 'scope_version', 'assignment_status', 'assignment_response', 'assignment_responded_at', 'finance_reviewed_by', 'finance_reviewed_at', 'finance_review_notes', 'is_emergency', 'emergency_reason', 'emergency_spend_cap', 'status', 'status_display', 'notes', 'rejection_reason', 'hold_reason', 'hold_owner', 'hold_recovery_date', 'approved_by', 'verified_by', 'is_overdue', 'material_requests', 'invoices', 'changes', 'site_packages', 'tasks', 'attachments', 'audit_logs', 'created_at', 'updated_at']
        read_only_fields = ['id', 'number', 'company', 'requester', 'approved_by', 'verified_by', 'actual_cost', 'actual_material_cost', 'actual_completion_date', 'scope_version', 'assignment_status', 'assignment_response', 'assignment_responded_at', 'finance_reviewed_by', 'finance_reviewed_at', 'finance_review_notes', 'approved_cost', 'created_at', 'updated_at']

    def name(self, user):
        return (user.get_full_name() or user.username) if user else ''
    def get_requester_name(self, obj): return self.name(obj.requester)
    def get_responsible_person_name(self, obj): return self.name(obj.responsible_person)
    def get_material_requests(self, obj):
        return list(obj.purchase_requests.values('id', 'number', 'status', 'title'))
    def get_invoices(self, obj):
        return list(obj.supplier_invoices.values('id', 'internal_number', 'invoice_number', 'supplier__name', 'total_amount', 'currency', 'status'))
    def get_actual_material_cost(self, obj):
        direct = obj.stock_movements.aggregate(total=Sum('total_cost'))['total'] or 0
        site_cost = obj.site_packages.aggregate(total=Sum('stock_movements__total_cost'))['total'] or 0
        return str(direct + site_cost)
    def get_actual_cost(self, obj):
        material_cost = obj.stock_movements.aggregate(total=Sum('total_cost'))['total'] or 0
        site_material_cost = obj.site_packages.aggregate(total=Sum('stock_movements__total_cost'))['total'] or 0
        service_cost = obj.supplier_invoices.filter(
            status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID],
        ).aggregate(total=Sum('total_amount'))['total'] or 0
        site_service_cost = obj.site_packages.filter(supplier_invoices__status__in=[SupplierInvoice.STATUS_POSTED, SupplierInvoice.STATUS_PARTIALLY_PAID, SupplierInvoice.STATUS_PAID]).aggregate(total=Sum('supplier_invoices__total_amount'))['total'] or 0
        return str(material_cost + site_material_cost + service_cost + site_service_cost)
    def get_committed_cost(self, obj):
        from apps.procurement.models import PurchaseOrderItem
        total = sum((item.quantity * item.unit_price for item in PurchaseOrderItem.objects.filter(purchase_order__purchase_request__work_order=obj).exclude(purchase_order__status='CANCELLED')), Decimal('0'))
        return str(total)
    def get_forecast_cost(self, obj):
        actual = Decimal(self.get_actual_cost(obj))
        committed = Decimal(self.get_committed_cost(obj))
        return str(max(actual, committed))
    def get_remaining_approved_budget(self, obj):
        approved = obj.approved_cost or obj.estimated_cost
        return str(approved - Decimal(self.get_forecast_cost(obj)))
    def get_is_overdue(self, obj):
        from django.utils import timezone
        return bool(obj.due_date and obj.due_date < timezone.localdate() and obj.status not in {WorkOrder.STATUS_CLOSED, WorkOrder.STATUS_CANCELLED})

    def validate(self, attrs):
        request = self.context['request']
        project = attrs.get('project', getattr(self.instance, 'project', None))
        if project and project.company_id != request.user.company_id:
            raise serializers.ValidationError({'project': 'Project must belong to your company.'})
        if not project:
            raise serializers.ValidationError({'project': 'Select the project that owns this work order.'})
        contractor = attrs.get('contractor', getattr(self.instance, 'contractor', None))
        if contractor and not contractor.is_contractor:
            raise serializers.ValidationError({'contractor': 'Select a supplier registered as a contractor.'})
        is_emergency = attrs.get('is_emergency', getattr(self.instance, 'is_emergency', False))
        emergency_reason = attrs.get('emergency_reason', getattr(self.instance, 'emergency_reason', ''))
        emergency_cap = attrs.get('emergency_spend_cap', getattr(self.instance, 'emergency_spend_cap', 0))
        if is_emergency and not str(emergency_reason).strip():
            raise serializers.ValidationError({'emergency_reason': 'Explain why emergency work is required.'})
        if is_emergency and Decimal(str(emergency_cap or 0)) <= 0:
            raise serializers.ValidationError({'emergency_spend_cap': 'Set a positive emergency spending cap.'})
        return attrs


class WorkOrderTransitionSerializer(serializers.Serializer):
    comments = serializers.CharField(required=False, allow_blank=True)


class WorkOrderMaterialRequestSerializer(serializers.Serializer):
    site_package = serializers.IntegerField(min_value=1, required=False)
    title = serializers.CharField(max_length=255, required=False)
    priority = serializers.ChoiceField(choices=PurchaseRequest.PRIORITY_CHOICES, default=PurchaseRequest.PRIORITY_NORMAL)
    justification = serializers.CharField(required=False, allow_blank=True)
    items = serializers.ListField(child=serializers.DictField(), min_length=1)
    def validate_items(self, items):
        cleaned = []
        for item in items:
            if not item.get('material') or not item.get('quantity'):
                raise serializers.ValidationError('Each item requires material and quantity.')
            cleaned.append(item)
        return cleaned
