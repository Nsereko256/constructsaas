from decimal import Decimal

from django.contrib.auth.password_validation import validate_password
from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone
from rest_framework import serializers

from apps.accounts.models import Company, User
from apps.materials.models import Category, Material
from apps.notifications.models import Notification
from apps.procurement.models import (
    GoodsReceivedNote,
    GoodsReceivedNoteItem,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SupplierClaim,
)
from apps.projects.access import accessible_projects
from apps.projects.models import ApprovalDelegation, ChatMessage, ChatRoom, Project, ProjectGoal, ProjectSite, ProjectStaffAssignment
from apps.suppliers.models import Supplier
from apps.warehouse.models import BinLocation, SiteTransfer, StockMovement, Warehouse
from apps.warehouse.valuation_services import available_for_project_issue, valuation_state
from apps.finance.models import BudgetApproval
from apps.finance import budget_services
from apps.finance.services import ensure_budget_clearance


class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'slug', 'is_active', 'created_at', 'updated_at']
        read_only_fields = fields


class CompanyRegistrationSerializer(serializers.Serializer):
    company_name = serializers.CharField(max_length=255)
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_company_name(self, value):
        if Company.objects.filter(name__iexact=value.strip()).exists():
            raise serializers.ValidationError('A company with this name is already registered.')
        return value.strip()

    def validate_username(self, value):
        if User.objects.filter(username__iexact=value.strip()).exists():
            raise serializers.ValidationError('This username is already in use.')
        return value.strip()

    def validate(self, attrs):
        if attrs['password'] != attrs['password_confirm']:
            raise serializers.ValidationError({'password_confirm': 'Passwords do not match.'})
        validate_password(attrs['password'])
        return attrs

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')
        company = Company.objects.create(name=validated_data.pop('company_name'))
        return User.objects.create_user(
            company=company,
            role=User.ROLE_ADMIN,
            password=password,
            **validated_data,
        )


class WorkflowBadgesSerializer(serializers.Serializer):
    requests = serializers.IntegerField(min_value=0, read_only=True)
    purchase_orders = serializers.IntegerField(min_value=0, read_only=True)
    deliveries = serializers.IntegerField(min_value=0, read_only=True)
    inventory = serializers.IntegerField(min_value=0, read_only=True)
    budgets = serializers.IntegerField(min_value=0, read_only=True)
    supplier_invoices = serializers.IntegerField(min_value=0, read_only=True)
    payments = serializers.IntegerField(min_value=0, read_only=True)
    expenses = serializers.IntegerField(min_value=0, read_only=True)
    ledger = serializers.IntegerField(min_value=0, read_only=True)
    supplier_claims = serializers.IntegerField(min_value=0, read_only=True)


class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    company_name = serializers.CharField(source='company.name', read_only=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=False)

    class Meta:
        model = User
        fields = ['id', 'username', 'first_name', 'last_name', 'email', 'phone', 'role', 'role_display', 'company', 'company_name', 'is_active', 'password']
        read_only_fields = ['id', 'company', 'company_name', 'role_display']

    def validate_role(self, role):
        valid_roles = {choice[0] for choice in User.ROLE_CHOICES}
        if role not in valid_roles:
            raise serializers.ValidationError('Select a valid role.')
        return role

    def create(self, validated_data):
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        password = validated_data.pop('password', None)
        if not password:
            raise serializers.ValidationError({'password': 'Password is required when creating a user.'})
        return User.objects.create_user(company=company, password=password, **validated_data)

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_password(self, value):
        validate_password(value)
        return value


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'company', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'company', 'created_at']


class MaterialSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source='category.name', read_only=True)
    unit_display = serializers.CharField(source='get_unit_display', read_only=True)
    current_stock = serializers.SerializerMethodField()
    stock_value = serializers.SerializerMethodField()
    is_low_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Material
        fields = [
            'id',
            'company',
            'category',
            'category_name',
            'name',
            'code',
            'unit',
            'unit_display',
            'unit_price',
            'min_stock_level',
            'current_stock',
            'stock_value',
            'is_low_stock',
            'description',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'company', 'category_name', 'unit_display', 'current_stock', 'stock_value', 'is_low_stock', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['category'].queryset = Category.objects.filter(company=company).order_by('name')

    def get_current_stock(self, obj) -> Decimal:
        if hasattr(obj, 'current_stock_value'):
            return obj.current_stock_value
        return obj.current_stock

    def get_stock_value(self, obj) -> Decimal:
        if hasattr(obj, 'stock_value'):
            return obj.stock_value
        return self.get_current_stock(obj) * obj.unit_price

    def validate_category(self, category):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if category.company_id != company_id:
            raise serializers.ValidationError('Category must belong to your company.')
        return category


class ProjectSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    manager_name = serializers.SerializerMethodField()
    site_engineer_names = serializers.SerializerMethodField()
    total_material_cost = serializers.SerializerMethodField()
    remaining_budget = serializers.SerializerMethodField()
    budget_source = serializers.SerializerMethodField()
    budget_revised = serializers.SerializerMethodField()
    budget_commitments = serializers.SerializerMethodField()
    budget_actual_expenditure = serializers.SerializerMethodField()
    budget_available_balance = serializers.SerializerMethodField()
    site_total = serializers.SerializerMethodField()
    closed_site_total = serializers.SerializerMethodField()
    site_closure_percent = serializers.SerializerMethodField()
    goal_total = serializers.SerializerMethodField()
    goal_completion_percent = serializers.SerializerMethodField()
    progress_percent = serializers.SerializerMethodField()
    progress_basis = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'id',
            'company',
            'name',
            'code',
            'client',
            'location',
            'description',
            'budget',
            'status',
            'status_display',
            'manager',
            'manager_name',
            'site_engineers',
            'site_engineer_names',
            'total_material_cost',
            'remaining_budget',
            'budget_source',
            'budget_revised',
            'budget_commitments',
            'budget_actual_expenditure',
            'budget_available_balance',
            'site_total',
            'closed_site_total',
            'site_closure_percent',
            'goal_total',
            'goal_completion_percent',
            'progress_percent',
            'progress_basis',
            'start_date',
            'end_date',
            'is_active',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'company', 'status_display', 'manager_name', 'site_engineer_names', 'total_material_cost', 'remaining_budget', 'budget_source', 'budget_revised', 'budget_commitments', 'budget_actual_expenditure', 'budget_available_balance', 'site_total', 'closed_site_total', 'site_closure_percent', 'goal_total', 'goal_completion_percent', 'progress_percent', 'progress_basis', 'created_at', 'updated_at']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['manager'].queryset = User.objects.filter(
                company=company,
                role=User.ROLE_PROJECT_MANAGER,
                is_active=True,
            ).order_by('username')
            self.fields['site_engineers'].child_relation.queryset = User.objects.filter(
                company=company,
                role=User.ROLE_SITE_ENGINEER,
                is_active=True,
            ).order_by('username')

    def get_manager_name(self, obj) -> str:
        if not obj.manager:
            return ''
        return obj.manager.get_full_name() or obj.manager.username

    def get_site_engineer_names(self, obj) -> list[str]:
        return [
            engineer.get_full_name() or engineer.username
            for engineer in obj.site_engineers.all()
        ]

    def get_total_material_cost(self, obj) -> Decimal:
        return getattr(obj, 'total_material_cost', 0)

    def get_remaining_budget(self, obj) -> Decimal:
        return self._budget_snapshot(obj)['available_balance']

    def _budget_snapshot(self, obj):
        return budget_services.project_budget_snapshot(
            obj,
            legacy_actual=self.get_total_material_cost(obj),
        )

    def get_budget_source(self, obj) -> str:
        return self._budget_snapshot(obj)['source']

    def get_budget_revised(self, obj) -> Decimal:
        return self._budget_snapshot(obj)['revised_budget']

    def get_budget_commitments(self, obj) -> Decimal:
        return self._budget_snapshot(obj)['open_commitments']

    def get_budget_actual_expenditure(self, obj) -> Decimal:
        return self._budget_snapshot(obj)['actual_expenditure']

    def get_budget_available_balance(self, obj) -> Decimal:
        return self._budget_snapshot(obj)['available_balance']

    def _sites(self, obj):
        return [site for site in obj.sites.all() if site.is_active]

    def _goals(self, obj):
        return list(obj.goals.all())

    def get_site_total(self, obj):
        return len(self._sites(obj))

    def get_closed_site_total(self, obj):
        return sum(1 for site in self._sites(obj) if site.status == ProjectSite.STATUS_COMPLETED)

    def get_site_closure_percent(self, obj):
        sites = self._sites(obj)
        return round((sum(1 for site in sites if site.status == ProjectSite.STATUS_COMPLETED) / len(sites) * 100) if sites else 0, 1)

    def get_goal_total(self, obj):
        return len(self._goals(obj))

    def get_goal_completion_percent(self, obj):
        goals = self._goals(obj)
        if not goals:
            return 0
        total_weight = sum(goal.weight for goal in goals)
        return round(float(sum(goal.weight * goal.completion_percent for goal in goals) / total_weight), 1) if total_weight else 0

    def get_progress_basis(self, obj):
        return 'goals' if self._goals(obj) else 'sites'

    def get_progress_percent(self, obj):
        return self.get_goal_completion_percent(obj) if self._goals(obj) else self.get_site_closure_percent(obj)


class ProjectSiteSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    manager_name = serializers.SerializerMethodField()
    engineer_names = serializers.SerializerMethodField()

    class Meta:
        model = ProjectSite
        fields = ['id', 'project', 'project_name', 'name', 'code', 'location', 'description', 'manager', 'manager_name', 'site_engineers', 'engineer_names', 'status', 'closed_at', 'closed_by', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project_name', 'manager_name', 'engineer_names', 'closed_at', 'closed_by', 'created_at', 'updated_at']

    def get_manager_name(self, obj):
        return (obj.manager.get_full_name() or obj.manager.username) if obj.manager else ''

    def get_engineer_names(self, obj):
        return [person.get_full_name() or person.username for person in obj.site_engineers.all()]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = getattr(getattr(self.context.get('request'), 'user', None), 'company', None)
        if company:
            self.fields['project'].queryset = Project.objects.filter(company=company, is_active=True)
            users = User.objects.filter(company=company, is_active=True)
            self.fields['manager'].queryset = users.filter(role=User.ROLE_PROJECT_MANAGER)
            self.fields['site_engineers'].child_relation.queryset = users.filter(role=User.ROLE_SITE_ENGINEER)

    def validate_manager(self, manager):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if manager and manager.company_id != company_id:
            raise serializers.ValidationError('Manager must belong to your company.')
        if manager and manager.role != User.ROLE_PROJECT_MANAGER:
            raise serializers.ValidationError('Manager must have the Project Manager role.')
        return manager

    def validate_site_engineers(self, site_engineers):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        for engineer in site_engineers:
            if engineer.company_id != company_id:
                raise serializers.ValidationError('Every engineer must belong to your company.')
            if engineer.role != User.ROLE_SITE_ENGINEER:
                raise serializers.ValidationError('Every assigned user must have the Site Engineer role.')
        return site_engineers

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if not user:
            return attrs
        if user.role != User.ROLE_ADMIN and 'manager' in attrs:
            raise serializers.ValidationError({'manager': 'Only admins can assign or change the project manager.'})
        if user.role == User.ROLE_PROJECT_MANAGER and self.instance:
            if self.instance.manager_id != user.id:
                raise serializers.ValidationError('You can only edit projects assigned to you.')
        return attrs


class ProjectGoalSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    site_name = serializers.CharField(source='site.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    completed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectGoal
        fields = ['id', 'project', 'project_name', 'site', 'site_name', 'title', 'description', 'weight', 'completion_percent', 'status', 'status_display', 'due_date', 'completed_at', 'completed_by', 'completed_by_name', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project_name', 'site_name', 'status_display', 'completed_at', 'completed_by', 'completed_by_name', 'created_at', 'updated_at']

    def get_completed_by_name(self, obj):
        return (obj.completed_by.get_full_name() or obj.completed_by.username) if obj.completed_by else ''

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        company = getattr(getattr(self.context.get('request'), 'user', None), 'company', None)
        if company:
            self.fields['project'].queryset = Project.objects.filter(company=company, is_active=True)
            self.fields['site'].queryset = ProjectSite.objects.filter(project__company=company, is_active=True)

    def validate(self, attrs):
        project = attrs.get('project', getattr(self.instance, 'project', None))
        site = attrs.get('site', getattr(self.instance, 'site', None))
        if site and project and site.project_id != project.id:
            raise serializers.ValidationError({'site': 'The selected site must belong to this project.'})
        return attrs

    def _apply_completion(self, validated_data):
        status = validated_data.get('status')
        if validated_data.get('completion_percent') == 100:
            validated_data['status'] = ProjectGoal.STATUS_COMPLETED
            status = ProjectGoal.STATUS_COMPLETED
        if status == ProjectGoal.STATUS_COMPLETED:
            validated_data['completion_percent'] = 100
            validated_data['completed_at'] = timezone.now()
            validated_data['completed_by'] = self.context['request'].user
        elif status and self.instance and self.instance.status == ProjectGoal.STATUS_COMPLETED:
            validated_data['completed_at'] = None
            validated_data['completed_by'] = None
        return validated_data

    def create(self, validated_data):
        return super().create(self._apply_completion(validated_data))

    def update(self, instance, validated_data):
        return super().update(instance, self._apply_completion(validated_data))


class ProjectStaffAssignmentSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    username = serializers.CharField(source='user.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ProjectStaffAssignment
        fields = ['id', 'project', 'project_name', 'user', 'username', 'user_name', 'role', 'is_primary_contact', 'allocation_percent', 'start_date', 'end_date', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'project_name', 'username', 'user_name', 'created_at', 'updated_at']


class ApprovalDelegationSerializer(serializers.ModelSerializer):
    delegator_name = serializers.CharField(source='delegator.username', read_only=True)
    delegate_name = serializers.CharField(source='delegate.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ApprovalDelegation
        fields = ['id', 'delegator', 'delegator_name', 'delegate', 'delegate_name', 'project', 'project_name', 'effective_from', 'effective_to', 'reason', 'is_active', 'created_at', 'revoked_at']
        read_only_fields = ['id', 'delegator', 'delegator_name', 'delegate_name', 'project_name', 'created_at', 'revoked_at']


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'company', 'name', 'contact_person', 'phone', 'email', 'address', 'rating', 'lead_time_days', 'is_preferred', 'is_contractor', 'contractor_specialty', 'contractor_mobilisation_days', 'contractor_rate_notes', 'contractor_insurance_expiry_date', 'contractor_safety_clearance_expiry_date', 'compliance_reference', 'compliance_expiry_date', 'notes', 'is_active', 'created_at', 'updated_at']
        read_only_fields = ['id', 'company', 'created_at', 'updated_at']


class StockMovementSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    movement_type_display = serializers.CharField(source='get_movement_type_display', read_only=True)
    source_display = serializers.CharField(source='get_source_display', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    purchase_order_number = serializers.CharField(source='purchase_order.number', read_only=True)
    purchase_request_number = serializers.CharField(source='purchase_request.number', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id',
            'company',
            'material',
            'material_name',
            'warehouse',
            'warehouse_name',
            'project',
            'project_name',
            'work_order',
            'movement_type',
            'movement_type_display',
            'source',
            'source_display',
            'transaction_type',
            'transaction_type_display',
            'quantity',
            'unit_price',
            'unit_cost',
            'valuation_rate',
            'total_cost',
            'quantity_effect',
            'value_effect',
            'date',
            'notes',
            'created_by',
            'created_by_username',
            'purchase_order',
            'purchase_order_number',
            'purchase_request',
            'purchase_request_number',
            'goods_received_note_item',
            'original_movement',
            'authorization_reason',
            'authorized_by',
            'created_at',
        ]
        read_only_fields = [
            'id',
            'company',
            'material_name',
            'warehouse_name',
            'project_name',
            'work_order',
            'movement_type_display',
            'source_display',
            'transaction_type',
            'transaction_type_display',
            'unit_cost',
            'valuation_rate',
            'total_cost',
            'quantity_effect',
            'value_effect',
            'created_by',
            'created_by_username',
            'purchase_order_number',
            'purchase_request',
            'purchase_request_number',
            'goods_received_note_item',
            'original_movement',
            'authorization_reason',
            'authorized_by',
            'created_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['warehouse'].required = False
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['material'].queryset = company.materials.filter(is_active=True).order_by('name')
            self.fields['project'].queryset = company.projects.filter(is_active=True).order_by('name')
            self.fields['purchase_order'].queryset = company.purchase_orders.order_by('-created_at')
            self.fields['warehouse'].queryset = company.warehouses.filter(is_active=True).order_by('name')

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        material = attrs.get('material') or getattr(self.instance, 'material', None)
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        purchase_order = attrs.get('purchase_order') or getattr(self.instance, 'purchase_order', None)
        warehouse = attrs.get('warehouse') or getattr(self.instance, 'warehouse', None)
        quantity = attrs.get('quantity') or getattr(self.instance, 'quantity', None)

        if material and material.company_id != company_id:
            raise serializers.ValidationError({'material': 'Selected material must belong to your company.'})
        if project and project.company_id != company_id:
            raise serializers.ValidationError({'project': 'Selected project must belong to your company.'})
        if purchase_order and purchase_order.company_id != company_id:
            raise serializers.ValidationError({'purchase_order': 'Selected purchase order must belong to your company.'})
        if warehouse and warehouse.company_id != company_id:
            raise serializers.ValidationError({'warehouse': 'Selected warehouse must belong to your company.'})
        if quantity is not None and quantity <= 0:
            raise serializers.ValidationError({'quantity': 'Quantity must be greater than zero.'})
        movement_type = attrs.get('movement_type') or getattr(self.instance, 'movement_type', None)
        source = attrs.get('source') or getattr(self.instance, 'source', None)
        if movement_type in {StockMovement.MOVEMENT_OUT, StockMovement.MOVEMENT_ADJUSTMENT_OUT}:
            raise serializers.ValidationError({
                'movement_type': (
                    'Stock reductions require a finance-approved purchase request and must be completed '
                    'through the warehouse stock-issue workflow.'
                ),
            })
        if source == StockMovement.SOURCE_SUPPLIER:
            raise serializers.ValidationError({
                'source': (
                    'Purchased stock must be received through the finance-approved purchase-order '
                    'and goods-received-note workflow.'
                ),
            })
        return attrs


class WarehouseSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_site_name = serializers.CharField(source='project_site.name', read_only=True)
    class Meta:
        model = Warehouse
        fields = [
            'id', 'company', 'name', 'code', 'location', 'project', 'project_name', 'project_site', 'project_site_name', 'is_default', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'company', 'project_name', 'project_site_name', 'created_at', 'updated_at']


class BinLocationSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = BinLocation
        fields = ['id', 'warehouse', 'warehouse_name', 'code', 'description', 'is_active']
        read_only_fields = ['id', 'warehouse_name']


class InventoryActionSerializer(serializers.Serializer):
    material = serializers.IntegerField(min_value=1)
    warehouse = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    date = serializers.DateField(default=timezone.localdate)
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False)


class OpeningBalanceRequestSerializer(InventoryActionSerializer):
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0'))


class ValuedReceiptRequestSerializer(serializers.Serializer):
    goods_received_note_item = serializers.IntegerField(min_value=1)
    warehouse = serializers.IntegerField(min_value=1, required=False)


class ProjectIssueRequestSerializer(InventoryActionSerializer):
    project = serializers.IntegerField(min_value=1)
    purchase_request = serializers.IntegerField(min_value=1)
    work_order = serializers.IntegerField(min_value=1, required=False)
    work_order_site = serializers.IntegerField(min_value=1, required=False)


class ProjectReturnRequestSerializer(serializers.Serializer):
    original_issue = serializers.IntegerField(min_value=1)
    warehouse = serializers.IntegerField(min_value=1, required=False)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=2, min_value=Decimal('0.01'))
    date = serializers.DateField(default=timezone.localdate)
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False)


class SiteTransferRequestSerializer(InventoryActionSerializer):
    project = serializers.IntegerField(min_value=1)


class SiteReturnRequestSerializer(InventoryActionSerializer):
    project = serializers.IntegerField(min_value=1)
    warehouse = serializers.IntegerField(min_value=1)


class SiteTransferSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    material_name = serializers.CharField(source='material.name', read_only=True)
    source_warehouse_name = serializers.CharField(source='source_warehouse.name', read_only=True)
    destination_store_name = serializers.CharField(source='destination_store.name', read_only=True)

    class Meta:
        model = SiteTransfer
        fields = ['id', 'project', 'project_name', 'material', 'material_name', 'source_warehouse', 'source_warehouse_name', 'destination_store', 'destination_store_name', 'quantity', 'status', 'reason', 'dispatched_by', 'dispatched_at', 'acknowledged_by', 'acknowledged_at', 'outbound_movement', 'inbound_movement']
        read_only_fields = fields


class SupplierReturnRequestSerializer(InventoryActionSerializer):
    original_receipt = serializers.IntegerField(min_value=1, required=False)


class ValuationAdjustmentRequestSerializer(serializers.Serializer):
    material = serializers.IntegerField(min_value=1)
    warehouse = serializers.IntegerField(min_value=1, required=False)
    new_unit_cost = serializers.DecimalField(max_digits=18, decimal_places=6, min_value=Decimal('0'))
    date = serializers.DateField(default=timezone.localdate)
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False)


class InventoryValuationSerializer(serializers.Serializer):
    material = serializers.IntegerField()
    material_code = serializers.CharField()
    material_name = serializers.CharField()
    warehouse = serializers.IntegerField()
    warehouse_code = serializers.CharField()
    warehouse_name = serializers.CharField()
    current_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    current_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    average_rate = serializers.DecimalField(max_digits=18, decimal_places=6)


class ProjectMaterialCostSerializer(serializers.Serializer):
    project = serializers.IntegerField()
    project_code = serializers.CharField()
    project_name = serializers.CharField()
    material = serializers.IntegerField()
    material_code = serializers.CharField()
    material_name = serializers.CharField()
    issued_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    returned_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    net_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    net_cost = serializers.DecimalField(max_digits=18, decimal_places=2)


class ValuationReconciliationSerializer(serializers.Serializer):
    material = serializers.IntegerField()
    warehouse = serializers.IntegerField()
    ledger_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    movement_quantity = serializers.DecimalField(max_digits=18, decimal_places=2)
    quantity_variance = serializers.DecimalField(max_digits=18, decimal_places=2)
    ledger_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    movement_value = serializers.DecimalField(max_digits=18, decimal_places=2)
    value_variance = serializers.DecimalField(max_digits=18, decimal_places=2)
    status = serializers.CharField()


class PurchaseRequestItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_code = serializers.CharField(source='material.code', read_only=True)
    unit = serializers.CharField(source='material.unit', read_only=True)
    unit_price = serializers.DecimalField(source='material.unit_price', max_digits=12, decimal_places=2, read_only=True)
    current_stock = serializers.SerializerMethodField()
    warehouse_available = serializers.SerializerMethodField()
    issued_quantity = serializers.SerializerMethodField()
    outstanding_quantity = serializers.SerializerMethodField()
    estimated_cost = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequestItem
        fields = [
            'id',
            'material',
            'material_name',
            'material_code',
            'unit',
            'unit_price',
            'current_stock',
            'warehouse_available',
            'quantity',
            'issued_quantity',
            'outstanding_quantity',
            'estimated_cost',
            'notes',
        ]
        read_only_fields = ['id', 'material_name', 'material_code', 'unit', 'unit_price', 'current_stock', 'warehouse_available', 'issued_quantity', 'outstanding_quantity', 'estimated_cost']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['material'].queryset = company.materials.filter(is_active=True).order_by('name')

    def get_current_stock(self, obj) -> Decimal:
        return obj.material.current_stock

    def get_warehouse_available(self, obj) -> Decimal:
        """Stock that can actually be issued from the company's default warehouse.

        `current_stock` remains the company-wide material balance for reporting.  A
        stock issue, however, always leaves the default warehouse, so Procurement
        must see that location's balance before asking the Storekeeper to issue it.
        """
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is None:
            return Decimal('0.00')
        warehouse = self.context.get('_purchase_request_default_warehouse')
        if warehouse is None:
            warehouse = Warehouse.objects.filter(
                company=company,
                is_default=True,
                is_active=True,
            ).first()
            self.context['_purchase_request_default_warehouse'] = warehouse
        if warehouse is None:
            return Decimal('0.00')
        if obj.purchase_request.project_id:
            return available_for_project_issue(
                company=company,
                material=obj.material,
                warehouse=warehouse,
                project=obj.purchase_request.project,
            )
        return max(
            valuation_state(company=company, material=obj.material, warehouse=warehouse)['quantity'],
            Decimal('0.00'),
        )

    def get_estimated_cost(self, obj) -> Decimal:
        return obj.quantity * obj.material.unit_price

    def get_issued_quantity(self, obj) -> Decimal:
        return sum((movement.quantity for movement in obj.stock_movements.filter(
            movement_type=StockMovement.MOVEMENT_OUT,
            transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
        )), Decimal('0.00'))

    def get_outstanding_quantity(self, obj) -> Decimal:
        return max(obj.quantity - self.get_issued_quantity(obj), Decimal('0.00'))

    def validate_material(self, material):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if material.company_id != company_id:
            raise serializers.ValidationError('Material must belong to your company.')
        return material


class PurchaseRequestSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    requested_by_username = serializers.CharField(source='requested_by.username', read_only=True)
    technical_approved_by_name = serializers.SerializerMethodField()
    manager_approved_by_name = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    items = PurchaseRequestItemSerializer(many=True)
    total_estimated_cost = serializers.SerializerMethodField()
    has_purchase_order = serializers.SerializerMethodField()
    can_request_stock_issue = serializers.SerializerMethodField()
    can_approve_stock_issue = serializers.SerializerMethodField()
    next_action_message = serializers.SerializerMethodField()
    can_fulfill_from_stock = serializers.SerializerMethodField()
    can_issue_from_stock = serializers.SerializerMethodField()
    can_create_purchase_order = serializers.SerializerMethodField()
    stock_issue_blockers = serializers.SerializerMethodField()
    finance_approval_id = serializers.SerializerMethodField()
    finance_status = serializers.SerializerMethodField()
    finance_status_display = serializers.SerializerMethodField()
    finance_review_reason = serializers.SerializerMethodField()
    finance_return_reason = serializers.SerializerMethodField()
    can_correct_return = serializers.SerializerMethodField()
    finance_budget_line = serializers.SerializerMethodField()
    can_submit_finance = serializers.SerializerMethodField()
    can_correct_finance_return = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseRequest
        fields = [
            'id',
            'company',
            'project',
            'project_name',
            'number',
            'title',
            'priority',
            'priority_display',
            'status',
            'status_display',
            'justification',
            'requested_by',
            'requested_by_username',
            'technical_approved_by_name',
            'manager_approved_by_name',
            'manager_approved_by_name',
              'rejection_reason',
            'technical_return_reason',
              'client_uuid',
            'total_estimated_cost',
            'has_purchase_order',
            'can_request_stock_issue',
            'can_approve_stock_issue',
            'next_action_message',
            'can_approve_stock_issue',
            'can_fulfill_from_stock',
            'can_issue_from_stock',
            'can_create_purchase_order',
            'stock_issue_blockers',
            'finance_approval_id',
            'finance_status',
            'finance_status_display',
            'finance_review_reason',
            'finance_return_reason',
            'finance_budget_line',
            'can_submit_finance',
            'can_correct_finance_return',
            'can_correct_return',
            'items',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'company',
            'project_name',
            'number',
            'status',
            'status_display',
            'requested_by',
            'requested_by_username',
            'technical_approved_by_name',
              'rejection_reason',
            'technical_return_reason',
            'total_estimated_cost',
            'has_purchase_order',
            'can_request_stock_issue',
            'can_fulfill_from_stock',
            'can_issue_from_stock',
            'can_create_purchase_order',
            'stock_issue_blockers',
            'finance_approval_id',
            'finance_status',
            'finance_status_display',
            'finance_review_reason',
            'finance_return_reason',
            'finance_budget_line',
            'can_submit_finance',
            'can_correct_finance_return',
            'can_correct_return',
            'created_at',
            'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        company = getattr(user, 'company', None)
        if company is not None:
            self.fields['project'].queryset = accessible_projects(
                user,
                Project.objects.filter(is_active=True),
            ).order_by('name')

    def get_total_estimated_cost(self, obj) -> Decimal:
        return sum(item.quantity * item.material.unit_price for item in obj.items.all())

    def get_technical_approved_by_name(self, obj) -> str:
        approver = obj.technical_approved_by
        return (approver.get_full_name() or approver.username) if approver else ''

    def get_manager_approved_by_name(self, obj) -> str:
        approver = obj.manager_approved_by
        return (approver.get_full_name() or approver.username) if approver else ''

    def get_has_purchase_order(self, obj) -> bool:
        if hasattr(obj, '_prefetched_objects_cache') and 'purchase_orders' in obj._prefetched_objects_cache:
            return bool(obj._prefetched_objects_cache['purchase_orders'])
        return obj.purchase_orders.exists()

    def get_can_request_stock_issue(self, obj) -> bool:
        return (
            obj.project_id is not None
            and obj.status == PurchaseRequest.STATUS_APPROVED
            and obj.technical_approved_by_id is not None
            and obj.technical_approved_by.role == User.ROLE_ADMIN
            and not self.get_has_purchase_order(obj)
            and obj.items.exists()
        )

    def get_can_approve_stock_issue(self, obj) -> bool:
        request_user = getattr(self.context.get('request'), 'user', None)
        return (
            getattr(request_user, 'role', None) == User.ROLE_ADMIN
            and obj.project_id is not None
            and obj.status == PurchaseRequest.STATUS_APPROVED
            and obj.manager_approved_by_id is not None
            and obj.manager_approved_by.role == User.ROLE_PROJECT_MANAGER
            and not obj.purchase_orders.exists()
            and obj.items.exists()
            and not (obj.technical_approved_by_id and obj.technical_approved_by.role == User.ROLE_ADMIN)
        )

    def get_can_fulfill_from_stock(self, obj) -> bool:
        # Once Procurement has moved a request into a stock-issue state, the
        # approval gate has already been completed. Re-checking the historical
        # approver roles here made the Storekeeper action disappear for older
        # records even though the fulfilment endpoint correctly accepted them.
        return obj.status in {
            PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
            PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED,
        } and obj.project_id is not None and not self.get_has_purchase_order(obj) and obj.items.exists()

    def get_can_issue_from_stock(self, obj) -> bool:
        return self.get_can_request_stock_issue(obj)

    def get_can_create_purchase_order(self, obj) -> bool:
        allowed_statuses = {PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED}
        # A projectless request created by Procurement is a warehouse
        # replenishment. It follows the PO -> Finance -> warehouse receipt
        # route, so it must not be blocked by the project-only rule used for
        # site demand.
        is_warehouse_replenishment = obj.project_id is None and obj.requested_by_id and obj.requested_by.role == User.ROLE_PROCUREMENT_OFFICER
        return (
            obj.status in allowed_statuses
            and not self.get_has_purchase_order(obj)
            and (obj.project_id is not None or is_warehouse_replenishment)
            and any(PurchaseRequestItemSerializer(item, context=self.context).get_outstanding_quantity(item) > 0 for item in obj.items.all())
        )

    def get_stock_issue_blockers(self, obj) -> list[str]:
        blockers = []
        if obj.project_id is None:
            blockers.append('Warehouse replenishment requests buy stock into the warehouse and cannot use the stock issue workflow.')
        stock_issue_state = obj.status in {
            PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED,
            PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED,
        }
        if not stock_issue_state:
            if not obj.technical_approved_by_id or obj.technical_approved_by.role != User.ROLE_ADMIN:
                blockers.append('Admin approval is required before Procurement can request warehouse stock issue.')
            if not obj.manager_approved_by_id or obj.manager_approved_by.role != User.ROLE_PROJECT_MANAGER:
                blockers.append('Project Manager approval is required before Admin can approve warehouse stock issue.')
        if self.get_has_purchase_order(obj):
            blockers.append('A purchase order is already linked to this request.')
        if obj.status not in {PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED}:
            blockers.append('Only approved or warehouse-requested PRs can use the stock issue workflow.')
        items = list(obj.items.all())
        if not items:
            blockers.append('The request has no line items.')
        return blockers

    def get_next_action_message(self, obj) -> str:
        """Give every role a plain-language next step for the request."""
        if obj.status == PurchaseRequest.STATUS_PENDING:
            return 'Awaiting Project Manager approval.'
        if obj.status == PurchaseRequest.STATUS_RETURNED:
            return 'Awaiting the requester to correct and resubmit.'
        if obj.status == PurchaseRequest.STATUS_REJECTED:
            return 'No action required — this request was rejected.'
        if obj.status == PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED:
            return 'Awaiting Storekeeper to issue the approved stock.'
        if obj.status == PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED:
            return 'Awaiting Procurement to source the remaining quantity.'
        if obj.status == PurchaseRequest.STATUS_STOCK_ISSUED:
            return 'Stock issued; the material value has been added to project budget actuals.'
        if obj.status == PurchaseRequest.STATUS_APPROVED:
            if obj.manager_approved_by_id is None:
                return 'Awaiting Project Manager approval.'
            if obj.project_id and not obj.purchase_orders.exists() and not (
                obj.technical_approved_by_id and obj.technical_approved_by.role == User.ROLE_ADMIN
            ):
                return 'Awaiting Procurement to obtain a supplier quote; Admin approval is required if warehouse stock issue is chosen.'
            if obj.purchase_orders.exists():
                return 'Awaiting Procurement to send the quoted purchase order to Finance.'
            return 'Awaiting Procurement to choose warehouse issue or create a purchase order.'
        if obj.status == PurchaseRequest.STATUS_PO_CREATED:
            approval = self._finance_approval(obj)
            if approval is None:
                return 'Awaiting Procurement to send the quoted purchase order to Finance.'
            if approval.status in {BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD}:
                return 'Awaiting Finance review of the quoted purchase order.'
            if approval.status == BudgetApproval.STATUS_RETURNED:
                return 'Finance returned this purchase order for correction and resubmission.'
            if approval.status in {BudgetApproval.STATUS_APPROVED, BudgetApproval.STATUS_OVERRIDDEN}:
                return 'Finance approved this purchase order; Procurement can progress it.'
            if approval.status == BudgetApproval.STATUS_REJECTED:
                return 'Finance rejected this purchase order; review the finance comments.'
            return 'Follow up the purchase order finance review.'
        return 'No further action is currently required.'

    def _finance_approval(self, obj):
        try:
            return obj.budget_approval
        except BudgetApproval.DoesNotExist:
            return None

    def get_finance_approval_id(self, obj):
        approval = self._finance_approval(obj)
        return approval.pk if approval else None

    def get_finance_status(self, obj):
        approval = self._finance_approval(obj)
        return approval.status if approval else 'NOT_SUBMITTED'

    def get_finance_status_display(self, obj):
        approval = self._finance_approval(obj)
        return approval.get_status_display() if approval else 'Not submitted'

    def get_finance_review_reason(self, obj):
        approval = self._finance_approval(obj)
        return approval.review_reason if approval else ''

    def get_finance_return_reason(self, obj):
        approval = self._finance_approval(obj)
        return approval.return_reason if approval else ''

    def get_finance_budget_line(self, obj):
        approval = self._finance_approval(obj)
        return approval.budget_line_id if approval else None

    def get_can_submit_finance(self, obj):
        approval = self._finance_approval(obj)
        return (
            obj.status in {PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PO_CREATED}
            and (obj.status == PurchaseRequest.STATUS_PO_CREATED or not self.get_has_purchase_order(obj))
            and (approval is None or approval.status == BudgetApproval.STATUS_RETURNED)
        )

    def get_can_correct_finance_return(self, obj):
        approval = self._finance_approval(obj)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(
            approval
            and approval.status == BudgetApproval.STATUS_RETURNED
            and user
            and (user.role == User.ROLE_ADMIN or obj.requested_by_id == user.id)
            and not self.get_has_purchase_order(obj)
        )

    def get_can_correct_return(self, obj):
        approval = self._finance_approval(obj)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        return bool(
            user
            and (user.role == User.ROLE_ADMIN or obj.requested_by_id == user.id)
            and not self.get_has_purchase_order(obj)
            and (obj.status == PurchaseRequest.STATUS_RETURNED or (approval and approval.status == BudgetApproval.STATUS_RETURNED))
        )

    def validate_project(self, project):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        company_id = getattr(user, 'company_id', None)
        if project and project.company_id != company_id:
            raise serializers.ValidationError('Project must belong to your company.')
        if user and user.role == User.ROLE_SITE_ENGINEER and project is None:
            raise serializers.ValidationError('Site Engineers must link every purchase request to a project.')
        if user and user.role == User.ROLE_PROCUREMENT_OFFICER and project is not None:
            raise serializers.ValidationError(
                'Procurement may only create projectless warehouse replenishment requests. Use the engineer request workflow for project demand.'
            )
        return project

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('At least one purchase request item is required.')
        material_ids = [item['material'].pk for item in items]
        if len(material_ids) != len(set(material_ids)):
            raise serializers.ValidationError('Each material may only appear once in a purchase request.')
        return items

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        purchase_request = PurchaseRequest.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseRequestItem.objects.create(purchase_request=purchase_request, **item_data)
        return purchase_request

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), 'updated_at'])
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseRequestItem.objects.create(purchase_request=instance, **item_data)
        return instance


