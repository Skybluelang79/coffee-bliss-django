"""Signals that push order changes to the kitchen display in realtime and
notify customers when their order progresses."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Order


@receiver(pre_save, sender=Order, dispatch_uid="coffee_bliss_capture_prev_status")
def capture_previous_status(sender, instance, **kwargs):
    """Remember the stored status so we can detect real transitions."""
    if not instance.pk:
        instance._previous_status = None
        return
    instance._previous_status = (
        Order.objects.filter(pk=instance.pk)
        .values_list("status", flat=True)
        .first()
    )


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


@receiver(post_save, sender=Order, dispatch_uid="coffee_bliss_notify_status")
def notify_status(sender, instance, **kwargs):
    """Stamp the ready time and email the customer on real status changes."""
    from django.conf import settings
    from django.db import transaction

    from .notifications import mark_ready, notify_status_change

    old_status = getattr(instance, "_previous_status", None)
    if old_status == instance.status:
        return

    mark_ready(instance, save=True)

    if not getattr(settings, "ORDER_NOTIFICATIONS_ENABLED", True):
        return

    def _notify():
        try:
            notify_status_change(instance, old_status)
        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                "Order status notification failed for %s", instance.number
            )

    transaction.on_commit(_notify)
