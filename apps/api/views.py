from decimal import Decimal

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, extend_schema

from apps.accounts.models import Company, User
from apps.dashboard.helpers import push_dashboard_update
from apps.materials.models import Category, Material
from apps.notifications.helpers import check_low_stock_for_company, get_unread_count, push_unread_count, send_notification
from apps.notifications.models import Notification, WebPushSubscription
from apps.procurement.models import (
    GoodsReceivedNote,
    PurchaseOrder,
    PurchaseOrderItem,
    PurchaseRequest,
    PurchaseRequestItem,
    SupplierClaim,
)
from apps.procurement.services import (
    notify_po_created_from_pr,
    notify_po_approved,
    notify_po_dispatch_confirmed,
    notify_po_received,
    notify_pr_approved,
    notify_pr_rejected,
    notify_pr_returned_for_correction,
    notify_pr_stock_issue_requested,
    notify_pr_stock_issued,
    notify_pr_submitted,
    record_goods_received_note,
    create_purchase_order,
    create_purchase_request,
    approve_purchase_request,
    approve_stock_issue_request,
    reject_purchase_request,
    return_purchase_request_for_correction,
    create_purchase_order_amendment,
    purchase_order_amendment_snapshot,
    approve_purchase_order_amendment,
    confirm_purchase_order_preapproval_edit,
    reject_purchase_order_amendment,
)
from apps.procurement.selectors import purchase_orders_for_user, purchase_requests_for_user
from apps.finance.services import ensure_budget_clearance
from apps.finance import budget_services
from apps.finance.configuration_services import record_finance_audit_event
from apps.finance.models import BudgetApproval, ProjectBudget, SupplierInvoice
from apps.pdf_exports import pdf_table_response
from apps.finance.report_exports import xlsx_response
from apps.finance.permissions import FinanceAdminPermission, FinanceCompanyPermission, FinanceReviewPermission, FinanceSubmissionPermission
from apps.projects.access import (
    accessible_chat_projects,
    accessible_project_sites,
    accessible_projects,
    accessible_purchase_requests,
)
from apps.projects.models import ApprovalDelegation, ChatMessage, ChatRoom, Project, ProjectGoal, ProjectSite, ProjectStaffAssignment
from apps.projects.services import annotate_project_costs
from apps.suppliers.models import Supplier
from apps.warehouse import valuation_services
from apps.warehouse.models import BinLocation, SiteTransfer, StockMovement, Warehouse

from .filters import StockMovementFilter
from .permissions import (
    IsAdminOnly,
    IsAuthenticatedCompanyUser,
    IsCompanyUserReadOnlyOrProjectManagerAdmin,
    IsCompanyUserReadOnlyOrStorekeeperAdmin,
    IsCompanyUserReadOnlyOrStorekeeperProcurementAdmin,
    IsProcurementOfficerOrAdmin,
    IsProjectManagerOrAdmin,
    IsPurchaseRequestSubmitterOrAdmin,
    IsReportsUser,
    IsSupplierReadUser,
    IsStorekeeperOrAdmin,
)
from .lifecycle import audit_lifecycle, require_draft


def _operational_export(*, kind, title, filename, columns, rows, totals):
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
        totals=totals, subtitle='Company-scoped operational export using the active filters.',
    )
from .serializers import (
    CategorySerializer,
    ChatMessageSerializer,
    ChatRoomSerializer,
    CompanySerializer,
    CompanyRegistrationSerializer,
    DashboardResponseSerializer,
    MaterialSerializer,
    NotificationSerializer,
    GoodsReceivedNoteSerializer,
    ProjectSerializer,
    ProjectGoalSerializer,
    ProjectSiteSerializer,
    ProjectStaffAssignmentSerializer,
    ApprovalDelegationSerializer,
    PurchaseOrderSerializer,
    PurchaseOrderReceiptRequestSerializer,
    PurchaseRequestSerializer,
    PurchaseRequestCorrectionSerializer,
    RejectPurchaseRequestSerializer,
    StockMovementSerializer,
    SupplierSerializer,
    SupplierClaimSerializer,
    UserSerializer,
    InventoryValuationSerializer,
    InventoryActionSerializer,
    OpeningBalanceRequestSerializer,
    ProjectIssueRequestSerializer,
    ProjectMaterialCostSerializer,
    ProjectReturnRequestSerializer,
    SiteReturnRequestSerializer,
    SiteTransferRequestSerializer,
    SiteTransferSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SupplierReturnRequestSerializer,
    ValuationAdjustmentRequestSerializer,
    ValuationReconciliationSerializer,
    ValuedReceiptRequestSerializer,
    WarehouseSerializer,
    BinLocationSerializer,
    WorkflowBadgesSerializer,
)
from apps.finance.serializers import (
    FinanceDecisionSerializer,
    FinanceSubmissionSerializer,
    FinancialApprovalSerializer,
    RequiredCommentsSerializer,
)
from .workflow import workflow_badges_for_user
from .delivery_serializers import PurchaseOrderDeliveryUpdateSerializer
from .amendment_serializers import (
    PurchaseOrderAmendmentDecisionSerializer,
    PurchaseOrderAmendmentRequestSerializer,
    PurchaseOrderAmendmentSerializer,
    PurchaseOrderPreApprovalEditSerializer,
)


class CompanyScopedReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]

    def get_company(self):
        return getattr(self.request.user, 'company', None)


