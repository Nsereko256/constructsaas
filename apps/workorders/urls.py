from rest_framework.routers import DefaultRouter
from .views import WorkOrderSiteViewSet, WorkOrderViewSet

router = DefaultRouter()
router.register('work-orders', WorkOrderViewSet, basename='work-order')
router.register('work-order-sites', WorkOrderSiteViewSet, basename='work-order-site')
urlpatterns = router.urls
