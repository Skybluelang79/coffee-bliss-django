from django.conf import settings
from django.utils import timezone

from accounts.demo import DEMO_LOGINS

from .models import Category, Coupon, StoreLocation


def site_context(request):
    """Adds global navigation and business info to every template."""
    cart = getattr(request, "cart", None)
    if cart is None and hasattr(request, "session"):
        from orders.cart import Cart

        cart = Cart(request)

    user = getattr(request, "user", None)
    namespace = getattr(getattr(request, "resolver_match", None), "namespace", "")
    staff_area = bool(
        user
        and user.is_authenticated
        and getattr(user, "is_staff_member", False)
        and namespace in {"dashboard", "inventory"}
    )

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
        "ai_assistant_enabled": bool(getattr(settings, "AI_ENABLED", True)),
        "assistant_surface": "staff" if staff_area else "customer",
        "hero_video_url": getattr(settings, "HERO_VIDEO_URL", ""),
    }
