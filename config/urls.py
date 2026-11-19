from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

from config.health import healthz
from dashboard.views import admin_home, staff_home


def smart_admin(request):
    """Route staff to operations, managers to analytics, superusers to Django admin."""
    user = request.user
    if not user.is_authenticated:
        return redirect("accounts:login")
    if user.is_superuser:
        return redirect("admin:index")
    if user.role == "staff":
        return staff_home(request)
    if user.is_manager:
        return admin_home(request)
    return redirect("store:home")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("staff-portal/", smart_admin, name="staff_portal"),
    path("django-admin/", admin.site.urls),
    path("", include("store.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("inventory/", include("inventory.urls")),
    path("api/", include("api.urls")),
    path("assistant/", include("assistant.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