class PurchaseRequestCorrectionSerializer(PurchaseRequestSerializer):
    correction_summary = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True, write_only=True)

    class Meta(PurchaseRequestSerializer.Meta):
        fields = ['project', 'title', 'priority', 'justification', 'items', 'correction_summary']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        current_project_id = getattr(self.instance, 'project_id', None)
        if current_project_id:
            # Queryset union fails when the company-scoped queryset is marked
            # unique/distinct. Use a single OR-filter instead so a returned
            # request can retain its existing project safely.
            accessible = self.fields['project'].queryset.order_by()
            self.fields['project'].queryset = Project.objects.filter(
                Q(pk=current_project_id) | Q(pk__in=accessible.values('pk'))
            ).order_by('name')

    @transaction.atomic
    def update(self, instance, validated_data):
        validated_data.pop('correction_summary')
        items_data = validated_data.pop('items')
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), 'updated_at'])
        instance.items.all().delete()
        for item_data in items_data:
            PurchaseRequestItem.objects.create(purchase_request=instance, **item_data)
        return instance


class RejectPurchaseRequestSerializer(serializers.Serializer):
    rejection_reason = serializers.CharField(required=True, allow_blank=False, trim_whitespace=True)


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='material.name', read_only=True)
    material_code = serializers.CharField(source='material.code', read_only=True)
    unit = serializers.CharField(source='material.unit', read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrderItem
        fields = ['id', 'material', 'material_name', 'material_code', 'unit', 'quantity', 'unit_price', 'line_total', 'notes']
        read_only_fields = ['id', 'material_name', 'material_code', 'unit', 'line_total']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['material'].queryset = company.materials.filter(is_active=True).order_by('name')

    def get_line_total(self, obj) -> Decimal:
        return obj.quantity * obj.unit_price

    def validate_material(self, material):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if material.company_id != company_id:
            raise serializers.ValidationError('Material must belong to your company.')
        return material


class PurchaseOrderSerializer(serializers.ModelSerializer):
    purchase_request_number = serializers.CharField(source='purchase_request.number', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    delivery_destination_display = serializers.CharField(source='get_delivery_destination_display', read_only=True)
    dispatch_confirmed_by_username = serializers.CharField(source='dispatch_confirmed_by.username', read_only=True)
    received_by_username = serializers.CharField(source='received_by.username', read_only=True)
    total_cost = serializers.SerializerMethodField()
    items = PurchaseOrderItemSerializer(many=True)
    supplier_name = serializers.CharField(read_only=True)
    delivery_follow_up_owner_name = serializers.CharField(source='delivery_follow_up_owner.get_full_name', read_only=True)
    is_overdue = serializers.SerializerMethodField()
    pending_preapproval_edit = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = [
            'id',
            'company',
            'purchase_request',
            'purchase_request_number',
            'project',
            'project_name',
            'number',
            'supplier',
            'supplier_name',
            'delivery_destination',
            'delivery_destination_display',
            'status',
            'status_display',
            'expected_delivery_date',
            'supplier_confirmed_delivery_date',
            'revised_delivery_date',
            'delivery_revision_reason',
            'delivery_follow_up_owner',
            'delivery_follow_up_owner_name',
            'is_overdue',
            'notes',
            'dispatch_confirmed_by',
            'dispatch_confirmed_by_username',
            'dispatch_confirmed_at',
            'received_by',
            'received_by_username',
            'received_at',
            'total_cost',
            'items',
            'created_at',
            'updated_at',
            'pending_preapproval_edit',
        ]
        read_only_fields = [
            'id',
            'company',
            'purchase_request_number',
            'project_name',
            'number',
            'supplier_name',
            'delivery_destination_display',
            'status_display',
            'delivery_follow_up_owner_name',
            'is_overdue',
            'dispatch_confirmed_by',
            'dispatch_confirmed_by_username',
            'dispatch_confirmed_at',
            'received_by',
            'received_by_username',
            'received_at',
            'total_cost',
            'created_at',
            'updated_at',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company = getattr(getattr(request, 'user', None), 'company', None)
        if company is not None:
            self.fields['purchase_request'].queryset = company.purchase_requests.filter(
                status__in=[PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED],
                purchase_orders__isnull=True,
            ).order_by('-created_at')
            self.fields['project'].queryset = company.projects.filter(is_active=True).order_by('name')
            self.fields['supplier'].queryset = company.suppliers.filter(is_active=True).order_by('name')

    def get_total_cost(self, obj) -> Decimal:
        return sum(item.quantity * item.unit_price for item in obj.items.all())

    def get_is_overdue(self, obj) -> bool:
        due = obj.revised_delivery_date or obj.supplier_confirmed_delivery_date or obj.expected_delivery_date
        return bool(due and due < timezone.localdate() and obj.status not in {PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED})

    def get_pending_preapproval_edit(self, obj):
        from apps.procurement.amendments import PurchaseOrderAmendment
        edit = obj.amendments.filter(
            amendment_type=PurchaseOrderAmendment.TYPE_PRE_APPROVAL_EDIT,
            status=PurchaseOrderAmendment.STATUS_SUBMITTED,
        ).select_related('submitted_by').first()
        if not edit:
            return None
        return {
            'id': edit.id,
            'version': edit.version,
            'changed_fields': edit.proposed_values.get('changed_fields', []),
            'original_values': edit.original_values,
            'proposed_values': edit.proposed_values.get('snapshot', {}),
            'submitted_by': edit.submitted_by_id,
            'submitted_by_username': edit.submitted_by.username,
            'created_at': edit.created_at,
        }

    def validate_supplier(self, supplier):
        if supplier is None:
            return supplier
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if supplier.company_id != company_id or not supplier.is_active:
            raise serializers.ValidationError('Select an active supplier from your company.')
        return supplier

    def validate_purchase_request(self, purchase_request):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if purchase_request and purchase_request.company_id != company_id:
            raise serializers.ValidationError('Purchase request must belong to your company.')
        if purchase_request and purchase_request.status not in {
            PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED,
        }:
            raise serializers.ValidationError('Only approved requests, including partially stock-issued requests, can be linked to a purchase order.')
        if purchase_request and purchase_request.purchase_orders.exclude(pk=getattr(self.instance, 'pk', None)).exists():
            raise serializers.ValidationError('This purchase request already has a purchase order.')
        return purchase_request

    def validate_project(self, project):
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        if project and project.company_id != company_id:
            raise serializers.ValidationError('Project must belong to your company.')
        return project

    def validate_items(self, items):
        if not items:
            raise serializers.ValidationError('At least one purchase order item is required.')
        material_ids = [item['material'].pk for item in items]
        if len(material_ids) != len(set(material_ids)):
            raise serializers.ValidationError('Each material may only appear once in a purchase order.')
        return items

    def validate(self, attrs):
        attrs = super().validate(attrs)
        supplier = attrs.get('supplier') or getattr(self.instance, 'supplier', None)
        if not supplier:
            raise serializers.ValidationError({'supplier': 'Supplier must be selected.'})
        status = attrs.get('status')
        if status == PurchaseOrder.STATUS_RECEIVED:
            raise serializers.ValidationError({'status': 'Use the receive endpoint to mark a purchase order as received.'})
        if status == PurchaseOrder.STATUS_DISPATCH_CONFIRMED:
            raise serializers.ValidationError({'status': 'Use the confirm-dispatch endpoint to confirm direct-to-site dispatch.'})
        purchase_request = attrs.get('purchase_request') or getattr(self.instance, 'purchase_request', None)
        if not purchase_request:
            raise serializers.ValidationError({'purchase_request': 'A manager-approved purchase request is required for every purchase order.'})
        project = attrs.get('project') or getattr(self.instance, 'project', None)
        delivery_destination = attrs.get('delivery_destination') or getattr(
            self.instance,
            'delivery_destination',
            PurchaseOrder.DELIVERY_WAREHOUSE,
        )
        if purchase_request and not project:
            attrs['project'] = purchase_request.project
        elif purchase_request and purchase_request.project_id and project != purchase_request.project:
            raise serializers.ValidationError({'project': 'Project must match the linked purchase request project.'})
        if delivery_destination == PurchaseOrder.DELIVERY_SITE and not (attrs.get('project') or project):
            raise serializers.ValidationError({'project': 'Direct-to-site purchase orders must be linked to a project.'})
        if self.instance is None and purchase_request.project_id and 'delivery_destination' not in attrs:
            # Project shortage POs go to the site by default. Procurement may
            # explicitly choose Warehouse only when the goods must be held as
            # reserved project stock before a controlled site transfer.
            attrs['delivery_destination'] = PurchaseOrder.DELIVERY_SITE
        # A PO executes an approval. Supplier and delivery choices can change,
        # but procurement must not alter the approved material scope or value.
        items = attrs.get('items')
        if self.instance is None and items is not None:
            request_items = list(purchase_request.items.select_related('material').all())
            issued_by_item = {
                row['purchase_request_item']: row['issued'] or Decimal('0.00')
                for row in StockMovement.objects.filter(
                    purchase_request=purchase_request,
                    purchase_request_item__isnull=False,
                    movement_type=StockMovement.MOVEMENT_OUT,
                    transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
                ).values('purchase_request_item').annotate(issued=Sum('quantity'))
            }
            approved_quantities = {
                item.material_id: max(item.quantity - issued_by_item.get(item.pk, Decimal('0.00')), Decimal('0.00'))
                for item in request_items
                if item.quantity - issued_by_item.get(item.pk, Decimal('0.00')) > 0
            }
            ordered_quantities = {item['material'].pk: item['quantity'] for item in items}
            if ordered_quantities != approved_quantities:
                raise serializers.ValidationError({
                    'items': 'Purchase order lines must exactly match the approved request quantities still outstanding after warehouse issue.',
                })
            # Procurement may use the supplier's actual quoted unit prices.
            # Finance reviews the resulting PO total after this draft is sent
            # for approval. Quantities and material scope remain locked above.
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop('items')
        purchase_order = PurchaseOrder.objects.create(**validated_data)
        for item_data in items_data:
            PurchaseOrderItem.objects.create(purchase_order=purchase_order, **item_data)
        return purchase_order

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop('items', None)
        for field, value in validated_data.items():
            setattr(instance, field, value)
        instance.save(update_fields=[*validated_data.keys(), 'updated_at'])
        if items_data is not None:
            instance.items.all().delete()
            for item_data in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item_data)
        return instance


class GoodsReceivedNoteItemSerializer(serializers.ModelSerializer):
    material_name = serializers.CharField(source='purchase_order_item.material.name', read_only=True)

    class Meta:
        model = GoodsReceivedNoteItem
        fields = [
            'id', 'purchase_order_item', 'material_name', 'accepted_quantity',
            'rejected_quantity', 'damaged_quantity', 'notes',
        ]
        read_only_fields = fields


class GoodsReceivedNoteSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.CharField(source='purchase_order.number', read_only=True)
    received_by_username = serializers.CharField(source='received_by.username', read_only=True)
    received_by_name = serializers.SerializerMethodField()
    items = GoodsReceivedNoteItemSerializer(many=True, read_only=True)

    def get_received_by_name(self, obj):
        if not obj.received_by_id:
            return None
        return obj.received_by.get_full_name() or obj.received_by.username

    class Meta:
        model = GoodsReceivedNote
        fields = [
            'id', 'purchase_order', 'purchase_order_number', 'number', 'receipt_date',
            'status', 'notes', 'received_by', 'received_by_username', 'received_by_name', 'created_at', 'items',
        ]
        read_only_fields = fields


class SupplierClaimSerializer(serializers.ModelSerializer):
    purchase_order_number = serializers.CharField(source='purchase_order.number', read_only=True)
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    material_name = serializers.CharField(source='goods_received_note_item.purchase_order_item.material.name', read_only=True)
    material_code = serializers.CharField(source='goods_received_note_item.purchase_order_item.material.code', read_only=True)
    grn_number = serializers.CharField(source='goods_received_note_item.goods_received_note.number', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    purchase_order_item = serializers.IntegerField(source='goods_received_note_item.purchase_order_item_id', read_only=True)
    replacement_quantity = serializers.SerializerMethodField()
    replacement_grn_number = serializers.SerializerMethodField()

    def get_replacement_quantity(self, obj):
        item = obj.goods_received_note_item
        return item.rejected_quantity + item.damaged_quantity

    def get_replacement_grn_number(self, obj):
        if not obj.replacement_grn_item_id:
            return None
        return obj.replacement_grn_item.goods_received_note.number

    class Meta:
        model = SupplierClaim
        fields = [
            'id', 'company', 'goods_received_note_item', 'grn_number', 'purchase_order',
            'purchase_order_number', 'supplier', 'supplier_name', 'project', 'project_name',
            'material_name', 'material_code', 'purchase_order_item', 'replacement_quantity', 'replacement_grn_item', 'replacement_grn_number', 'reported_by', 'reported_by_name', 'assigned_to',
            'assigned_to_name', 'status', 'status_display', 'due_date', 'supplier_reference',
            'notes', 'resolution_notes', 'resolved_by', 'resolved_at', 'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'company', 'goods_received_note_item', 'grn_number', 'purchase_order',
            'purchase_order_number', 'supplier', 'supplier_name', 'project', 'project_name',
            'material_name', 'material_code', 'reported_by', 'reported_by_name', 'assigned_to_name',
            'status_display', 'resolved_by', 'resolved_at', 'created_at', 'updated_at',
        ]

    def validate_assigned_to(self, user):
        request = self.context.get('request')
        if not request or user.company_id != request.user.company_id:
            raise serializers.ValidationError('Assignee must belong to your company.')
        if user.role not in {User.ROLE_PROCUREMENT_OFFICER, User.ROLE_ADMIN}:
            raise serializers.ValidationError('Supplier claims may only be assigned to Procurement or Admin users.')
        return user

    def validate(self, attrs):
        status = attrs.get('status', getattr(self.instance, 'status', None))
        resolution = attrs.get('resolution_notes', getattr(self.instance, 'resolution_notes', ''))
        if status == SupplierClaim.STATUS_RESOLVED and not resolution.strip():
            raise serializers.ValidationError({'resolution_notes': 'Explain how the supplier claim was resolved.'})
        return attrs


class PurchaseOrderReceiptItemRequestSerializer(serializers.Serializer):
    purchase_order_item = serializers.PrimaryKeyRelatedField(queryset=PurchaseOrderItem.objects.none())
    accepted_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'), default=Decimal('0.00'),
    )
    rejected_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'), default=Decimal('0.00'),
    )
    damaged_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal('0.00'), default=Decimal('0.00'),
    )
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)

    def validate(self, attrs):
        total = attrs['accepted_quantity'] + attrs['rejected_quantity'] + attrs['damaged_quantity']
        if total <= Decimal('0.00'):
            raise serializers.ValidationError('At least one disposition quantity must be greater than zero.')
        if (attrs['rejected_quantity'] > 0 or attrs['damaged_quantity'] > 0) and not attrs.get('notes', '').strip():
            raise serializers.ValidationError({
                'notes': 'A line note is required when goods are rejected or damaged.',
            })
        return attrs