class PasswordResetRequestAPIView(APIView):
    """Send a one-time reset link without exposing whether an email exists."""

    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email']
        user = User.objects.filter(email__iexact=email, is_active=True).first()
        if user and user.has_usable_password():
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            reset_url = f'{settings.FRONTEND_BASE_URL}/reset-password?uid={uid}&token={token}'
            send_mail(
                subject='Reset your ConstructSaaS password',
                message=(
                    'A password reset was requested for your ConstructSaaS account.\n\n'
                    f'Use this one-time link to choose a new password:\n{reset_url}\n\n'
                    'If you did not request this, you can ignore this email.'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        return Response({'detail': 'If that email belongs to an active account, a reset link has been sent.'})


class CompanyRegistrationAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = CompanyRegistrationSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = serializer.save()
        return Response(
            {'detail': 'Company registered successfully.', 'username': user.username},
            status=status.HTTP_201_CREATED,
        )


class PasswordResetConfirmAPIView(APIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user_id = urlsafe_base64_decode(serializer.validated_data['uid']).decode()
            user = User.objects.get(pk=user_id, is_active=True)
        except (User.DoesNotExist, ValueError, TypeError, UnicodeDecodeError):
            raise ValidationError({'token': ['This password reset link is invalid or has expired.']})
        if not default_token_generator.check_token(user, serializer.validated_data['token']):
            raise ValidationError({'token': ['This password reset link is invalid or has expired.']})
        user.set_password(serializer.validated_data['password'])
        user.save(update_fields=['password'])
        return Response({'detail': 'Your password has been reset. You can now sign in.'})


def paginated_data_response(*, request, data, serializer_class):
    paginator = PageNumberPagination()
    page = paginator.paginate_queryset(data, request)
    serialized = serializer_class(page if page is not None else data, many=True).data
    return paginator.get_paginated_response(serialized) if page is not None else Response(serialized)


class DashboardAPIView(APIView):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = DashboardResponseSerializer

    def get(self, request):
        company = request.user.company
        today = timezone.localdate()
        materials = Material.objects.for_company(company).with_current_stock().with_inventory_value().select_related('category')
        active_materials = materials.filter(is_active=True)
        low_stock_materials = active_materials.filter(current_stock_value__lte=F('min_stock_level')).order_by(
            'current_stock_value',
            'name',
        )
        pending_purchase_requests = PurchaseRequest.objects.filter(
            company=company,
            status=PurchaseRequest.STATUS_PENDING,
        ).select_related('project', 'requested_by')

        stock_in_today = StockMovement.objects.filter(
            company=company,
            date=today,
            movement_type=StockMovement.MOVEMENT_IN,
        ).aggregate(total=Coalesce(Sum('quantity'), Decimal('0.00')))['total']
        inventory_value = active_materials.aggregate(
            total=Coalesce(Sum('stock_value'), Decimal('0.00')),
        )['total']
        projects = annotate_project_costs(
            accessible_projects(
                request.user,
                Project.objects.filter(is_active=True),
            ).select_related('manager').prefetch_related('sites', 'goals')
        ).order_by('name')
        project_list = list(projects)
        approved_budgets = {
            budget.project_id: budget
            for budget in ProjectBudget.objects.filter(
                company=company,
                project_id__in=[project.id for project in project_list],
                status=ProjectBudget.STATUS_APPROVED,
            ).prefetch_related('revisions', 'transactions')
        }
        project_budget_rows = []
        for project in project_list:
            goals = list(project.goals.all())
            sites = [site for site in project.sites.all() if site.is_active]
            if goals:
                total_weight = sum(goal.weight for goal in goals)
                actual_progress = round(float(sum(goal.weight * goal.completion_percent for goal in goals) / total_weight), 1) if total_weight else 0
            else:
                actual_progress = round((sum(site.status == ProjectSite.STATUS_COMPLETED for site in sites) / len(sites) * 100), 1) if sites else 0
            if project.start_date and project.end_date and project.end_date > project.start_date:
                elapsed_days = (today - project.start_date).days
                duration_days = (project.end_date - project.start_date).days
                planned_progress = round(max(0, min(100, elapsed_days / duration_days * 100)), 1)
            else:
                planned_progress = 100 if project.status == Project.STATUS_COMPLETED else 0
            finance_budget = approved_budgets.get(project.id)
            if finance_budget:
                budget_summary = budget_services.project_budget_summary(finance_budget)
                budget_source = 'finance'
            else:
                budget_summary = {
                    'revised_budget': project.budget,
                    'open_commitments': Decimal('0.00'),
                    'actual_expenditure': project.total_material_cost,
                    'available_balance': project.budget - project.total_material_cost,
                }
                budget_source = 'legacy'
            project_budget_rows.append({
                'id': project.id,
                'name': project.name,
                'code': project.code,
                'budget': budget_summary['revised_budget'],
                'actual_material_cost': project.total_material_cost,
                'actual_expenditure': budget_summary['actual_expenditure'],
                'open_commitments': budget_summary['open_commitments'],
                'remaining_budget': budget_summary['available_balance'],
                'budget_source': budget_source,
                'planned_progress': planned_progress,
                'actual_progress': actual_progress,
            })

        return Response(
            {
                'total_active_materials': active_materials.count(),
                'inventory_health': [
                    {'name': 'Healthy (OK)', 'count': active_materials.filter(current_stock_value__gt=F('min_stock_level')).count(), 'color': '#0F7075'},
                    {'name': 'Low stock', 'count': active_materials.filter(current_stock_value__gt=0, current_stock_value__lte=F('min_stock_level')).count(), 'color': '#E99A17'},
                    {'name': 'Out of stock', 'count': active_materials.filter(current_stock_value__lte=0).count(), 'color': '#D34C5C'},
                ],
                'active_projects': len(project_list),
                'low_stock_count': low_stock_materials.count(),
                'pending_purchase_requests': pending_purchase_requests.count(),
                'stock_in_today': stock_in_today,
                'inventory_value': inventory_value,
                'recent_stock_movements': [
                    {
                        'id': movement.id,
                        'material': {
                            'id': movement.material_id,
                            'name': movement.material.name,
                            'code': movement.material.code,
                        },
                        'project': {
                            'id': movement.project_id,
                            'name': movement.project.name,
                            'code': movement.project.code,
                        }
                        if movement.project_id
                        else None,
                        'movement_type': movement.movement_type,
                        'movement_type_display': movement.get_movement_type_display(),
                        'source': movement.source,
                        'source_display': movement.get_source_display(),
                        'quantity': movement.quantity,
                        'unit_price': movement.unit_price,
                        'date': movement.date,
                        'notes': movement.notes,
                    }
                    for movement in StockMovement.objects.filter(company=company)
                    .select_related('material', 'project')
                    .order_by('-date', '-created_at')[:8]
                ],
                'low_stock_materials': [
                    {
                        'id': material.id,
                        'name': material.name,
                        'code': material.code,
                        'category': material.category.name if material.category_id else '',
                        'unit': material.unit,
                        'current_stock': material.current_stock_value,
                        'min_stock_level': material.min_stock_level,
                        'unit_price': material.unit_price,
                        'stock_value': material.stock_value,
                    }
                    for material in low_stock_materials[:8]
                ],
                'pending_purchase_requests_list': [
                    {
                        'id': purchase_request.id,
                        'number': purchase_request.number,
                        'title': purchase_request.title,
                        'priority': purchase_request.priority,
                        'priority_display': purchase_request.get_priority_display(),
                        'project': {
                            'id': purchase_request.project_id,
                            'name': purchase_request.project.name,
                            'code': purchase_request.project.code,
                        }
                        if purchase_request.project_id
                        else None,
                        'requested_by': {
                            'id': purchase_request.requested_by_id,
                            'name': purchase_request.requested_by.get_full_name()
                            or purchase_request.requested_by.username,
                        }
                        if purchase_request.requested_by_id
                        else None,
                        'created_at': purchase_request.created_at,
                    }
                    for purchase_request in pending_purchase_requests.order_by('-created_at')[:8]
                ],
                'project_budget_vs_actual': project_budget_rows
                if request.user.role
                in {
                    User.ROLE_PROJECT_MANAGER,
                    User.ROLE_PROCUREMENT_OFFICER,
                    User.ROLE_ADMIN,
                }
                else [],
            }
        )


class WorkflowBadgesAPIView(APIView):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = WorkflowBadgesSerializer

    @extend_schema(
        tags=['Workflow'],
        summary='Return role-aware pending workflow counts',
        responses=WorkflowBadgesSerializer,
    )
    def get(self, request):
        return Response(workflow_badges_for_user(request.user))


class ReportsAPIView(DashboardAPIView):
    permission_classes = [IsReportsUser]


class CompanyViewSet(CompanyScopedReadOnlyViewSet):
    permission_classes = [IsAdminOnly]
    serializer_class = CompanySerializer
    search_fields = ['name', 'slug']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Company.objects.none()
        return Company.objects.filter(pk=company.pk)


class UserViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = UserSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['role', 'is_active']
    search_fields = ['username', 'first_name', 'last_name', 'email', 'phone']
    ordering_fields = ['username', 'first_name', 'last_name']
    ordering = ['username']

    def get_permissions(self):
        if self.action in {'create', 'partial_update', 'update', 'destroy'}:
            permission_classes = [IsAdminOnly]
        else:
            permission_classes = [IsAuthenticatedCompanyUser]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return User.objects.none()
        queryset = User.objects.filter(company=company)
        if self.request.user.role in {
            User.ROLE_ADMIN,
            User.ROLE_FINANCE_OFFICER,
            User.ROLE_FINANCE_MANAGER,
            User.ROLE_FINANCE_VIEWER,
        }:
            return queryset
        if self.request.user.role == User.ROLE_PROJECT_MANAGER:
            return queryset.filter(Q(pk=self.request.user.pk) | Q(role=User.ROLE_SITE_ENGINEER))
        return queryset.filter(pk=self.request.user.pk)

    @action(detail=False, methods=['get'])
    def me(self, request):
        return Response(self.get_serializer(request.user).data)


class CategoryViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrStorekeeperAdmin]
    serializer_class = CategorySerializer
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Category.objects.none()
        return Category.objects.filter(company=company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    def perform_destroy(self, instance):
        instance.delete()


class MaterialViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrStorekeeperProcurementAdmin]
    serializer_class = MaterialSerializer
    filterset_fields = ['category', 'unit', 'is_active']
    search_fields = ['name', 'code', 'category__name', 'description']
    ordering_fields = ['name', 'code', 'unit_price', 'min_stock_level', 'current_stock_value', 'stock_value', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        # Deactivation changes the catalogue, so it is intentionally separate
        # from Storekeeper stock operations and Procurement maintenance.
        permission_classes = [IsAdminOnly] if self.action == 'destroy' else self.permission_classes
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Material.objects.none()
        queryset = (
            Material.objects.for_company(company)
            .with_current_stock()
            .with_inventory_value()
            .select_related('category', 'company')
        )

        low_stock = self.request.query_params.get('low_stock', '').lower()
        if low_stock in {'true', '1', 'yes'}:
            queryset = queryset.filter(current_stock_value__lte=F('min_stock_level'))
        elif low_stock in {'false', '0', 'no'}:
            queryset = queryset.filter(
                Q(current_stock_value__gt=F('min_stock_level')) | Q(min_stock_level__isnull=True)
            )
        if self.request.query_params.get('project_site'):
            queryset = queryset.filter(movements__warehouse__project_site_id=self.request.query_params['project_site']).distinct()
        return queryset

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    def destroy(self, request, *args, **kwargs):
        material = self.get_object()
        if not material.is_active:
            return Response({'detail': 'This material is already deactivated.'}, status=status.HTTP_400_BAD_REQUEST)
        material.is_active = False
        material.save(update_fields=['is_active', 'updated_at'])
        record_finance_audit_event(
            company=material.company,
            actor=request.user,
            action='material.deactivated',
            object_type='Material',
            object_id=material.pk,
            message=f'Material catalogue record deactivated: {material.code} / {material.name}.',
            metadata={'material_code': material.code, 'material_name': material.name},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(tags=['Inventory'], summary='Download inventory register as PDF', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        rows = [{
            'code': material.code, 'material': material.name, 'category': material.category.name,
            'unit': material.get_unit_display(), 'stock': material.current_stock_value,
            'minimum': material.min_stock_level, 'value': f'UGX {material.stock_value:,.2f}',
            'status': 'Low stock' if material.current_stock_value <= material.min_stock_level else 'Healthy',
        } for material in queryset]
        totals = {
            'Materials': len(rows),
            'Low stock items': sum(1 for material in queryset if material.current_stock_value <= material.min_stock_level),
            'Inventory value': f'UGX {sum((material.stock_value for material in queryset), Decimal("0.00")):,.2f}',
        }
        return pdf_table_response(
            title='Inventory register', filename='inventory-register',
            columns=[('code', 'Code'), ('material', 'Material'), ('category', 'Category'), ('unit', 'Unit'), ('stock', 'Stock'), ('minimum', 'Minimum'), ('value', 'Value'), ('status', 'Status')],
            rows=rows, totals=totals, subtitle='Current stock and value for the selected inventory filters.',
        )

    @extend_schema(tags=['Inventory'], summary='Download inventory register as Excel', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-xlsx')
    def download_xlsx(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        rows = [{
            'code': material.code, 'material': material.name, 'category': material.category.name,
            'unit': material.get_unit_display(), 'stock': material.current_stock_value,
            'minimum': material.min_stock_level, 'value': material.stock_value,
            'status': 'Low stock' if material.current_stock_value <= material.min_stock_level else 'Healthy',
        } for material in queryset]
        return xlsx_response({
            'title': 'Inventory register',
            'columns': [{'key': key, 'label': label} for key, label in [('code', 'Code'), ('material', 'Material'), ('category', 'Category'), ('unit', 'Unit'), ('stock', 'Stock'), ('minimum', 'Minimum'), ('value', 'Value'), ('status', 'Status')]],
            'rows': rows,
            'totals': {'Materials': len(rows), 'Low stock items': sum(1 for row in rows if row['status'] == 'Low stock')},
        }, 'inventory-register')


class ProjectViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrProjectManagerAdmin]
    serializer_class = ProjectSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['status', 'is_active', 'manager']
    search_fields = ['name', 'code', 'client', 'location', 'description']
    ordering_fields = ['name', 'code', 'budget', 'total_material_cost', 'start_date', 'end_date', 'created_at']
    ordering = ['name']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Project.objects.none()
        return annotate_project_costs(
            accessible_projects(
                self.request.user,
                Project.objects.all(),
            )
            .select_related('manager', 'company')
            .prefetch_related('site_engineers', 'sites', 'goals')
        )

    def perform_create(self, serializer):
        save_kwargs = {'company': self.request.user.company}
        if self.request.user.role == User.ROLE_PROJECT_MANAGER:
            save_kwargs['manager'] = self.request.user
        project = serializer.save(**save_kwargs)
        transaction.on_commit(lambda: push_dashboard_update(project.company))

    def perform_update(self, serializer):
        project = serializer.save()
        transaction.on_commit(lambda: push_dashboard_update(project.company))


class ProjectSiteViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrProjectManagerAdmin]
    serializer_class = ProjectSiteSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['project', 'status', 'is_active', 'manager']
    search_fields = ['name', 'code', 'location', 'description', 'project__name']
    ordering = ['project__name', 'name']

    def get_queryset(self):
        return accessible_project_sites(self.request.user, ProjectSite.objects.all()).select_related('project', 'manager').prefetch_related('site_engineers')

    @action(detail=True, methods=['post'], url_path='toggle-closed')
    def toggle_closed(self, request, pk=None):
        site = self.get_object()
        if request.user.role not in {User.ROLE_ADMIN, User.ROLE_PROJECT_MANAGER}:
            raise ValidationError({'detail': 'Only a project manager or admin can close or reopen a site.'})
        if site.status == ProjectSite.STATUS_COMPLETED:
            site.status = ProjectSite.STATUS_ACTIVE
            site.closed_at = None
            site.closed_by = None
            message = 'Site reopened.'
        else:
            site.status = ProjectSite.STATUS_COMPLETED
            site.closed_at = timezone.now()
            site.closed_by = request.user
            message = 'Site closed and included in project completion.'
        site.save(update_fields=['status', 'closed_at', 'closed_by', 'updated_at'])
        transaction.on_commit(lambda: push_dashboard_update(site.project.company))
        return Response({'detail': message, 'site': self.get_serializer(site).data})


class ProjectGoalViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrProjectManagerAdmin]
    serializer_class = ProjectGoalSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['project', 'site', 'status']
    search_fields = ['title', 'description', 'project__name', 'site__name']
    ordering = ['due_date', 'title']

    def get_queryset(self):
        return ProjectGoal.objects.filter(
            project__in=accessible_projects(self.request.user, Project.objects.all()),
        ).select_related('project', 'site', 'completed_by')

    def perform_create(self, serializer):
        goal = serializer.save()
        transaction.on_commit(lambda: push_dashboard_update(goal.project.company))

    def perform_update(self, serializer):
        goal = serializer.save()
        transaction.on_commit(lambda: push_dashboard_update(goal.project.company))


class ProjectStaffAssignmentViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectStaffAssignmentSerializer
    permission_classes = [IsProjectManagerOrAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['project', 'user', 'role', 'is_active']
    search_fields = ['project__name', 'user__username', 'user__first_name', 'user__last_name']

    def get_queryset(self):
        return ProjectStaffAssignment.objects.filter(project__company=self.request.user.company).select_related('project', 'user')

    def perform_create(self, serializer):
        project = serializer.validated_data['project']
        user = serializer.validated_data['user']
        if project.company_id != self.request.user.company_id or user.company_id != self.request.user.company_id:
            raise ValidationError({'detail': 'Project and user must belong to your company.'})
        if self.request.user.role == User.ROLE_PROJECT_MANAGER and project.manager_id != self.request.user.id:
            raise ValidationError({'project': ['You can manage staffing only for your own projects.']})
        serializer.save()


class ApprovalDelegationViewSet(viewsets.ModelViewSet):
    serializer_class = ApprovalDelegationSerializer
    permission_classes = [IsProjectManagerOrAdmin]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['project', 'is_active']

    def get_queryset(self):
        user = self.request.user
        rows = ApprovalDelegation.objects.filter(delegator__company=user.company).select_related('delegator', 'delegate', 'project')
        return rows if user.role == User.ROLE_ADMIN else rows.filter(delegator=user)

    def perform_create(self, serializer):
        delegate = serializer.validated_data['delegate']
        project = serializer.validated_data.get('project')
        if delegate.company_id != self.request.user.company_id or (project and project.company_id != self.request.user.company_id):
            raise ValidationError({'detail': 'Delegation participants and project must belong to your company.'})
        serializer.save(delegator=self.request.user)


class SupplierViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    filterset_fields = ['rating', 'is_active']
    search_fields = ['name', 'contact_person', 'phone', 'email', 'address', 'notes']
    ordering_fields = ['name', 'rating', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        # Finance can read supplier master data for statements, invoice matching,
        # payment preparation and reporting. Supplier maintenance remains a
        # procurement control.
        permission = IsSupplierReadUser if self.action in {'list', 'retrieve'} else IsProcurementOfficerOrAdmin
        return [permission()]

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Supplier.objects.none()
        return Supplier.objects.filter(company=company)

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)

    def destroy(self, request, *args, **kwargs):
        supplier = self.get_object()
        supplier.is_active = False
        supplier.save(update_fields=['is_active', 'updated_at'])
        return Response(status=status.HTTP_204_NO_CONTENT)


class StockMovementViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsCompanyUserReadOnlyOrStorekeeperAdmin]
    serializer_class = StockMovementSerializer
    http_method_names = ['get', 'post', 'head', 'options']
    filterset_class = StockMovementFilter
    search_fields = ['material__name', 'material__code', 'project__name', 'notes', 'purchase_order__number']
    ordering_fields = ['date', 'created_at', 'quantity', 'unit_price']
    ordering = ['-date', '-created_at']

    def get_permissions(self):
        if self.action == 'adjust_valuation':
            permission_classes = [FinanceAdminPermission]
        else:
            permission_classes = [IsCompanyUserReadOnlyOrStorekeeperAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return StockMovement.objects.none()
        return StockMovement.objects.filter(company=company).select_related(
            'material', 'warehouse', 'project', 'purchase_order', 'created_by', 'authorized_by',
        )

    def perform_create(self, serializer):
        material_id = serializer.validated_data['material'].pk
        with transaction.atomic():
            material = Material.objects.select_for_update().get(
                pk=material_id,
                company=self.request.user.company,
            )
            movement = serializer.save(
                company=self.request.user.company,
                created_by=self.request.user,
                material=material,
            )
            transaction.on_commit(lambda: check_low_stock_for_company(movement.company))
            transaction.on_commit(lambda: push_dashboard_update(movement.company))

    def _run_action(self, request, request_serializer, service, **extra):
        payload = request_serializer(data=request.data)
        payload.is_valid(raise_exception=True)
        movement = service(user=request.user, **payload.validated_data, **extra)
        transaction.on_commit(lambda: check_low_stock_for_company(movement.company))
        transaction.on_commit(lambda: push_dashboard_update(movement.company))
        return Response(self.get_serializer(movement).data, status=status.HTTP_201_CREATED)

    @extend_schema(tags=['Inventory Valuation'], request=OpeningBalanceRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='record-opening-balance')
    def record_opening_balance(self, request):
        return self._run_action(
            request, OpeningBalanceRequestSerializer, valuation_services.record_opening_balance,
        )

    @extend_schema(tags=['Inventory Valuation'], request=ValuedReceiptRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='receive-valued-stock')
    def receive_valued_stock(self, request):
        return self._run_action(
            request, ValuedReceiptRequestSerializer, valuation_services.receive_valued_stock,
        )

    @extend_schema(tags=['Inventory Valuation'], request=ProjectIssueRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='issue-stock-to-project')
    def issue_stock_to_project(self, request):
        return self._run_action(
            request, ProjectIssueRequestSerializer, valuation_services.issue_stock_to_project,
        )

    @extend_schema(tags=['Inventory Valuation'], request=ProjectReturnRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='return-stock-from-project')
    def return_stock_from_project(self, request):
        return self._run_action(
            request, ProjectReturnRequestSerializer, valuation_services.return_stock_from_project,
        )

    @action(detail=False, methods=['post'], url_path='dispatch-to-site')
    def dispatch_to_site(self, request):
        payload = SiteTransferRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        transfer = valuation_services.dispatch_to_site(user=request.user, **payload.validated_data)
        return Response(SiteTransferSerializer(transfer).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path=r'site-transfers/(?P<transfer_id>[^/.]+)/acknowledge')
    def acknowledge_site_transfer(self, request, transfer_id=None):
        transfer = valuation_services.acknowledge_site_transfer(user=request.user, site_transfer=transfer_id)
        transaction.on_commit(lambda: push_dashboard_update(transfer.company))
        return Response(SiteTransferSerializer(transfer).data)

    @action(detail=False, methods=['post'], url_path='consume-site-stock')
    def consume_site_stock(self, request):
        return self._run_action(request, SiteTransferRequestSerializer, valuation_services.consume_site_stock)

    @action(detail=False, methods=['post'], url_path='return-site-stock')
    def return_site_stock(self, request):
        return self._run_action(request, SiteReturnRequestSerializer, valuation_services.return_site_stock_to_warehouse)

    @action(detail=False, methods=['get'], url_path='site-transfers')
    def site_transfers(self, request):
        rows = SiteTransfer.objects.filter(company=request.user.company).select_related('project', 'material', 'source_warehouse', 'destination_store', 'acknowledged_by')
        if request.query_params.get('project_site'):
            rows = rows.filter(destination_store__project_site_id=request.query_params['project_site'])
        return Response(SiteTransferSerializer(rows, many=True).data)

    @extend_schema(tags=['Inventory Valuation'], request=SupplierReturnRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='return-stock-to-supplier')
    def return_stock_to_supplier(self, request):
        return self._run_action(
            request, SupplierReturnRequestSerializer, valuation_services.return_stock_to_supplier,
        )

    @extend_schema(tags=['Inventory Valuation'], request=ValuationAdjustmentRequestSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='adjust-valuation')
    def adjust_valuation(self, request):
        return self._run_action(
            request, ValuationAdjustmentRequestSerializer, valuation_services.adjust_valuation,
        )

    @extend_schema(tags=['Inventory Valuation'], request=InventoryActionSerializer, responses=StockMovementSerializer)
    @action(detail=False, methods=['post'], url_path='write-off-damaged-stock')
    def write_off_damaged_stock(self, request):
        return self._run_action(
            request, InventoryActionSerializer, valuation_services.write_off_damaged_stock,
        )

    @extend_schema(tags=['Inventory Valuation'], responses=StockMovementSerializer(many=True))
    @action(detail=False, methods=['get'], url_path='valuation-history')
    def valuation_history(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-date', '-created_at')
        page = self.paginate_queryset(queryset)
        serializer = self.get_serializer(page if page is not None else queryset, many=True)
        if page is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)

    @extend_schema(tags=['Inventory'], summary='Download stock movement register as PDF', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-date', '-created_at')
        rows = [{
            'date': movement.date.isoformat(), 'material': f'{movement.material.code} / {movement.material.name}',
            'direction': movement.get_movement_type_display(), 'transaction': movement.get_transaction_type_display(),
            'project': movement.project.name if movement.project else 'Warehouse',
            'quantity': movement.quantity, 'value': f'UGX {movement.total_cost:,.2f}',
            'recorded_by': movement.created_by.get_full_name() or movement.created_by.username if movement.created_by else '-',
        } for movement in queryset]
        totals = {
            'Movements': len(rows),
            'Stock in quantity': sum((movement.quantity for movement in queryset if movement.movement_type in {StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN}), Decimal('0.00')),
            'Stock out quantity': sum((movement.quantity for movement in queryset if movement.movement_type in {StockMovement.MOVEMENT_OUT, StockMovement.MOVEMENT_ADJUSTMENT_OUT}), Decimal('0.00')),
        }
        return pdf_table_response(
            title='Stock movement register', filename='stock-movements',
            columns=[('date', 'Date'), ('material', 'Material'), ('direction', 'Direction'), ('transaction', 'Transaction'), ('project', 'Project'), ('quantity', 'Quantity'), ('value', 'Value'), ('recorded_by', 'Recorded by')],
            rows=rows, totals=totals, subtitle='Stock in, stock out, returns, and adjustments for the selected filters.',
        )

    @extend_schema(tags=['Inventory'], summary='Download stock movement register as Excel', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-xlsx')
    def download_xlsx(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-date', '-created_at')
        rows = [{
            'date': movement.date, 'material': f'{movement.material.code} / {movement.material.name}',
            'direction': movement.get_movement_type_display(), 'transaction': movement.get_transaction_type_display(),
            'project': movement.project.name if movement.project else 'Warehouse',
            'quantity': movement.quantity, 'value': movement.total_cost,
            'recorded_by': movement.created_by.get_full_name() or movement.created_by.username if movement.created_by else '-',
        } for movement in queryset]
        return xlsx_response({
            'title': 'Stock movement register',
            'columns': [{'key': key, 'label': label} for key, label in [('date', 'Date'), ('material', 'Material'), ('direction', 'Direction'), ('transaction', 'Transaction'), ('project', 'Project'), ('quantity', 'Quantity'), ('value', 'Value'), ('recorded_by', 'Recorded by')]],
            'rows': rows,
            'totals': {'Movements': len(rows), 'Stock in quantity': sum((movement.quantity for movement in queryset if movement.movement_type in {StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN}), Decimal('0.00')), 'Stock out quantity': sum((movement.quantity for movement in queryset if movement.movement_type in {StockMovement.MOVEMENT_OUT, StockMovement.MOVEMENT_ADJUSTMENT_OUT}), Decimal('0.00'))},
        }, 'stock-movements')


class BinLocationViewSet(viewsets.ModelViewSet):
    serializer_class = BinLocationSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['warehouse', 'is_active']
    search_fields = ['code', 'description', 'warehouse__name']
    permission_classes = [IsCompanyUserReadOnlyOrStorekeeperAdmin]

    def get_queryset(self):
        return BinLocation.objects.filter(warehouse__company=self.request.user.company).select_related('warehouse')

    def perform_create(self, serializer):
        warehouse = serializer.validated_data['warehouse']
        if warehouse.company_id != self.request.user.company_id:
            raise ValidationError({'warehouse': ['Select a warehouse in your company.']})
        serializer.save()


class WarehouseViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    serializer_class = WarehouseSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['is_active', 'is_default', 'project_site']
    search_fields = ['name', 'code', 'location']
    ordering_fields = ['name', 'code', 'created_at']
    ordering = ['name']

    def get_permissions(self):
        permission_classes = [IsAuthenticatedCompanyUser] if self.request.method in {'GET', 'HEAD', 'OPTIONS'} else [IsAdminOnly]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        company = self.get_company()
        return Warehouse.objects.for_company(company) if company else Warehouse.objects.none()

    def perform_create(self, serializer):
        serializer.save(company=self.request.user.company)


class InventoryValuationAPIView(APIView):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = InventoryValuationSerializer

    @extend_schema(
        tags=['Inventory Valuation'], responses=InventoryValuationSerializer(many=True),
        parameters=[
            OpenApiParameter('material', int), OpenApiParameter('warehouse', int),
            OpenApiParameter('search', str, description='Material name or code.'),
            OpenApiParameter(
                'ordering', str,
                description='material, warehouse, current_quantity, current_value; prefix with - for descending.',
            ),
        ],
    )
    def get(self, request):
        queryset = StockMovement.objects.filter(company=request.user.company)
        if request.query_params.get('material'):
            queryset = queryset.filter(material_id=request.query_params['material'])
        if request.query_params.get('warehouse'):
            queryset = queryset.filter(warehouse_id=request.query_params['warehouse'])
        if request.query_params.get('project_site'):
            queryset = queryset.filter(warehouse__project_site_id=request.query_params['project_site'])
        if request.query_params.get('search'):
            search = request.query_params['search']
            queryset = queryset.filter(Q(material__name__icontains=search) | Q(material__code__icontains=search))
        rows = queryset.values(
            'material_id', 'material__code', 'material__name',
            'warehouse_id', 'warehouse__code', 'warehouse__name',
        ).annotate(
            current_quantity=Coalesce(Sum('quantity_effect'), Decimal('0.00')),
            current_value=Coalesce(Sum('value_effect'), Decimal('0.00')),
        )
        ordering_map = {
            'material': 'material__name', 'warehouse': 'warehouse__name',
            'current_quantity': 'current_quantity', 'current_value': 'current_value',
        }
        requested_ordering = request.query_params.get('ordering', 'material')
        descending = requested_ordering.startswith('-')
        order_field = ordering_map.get(requested_ordering.lstrip('-'), 'material__name')
        rows = rows.order_by(f'-{order_field}' if descending else order_field, 'warehouse__name')
        data = [{
            'material': row['material_id'],
            'material_code': row['material__code'],
            'material_name': row['material__name'],
            'warehouse': row['warehouse_id'],
            'warehouse_code': row['warehouse__code'],
            'warehouse_name': row['warehouse__name'],
            'current_quantity': row['current_quantity'],
            'current_value': row['current_value'],
            'average_rate': (
                Decimal('0.000000') if row['current_quantity'] == 0
                else valuation_services.rate(row['current_value'] / row['current_quantity'])
            ),
        } for row in rows]
        return paginated_data_response(
            request=request, data=data, serializer_class=self.serializer_class,
        )


class ProjectMaterialCostAPIView(APIView):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = ProjectMaterialCostSerializer

    @extend_schema(
        tags=['Inventory Valuation'], responses=ProjectMaterialCostSerializer(many=True),
        parameters=[
            OpenApiParameter('project', int), OpenApiParameter('material', int),
            OpenApiParameter('search', str, description='Project or material name/code.'),
        ],
    )
    def get(self, request):
        queryset = StockMovement.objects.filter(
            company=request.user.company, project__isnull=False,
            transaction_type__in=[
                StockMovement.TRANSACTION_PROJECT_ISSUE,
                StockMovement.TRANSACTION_PROJECT_RETURN,
            ],
        )
        if request.query_params.get('project'):
            queryset = queryset.filter(project_id=request.query_params['project'])
        if request.query_params.get('material'):
            queryset = queryset.filter(material_id=request.query_params['material'])
        if request.query_params.get('search'):
            search = request.query_params['search']
            queryset = queryset.filter(
                Q(project__name__icontains=search) | Q(project__code__icontains=search)
                | Q(material__name__icontains=search) | Q(material__code__icontains=search)
            )
        rows = queryset.values(
            'project_id', 'project__code', 'project__name',
            'material_id', 'material__code', 'material__name',
        ).annotate(
            issued_quantity=Coalesce(Sum('quantity', filter=Q(
                transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
            )), Decimal('0.00')),
            returned_quantity=Coalesce(Sum('quantity', filter=Q(
                transaction_type=StockMovement.TRANSACTION_PROJECT_RETURN,
            )), Decimal('0.00')),
            issued_cost=Coalesce(Sum('total_cost', filter=Q(
                transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
            )), Decimal('0.00')),
            returned_cost=Coalesce(Sum('total_cost', filter=Q(
                transaction_type=StockMovement.TRANSACTION_PROJECT_RETURN,
            )), Decimal('0.00')),
        ).order_by('project__name', 'material__name')
        data = [{
            'project': row['project_id'], 'project_code': row['project__code'],
            'project_name': row['project__name'], 'material': row['material_id'],
            'material_code': row['material__code'], 'material_name': row['material__name'],
            'issued_quantity': row['issued_quantity'], 'returned_quantity': row['returned_quantity'],
            'net_quantity': row['issued_quantity'] - row['returned_quantity'],
            'net_cost': row['issued_cost'] - row['returned_cost'],
        } for row in rows]
        return paginated_data_response(
            request=request, data=data, serializer_class=self.serializer_class,
        )


class ValuationReconciliationAPIView(APIView):
    permission_classes = [FinanceCompanyPermission]
    serializer_class = ValuationReconciliationSerializer

    @extend_schema(
        tags=['Inventory Valuation'], responses=ValuationReconciliationSerializer(many=True),
        parameters=[OpenApiParameter('material', int), OpenApiParameter('warehouse', int)],
    )
    def get(self, request):
        queryset = StockMovement.objects.filter(company=request.user.company)
        if request.query_params.get('material'):
            queryset = queryset.filter(material_id=request.query_params['material'])
        if request.query_params.get('warehouse'):
            queryset = queryset.filter(warehouse_id=request.query_params['warehouse'])
        rows = queryset.values(
            'material_id', 'warehouse_id',
        ).annotate(
            ledger_quantity=Coalesce(Sum('quantity_effect'), Decimal('0.00')),
            ledger_value=Coalesce(Sum('value_effect'), Decimal('0.00')),
            movement_quantity=Coalesce(Sum(Case(
                When(transaction_type__in=[
                    StockMovement.TRANSACTION_VALUATION_ADJUSTMENT,
                    StockMovement.TRANSACTION_LANDED_COST,
                    StockMovement.TRANSACTION_LANDED_COST_REVERSAL,
                ], then=Value(Decimal('0.00'))),
                When(movement_type__in=[StockMovement.MOVEMENT_IN, StockMovement.MOVEMENT_ADJUSTMENT_IN], then=F('quantity')),
                default=-F('quantity'), output_field=DecimalField(max_digits=18, decimal_places=2),
            )), Decimal('0.00')),
            movement_value=Coalesce(Sum(Case(
                When(transaction_type__in=[
                    StockMovement.TRANSACTION_VALUATION_ADJUSTMENT,
                    StockMovement.TRANSACTION_LANDED_COST,
                    StockMovement.TRANSACTION_LANDED_COST_REVERSAL,
                ], then=F('value_effect')),
                When(quantity_effect__gt=0, then=F('total_cost')),
                default=-F('total_cost'), output_field=DecimalField(max_digits=18, decimal_places=2),
            )), Decimal('0.00')),
        ).order_by('material_id', 'warehouse_id')
        data = []
        for row in rows:
            quantity_variance = row['ledger_quantity'] - row['movement_quantity']
            value_variance = row['ledger_value'] - row['movement_value']
            data.append({
                'material': row['material_id'], 'warehouse': row['warehouse_id'],
                'ledger_quantity': row['ledger_quantity'], 'movement_quantity': row['movement_quantity'],
                'quantity_variance': quantity_variance, 'ledger_value': row['ledger_value'],
                'movement_value': row['movement_value'], 'value_variance': value_variance,
                'status': 'BALANCED' if quantity_variance == 0 and value_variance == 0 else 'VARIANCE',
            })
        return paginated_data_response(
            request=request, data=data, serializer_class=self.serializer_class,
        )


class PurchaseRequestViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = PurchaseRequestSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    filterset_fields = ['project', 'priority', 'status', 'requested_by']
    search_fields = ['number', 'title', 'project__name', 'requested_by__username', 'justification']
    ordering_fields = ['number', 'priority', 'status', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in {'finance_approve', 'finance_reject', 'finance_return', 'finance_hold'}:
            permission_classes = [FinanceReviewPermission]
        elif self.action == 'submit_finance':
            permission_classes = [FinanceSubmissionPermission]
        elif self.action in {'approve', 'reject', 'return_for_correction'}:
            permission_classes = [IsProjectManagerOrAdmin]
        elif self.action == 'issue_stock':
            permission_classes = [IsProcurementOfficerOrAdmin]
        elif self.action == 'fulfill_stock':
            permission_classes = [IsStorekeeperOrAdmin]
        elif self.action in {'create', 'correct', 'partial_update', 'update', 'destroy'}:
            permission_classes = [IsPurchaseRequestSubmitterOrAdmin]
        else:
            permission_classes = [IsAuthenticatedCompanyUser]
        return [permission() for permission in permission_classes]

    def perform_update(self, serializer):
        purchase_request = self.get_object()
        require_draft(
            instance=purchase_request,
            allowed_statuses={PurchaseRequest.STATUS_PENDING, PurchaseRequest.STATUS_RETURNED},
            actor=self.request.user,
            owner_id=purchase_request.requested_by_id,
            owner_label='purchase request',
        )
        if purchase_request.purchase_orders.exists():
            raise ValidationError({'status': 'A purchase request with a purchase order must be corrected through the amendment workflow.'})
        updated = serializer.save()
        audit_lifecycle(instance=updated, actor=self.request.user, action='purchase_request.updated', message='Draft purchase request updated.')

    def perform_destroy(self, instance):
        require_draft(
            instance=instance,
            allowed_statuses={PurchaseRequest.STATUS_PENDING},
            actor=self.request.user,
            owner_id=instance.requested_by_id,
            owner_label='purchase request',
        )
        if instance.purchase_orders.exists():
            raise ValidationError({'status': 'A purchase request with a purchase order cannot be deleted.'})
        audit_lifecycle(instance=instance, actor=self.request.user, action='purchase_request.deleted', message='Draft purchase request deleted.')
        instance.delete()

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return PurchaseRequest.objects.none()
        queryset = purchase_requests_for_user(self.request.user)
        if self.request.query_params.get('project_site'):
            queryset = queryset.filter(work_order_site__project_site_id=self.request.query_params['project_site'])
        queue = self.request.query_params.get('action_queue')
        role = self.request.user.role
        if queue == 'my_requests':
            if role == User.ROLE_PROJECT_MANAGER:
                return queryset.filter(status=PurchaseRequest.STATUS_PENDING).distinct()
            if role == User.ROLE_PROCUREMENT_OFFICER:
                return queryset.filter(status__in=[PurchaseRequest.STATUS_APPROVED, PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED], purchase_orders__isnull=True).distinct()
            if role == User.ROLE_FINANCE_OFFICER:
                return queryset.filter(
                    Q(status=PurchaseRequest.STATUS_PO_CREATED, budget_approval__isnull=True)
                    | Q(status=PurchaseRequest.STATUS_PO_CREATED, budget_approval__status=BudgetApproval.STATUS_RETURNED)
                    | Q(budget_approval__status__in=[BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD])
                ).distinct()
            if role == User.ROLE_FINANCE_MANAGER:
                return queryset.filter(budget_approval__status__in=[BudgetApproval.STATUS_SUBMITTED, BudgetApproval.STATUS_HOLD]).distinct()
            if role == User.ROLE_STOREKEEPER:
                # Keep every requested stock issue visible to the Storekeeper.
                # Finance may still be reviewing it; the serializer exposes the
                # blocker and the fulfil action remains unavailable until clearance.
                return queryset.filter(status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED).distinct()
            if role == User.ROLE_ADMIN:
                return queryset.filter(Q(status=PurchaseRequest.STATUS_PENDING) | Q(status=PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED) | Q(status=PurchaseRequest.STATUS_APPROVED, purchase_orders__isnull=True)).distinct()
        return queryset

    def perform_create(self, serializer):
        # Warehouse replenishment is a procurement-owned technical decision,
        # not site demand. Finance approval remains mandatory before a PO.
        purchase_request, is_warehouse_replenishment = create_purchase_request(
            serializer=serializer, user=self.request.user,
        )
        if is_warehouse_replenishment:
            record_finance_audit_event(
                company=purchase_request.company,
                actor=self.request.user,
                action='warehouse_replenishment.technical_approved',
                object_type='PurchaseRequest',
                object_id=purchase_request.pk,
                message='Procurement created a projectless warehouse replenishment request; Finance approval is required before ordering.',
                metadata={'number': purchase_request.number},
            )
        else:
            transaction.on_commit(lambda: notify_pr_submitted(purchase_request))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))
        record_finance_audit_event(
            company=purchase_request.company,
            actor=self.request.user,
            action='warehouse_replenishment.submitted' if is_warehouse_replenishment else 'purchase_request.submitted',
            object_type='PurchaseRequest',
            object_id=purchase_request.pk,
            metadata={'number': purchase_request.number},
        )

    def create(self, request, *args, **kwargs):
        """An offline retry with the same client UUID returns its original PR."""
        client_uuid = request.data.get('client_uuid')
        if client_uuid:
            existing = PurchaseRequest.objects.filter(
                company=request.user.company, client_uuid=client_uuid,
            ).first()
            if existing:
                return Response(self.get_serializer(existing).data, status=status.HTTP_200_OK)
        return super().create(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        purchase_request = self.get_object()
        try:
            purchase_request = approve_purchase_request(purchase_request=purchase_request, approver=request.user)
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(
            company=purchase_request.company,
            actor=request.user,
            action='purchase_request.technical_approved',
            object_type='PurchaseRequest',
            object_id=purchase_request.pk,
        )
        transaction.on_commit(lambda: notify_pr_approved(purchase_request))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))
        return Response(self.get_serializer(purchase_request).data)

    @action(detail=True, methods=['post'], url_path='approve-stock-issue')
    def approve_stock_issue(self, request, pk=None):
        purchase_request = self.get_object()
        if request.user.role != User.ROLE_ADMIN:
            return Response({'detail': 'Only an Admin can approve a warehouse stock issue.'}, status=status.HTTP_403_FORBIDDEN)
        try:
            purchase_request = approve_stock_issue_request(
                purchase_request=purchase_request,
                approver=request.user,
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(
            company=purchase_request.company,
            actor=request.user,
            action='purchase_request.stock_issue_approved',
            object_type='PurchaseRequest',
            object_id=purchase_request.pk,
            metadata={'number': purchase_request.number},
        )
        transaction.on_commit(lambda: notify_pr_approved(purchase_request))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))
        return Response(self.get_serializer(purchase_request).data)

    @extend_schema(
        tags=['Finance - Approvals'], request=FinanceSubmissionSerializer,
        responses=FinancialApprovalSerializer,
    )
    @action(detail=True, methods=['post'], url_path='submit-finance')
    def submit_finance(self, request, pk=None):
        purchase_request = self.get_object()
        payload = FinanceSubmissionSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        approval = budget_services.submit_purchase_request_to_finance(
            purchase_request=purchase_request, user=request.user, **payload.validated_data,
        )
        return Response(FinancialApprovalSerializer(approval).data)

    @extend_schema(
        tags=['Finance - Approvals'], request=FinanceDecisionSerializer,
        responses=FinancialApprovalSerializer,
    )
    @action(detail=True, methods=['post'], url_path='finance-approve')
    def finance_approve(self, request, pk=None):
        if request.data.get('override') and request.user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
            raise PermissionDenied('Only a Finance Manager or Admin can authorize a budget override.')
        purchase_request = self.get_object()
        payload = FinanceDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = budget_services.review_purchase_request_finance(
            purchase_request=purchase_request, user=request.user,
            decision=BudgetApproval.STATUS_APPROVED, **payload.validated_data,
        )
        return Response(FinancialApprovalSerializer(approval).data)

    def _finance_comment_action(self, request, decision):
        purchase_request = self.get_object()
        payload = RequiredCommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        approval = budget_services.review_purchase_request_finance(
            purchase_request=purchase_request, user=request.user,
            decision=decision, comments=payload.validated_data['comments'],
        )
        return Response(FinancialApprovalSerializer(approval).data)

    @extend_schema(
        tags=['Finance - Approvals'], request=RequiredCommentsSerializer,
        responses=FinancialApprovalSerializer,
    )
    @action(detail=True, methods=['post'], url_path='finance-reject')
    def finance_reject(self, request, pk=None):
        return self._finance_comment_action(request, BudgetApproval.STATUS_REJECTED)

    @extend_schema(
        tags=['Finance - Approvals'], request=RequiredCommentsSerializer,
        responses=FinancialApprovalSerializer,
    )
    @action(detail=True, methods=['post'], url_path='finance-return')
    def finance_return(self, request, pk=None):
        return self._finance_comment_action(request, BudgetApproval.STATUS_RETURNED)

    @extend_schema(tags=['Finance - Approvals'], request=PurchaseRequestCorrectionSerializer, responses=PurchaseRequestSerializer)
    @action(detail=True, methods=['post'])
    def correct(self, request, pk=None):
        purchase_request = self.get_object()
        if purchase_request.requested_by_id != request.user.id and request.user.role != User.ROLE_ADMIN:
            return Response({'detail': 'Only the original requester can correct a returned purchase request.'}, status=status.HTTP_403_FORBIDDEN)
        approval = BudgetApproval.objects.filter(purchase_request=purchase_request, company=request.user.company).first()
        finance_returned = bool(approval and approval.status == BudgetApproval.STATUS_RETURNED)
        technical_returned = purchase_request.status == PurchaseRequest.STATUS_RETURNED
        if not finance_returned and not technical_returned:
            return Response({'detail': 'Only requests returned for correction can be corrected.'}, status=status.HTTP_400_BAD_REQUEST)
        serializer = PurchaseRequestCorrectionSerializer(purchase_request, data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        corrected = serializer.save()
        is_warehouse_replenishment = (
            corrected.project_id is None
            and corrected.requested_by_id is not None
            and corrected.requested_by.role == User.ROLE_PROCUREMENT_OFFICER
        )
        corrected.status = PurchaseRequest.STATUS_APPROVED if is_warehouse_replenishment else PurchaseRequest.STATUS_PENDING
        corrected.technical_return_reason = ''
        corrected.technical_approved_by = None
        corrected.manager_approved_by = None
        corrected.save(update_fields=['status', 'technical_return_reason', 'technical_approved_by', 'manager_approved_by', 'updated_at'])
        record_finance_audit_event(
            company=corrected.company, actor=request.user, action='purchase_request.corrected_after_return',
            object_type='PurchaseRequest', object_id=corrected.pk,
            message=request.data.get('correction_summary', ''), metadata={
                'approval': approval.pk if approval else None,
                'return_source': 'finance' if finance_returned else 'project_manager',
                'technical_reapproval_required': not is_warehouse_replenishment,
                'warehouse_replenishment': is_warehouse_replenishment,
            },
        )
        transaction.on_commit(lambda: push_dashboard_update(corrected.company))
        return Response(self.get_serializer(corrected).data)

    @extend_schema(tags=['Purchase Requests'], request=RequiredCommentsSerializer, responses=PurchaseRequestSerializer)
    @action(detail=True, methods=['post'], url_path='return-for-correction')
    def return_for_correction(self, request, pk=None):
        purchase_request = self.get_object()
        payload = RequiredCommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            purchase_request = return_purchase_request_for_correction(
                purchase_request=purchase_request,
                comments=payload.validated_data['comments'],
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(
            company=purchase_request.company, actor=request.user, action='purchase_request.returned_for_correction',
            object_type='PurchaseRequest', object_id=purchase_request.pk,
            message=purchase_request.technical_return_reason,
            metadata={'number': purchase_request.number, 'requested_by': purchase_request.requested_by_id},
        )
        transaction.on_commit(lambda: notify_pr_returned_for_correction(purchase_request))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))
        return Response(self.get_serializer(purchase_request).data)

    @extend_schema(
        tags=['Finance - Approvals'], request=RequiredCommentsSerializer,
        responses=FinancialApprovalSerializer,
    )
    @action(detail=True, methods=['post'], url_path='finance-hold')
    def finance_hold(self, request, pk=None):
        return self._finance_comment_action(request, BudgetApproval.STATUS_HOLD)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        purchase_request = self.get_object()
        serializer = RejectPurchaseRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            purchase_request = reject_purchase_request(
                purchase_request=purchase_request,
                rejection_reason=serializer.validated_data['rejection_reason'],
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        transaction.on_commit(lambda: notify_pr_rejected(purchase_request))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))
        return Response(self.get_serializer(purchase_request).data)

    @action(detail=True, methods=['post'], url_path='issue-stock')
    def issue_stock(self, request, pk=None):
        purchase_request = self.get_object()
        if purchase_request.project_id is None:
            return Response(
                {'purchase_request': 'Warehouse replenishment requests must be converted to a purchase order; they cannot request stock issue.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if purchase_request.status != PurchaseRequest.STATUS_APPROVED:
            return Response(
                {'detail': 'Only approved purchase requests can be accepted for warehouse stock issue.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not purchase_request.technical_approved_by_id or purchase_request.technical_approved_by.role != User.ROLE_ADMIN:
            return Response(
                {'detail': 'Admin approval is required before Procurement can request warehouse stock issue.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if purchase_request.purchase_orders.exists():
            return Response(
                {'purchase_request': 'This purchase request already has a purchase order and cannot be requested from stock.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not purchase_request.items.exists():
            return Response(
                {'items': 'Purchase request must have at least one item before stock issue can be requested.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        purchase_request.status = PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED
        purchase_request.save(update_fields=['status', 'updated_at'])
        transaction.on_commit(lambda: notify_pr_stock_issue_requested(purchase_request, request.user))
        transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))

        return Response(self.get_serializer(purchase_request).data)

    @action(detail=True, methods=['post'], url_path='fulfill-stock')
    def fulfill_stock(self, request, pk=None):
        with transaction.atomic():
            purchase_request = accessible_purchase_requests(
                request.user,
                PurchaseRequest.objects.select_for_update(),
            ).filter(pk=pk).first()
            if purchase_request is None:
                return Response({'detail': 'Purchase request not found.'}, status=status.HTTP_404_NOT_FOUND)
            if purchase_request.status != PurchaseRequest.STATUS_STOCK_ISSUE_REQUESTED:
                return Response(
                    {'detail': 'Only stock issue requests can be fulfilled by warehouse.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_request.project_id is None:
                return Response(
                    {'purchase_request': 'Warehouse replenishment requests cannot be fulfilled as stock issues.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_request.purchase_orders.exists():
                return Response(
                    {'purchase_request': 'This purchase request already has a purchase order and cannot be issued from stock.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            items = list(purchase_request.items.select_related('material'))
            if not items:
                return Response(
                    {'items': 'Purchase request must have at least one item before stock can be issued.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            locked_materials = Material.objects.select_for_update().filter(
                company=request.user.company,
                pk__in=sorted(item.material_id for item in items),
            ).in_bulk()
            issued_by_item = {
                row['purchase_request_item']: row['issued'] or Decimal('0.00')
                for row in StockMovement.objects.filter(
                    purchase_request=purchase_request,
                    purchase_request_item__isnull=False,
                    movement_type=StockMovement.MOVEMENT_OUT,
                    transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
                ).values('purchase_request_item').annotate(issued=Sum('quantity'))
            }
            outstanding_by_item = {
                item.pk: max(item.quantity - issued_by_item.get(item.pk, Decimal('0.00')), Decimal('0.00'))
                for item in items
            }
            requested_lines = request.data.get('items')
            if requested_lines is None:
                requested_lines = [
                    {'purchase_request_item': item.pk, 'quantity': outstanding_by_item[item.pk]}
                    for item in items if outstanding_by_item[item.pk] > 0
                ]
            if not isinstance(requested_lines, list) or not requested_lines:
                return Response({'items': 'Provide at least one positive quantity to issue.'}, status=status.HTTP_400_BAD_REQUEST)
            issue_by_item = {}
            for index, line in enumerate(requested_lines):
                try:
                    item_id = int(line.get('purchase_request_item'))
                    quantity = Decimal(str(line.get('quantity')))
                except (TypeError, ValueError, ArithmeticError):
                    return Response({'items': {index: 'Each line needs a valid request item and positive quantity.'}}, status=status.HTTP_400_BAD_REQUEST)
                if item_id not in outstanding_by_item or quantity <= 0:
                    return Response({'items': {index: 'Select a request item with a positive outstanding quantity.'}}, status=status.HTTP_400_BAD_REQUEST)
                if item_id in issue_by_item:
                    return Response({'items': {index: 'Each request line may be issued only once per submission.'}}, status=status.HTTP_400_BAD_REQUEST)
                if quantity > outstanding_by_item[item_id]:
                    return Response({'items': {index: f'Cannot issue more than the outstanding quantity of {outstanding_by_item[item_id]}.'}}, status=status.HTTP_400_BAD_REQUEST)
                issue_by_item[item_id] = quantity
            insufficient_items = []
            default_warehouse = valuation_services.get_default_warehouse(request.user.company)
            for item in items:
                quantity = issue_by_item.get(item.pk)
                if not quantity:
                    continue
                material = locked_materials[item.material_id]
                available_stock = valuation_services.available_for_project_issue(
                    company=request.user.company,
                    material=material,
                    warehouse=default_warehouse,
                    project=purchase_request.project,
                )
                if quantity > available_stock:
                    insufficient_items.append(
                        {
                            'material': material.name,
                            'requested_quantity': quantity,
                            'available_stock': available_stock,
                        }
                    )
            if insufficient_items:
                return Response(
                    {
                        'detail': 'Some requested materials do not have enough warehouse stock.',
                        'items': insufficient_items,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in items:
                quantity = issue_by_item.get(item.pk)
                if not quantity:
                    continue
                material = locked_materials[item.material_id]
                notes = f'Warehouse fulfilled stock issue request {purchase_request.number}'
                if item.notes:
                    notes = f'{notes}. {item.notes}'
                valuation_services.issue_stock_to_project(
                    user=request.user,
                    material=material,
                    project=purchase_request.project,
                    quantity=quantity,
                    warehouse=default_warehouse,
                    date=timezone.localdate(),
                    reason=notes,
                    purchase_request=purchase_request,
                    purchase_request_item=item,
                )
            fully_issued = all(
                issued_by_item.get(item.pk, Decimal('0.00')) + issue_by_item.get(item.pk, Decimal('0.00')) >= item.quantity
                for item in items
            )
            purchase_request.status = (
                PurchaseRequest.STATUS_STOCK_ISSUED if fully_issued
                else PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED
            )
            purchase_request.save(update_fields=['status', 'updated_at'])
            if fully_issued:
                transaction.on_commit(lambda: notify_pr_stock_issued(purchase_request))
            else:
                def notify_partial_issue():
                    outstanding = ', '.join(f'{item.material.name}: {max(item.quantity - issued_by_item.get(item.pk, Decimal("0.00")) - issue_by_item.get(item.pk, Decimal("0.00")), Decimal("0.00"))}' for item in items)
                    recipients = [purchase_request.requested_by] if purchase_request.requested_by else []
                    recipients += list(User.objects.filter(company=purchase_request.company, role__in=[User.ROLE_PROCUREMENT_OFFICER, User.ROLE_PROJECT_MANAGER, User.ROLE_ADMIN], is_active=True))
                    for recipient in {user.pk: user for user in recipients if user}.values():
                        send_notification(recipient, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING,
                                          f'Partial stock issue: {purchase_request.number}',
                                          f'Warehouse issued the available quantity. Remaining to source: {outstanding}.',
                                          f'/api/purchase-requests/{purchase_request.pk}/')
                transaction.on_commit(notify_partial_issue)
            transaction.on_commit(lambda: check_low_stock_for_company(purchase_request.company))
            transaction.on_commit(lambda: push_dashboard_update(purchase_request.company))

        return Response(self.get_serializer(purchase_request).data)


    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        queryset = self.filter_queryset(self.get_queryset()).prefetch_related('items__material')
        rows = [{
            'request': request_record.number,
            'project': request_record.project.name if request_record.project_id else '-',
            'title': request_record.title,
            'status': request_record.get_status_display(),
            'priority': request_record.get_priority_display(),
            'requested_by': request_record.requested_by.get_full_name() or request_record.requested_by.username,
            'items': ' | '.join(f'{item.material.name} x {item.quantity}' for item in request_record.items.all()),
            'created': request_record.created_at,
        } for request_record in queryset]
        return _operational_export(
            kind=kind, title='Purchase request register', filename='purchase-request-register',
            columns=[('request', 'Request'), ('project', 'Project'), ('title', 'Title'), ('status', 'Status'), ('priority', 'Priority'), ('requested_by', 'Requested by'), ('items', 'Requested materials'), ('created', 'Created')],
            rows=rows, totals={'Requests': len(rows)},
        )


class PurchaseOrderViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    permission_classes = [IsProcurementOfficerOrAdmin]
    serializer_class = PurchaseOrderSerializer
    http_method_names = ['get', 'post', 'patch', 'delete', 'head', 'options']
    # Deliveries uses this as a real operational queue.  Keeping it server-side
    # prevents warehouse and direct-site POs being mixed across paginated pages.
    filterset_fields = ['purchase_request', 'project', 'status', 'delivery_destination']
    search_fields = ['number', 'supplier_name', 'purchase_request__number', 'project__name', 'notes']
    ordering_fields = ['number', 'status', 'created_at', 'updated_at']
    ordering = ['-created_at']

    def get_permissions(self):
        if self.action in {'list', 'retrieve', 'receive', 'three_way_summary', 'amendments', 'download'}:
            permission_classes = [IsAuthenticatedCompanyUser]
        elif self.action in {'approve_amendment', 'reject_amendment', 'confirm_preapproval_edit'}:
            permission_classes = [FinanceAdminPermission]
        elif self.action in {'partial_update', 'update', 'destroy'}:
            permission_classes = [IsProcurementOfficerOrAdmin]
        else:
            permission_classes = [IsProcurementOfficerOrAdmin]
        return [permission() for permission in permission_classes]

    def perform_update(self, serializer):
        purchase_order = self.get_object()
        require_draft(
            instance=purchase_order,
            allowed_statuses={PurchaseOrder.STATUS_DRAFT},
            actor=self.request.user,
            owner_label='purchase order',
        )
        if purchase_order.goods_received_notes.exists():
            raise ValidationError({'status': 'A purchase order with receipts must be corrected through an amendment or reversal workflow.'})
        updated = serializer.save()
        audit_lifecycle(instance=updated, actor=self.request.user, action='purchase_order.updated', message='Draft purchase order updated.')

    def perform_destroy(self, instance):
        require_draft(instance=instance, allowed_statuses={PurchaseOrder.STATUS_DRAFT}, actor=self.request.user, owner_label='purchase order')
        if instance.goods_received_notes.exists() or instance.supplier_invoices.exists():
            raise ValidationError({'status': 'A purchase order with receipts or invoices cannot be deleted.'})
        audit_lifecycle(instance=instance, actor=self.request.user, action='purchase_order.deleted', message='Draft purchase order deleted.')
        instance.delete()

    @action(detail=True, methods=['get'], url_path='three-way-summary')
    def three_way_summary(self, request, pk=None):
        from apps.finance.matching_services import purchase_order_three_way_summary

        purchase_order = self.get_object()
        return Response({
            'purchase_order': purchase_order.pk,
            'purchase_order_number': purchase_order.number,
            'items': purchase_order_three_way_summary(purchase_order=purchase_order),
        })

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return PurchaseOrder.objects.none()
        queryset = purchase_orders_for_user(self.request.user)
        if self.request.query_params.get('project_site'):
            queryset = queryset.filter(purchase_request__work_order_site__project_site_id=self.request.query_params['project_site'])
        queue = self.request.query_params.get('action_queue')
        if queue == 'warehouse_receipts':
            return queryset.filter(delivery_destination=PurchaseOrder.DELIVERY_WAREHOUSE, status__in=[PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_PARTIAL])
        if queue == 'site_receipts':
            return queryset.filter(delivery_destination=PurchaseOrder.DELIVERY_SITE, status__in=[PurchaseOrder.STATUS_DISPATCH_CONFIRMED, PurchaseOrder.STATUS_PARTIAL])
        if queue == 'site_dispatch':
            return queryset.filter(delivery_destination=PurchaseOrder.DELIVERY_SITE, status=PurchaseOrder.STATUS_ORDERED)
        if queue == 'po_progress':
            return queryset.filter(status__in=[PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING])
        return queryset

    def perform_create(self, serializer):
        purchase_order = create_purchase_order(serializer=serializer, user=self.request.user)
        if purchase_order.purchase_request_id:
            purchase_order.purchase_request.status = PurchaseRequest.STATUS_PO_CREATED
            purchase_order.purchase_request.save(update_fields=['status', 'updated_at'])
            transaction.on_commit(lambda: notify_po_created_from_pr(purchase_order, self.request.user))
        transaction.on_commit(lambda: push_dashboard_update(purchase_order.company))

    def create(self, request, *args, **kwargs):
        requested_status = request.data.get('status')
        if requested_status in {PurchaseOrder.STATUS_ORDERED, PurchaseOrder.STATUS_CANCELLED}:
            return Response(
                {'status': 'Use the dedicated approve or cancel endpoint for this status change.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if requested_status == PurchaseOrder.STATUS_RECEIVED:
            return Response(
                {'status': 'Use the receive endpoint to mark a purchase order as received.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if requested_status == PurchaseOrder.STATUS_DISPATCH_CONFIRMED:
            return Response(
                {'status': 'Use the confirm-dispatch endpoint to confirm direct-to-site dispatch.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().create(request, *args, **kwargs)

    @extend_schema(tags=['Procurement'], request=None, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        purchase_order = budget_services.approve_purchase_order(
            purchase_order=self.get_object(), user=request.user,
        )
        transaction.on_commit(lambda: notify_po_approved(purchase_order))
        transaction.on_commit(lambda: push_dashboard_update(purchase_order.company))
        return Response(self.get_serializer(purchase_order).data)

    @extend_schema(tags=['Procurement'], request=RequiredCommentsSerializer, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        payload = RequiredCommentsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        purchase_order = budget_services.cancel_purchase_order(
            purchase_order=self.get_object(), user=request.user,
            comments=payload.validated_data['comments'],
        )
        transaction.on_commit(lambda: push_dashboard_update(purchase_order.company))
        return Response(self.get_serializer(purchase_order).data)

    @action(detail=False, methods=['post'], url_path=r'from-pr/(?P<purchase_request_id>[^/.]+)')
    def from_pr(self, request, purchase_request_id=None):
        purchase_request = (
            PurchaseRequest.objects.filter(company=request.user.company)
            .prefetch_related('items__material', 'purchase_orders')
            .filter(pk=purchase_request_id)
            .first()
        )
        if purchase_request is None:
            return Response({'detail': 'Purchase request not found.'}, status=status.HTTP_404_NOT_FOUND)
        if purchase_request.status not in {
            PurchaseRequest.STATUS_APPROVED,
            PurchaseRequest.STATUS_PARTIAL_STOCK_ISSUED,
        }:
            return Response(
                {'purchase_request': 'Only approved requests, including partially stock-issued requests, can be converted to a purchase order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Procurement creates a pending, quoted PO before Finance review. The
        # finance clearance guard remains enforced when the PO is approved,
        # dispatched, or received, so this draft cannot become an obligation.
        if purchase_request.purchase_orders.exists():
            return Response(
                {'purchase_request': 'This purchase request already has a purchase order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not purchase_request.items.exists():
            return Response(
                {'items': 'Purchase request must have at least one item before a purchase order can be created.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = request.data.copy()
        payload['purchase_request'] = purchase_request.pk
        payload['project'] = payload.get('project') or purchase_request.project_id
        payload['status'] = payload.get('status') or PurchaseOrder.STATUS_PENDING
        if 'items' not in payload:
            issued_by_item = {
                row['purchase_request_item']: row['issued'] or Decimal('0.00')
                for row in StockMovement.objects.filter(
                    purchase_request=purchase_request,
                    purchase_request_item__isnull=False,
                    movement_type=StockMovement.MOVEMENT_OUT,
                    transaction_type=StockMovement.TRANSACTION_PROJECT_ISSUE,
                ).values('purchase_request_item').annotate(issued=Sum('quantity'))
            }
            payload['items'] = [
                {
                    'material': item.material_id,
                    'quantity': max(item.quantity - issued_by_item.get(item.pk, Decimal('0.00')), Decimal('0.00')),
                    'unit_price': item.material.unit_price,
                    'notes': item.notes,
                }
                for item in purchase_request.items.all()
                if item.quantity - issued_by_item.get(item.pk, Decimal('0.00')) > 0
            ]

        serializer = self.get_serializer(data=payload)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except IntegrityError:
            return Response(
                {'purchase_request': 'This purchase request already has a purchase order.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='confirm-dispatch')
    def confirm_dispatch(self, request, pk=None):
        with transaction.atomic():
            visible_purchase_order = self.get_queryset().filter(pk=pk).first()
            if visible_purchase_order is None:
                return Response({'detail': 'Purchase order not found.'}, status=status.HTTP_404_NOT_FOUND)
            # Lock the PO without the nullable joins from the visibility queryset.
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=visible_purchase_order.pk, company=request.user.company,
            )
            if purchase_order.delivery_destination != PurchaseOrder.DELIVERY_SITE:
                return Response(
                    {'detail': 'Dispatch confirmation is only used for direct-to-site purchase orders.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_order.status == PurchaseOrder.STATUS_RECEIVED:
                return Response(
                    {'detail': 'This purchase order has already been received.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_order.status == PurchaseOrder.STATUS_CANCELLED:
                return Response(
                    {'detail': 'Cancelled purchase orders cannot be dispatched.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_order.status == PurchaseOrder.STATUS_DISPATCH_CONFIRMED:
                return Response(
                    {'detail': 'Dispatch has already been confirmed for this purchase order.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if not purchase_order.purchase_request_id:
                raise ValidationError({
                    'purchase_request': [
                        'A finance-approved purchase request is required before supplier dispatch.'
                    ],
                })
            ensure_budget_clearance(purchase_order.purchase_request)
            budget_services.ensure_purchase_order_committed(purchase_order)
            if not purchase_order.items.exists():
                return Response(
                    {'items': 'A purchase order must have at least one item before dispatch can be confirmed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            purchase_order.status = PurchaseOrder.STATUS_DISPATCH_CONFIRMED
            purchase_order.dispatch_confirmed_by = request.user
            purchase_order.dispatch_confirmed_at = timezone.now()
            purchase_order.save(
                update_fields=[
                    'status',
                    'dispatch_confirmed_by',
                    'dispatch_confirmed_at',
                    'updated_at',
                ]
            )
            transaction.on_commit(lambda: notify_po_dispatch_confirmed(purchase_order))
            transaction.on_commit(lambda: push_dashboard_update(purchase_order.company))
        return Response(self.get_serializer(purchase_order).data)

    @action(detail=True, methods=['post'], url_path='update-delivery')
    def update_delivery(self, request, pk=None):
        purchase_order = self.get_object()
        payload = PurchaseOrderDeliveryUpdateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        for field, value in payload.validated_data.items():
            setattr(purchase_order, field, value)
        purchase_order.delivery_follow_up_owner = request.user
        purchase_order.save()
        due = purchase_order.revised_delivery_date or purchase_order.supplier_confirmed_delivery_date or purchase_order.expected_delivery_date
        if due and due < timezone.localdate() and purchase_order.status not in {PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED}:
            send_notification(request.user, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING, f'Overdue PO: {purchase_order.number}', f'Delivery commitment was due on {due:%d %b %Y}. Follow up with the supplier.', f'/procurement/purchase-orders')
        return Response(self.get_serializer(purchase_order).data)

    @action(detail=True, methods=['post'], url_path='submit-amendment')
    def submit_amendment(self, request, pk=None):
        from apps.procurement.amendments import PurchaseOrderAmendment
        po = self.get_object()
        if po.status != PurchaseOrder.STATUS_ORDERED:
            return Response({'detail': 'Only approved, undelivered purchase orders can be amended. Edit draft or pending purchase orders directly; after supplier dispatch use delivery follow-up only.'}, status=status.HTTP_400_BAD_REQUEST)
        if po.status in {PurchaseOrder.STATUS_RECEIVED, PurchaseOrder.STATUS_CANCELLED} or po.goods_received_notes.exists():
            return Response({'detail': 'Received or cancelled purchase orders cannot be amended.'}, status=status.HTTP_400_BAD_REQUEST)
        if SupplierInvoice.objects.filter(purchase_order=po).exists():
            return Response({'detail': 'A purchase order with an invoice cannot be amended. Use a supplier credit note or a new PO.'}, status=status.HTTP_400_BAD_REQUEST)
        if po.amendments.filter(status=PurchaseOrderAmendment.STATUS_SUBMITTED).exists():
            return Response({'detail': 'A Finance decision is still required for the existing amendment.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = PurchaseOrderAmendmentRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data.copy()
        reason = values.pop('reason').strip()
        if 'supplier' in values:
            supplier = Supplier.objects.filter(pk=values['supplier'], company=po.company, is_active=True).first()
            if not supplier:
                raise ValidationError({'supplier': ['Select an active supplier from this company.']})
        if values.get('delivery_destination') == PurchaseOrder.DELIVERY_SITE and not po.project_id:
            raise ValidationError({'delivery_destination': ['Direct-to-site delivery requires the PO project.']})
        if 'expected_delivery_date' in values:
            values['expected_delivery_date'] = values['expected_delivery_date'].isoformat() if values['expected_delivery_date'] else None
        if 'price_lines' in values:
            locked_items = {item.pk: item for item in po.items.select_for_update().select_related('material')}
            proposed_prices = []
            seen_line_ids = set()
            for index, line in enumerate(values['price_lines'], start=1):
                try:
                    line_id = int(line['purchase_order_item'])
                    proposed_price = Decimal(str(line['unit_price']))
                except (KeyError, TypeError, ValueError, ArithmeticError):
                    raise ValidationError({'price_lines': [f'Line {index} must provide a PO line and a unit price.']})
                po_item = locked_items.get(line_id)
                if not po_item:
                    raise ValidationError({'price_lines': [f'Line {index} is not part of this purchase order.']})
                if line_id in seen_line_ids:
                    raise ValidationError({'price_lines': ['A PO line can only appear once in a price amendment.']})
                if proposed_price < 0:
                    raise ValidationError({'price_lines': [f'Line {index} has an invalid unit price.']})
                if proposed_price == po_item.unit_price:
                    raise ValidationError({'price_lines': [f'Line {index} has no price change.']})
                seen_line_ids.add(line_id)
                proposed_prices.append({
                    'purchase_order_item': line_id,
                    'material': po_item.material_id,
                    'material_name': po_item.material.name,
                    'quantity': str(po_item.quantity),
                    'original_unit_price': str(po_item.unit_price),
                    'unit_price': str(proposed_price),
                    'original_line_total': str(po_item.quantity * po_item.unit_price),
                    'proposed_line_total': str(po_item.quantity * proposed_price),
                })
            values['price_lines'] = proposed_prices
        if 'items' in values:
            material_ids = []
            normalised_items = []
            for index, item in enumerate(values['items'], start=1):
                try:
                    material_id = int(item['material'])
                    quantity = Decimal(str(item['quantity']))
                    unit_price = Decimal(str(item['unit_price']))
                except (KeyError, TypeError, ValueError, ArithmeticError):
                    raise ValidationError({'items': [f'Line {index} must provide material, quantity, and unit_price.']})
                if quantity <= 0 or unit_price < 0:
                    raise ValidationError({'items': [f'Line {index} has an invalid quantity or unit price.']})
                material_ids.append(material_id)
                normalised_items.append({'material': material_id, 'quantity': str(quantity), 'unit_price': str(unit_price), 'notes': str(item.get('notes', ''))[:255]})
            if len(material_ids) != len(set(material_ids)):
                raise ValidationError({'items': ['A material can only appear once on an amended PO.']})
            if Material.objects.filter(pk__in=material_ids, company=po.company, is_active=True).count() != len(material_ids):
                raise ValidationError({'items': ['Every material must be active and belong to this company.']})
            values['items'] = normalised_items
        with transaction.atomic():
            amendment = create_purchase_order_amendment(
                purchase_order=po, user=request.user, reason=reason,
                proposed_values=values,
            )
        record_finance_audit_event(company=po.company, actor=request.user, action='purchase_order.amendment_submitted', object_type='PurchaseOrder', object_id=po.pk, metadata={'amendment_id': amendment.pk, 'version': amendment.version})
        return Response(PurchaseOrderAmendmentSerializer(amendment).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='edit-before-approval')
    def edit_before_approval(self, request, pk=None):
        """Let Procurement correct commercial data before the first Finance decision."""
        po = self.get_object()
        if po.status not in {PurchaseOrder.STATUS_DRAFT, PurchaseOrder.STATUS_PENDING}:
            return Response({'detail': 'Use the controlled amendment workflow after a purchase order has been approved.'}, status=status.HTTP_400_BAD_REQUEST)
        payload = PurchaseOrderPreApprovalEditSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        values = payload.validated_data
        from apps.procurement.amendments import PurchaseOrderAmendment
        if po.amendments.filter(amendment_type=PurchaseOrderAmendment.TYPE_PRE_APPROVAL_EDIT, status=PurchaseOrderAmendment.STATUS_SUBMITTED).exists():
            return Response({'detail': 'Finance must confirm the existing PO edit before another edit can be submitted.'}, status=status.HTTP_400_BAD_REQUEST)
        before_values = purchase_order_amendment_snapshot(po)
        changed_fields = []
        with transaction.atomic():
            po = PurchaseOrder.objects.select_for_update().get(pk=po.pk)
            if 'expected_delivery_date' in values and values['expected_delivery_date'] != po.expected_delivery_date:
                po.expected_delivery_date = values['expected_delivery_date']; changed_fields.append('expected delivery date')
            if 'notes' in values and values['notes'] != po.notes:
                po.notes = values['notes']; changed_fields.append('PO notes')
            if 'price_lines' in values:
                locked_items = {item.pk: item for item in po.items.select_for_update().select_related('material')}
                seen_line_ids = set()
                for index, line in enumerate(values['price_lines'], start=1):
                    try:
                        line_id = int(line['purchase_order_item'])
                        proposed_price = Decimal(str(line['unit_price']))
                    except (KeyError, TypeError, ValueError, ArithmeticError):
                        raise ValidationError({'price_lines': [f'Line {index} must provide a PO line and a unit price.']})
                    po_item = locked_items.get(line_id)
                    if not po_item or line_id in seen_line_ids:
                        raise ValidationError({'price_lines': [f'Line {index} is invalid or repeated.']})
                    if proposed_price < 0 or proposed_price == po_item.unit_price:
                        raise ValidationError({'price_lines': [f'Line {index} must have a different non-negative price.']})
                    seen_line_ids.add(line_id)
                    po_item.unit_price = proposed_price
                    po_item.save(update_fields=['unit_price'])
                changed_fields.append('line prices')
            if not changed_fields:
                raise ValidationError({'detail': 'Provide at least one value that differs from the current PO.'})
            po.save()
            after_values = purchase_order_amendment_snapshot(po)
            version = (po.amendments.select_for_update().order_by('-version').values_list('version', flat=True).first() or 0) + 1
            edit = PurchaseOrderAmendment.objects.create(
                purchase_order=po, company=po.company,
                amendment_type=PurchaseOrderAmendment.TYPE_PRE_APPROVAL_EDIT,
                version=version,
                reason='Pre-approval PO edit submitted for Finance confirmation.',
                original_values=before_values,
                proposed_values={'snapshot': after_values, 'changed_fields': changed_fields},
                submitted_by=request.user,
            )
        record_finance_audit_event(company=po.company, actor=request.user, action='purchase_order.preapproval_edited', object_type='PurchaseOrder', object_id=po.pk, metadata={'amendment_id': edit.pk, 'changed_fields': changed_fields, 'before': before_values, 'after': after_values})
        for recipient in User.objects.filter(company=po.company, role__in=[User.ROLE_FINANCE_OFFICER, User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN], is_active=True):
            send_notification(recipient, Notification.TYPE_SYSTEM, Notification.LEVEL_WARNING, f'PO edit requires Finance confirmation: {po.number}', f'Procurement changed {", ".join(changed_fields)}. Review the before/after values before PO approval.', f'/procurement/purchase-orders?action_queue=po_progress')
        return Response(self.get_serializer(po).data)

    @action(detail=True, methods=['get'])
    def amendments(self, request, pk=None):
        return Response(PurchaseOrderAmendmentSerializer(self.get_object().amendments.select_related('submitted_by', 'decided_by'), many=True).data)

    @action(detail=True, methods=['post'], url_path=r'amendments/(?P<amendment_id>[^/.]+)/approve')
    def approve_amendment(self, request, pk=None, amendment_id=None):
        from apps.procurement.amendments import PurchaseOrderAmendment
        if request.user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
            return Response({'detail': 'Finance Manager approval is required.'}, status=status.HTTP_403_FORBIDDEN)
        data = PurchaseOrderAmendmentDecisionSerializer(data=request.data); data.is_valid(raise_exception=True)
        try:
            po, amendment = approve_purchase_order_amendment(
                purchase_order=self.get_object(), amendment_id=amendment_id,
                user=request.user, comments=data.validated_data['comments'],
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(company=po.company, actor=request.user, action='purchase_order.amendment_approved', object_type='PurchaseOrder', object_id=po.pk, message=data.validated_data['comments'], metadata={'amendment_id': amendment.pk, 'version': amendment.version})
        transaction.on_commit(lambda: push_dashboard_update(po.company))
        return Response(self.get_serializer(po).data)

    @action(detail=True, methods=['post'], url_path='confirm-preapproval-edit')
    def confirm_preapproval_edit(self, request, pk=None):
        data = PurchaseOrderAmendmentDecisionSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            po, edit = confirm_purchase_order_preapproval_edit(
                purchase_order=self.get_object(), user=request.user,
                comments=data.validated_data['comments'],
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(company=po.company, actor=request.user, action='purchase_order.preapproval_edit_confirmed', object_type='PurchaseOrder', object_id=po.pk, message=data.validated_data['comments'], metadata={'amendment_id': edit.pk, 'version': edit.version})
        transaction.on_commit(lambda: push_dashboard_update(po.company))
        return Response(self.get_serializer(po).data)

    @action(detail=True, methods=['post'], url_path=r'amendments/(?P<amendment_id>[^/.]+)/reject')
    def reject_amendment(self, request, pk=None, amendment_id=None):
        if request.user.role not in {User.ROLE_FINANCE_MANAGER, User.ROLE_ADMIN}:
            return Response({'detail': 'Finance Manager approval is required.'}, status=status.HTTP_403_FORBIDDEN)
        data = PurchaseOrderAmendmentDecisionSerializer(data=request.data); data.is_valid(raise_exception=True)
        try:
            po, amendment = reject_purchase_order_amendment(
                purchase_order=self.get_object(), amendment_id=amendment_id,
                user=request.user, comments=data.validated_data['comments'],
            )
        except ValidationError as exc:
            return Response({'detail': str(exc.detail)}, status=status.HTTP_400_BAD_REQUEST)
        record_finance_audit_event(company=po.company, actor=request.user, action='purchase_order.amendment_rejected', object_type='PurchaseOrder', object_id=po.pk, message=data.validated_data['comments'], metadata={'amendment_id': amendment.pk, 'version': amendment.version})
        return Response({'id': amendment.id, 'status': amendment.status})

    @extend_schema(tags=['Procurement'], request=PurchaseOrderReceiptRequestSerializer, responses=PurchaseOrderSerializer)
    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        with transaction.atomic():
            visible_purchase_order = self.get_queryset().filter(pk=pk).first()
            if visible_purchase_order is None:
                return Response({'detail': 'Purchase order not found.'}, status=status.HTTP_404_NOT_FOUND)
            # Lock the PO without the nullable joins from the visibility queryset.
            purchase_order = PurchaseOrder.objects.select_for_update().get(
                pk=visible_purchase_order.pk, company=request.user.company,
            )
            from apps.procurement.amendments import PurchaseOrderAmendment
            if purchase_order.amendments.filter(status=PurchaseOrderAmendment.STATUS_SUBMITTED).exists():
                return Response({'detail': 'Finance must decide the pending PO amendment before receipt can be recorded.'}, status=status.HTTP_400_BAD_REQUEST)

            client_uuid = request.data.get('client_uuid')
            if client_uuid:
                existing_grn = GoodsReceivedNote.objects.filter(
                    company=request.user.company, client_uuid=client_uuid,
                ).first()
                if existing_grn:
                    return Response(self.get_serializer(existing_grn.purchase_order).data, status=status.HTTP_200_OK)

            is_warehouse_delivery = purchase_order.delivery_destination == PurchaseOrder.DELIVERY_WAREHOUSE
            is_site_delivery = purchase_order.delivery_destination == PurchaseOrder.DELIVERY_SITE
            is_storekeeper = request.user.role == User.ROLE_STOREKEEPER
            is_assigned_engineer = bool(
                purchase_order.project_id
                and purchase_order.project.site_engineers.filter(pk=request.user.id).exists()
            )
            is_requesting_engineer = bool(
                purchase_order.purchase_request_id
                and purchase_order.purchase_request.requested_by_id == request.user.id
                and request.user.role == User.ROLE_SITE_ENGINEER
            )
            if is_warehouse_delivery and not is_storekeeper:
                return Response(
                    {'detail': 'Only the Storekeeper can record a warehouse PO receipt and create its GRN.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if is_site_delivery and not (is_storekeeper or is_assigned_engineer or is_requesting_engineer):
                return Response(
                    {'detail': 'Only the assigned site engineer or Storekeeper can record this direct-site GRN.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            if not purchase_order.purchase_request_id:
                raise ValidationError({
                    'purchase_request': [
                        'A finance-approved purchase request is required before receiving a purchase order.'
                    ],
                })
            ensure_budget_clearance(purchase_order.purchase_request)
            if purchase_order.status == PurchaseOrder.STATUS_RECEIVED:
                return Response(
                    {'detail': 'This purchase order has already been received.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if purchase_order.status == PurchaseOrder.STATUS_CANCELLED:
                return Response(
                    {'detail': 'Cancelled purchase orders cannot be received.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            budget_services.ensure_purchase_order_committed(purchase_order)
            if is_site_delivery and purchase_order.status not in {
                PurchaseOrder.STATUS_DISPATCH_CONFIRMED, PurchaseOrder.STATUS_PARTIAL,
            }:
                return Response(
                    {'detail': 'Procurement must confirm supplier dispatch before site receipt can be confirmed.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            payload = PurchaseOrderReceiptRequestSerializer(
                data=request.data, context={'request': request},
            )
            payload.is_valid(raise_exception=True)
            purchase_order, grn = record_goods_received_note(
                purchase_order=purchase_order, user=request.user,
                receipt_date=payload.validated_data['receipt_date'],
                items=payload.validated_data.get('items'),
                notes=payload.validated_data.get('notes', ''),
                client_uuid=payload.validated_data.get('client_uuid'),
            )
            if purchase_order.purchase_request_id and purchase_order.status == PurchaseOrder.STATUS_RECEIVED:
                linked_request = PurchaseRequest.objects.select_for_update().get(
                    pk=purchase_order.purchase_request_id,
                    company=request.user.company,
                )
                if linked_request.status != PurchaseRequest.STATUS_PO_CREATED:
                    linked_request.status = PurchaseRequest.STATUS_PO_CREATED
                    linked_request.save(update_fields=['status', 'updated_at'])
            if purchase_order.status == PurchaseOrder.STATUS_RECEIVED:
                transaction.on_commit(lambda: notify_po_received(purchase_order))
            if is_warehouse_delivery:
                transaction.on_commit(lambda: check_low_stock_for_company(purchase_order.company))
            transaction.on_commit(lambda: push_dashboard_update(purchase_order.company))

        return Response(self.get_serializer(purchase_order).data)


    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        queryset = self.filter_queryset(self.get_queryset()).prefetch_related('items__material')
        rows = [{
            'po': po.number,
            'supplier': po.supplier_name or (po.supplier.name if po.supplier_id else '-'),
            'project': po.project.name if po.project_id else '-',
            'status': po.get_status_display(),
            'destination': po.get_delivery_destination_display(),
            'total': sum((item.quantity * item.unit_price for item in po.items.all()), Decimal('0.00')),
            'items': ' | '.join(f'{item.material.name} x {item.quantity} @ {item.unit_price}' for item in po.items.all()),
            'created': po.created_at,
        } for po in queryset]
        return _operational_export(
            kind=kind, title='Purchase order register', filename='purchase-order-register',
            columns=[('po', 'Purchase order'), ('supplier', 'Supplier'), ('project', 'Project'), ('status', 'Status'), ('destination', 'Destination'), ('total', 'Total'), ('items', 'Order lines'), ('created', 'Created')],
            rows=rows, totals={'Purchase orders': len(rows), 'Order value': sum((row['total'] for row in rows), Decimal('0.00'))},
        )


class GoodsReceivedNoteViewSet(CompanyScopedReadOnlyViewSet):
    serializer_class = GoodsReceivedNoteSerializer
    filterset_fields = ['purchase_order', 'status', 'receipt_date', 'received_by']
    search_fields = ['number', 'purchase_order__number', 'notes']
    ordering_fields = ['number', 'receipt_date', 'created_at']
    ordering = ['-receipt_date', '-created_at']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return GoodsReceivedNote.objects.none()
        return GoodsReceivedNote.objects.filter(company=company).select_related(
            'purchase_order', 'received_by',
        ).prefetch_related('items__purchase_order_item__material')

    @extend_schema(tags=['Procurement'], summary='Download goods received note register as PDF', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-register-pdf')
    def download_register_pdf(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-receipt_date', '-created_at')
        rows = []
        for grn in queryset:
            receiver = grn.received_by.get_full_name() if grn.received_by_id else ''
            line_details = []
            for item in grn.items.all():
                detail = (
                    f'{item.purchase_order_item.material.code} / {item.purchase_order_item.material.name}: '
                    f'accepted {item.accepted_quantity}, rejected {item.rejected_quantity}, damaged {item.damaged_quantity}'
                )
                if item.notes:
                    detail += f' ({item.notes})'
                line_details.append(detail)
            rows.append({
                'grn': grn.number,
                'po': grn.purchase_order.number,
                'date': grn.receipt_date.isoformat(),
                'receiver': receiver or (grn.received_by.username if grn.received_by_id else 'Recorded receiver'),
                'status': grn.get_status_display(),
                'details': ' | '.join(line_details) or '-',
            })
        totals = {
            'GRNs included': len(rows),
            'Accepted quantity': sum((item.accepted_quantity for grn in queryset for item in grn.items.all()), Decimal('0.00')),
            'Rejected quantity': sum((item.rejected_quantity for grn in queryset for item in grn.items.all()), Decimal('0.00')),
            'Damaged quantity': sum((item.damaged_quantity for grn in queryset for item in grn.items.all()), Decimal('0.00')),
        }
        return pdf_table_response(
            title='Goods received note register', filename='goods-received-note-register',
            columns=[('grn', 'GRN'), ('po', 'Purchase order'), ('date', 'Receipt date'), ('receiver', 'Received by'), ('status', 'Status'), ('details', 'Material receipt details')],
            rows=rows, totals=totals,
            subtitle='Company GRN register. Material details show accepted, rejected and damaged quantities for every receipt line.',
        )

    @extend_schema(tags=['Procurement'], summary='Download goods received note register as Excel', responses={200: bytes})
    @action(detail=False, methods=['get'], url_path='download-register-xlsx')
    def download_register_xlsx(self, request):
        queryset = self.filter_queryset(self.get_queryset()).order_by('-receipt_date', '-created_at')
        rows = []
        for grn in queryset:
            rows.append({
                'grn': grn.number, 'po': grn.purchase_order.number, 'date': grn.receipt_date,
                'receiver': grn.received_by.get_full_name() if grn.received_by_id else 'Recorded receiver',
                'status': grn.get_status_display(),
                'accepted': sum((item.accepted_quantity for item in grn.items.all()), Decimal('0.00')),
                'rejected': sum((item.rejected_quantity for item in grn.items.all()), Decimal('0.00')),
                'damaged': sum((item.damaged_quantity for item in grn.items.all()), Decimal('0.00')),
            })
        return xlsx_response({
            'title': 'Goods received note register',
            'columns': [{'key': key, 'label': label} for key, label in [('grn', 'GRN'), ('po', 'Purchase order'), ('date', 'Receipt date'), ('receiver', 'Received by'), ('status', 'Status'), ('accepted', 'Accepted quantity'), ('rejected', 'Rejected quantity'), ('damaged', 'Damaged quantity')]],
            'rows': rows,
            'totals': {'GRNs included': len(rows), 'Accepted quantity': sum((row['accepted'] for row in rows), Decimal('0.00')), 'Rejected quantity': sum((row['rejected'] for row in rows), Decimal('0.00')), 'Damaged quantity': sum((row['damaged'] for row in rows), Decimal('0.00'))},
        }, 'goods-received-note-register')

    @extend_schema(tags=['Procurement'], summary='Download goods received note as PDF', responses={200: bytes})
    @action(detail=True, methods=['get'], url_path='download-pdf')
    def download_pdf(self, request, pk=None):
        grn = self.get_object()
        items = grn.items.select_related('purchase_order_item__material').all()
        rows = [{
            'material': f'{item.purchase_order_item.material.code} / {item.purchase_order_item.material.name}',
            'accepted': item.accepted_quantity,
            'rejected': item.rejected_quantity,
            'damaged': item.damaged_quantity,
            'notes': item.notes or '-',
        } for item in items]
        totals = {
            'Status': grn.get_status_display(),
            'Accepted quantity': sum((item.accepted_quantity for item in items), Decimal('0.00')),
            'Rejected quantity': sum((item.rejected_quantity for item in items), Decimal('0.00')),
            'Damaged quantity': sum((item.damaged_quantity for item in items), Decimal('0.00')),
        }
        receiver = grn.received_by.get_full_name() if grn.received_by_id else ''
        subtitle = ' | '.join(filter(None, [
            f'Purchase order: {grn.purchase_order.number}',
            f'Receipt date: {grn.receipt_date.isoformat()}',
            f'Physically received by: {receiver or (grn.received_by.username if grn.received_by_id else "Recorded receiver")}',
            f'Notes: {grn.notes}' if grn.notes else '',
        ]))
        return pdf_table_response(
            title=f'Goods received note - {grn.number}', filename=grn.number,
            columns=[('material', 'Material'), ('accepted', 'Accepted'), ('rejected', 'Rejected'), ('damaged', 'Damaged'), ('notes', 'Line notes')],
            rows=rows, totals=totals, subtitle=subtitle,
        )


class SupplierClaimViewSet(CompanyScopedReadOnlyViewSet, viewsets.ModelViewSet):
    serializer_class = SupplierClaimSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    filterset_fields = ['status', 'supplier', 'purchase_order', 'project', 'assigned_to']
    search_fields = ['purchase_order__number', 'supplier__name', 'notes', 'supplier_reference']
    ordering_fields = ['status', 'due_date', 'created_at', 'updated_at']
    ordering = ['status', 'due_date', '-created_at']

    def get_permissions(self):
        permission_classes = [IsAuthenticatedCompanyUser] if self.request.method in {'GET', 'HEAD', 'OPTIONS'} or self.action == 'receive_replacement' else [IsProcurementOfficerOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return SupplierClaim.objects.none()
        queryset = SupplierClaim.objects.filter(company=company).select_related(
            'goods_received_note_item__goods_received_note',
            'goods_received_note_item__purchase_order_item__material',
            'replacement_grn_item__goods_received_note',
            'purchase_order', 'supplier', 'project', 'reported_by', 'assigned_to', 'resolved_by',
        )
        user = self.request.user
        if user.role == User.ROLE_SITE_ENGINEER:
            queryset = queryset.filter(Q(project__site_engineers=user) | Q(reported_by=user)).distinct()
        elif user.role == User.ROLE_PROJECT_MANAGER:
            queryset = queryset.filter(project__manager=user)
        queue = self.request.query_params.get('action_queue')
        if queue == 'my_claims':
            queryset = queryset.exclude(status__in=[SupplierClaim.STATUS_RESOLVED, SupplierClaim.STATUS_CANCELLED])
        elif queue == 'site_replacements':
            queryset = queryset.filter(
                purchase_order__delivery_destination=PurchaseOrder.DELIVERY_SITE,
                status__in=[SupplierClaim.STATUS_OPEN, SupplierClaim.STATUS_AWAITING_SUPPLIER, SupplierClaim.STATUS_REPLACEMENT_PENDING, SupplierClaim.STATUS_REPLACEMENT_RECEIVED],
            )
        return queryset

    def perform_update(self, serializer):
        previous_status = serializer.instance.status
        claim = serializer.save()
        if claim.status == SupplierClaim.STATUS_RESOLVED and claim.resolved_at is None:
            claim.resolved_by = self.request.user
            claim.resolved_at = timezone.now()
            claim.save(update_fields=['resolved_by', 'resolved_at', 'updated_at'])
        elif claim.status != SupplierClaim.STATUS_RESOLVED and claim.resolved_at is not None:
            claim.resolved_by = None
            claim.resolved_at = None
            claim.save(update_fields=['resolved_by', 'resolved_at', 'updated_at'])
        if claim.status == SupplierClaim.STATUS_REPLACEMENT_PENDING and previous_status != SupplierClaim.STATUS_REPLACEMENT_PENDING:
            recipients = [claim.reported_by]
            if claim.purchase_order.delivery_destination == PurchaseOrder.DELIVERY_WAREHOUSE:
                recipients.extend(User.objects.filter(company=claim.company, role=User.ROLE_STOREKEEPER, is_active=True))
            elif claim.project_id:
                recipients.extend(claim.project.site_engineers.filter(is_active=True))
            for recipient in {person.pk: person for person in recipients if person}.values():
                send_notification(
                    recipient, Notification.TYPE_SUPPLIER_CLAIM_OPENED, Notification.LEVEL_WARNING,
                    f'Replacement ready: {claim.purchase_order.number}',
                    f'Supplier replacement for {claim.goods_received_note_item.purchase_order_item.material.name} is ready for physical receipt.',
                    f'/procurement/deliveries?replacement_claim={claim.pk}',
                )
        transaction.on_commit(lambda: push_dashboard_update(claim.company))

    @action(detail=True, methods=['post'], url_path='receive-replacement')
    def receive_replacement(self, request, pk=None):
        """Record the supplier's replacement against one rejected/damaged claim."""
        claim = self.get_object()
        po = claim.purchase_order
        is_warehouse = po.delivery_destination == PurchaseOrder.DELIVERY_WAREHOUSE
        assigned_engineer = bool(po.project_id and po.project.site_engineers.filter(pk=request.user.pk).exists())
        allowed = (is_warehouse and request.user.role == User.ROLE_STOREKEEPER) or (
            not is_warehouse and request.user.role in {User.ROLE_STOREKEEPER, User.ROLE_SITE_ENGINEER} and (
                request.user.role == User.ROLE_STOREKEEPER or assigned_engineer or po.purchase_request.requested_by_id == request.user.pk
            )
        )
        if not allowed:
            return Response({'detail': 'Only the responsible receiver can record this supplier replacement.'}, status=status.HTTP_403_FORBIDDEN)
        payload = PurchaseOrderReceiptRequestSerializer(data=request.data, context={'request': request})
        payload.is_valid(raise_exception=True)
        _, grn = record_goods_received_note(
            purchase_order=po, user=request.user, receipt_date=payload.validated_data['receipt_date'],
            items=payload.validated_data.get('items'), notes=payload.validated_data.get('notes', ''),
            client_uuid=payload.validated_data.get('client_uuid'), replacement_claim=claim,
        )
        transaction.on_commit(lambda: push_dashboard_update(claim.company))
        return Response(GoodsReceivedNoteSerializer(grn).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='download/(?P<kind>pdf|xlsx)')
    def download(self, request, kind=None):
        queryset = self.filter_queryset(self.get_queryset())
        rows = [{
            'claim': claim.pk,
            'supplier': claim.supplier.name,
            'po': claim.purchase_order.number,
            'project': claim.project.name if claim.project_id else '-',
            'material': claim.goods_received_note_item.purchase_order_item.material.name,
            'status': claim.get_status_display(),
            'due': claim.due_date or '-',
            'reported_by': claim.reported_by.get_full_name() or claim.reported_by.username,
            'assigned_to': claim.assigned_to.get_full_name() if claim.assigned_to_id else '-',
            'notes': claim.notes or '-',
        } for claim in queryset]
        return _operational_export(
            kind=kind, title='Supplier claims register', filename='supplier-claims-register',
            columns=[('claim', 'Claim'), ('supplier', 'Supplier'), ('po', 'Purchase order'), ('project', 'Project'), ('material', 'Material'), ('status', 'Status'), ('due', 'Due date'), ('reported_by', 'Reported by'), ('assigned_to', 'Assigned to'), ('notes', 'Notes')],
            rows=rows, totals={'Claims': len(rows), 'Open claims': sum(1 for claim in queryset if claim.status not in {SupplierClaim.STATUS_RESOLVED, SupplierClaim.STATUS_CANCELLED})},
        )


class NotificationViewSet(CompanyScopedReadOnlyViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = NotificationSerializer
    filterset_fields = ['notification_type', 'level', 'is_read']
    search_fields = ['title', 'message']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return Notification.objects.none()
        return Notification.objects.for_company(company).for_recipient(self.request.user)

    @action(detail=False, methods=['get'], url_path='unread-count')
    def unread_count(self, request):
        return Response({'unread_count': get_unread_count(request.user, request.user.company)})

    @action(detail=True, methods=['post'], url_path='mark-read')
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_read()
        push_unread_count(request.user, request.user.company)
        return Response(
            {
                'notification': self.get_serializer(notification).data,
                'unread_count': get_unread_count(request.user, request.user.company),
            }
        )

    @action(detail=False, methods=['post'], url_path='mark-all-read')
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True)
        push_unread_count(request.user, request.user.company)
        return Response(
            {
                'updated': updated,
                'unread_count': get_unread_count(request.user, request.user.company),
            }
        )

    @action(detail=False, methods=['get'], url_path='push-config')
    def push_config(self, request):
        public_key = settings.WEB_PUSH_VAPID_PUBLIC_KEY
        return Response({'enabled': bool(public_key), 'public_key': public_key})

    @action(detail=False, methods=['post'], url_path='push-subscription')
    def push_subscription(self, request):
        endpoint = str(request.data.get('endpoint', '')).strip()
        keys = request.data.get('keys') or {}
        p256dh = str(keys.get('p256dh', '')).strip()
        auth = str(keys.get('auth', '')).strip()
        if not endpoint.startswith('https://') or not p256dh or not auth:
            raise ValidationError({'subscription': 'A valid browser push subscription is required.'})
        WebPushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={
                'company': request.user.company,
                'user': request.user,
                'p256dh': p256dh,
                'auth': auth,
                'user_agent': request.headers.get('User-Agent', '')[:512],
            },
        )
        return Response({'enabled': True}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['delete'], url_path='push-subscription')
    def remove_push_subscription(self, request):
        endpoint = str(request.data.get('endpoint', '')).strip()
        WebPushSubscription.objects.filter(
            company=request.user.company, user=request.user, endpoint=endpoint,
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], url_path='send-test-push')
    def send_test_push(self, request):
        notification = Notification.objects.create(
            company=request.user.company,
            recipient=request.user,
            notification_type=Notification.TYPE_SYSTEM,
            level=Notification.LEVEL_INFO,
            title='Phone notifications are working',
            message='This test alert was sent to your subscribed device.',
            link='/notifications',
        )
        from apps.notifications.helpers import send_web_push_notification
        delivered = send_web_push_notification(notification)
        return Response({'delivered': delivered})


class ChatRoomViewSet(CompanyScopedReadOnlyViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = ChatRoomSerializer
    filterset_fields = ['project']
    search_fields = ['project__name', 'project__code']
    ordering_fields = ['created_at', 'project__name']
    ordering = ['project__name']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return ChatRoom.objects.none()
        project_ids = accessible_chat_projects(
            self.request.user,
            Project.objects.all(),
        ).values('pk')
        return ChatRoom.objects.filter(
            company=company,
            project_id__in=project_ids,
        ).select_related('project')


class ChatMessageViewSet(CompanyScopedReadOnlyViewSet):
    permission_classes = [IsAuthenticatedCompanyUser]
    serializer_class = ChatMessageSerializer
    filterset_fields = ['room', 'sender', 'is_system_message']
    search_fields = ['content', 'sender__username', 'room__project__name']
    ordering_fields = ['created_at']
    ordering = ['-created_at']

    def get_queryset(self):
        company = self.get_company()
        if not company:
            return ChatMessage.objects.none()
        project_ids = accessible_chat_projects(
            self.request.user,
            Project.objects.all(),
        ).values('pk')
        return ChatMessage.objects.filter(
            room__company=company,
            room__project_id__in=project_ids,
            is_system_message=False,
        ).select_related('room__project', 'sender')
