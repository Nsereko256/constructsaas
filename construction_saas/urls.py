"""
URL configuration for construction_saas project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenBlacklistView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.api.authentication import CompanyTokenLogoutAPIView, CompanyTokenObtainPairView, CompanyTokenRefreshView

urlpatterns = [
    path('api/schema/', SpectacularAPIView.as_view(), name='api-schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='api-schema'), name='api-docs'),
    path('api/v1/finance/', include('apps.finance.urls')),
    path('api/', include('apps.api.urls')),
    path('api/token/', CompanyTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', CompanyTokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'),
    path('api/token/logout/', CompanyTokenLogoutAPIView.as_view(), name='token_logout'),
    path('api/', include('apps.workorders.urls')),
    path('api/auth/', include('rest_framework.urls')),
    path('admin/', admin.site.urls),
    path('', include('apps.web.urls')),
]