class PurchaseOrderReceiptRequestSerializer(serializers.Serializer):
    client_uuid = serializers.UUIDField(required=False)
    receipt_date = serializers.DateField(required=False, default=timezone.localdate)
    notes = serializers.CharField(required=False, allow_blank=True)
    items = PurchaseOrderReceiptItemRequestSerializer(many=True, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get('request')
        company_id = getattr(getattr(request, 'user', None), 'company_id', None)
        self.fields['items'].child.fields['purchase_order_item'].queryset = PurchaseOrderItem.objects.filter(
            purchase_order__company_id=company_id,
        )

class NotificationSerializer(serializers.ModelSerializer):
    notification_type_display = serializers.CharField(source='get_notification_type_display', read_only=True)
    level_display = serializers.CharField(source='get_level_display', read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'company', 'recipient', 'notification_type', 'notification_type_display', 'level', 'level_display', 'title', 'message', 'link', 'is_read', 'created_at']
        read_only_fields = fields


class ChatRoomSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)

    class Meta:
        model = ChatRoom
        fields = ['id', 'company', 'project', 'project_name', 'created_at']
        read_only_fields = fields


class ChatMessageSerializer(serializers.ModelSerializer):
    sender_username = serializers.CharField(source='sender.username', read_only=True)
    project = serializers.IntegerField(source='room.project_id', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ['id', 'room', 'project', 'sender', 'sender_username', 'content', 'is_system_message', 'created_at']
        read_only_fields = fields


class DashboardResponseSerializer(serializers.Serializer):
    total_active_materials = serializers.IntegerField()
    active_projects = serializers.IntegerField()
    low_stock_count = serializers.IntegerField()
    pending_purchase_requests = serializers.IntegerField()
    stock_in_today = serializers.DecimalField(max_digits=16, decimal_places=2)
    inventory_value = serializers.DecimalField(max_digits=16, decimal_places=2)
    recent_stock_movements = serializers.ListField(child=serializers.DictField())
    low_stock_materials = serializers.ListField(child=serializers.DictField())
    pending_purchase_requests_list = serializers.ListField(child=serializers.DictField())
    project_budget_vs_actual = serializers.ListField(child=serializers.DictField())
