"""项目总路由。"""
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core import views as core_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", core_views.dashboard, name="dashboard"),
    path("accounts/", include("accounts.urls")),
    path("services/", include("services.urls")),
    path("orders/", include("orders.urls")),
    path("appointments/", include("appointments.urls")),
    path("reports/", include("reports.urls")),
]

handler403 = "core.views.permission_denied"
handler404 = "core.views.page_not_found"

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
