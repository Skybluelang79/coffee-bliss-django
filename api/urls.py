from django.urls import include, path
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from . import views

app_name = "api"

router = DefaultRouter()
router.register("products", views.ProductViewSet, basename="product")
router.register("categories", views.CategoryViewSet, basename="category")
router.register("plans", views.SubscriptionPlanViewSet, basename="plan")
router.register("locations", views.StoreLocationViewSet, basename="location")
router.register("orders", views.OrderViewSet, basename="order")
router.register("reservations", views.ReservationViewSet, basename="reservation")

urlpatterns = [
    path("", include(router.urls)),
    path("auth/register/", views.api_register, name="register"),
    path("auth/login/", views.api_login, name="login"),
    path("auth/logout/", views.api_logout, name="logout"),
    path("auth/me/", views.api_me, name="me"),
    path("cart/", views.api_cart, name="cart"),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="api:schema"), name="docs"),
]
