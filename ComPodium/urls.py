"""
URL configuration for ComPodium project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
# from django.contrib import admin
from django.urls import path

from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.contrib.sitemaps.views import sitemap
from django.contrib.sitemaps import GenericSitemap

from core.sitemaps import StaticViewSitemap
from accounts import views as accounts_views
from competitions import views as competitions_views
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as static_serve
from competitions.models import Competition
from competitions.serializers import GetTokenView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView

sitemaps = {
    'competitions': GenericSitemap(
        info_dict={
            'queryset': Competition.objects.filter(publication_status='published', approval_status='approved'),
            'date_field': 'comp_date',
        },
        priority=0.9,
        changefreq='weekly',
    ),
    'static': StaticViewSitemap(),
}


urlpatterns = [
    path('dashboard/', admin.site.urls),
    path('auth/', include('django.contrib.auth.urls')),
    path('competitions/', include('competitions.urls', namespace='competitions')),  # HTML views
    path('api/', include('competitions.api_urls')),  # API views
    path('', competitions_views.home, name='home'),
    path('accounts/', include('accounts.urls', namespace='accounts')),
    path('activate/<uidb64>/<token>/', accounts_views.activate, name='activate'),
    path('chat/', include('chat.urls', namespace='chat')),
    path('tinymce/', include('tinymce.urls')),
    path('api_auth/', include('rest_framework.urls')),
    path('api/get-token/', GetTokenView.as_view(), name='get-token'),
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
    path("select2/", include("django_select2.urls")),
    path('sitemap.xml', sitemap, {'sitemaps':sitemaps}, name='django.contrib.sitemaps.views.sitemap'),
    path("robots.txt", static_serve, {"path": "robots.txt", "document_root": settings.STATIC_ROOT}, name="robots"),
    path("BingSiteAuth.xml", static_serve, {"path": "BingSiteAuth.xml", "document_root": settings.STATIC_ROOT}, name="BingSiteAuth"),
    ] + static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

if settings.DEBUG:
    urlpatterns += [path("__reload__/", include("django_browser_reload.urls"))]
