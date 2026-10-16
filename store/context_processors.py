from django.conf import settings
from django.utils import timezone

from .models import Category, Coupon, StoreLocation

# Credentials created by the ``seed`` management command. Only ever exposed to
# templates when DEBUG is on, for quick sign-in during local development.
DEMO_LOGINS = [
    {"label": "Admin", "email": "admin@coffeebliss.test", "password": "admin12345"},
    {"label": "Staff", "email": "staff@coffeebliss.test", "password": "staff12345"},
    {"label": "Customer", "email": "customer1@example.com", "password": "demo12345"},
]


def site_context(request):
    """Adds global navigation and business info to every template."""
    cart = getattr(request, "cart", None)
    if cart is None and hasattr(request, "session"):
        from orders.cart import Cart

        cart = Cart(request)

    return {
        "SITE_NAME": settings.SITE_NAME,
        "DEBUG": settings.DEBUG,
        "demo_logins": DEMO_LOGINS if settings.DEBUG else [],
        "nav_categories": Category.objects.filter(is_active=True)[:8],
        "store_locations": StoreLocation.objects.filter(is_active=True)[:6],
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "cart": cart,
        "cart_count": len(cart) if cart else 0,
        "free_delivery_threshold": settings.FREE_DELIVERY_THRESHOLD,
        "current_year": timezone.now().year,
    }
