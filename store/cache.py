from django.core.cache import cache

from .models import SubscriptionPlan

PLANS_KEY = "store:plans:active"


def active_plans():
    """Return active Coffee Club plans, cached to avoid repeated queries."""
    return cache.get_or_set(
        PLANS_KEY,
        lambda: list(SubscriptionPlan.objects.filter(is_active=True)),
        300,
    )


def invalidate_plans():
    cache.delete(PLANS_KEY)
