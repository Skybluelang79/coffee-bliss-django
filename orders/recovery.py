"""Abandoned-cart tracking and recovery emails.

Carts live in the session, so we snapshot them into :class:`AbandonedCart`
rows as the customer shops. A management command (or an admin action) then
nudges people who never checked out.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from .cart import Cart
from .models import AbandonedCart

logger = logging.getLogger(__name__)

TRACKED_PATH_PREFIX = "/orders/"


def _snapshot(cart):
    items = []
    for line in cart:
        product = line["product"]
        items.append(
            {
                "product_id": product.pk,
                "name": product.name,
                "slug": product.slug,
                "quantity": line["quantity"],
                "unit_price": str(line["unit_price"]),
            }
        )
    return items


def _known_email(request):
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        return user.email
    if request.method == "POST":
        return (request.POST.get("guest_email") or "").strip()
    return ""


def track_cart(request):
    """Create or refresh the open abandoned cart for the current session."""
    session = getattr(request, "session", None)
    if session is None:
        return None
    cart = Cart(request)
    session_key = session.session_key
    if not session_key:
        if not len(cart):
            return None
        session.save()
        session_key = session.session_key
    if not len(cart):
        AbandonedCart.objects.filter(
            session_key=session_key, status=AbandonedCart.Status.OPEN
        ).update(status=AbandonedCart.Status.EXPIRED)
        return None

    user = getattr(request, "user", None)
    is_authed = bool(user is not None and user.is_authenticated)
    email = _known_email(request)
    items = _snapshot(cart)

    obj, created = AbandonedCart.objects.get_or_create(
        session_key=session_key,
        status=AbandonedCart.Status.OPEN,
        defaults={
            "user": user if is_authed else None,
            "email": email,
            "items": items,
            "item_count": len(cart),
            "subtotal": cart.subtotal,
        },
    )
    if created:
        return obj

    obj.items = items
    obj.item_count = len(cart)
    obj.subtotal = cart.subtotal
    if is_authed:
        obj.user = user
        if not obj.email:
            obj.email = user.email
    elif email and not obj.email:
        obj.email = email
    obj.save()
    return obj


def capture_email(request, email):
    """Attach an email address to the current session's open cart."""
    if not request.session.session_key:
        request.session.save()
    track_cart(request)
    query = AbandonedCart.objects.filter(
        session_key=request.session.session_key, status=AbandonedCart.Status.OPEN
    )
    payload = {"email": email}
    user = getattr(request, "user", None)
    if user is not None and user.is_authenticated:
        payload["user"] = user
    updated = query.update(**payload)
    return updated


def mark_cart_recovered(request, order):
    """Flag carts for this session (or user) as recovered."""
    query = AbandonedCart.objects.filter(status=AbandonedCart.Status.OPEN)
    session_key = getattr(request.session, "session_key", None)
    if session_key:
        query = query.filter(session_key=session_key)
    elif order.user_id:
        query = query.filter(user_id=order.user_id)
    else:
        return 0
    return query.update(
        status=AbandonedCart.Status.RECOVERED,
        order=order,
        recovered_at=timezone.now(),
    )


def eligible_for_recovery(hours=6, max_reminders=2, now=None):
    now = now or timezone.now()
    cutoff = now - timedelta(hours=hours)
    return AbandonedCart.objects.filter(
        status=AbandonedCart.Status.OPEN,
        updated_at__lte=cutoff,
        reminders_sent__lt=max_reminders,
    ).filter(Q(email__gt="") | Q(user__email__gt=""))


def send_recovery_email(abandoned, site_url=None):
    """Send a single recovery email. Returns True when an email was sent."""
    email = abandoned.recipient_email
    if not email:
        return False

    base = (site_url or settings.SITE_URL).rstrip("/")
    context = {
        "abandoned": abandoned,
        "items": abandoned.items,
        "subtotal": abandoned.subtotal,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "site_name": settings.SITE_NAME,
        "cart_url": f"{base}{reverse('orders:cart')}",
        "menu_url": f"{base}{reverse('store:menu')}",
        "first_name": abandoned.user.get_short_name() if abandoned.user_id else "",
    }
    subject = f"You left something delicious behind, {context['first_name'] or 'friend'} ☕"
    text_body = render_to_string("emails/cart_recovery.txt", context)
    html_body = render_to_string("emails/cart_recovery.html", context)

    message = EmailMultiAlternatives(
        subject, text_body, settings.DEFAULT_FROM_EMAIL, [email]
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)

    abandoned.reminders_sent += 1
    abandoned.last_reminder_at = timezone.now()
    abandoned.save(update_fields=["reminders_sent", "last_reminder_at", "updated_at"])
    return True


def run_recovery(hours=6, max_reminders=2, dry_run=False, limit=None, site_url=None):
    """Send reminders to every eligible cart. Returns (sent, considered)."""
    carts = list(eligible_for_recovery(hours=hours, max_reminders=max_reminders))
    if limit is not None:
        carts = carts[:limit]
    sent = 0
    for cart in carts:
        if dry_run:
            sent += 1
            continue
        if send_recovery_email(cart, site_url=site_url):
            sent += 1
    return sent, len(carts)
