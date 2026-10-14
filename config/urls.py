from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from dashboard.views import admin_home, staff_home


def smart_admin(request):
    """Route staff to the operations board, managers/admins to analytics."""
    user = request.user
    if user.is_authenticated and not user.is_superuser:
        if user.role == "staff":
            return staff_home(request)
    return admin_home(request)


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("", include("store.urls")),
    path("accounts/", include("accounts.urls")),
    path("orders/", include("orders.urls")),
    path("dashboard/", include("dashboard.urls")),
    path("inventory/", include("inventory.urls")),
    path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
