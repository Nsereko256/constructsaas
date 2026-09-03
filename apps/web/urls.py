from django.urls import path, re_path

from .views import ReactAppView, ServiceWorkerView


app_name = 'web'

urlpatterns = [
    path('sw.js', ServiceWorkerView.as_view(), name='service-worker'),
    path('', ReactAppView.as_view(), name='app'),
    re_path(r'^(?!static/).+$', ReactAppView.as_view(), name='react-route'),
]
