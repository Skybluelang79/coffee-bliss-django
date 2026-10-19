"""Customer notifications for order status changes.

Emails are sent through the configured Django email backend (console in
development, SMTP in production). SMS is intentionally pluggable: set
``SMS_BACKEND`` to a dotted path to a callable ``send(phone, message)`` to
enable it; otherwise messages are logged so the flow is testable offline.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)

# Only these transitions are worth emailing the customer about.
NOTIFY_STATUSES = {
    "confirmed",
    "preparing",
    "ready",
    "out_for_delivery",
    "completed",
    "cancelled",
    "refunded",
}

SUBJECTS = {
    "confirmed": "Your Coffee Bliss order {number} is confirmed",
    "preparing": "Your coffee is being brewed — order {number}",
    "ready": "Your order {number} is ready",
    "out_for_delivery": "Order {number} is on its way",
    "completed": "Order {number} is complete — enjoy!",
    "cancelled": "Order {number} has been cancelled",
    "refunded": "A refund is on the way for order {number}",
}

MESSAGES = {
    "confirmed": "We've received your payment and our baristas are queuing up your order.",
    "preparing": "Good news — your order is on the bar being made right now.",
    "ready": "Your order is ready! Swing by the counter when you can.",
    "out_for_delivery": "Your courier has picked up your order and is heading your way.",
    "completed": "Thanks for choosing Coffee Bliss. We hope every sip was blissful.",
    "cancelled": "This order was cancelled. Any payment made will be refunded to you.",
    "refunded": "We've processed a refund for this order. It may take a few days to appear.",
}


def _base_url():
    return getattr(settings, "SITE_URL", "").rstrip("/")


def _track_url(order):
    return f"{_base_url()}{reverse('orders:track', args=[order.number])}"


def _unsubscribe_url(order):
    return (
        f"{_base_url()}{reverse('orders:notify_pref')}"
        f"?token={order.notification_token()}&off=1"
    )


def send_sms(phone, message):
    """Send an SMS when a backend is configured, otherwise log it."""
    if not phone:
        return False
    backend = getattr(settings, "SMS_BACKEND", "")
    if not backend:
        logger.info("SMS (no backend) to %s: %s", phone, message)
        return False
    try:
        from importlib import import_module

        module_path, _, func_name = backend.rpartition(".")
        func = getattr(import_module(module_path), func_name)
        func(phone, message)
        return True
    except Exception:  # pragma: no cover - never break the request cycle
        logger.exception("SMS send failed")
        return False


def send_status_email(order, status=None):
    """Email the customer about a status change. Returns True when sent."""
    email = order.recipient_email
    if not email or not order.notify_email:
        return False

    status = status or order.status
    if status not in NOTIFY_STATUSES:
        return False

    subject = SUBJECTS.get(status, "Order {number} update").format(number=order.number)
    context = {
        "order": order,
        "status": status,
        "status_display": order.get_status_display(),
        "message": MESSAGES.get(status, ""),
        "site_name": settings.SITE_NAME,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "track_url": _track_url(order),
        "unsubscribe_url": _unsubscribe_url(order),
        "first_name": order.user.get_short_name()
        if order.user_id and order.user
        else order.customer_name.split(" ")[0]
        if order.customer_name
        else "friend",
    }

    text_body = render_to_string("emails/order_status.txt", context)
    html_body = render_to_string("emails/order_status.html", context)
    message = EmailMultiAlternatives(
        subject, text_body, settings.DEFAULT_FROM_EMAIL, [email]
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)

    if order.sms_opt_in and order.customer_phone:
        send_sms(order.customer_phone, f"{subject}. {context['message']}")

    return True


def notify_status_change(order, old_status):
    """Fan out a status-change notification when the status actually changed."""
    if old_status == order.status:
        return False
    return send_status_email(order, order.status)


def mark_ready(order, save=True):
    """Stamp the actual ready time the first time an order is ready."""
    if order.status in {"ready", "out_for_delivery", "completed"} and not order.ready_at:
        order.ready_at = timezone.now()
        if save:
            type(order).objects.filter(pk=order.pk).update(ready_at=order.ready_at)
    return order.ready_at
