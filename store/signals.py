from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .cache import invalidate_plans
from .models import SubscriptionPlan


@receiver([post_save, post_delete], sender=SubscriptionPlan)
def clear_plan_cache(sender, instance, **kwargs):
    invalidate_plans()
