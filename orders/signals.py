"""Signals that push order changes to the kitchen display in realtime."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Order


@receiver(post_save, sender=Order, dispatch_uid="coffee_bliss_broadcast_order")
def broadcast_order_update(sender, instance, **kwargs):
    from django.conf import settings

    if not getattr(settings, "KDS_ENABLED", True):
        return

    def _send():
        from .realtime import broadcast_order

        try:
            broadcast_order(instance)
        except Exception:
            # Never let a realtime failure break the request cycle.
            pass

    from django.db import transaction

    transaction.on_commit(_send)
