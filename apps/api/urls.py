from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    CategoryViewSet,
    ChatMessageViewSet,
    ChatRoomViewSet,
    CompanyViewSet,
    CompanyRegistrationAPIView,
    DashboardAPIView,
    GoodsReceivedNoteViewSet,
    SupplierClaimViewSet,
    MaterialViewSet,
    NotificationViewSet,
    InventoryValuationAPIView,
    ProjectMaterialCostAPIView,
    ProjectViewSet,
    ProjectGoalViewSet,
    ProjectSiteViewSet,
    ProjectStaffAssignmentViewSet,
    ApprovalDelegationViewSet,
    PurchaseOrderViewSet,
    PurchaseRequestViewSet,
    PasswordResetConfirmAPIView,
    PasswordResetRequestAPIView,
    ReportsAPIView,
    StockMovementViewSet,
    SupplierViewSet,
    UserViewSet,
    ValuationReconciliationAPIView,
    WarehouseViewSet,
    BinLocationViewSet,
    WorkflowBadgesAPIView,
)


app_name = 'api'

router = DefaultRouter()
router.register('companies', CompanyViewSet, basename='company')
router.register('users', UserViewSet, basename='user')
router.register('categories', CategoryViewSet, basename='category')
router.register('materials', MaterialViewSet, basename='material')
router.register('projects', ProjectViewSet, basename='project')
router.register('project-goals', ProjectGoalViewSet, basename='project-goal')
router.register('project-sites', ProjectSiteViewSet, basename='project-site')
router.register('project-staff-assignments', ProjectStaffAssignmentViewSet, basename='project-staff-assignment')
router.register('approval-delegations', ApprovalDelegationViewSet, basename='approval-delegation')
router.register('suppliers', SupplierViewSet, basename='supplier')
router.register('stock-movements', StockMovementViewSet, basename='stock-movement')
router.register('warehouses', WarehouseViewSet, basename='warehouse')
router.register('bin-locations', BinLocationViewSet, basename='bin-location')
router.register('purchase-requests', PurchaseRequestViewSet, basename='purchase-request')
router.register('purchase-orders', PurchaseOrderViewSet, basename='purchase-order')
router.register('goods-received-notes', GoodsReceivedNoteViewSet, basename='goods-received-note')
router.register('supplier-claims', SupplierClaimViewSet, basename='supplier-claim')
router.register('notifications', NotificationViewSet, basename='notification')
router.register('chat-rooms', ChatRoomViewSet, basename='chat-room')
router.register('chat-messages', ChatMessageViewSet, basename='chat-message')

urlpatterns = [
    path('register-company/', CompanyRegistrationAPIView.as_view(), name='register-company'),
    path('password-reset/', PasswordResetRequestAPIView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmAPIView.as_view(), name='password-reset-confirm'),
    path('workflow-badges/', WorkflowBadgesAPIView.as_view(), name='workflow-badges'),
    path('dashboard/', DashboardAPIView.as_view(), name='dashboard'),
    path('reports/', ReportsAPIView.as_view(), name='reports'),
    path('inventory-valuations/', InventoryValuationAPIView.as_view(), name='inventory-valuations'),
    path('project-material-costs/', ProjectMaterialCostAPIView.as_view(), name='project-material-costs'),
    path('valuation-reconciliation/', ValuationReconciliationAPIView.as_view(), name='valuation-reconciliation'),
    path('', include(router.urls)),
]
