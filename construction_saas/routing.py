from apps.dashboard.routing import websocket_urlpatterns as dashboard_websocket_urlpatterns
from apps.notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from apps.projects.routing import websocket_urlpatterns as project_websocket_urlpatterns

websocket_urlpatterns = [
    *dashboard_websocket_urlpatterns,
    *notification_websocket_urlpatterns,
    *project_websocket_urlpatterns,
]
