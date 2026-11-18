"""Coffee Club subscriptions: delivery orders, billing and renewals.

Simulated billing works with no external account. Stripe uses Checkout in
subscription mode; Paystack takes the first payment up front and later cycles
are billed with a payable invoice link.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from . import payments
from .models import Order, OrderItem, Subscription, SubscriptionDelivery

INTERVAL_DAYS = {"weekly": 7, "biweekly": 14, "monthly": 30}


def available_providers() -> list[str]:
    providers = [Subscription.Provider.SIMULATED]
    if payments.is_configured():
        providers.append(Subscription.Provider.STRIPE)
    if payments.is_paystack_configured():
        providers.append(Subscription.Provider.PAYSTACK)
    return providers


def create_subscription(user, plan, *, grind, roast, address, provider) -> Subscription:
    days = INTERVAL_DAYS.get(plan.interval, 30)
    return Subscription.objects.create(
        user=user,
        plan=plan,
        grind=grind,
        roast=roast,
        address=address,
        price=plan.price,
        interval=plan.interval,
        bags_per_delivery=plan.bags_per_delivery,
        provider=provider,
        next_delivery=timezone.now().date() + timedelta(days=days),
    )


def get_or_create_delivery(subscription: Subscription, scheduled_for=None):
    scheduled_for = scheduled_for or subscription.next_delivery or timezone.now().date()
    delivery, _ = SubscriptionDelivery.objects.get_or_create(
        subscription=subscription, scheduled_for=scheduled_for
    )
    return delivery


def create_delivery_order(subscription: Subscription, delivery: SubscriptionDelivery) -> Order:
    address = subscription.address
    order = Order.objects.create(
        user=subscription.user,
        customer_name=subscription.user.get_full_name() or subscription.user.get_short_name(),
        customer_phone=subscription.user.phone or "",
        delivery_address=address.one_line if address else "",
        fulfillment=Order.Fulfillment.DELIVERY,
        note=f"Coffee Club · {subscription.plan.name}",
    )
    OrderItem.objects.create(
        order=order,
        name=f"Coffee Club — {subscription.plan.name}",
        unit_price=subscription.price,
        quantity=1,
        options={
            "grind": subscription.get_grind_display(),
            "roast": subscription.get_roast_display(),
            "bags": subscription.bags_per_delivery,
            "plan": subscription.plan.name,
        },
    )
    # Subscription prices are all-inclusive: no delivery fee or tax is added.
    order.subtotal = subscription.price
    order.discount = Decimal("0.00")
    order.delivery_fee = Decimal("0.00")
    order.tax = Decimal("0.00")
    order.total = subscription.price
    order.save(
        update_fields=[
            "subtotal", "discount", "delivery_fee", "tax", "total", "updated_at"
        ]
    )
    delivery.order = order
    delivery.save(update_fields=["order"])
    return order


def settle_delivery(delivery: SubscriptionDelivery, *, reference: str = "", user=None):
    if delivery.status in {
        SubscriptionDelivery.Status.PAID,
        SubscriptionDelivery.Status.FULFILLED,
    }:
        return delivery.order
    order = delivery.order or create_delivery_order(delivery.subscription, delivery)
    payments.mark_order_paid(order, reference=reference, user=user)
    delivery.status = SubscriptionDelivery.Status.PAID
    delivery.provider_reference = reference or delivery.provider_reference
    delivery.save(update_fields=["status", "provider_reference"])
    subscription = delivery.subscription
    if subscription.status == Subscription.Status.PAST_DUE:
        subscription.resume()
    if subscription.next_delivery and subscription.next_delivery <= delivery.scheduled_for:
        subscription.advance_delivery()
    return order


def send_subscription_email(template_prefix: str, subscription: Subscription, **extra):
    """Queue a subscription email (runs inline when Celery is not configured)."""
    from config.tasks import delay

    from .tasks import send_subscription_email_task

    payload = dict(extra)
    order = payload.pop("order", None)
    if order is not None:
        payload["order_number"] = order.number
    delay(send_subscription_email_task, template_prefix, subscription.pk, payload)


def _send_subscription_email(
    template_prefix: str, subscription: Subscription, **extra
):
    context = {
        "subscription": subscription,
        "site_name": settings.SITE_NAME,
        "currency_symbol": settings.CURRENCY_SYMBOL,
        "manage_url": settings.SITE_URL.rstrip("/")
        + reverse("orders:subscription_manage"),
        **extra,
    }
    subject = f"{settings.SITE_NAME} · {subscription.plan.name} subscription"
    text = render_to_string(f"emails/subscription_{template_prefix}.txt", context)
    html = render_to_string(f"emails/subscription_{template_prefix}.html", context)
    message = EmailMultiAlternatives(
        subject.strip(), text, settings.DEFAULT_FROM_EMAIL, [subscription.user.email]
    )
    message.attach_alternative(html, "text/html")
    message.send(fail_silently=True)


def _stripe_interval(interval: str) -> dict:
    if interval == "weekly":
        return {"interval": "week", "interval_count": 1}
    if interval == "biweekly":
        return {"interval": "week", "interval_count": 2}
    return {"interval": "month", "interval_count": 1}


def start_billing(subscription: Subscription, request) -> str | None:
    """Start the first payment. Returns a provider URL, or None when settled."""
    if subscription.provider == Subscription.Provider.SIMULATED:
        delivery = get_or_create_delivery(subscription)
        order = create_delivery_order(subscription, delivery)
        payments.simulate_success(order, user=subscription.user)
        settle_delivery(delivery, reference=order.payments.first().reference, user=subscription.user)
        send_subscription_email("welcome", subscription)
        return None

    if subscription.provider == Subscription.Provider.STRIPE:
        client = payments._client()
        session = client.checkout.Session.create(
            mode="subscription",
            customer_email=subscription.user.email,
            client_reference_id=str(subscription.pk),
            metadata={"subscription_id": str(subscription.pk)},
            line_items=[
                {
                    "price_data": {
                        "currency": settings.STRIPE_CURRENCY,
                        "product_data": {
                            "name": f"Coffee Club — {subscription.plan.name}"
                        },
                        "unit_amount": payments._to_minor_units(subscription.price),
                        "recurring": _stripe_interval(subscription.interval),
                    },
                    "quantity": 1,
                }
            ],
            success_url=(
                settings.SITE_URL.rstrip("/")
                + reverse("orders:subscription_return")
                + "?session_id={CHECKOUT_SESSION_ID}"
            ),
            cancel_url=settings.SITE_URL.rstrip("/")
            + reverse("orders:subscription_manage"),
        )
        subscription.provider_reference = session.id
        subscription.save(update_fields=["provider_reference"])
        return session.url

    if subscription.provider == Subscription.Provider.PAYSTACK:
        delivery = get_or_create_delivery(subscription)
        order = create_delivery_order(subscription, delivery)
        callback = (
            settings.SITE_URL.rstrip("/")
            + reverse("orders:subscription_paystack_callback", args=[subscription.pk])
        )
        result = payments.create_paystack_transaction(order, callback_url=callback)
        subscription.provider_reference = result["reference"]
        subscription.save(update_fields=["provider_reference"])
        delivery.provider_reference = result["reference"]
        delivery.save(update_fields=["provider_reference"])
        return result["authorization_url"]

    raise ValueError(f"Unsupported billing provider: {subscription.provider}")


def ensure_invoice_order(subscription: Subscription, delivery: SubscriptionDelivery) -> Order:
    order = delivery.order or create_delivery_order(subscription, delivery)
    payment = payments.get_or_create_payment(order)
    payment.state = payment.state if payment.is_successful else payments.Payment.State.PENDING
    payment.save(update_fields=["state", "updated_at"])
    return order


def paystack_invoice_url(order: Order) -> str:
    return (
        settings.SITE_URL.rstrip("/")
        + reverse("orders:payment", args=[order.number])
        + "?provider=paystack"
    )


def _event_data(data) -> dict:
    if isinstance(data, dict):
        return data
    try:
        return dict(data)
    except Exception:  # pragma: no cover - stripe objects are dict-like
        return {}


def handle_stripe_subscription_event(event_type: str, data) -> tuple[bool, str]:
    """Activate, settle or flag a Stripe-backed Coffee Club subscription."""
    payload = _event_data(data)
    metadata = payload.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    reference = payload.get("subscription") or ""
    subscription_id = metadata.get("subscription_id") or payload.get("client_reference_id")
    if subscription_id:
        subscription = Subscription.objects.filter(pk=subscription_id).first()
    elif reference:
        subscription = Subscription.objects.filter(provider_reference=reference).first()
    else:
        subscription = None
    if subscription is None:
        return False, "No matching Coffee Club subscription."

    currency = str(payload.get("currency") or "").lower()
    if currency and currency != str(settings.STRIPE_CURRENCY).lower():
        return False, "Subscription payment currency does not match."

    if event_type == "checkout.session.completed":
        if payload.get("payment_status") and payload["payment_status"] != "paid":
            return False, "Checkout session is not paid."
        if payload.get("amount_total") is not None and int(
            payload["amount_total"]
        ) < payments._to_minor_units(subscription.price):
            return False, "Subscription payment is less than the plan price."
        subscription.provider_reference = reference or subscription.provider_reference
        subscription.status = Subscription.Status.ACTIVE
        subscription.save(update_fields=["provider_reference", "status"])
        send_subscription_email("welcome", subscription)
        return True, "Coffee Club subscription activated."

    if event_type == "invoice.paid":
        if payload.get("amount_paid") is None or int(
            payload["amount_paid"]
        ) < payments._to_minor_units(subscription.price):
            return False, "Subscription invoice amount is less than the plan price."
        invoice_id = str(payload.get("id") or "")
        if SubscriptionDelivery.objects.filter(provider_reference=invoice_id).exists():
            return True, "Invoice already recorded."
        delivery = get_or_create_delivery(subscription)
        settle_delivery(delivery, reference=invoice_id)
        return True, "Coffee Club delivery marked paid."

    if event_type == "invoice.payment_failed":
        subscription.status = Subscription.Status.PAST_DUE
        subscription.save(update_fields=["status"])
        return True, "Coffee Club payment issue recorded."

    return False, f"Unhandled event: {event_type}"
