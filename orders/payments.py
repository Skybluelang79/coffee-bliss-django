"""Stripe payment integration.

When ``STRIPE_SECRET_KEY`` is not configured the platform falls back to a
simulated gateway so the whole flow still works out of the box.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from .models import GiftCardTransaction, Order, OrderStatusHistory, Payment

logger = logging.getLogger(__name__)

try:  # stripe is optional at import time
    import stripe
except Exception:  # pragma: no cover
    stripe = None


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY) and stripe is not None


def _client():
    stripe.api_key = settings.STRIPE_SECRET_KEY
    return stripe


def _to_minor_units(amount: Decimal) -> int:
    """Convert a decimal amount to the smallest currency unit (cents)."""
    return int((Decimal(amount) * 100).to_integral_value())


def get_or_create_payment(order: Order, method: str = Payment.Method.CARD) -> Payment:
    payment = order.payments.first()
    if payment is None:
        payment = Payment.objects.create(
            order=order, method=method, amount=order.total, state=Payment.State.PENDING
        )
    return payment


def create_payment_intent(order: Order, payment: Payment | None = None, force_simulated: bool = False):
    """Create (or reuse) a Stripe PaymentIntent for an order.

    Returns a dict: {"client_secret": str, "payment_intent_id": str, "simulated": bool}
    """
    payment = payment or get_or_create_payment(order)

    if force_simulated or not is_configured():
        # Simulated mode — no external calls.
        payment.reference = payment.reference or f"SIM-{order.number}"
        payment.state = Payment.State.PENDING
        payment.save()
        return {"client_secret": "", "payment_intent_id": payment.reference, "simulated": True}

    client = _client()
    metadata = {"order_number": order.number, "order_id": str(order.pk)}
    if payment.stripe_payment_intent_id:
        intent = client.PaymentIntent.retrieve(payment.stripe_payment_intent_id)
        if intent.status not in {"succeeded", "canceled"}:
            return {
                "client_secret": intent.client_secret,
                "payment_intent_id": intent.id,
                "simulated": False,
            }

    intent = client.PaymentIntent.create(
        amount=_to_minor_units(order.total),
        currency=settings.STRIPE_CURRENCY,
        automatic_payment_methods={"enabled": True},
        metadata=metadata,
        description=f"Coffee Bliss order {order.number}",
    )
    payment.stripe_payment_intent_id = intent.id
    payment.reference = intent.id
    payment.save(update_fields=["stripe_payment_intent_id", "reference", "updated_at"])
    return {"client_secret": intent.client_secret, "payment_intent_id": intent.id, "simulated": False}


def mark_order_paid(order: Order, *, reference: str = "", charge_id: str = "", user=None):
    """Mark an order and its payment as paid, then confirm the order."""
    payment = get_or_create_payment(order)
    payment.state = Payment.State.SUCCEEDED
    payment.is_successful = True
    if reference:
        payment.reference = reference
    if charge_id:
        payment.stripe_charge_id = charge_id
    payment.save()

    order.payment_status = Order.PaymentStatus.PAID
    if order.status == Order.Status.PENDING:
        order.status = Order.Status.CONFIRMED
    order.save(update_fields=["payment_status", "status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order,
        status=order.status,
        changed_by=user,
        note="Payment received",
    )

    # Deduct inventory now that the order is confirmed.
    from inventory.services import consume_for_order

    consume_for_order(order, user=user)
    return payment


def simulate_success(order: Order, *, user=None):
    """Used by the demo gateway and cash flow."""
    payment = get_or_create_payment(order)
    payment.reference = payment.reference or f"SIM-{order.number}"
    return mark_order_paid(order, reference=payment.reference, user=user)


def refund_order(order: Order, amount: Decimal | None = None, user=None):
    """Refund an order (full or partial) through Stripe or in simulation."""
    payment = order.payments.filter(is_successful=True).first()
    if not payment:
        return False, "No successful payment to refund."

    amount = Decimal(amount) if amount is not None else payment.amount
    amount = min(amount, payment.amount - payment.refunded_amount)

    if is_configured() and payment.stripe_payment_intent_id:
        try:
            client = _client()
            client.Refund.create(
                payment_intent=payment.stripe_payment_intent_id,
                amount=_to_minor_units(amount),
            )
        except Exception as exc:  # pragma: no cover
            logger.exception("Stripe refund failed")
            return False, str(exc)

    payment.refunded_amount = payment.refunded_amount + amount
    if payment.refunded_amount >= payment.amount:
        payment.state = Payment.State.REFUNDED
        payment.is_successful = False
        order.payment_status = Order.PaymentStatus.REFUNDED
    else:
        order.payment_status = Order.PaymentStatus.PAID
    payment.save()
    order.status = Order.Status.REFUNDED
    order.save(update_fields=["payment_status", "status", "updated_at"])

    from inventory.services import restore_for_order

    restore_for_order(order, user=user)

    # Return the portion of any applied gift card, proportional to the amount
    # being refunded (a full refund returns the whole gift card contribution).
    if order.gift_card_id and order.gift_card_amount and payment.amount > 0:
        fraction = amount / payment.amount
        credit = (order.gift_card_amount * fraction).quantize(Decimal("0.01"))
        if credit > 0:
            card = order.gift_card
            credited = card.credit(credit)
            GiftCardTransaction.objects.create(
                gift_card=card,
                order=order,
                kind=GiftCardTransaction.Kind.REFUND,
                amount=credited,
                balance_after=card.balance,
                note=f"Refunded from order {order.number}",
            )

    OrderStatusHistory.objects.create(
        order=order, status=Order.Status.REFUNDED, changed_by=user, note=f"Refunded {amount}"
    )
    return True, None


def handle_webhook_event(payload: bytes, sig_header: str):
    """Verify and process a Stripe webhook. Returns (handled: bool, message: str)."""
    if not is_configured():
        return False, "Stripe not configured."

    client = _client()
    try:
        if settings.STRIPE_WEBHOOK_SECRET:
            event = client.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        else:
            import json

            event = json.loads(payload)
    except Exception as exc:  # signature verification failed
        logger.warning("Stripe webhook rejected: %s", exc)
        return False, "Invalid signature."

    event_type = event["type"] if isinstance(event, dict) else event.type
    data = event["data"]["object"] if isinstance(event, dict) else event.data.object

    if event_type == "payment_intent.succeeded":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order and order.payment_status != Order.PaymentStatus.PAID:
            charge_id = ""
            charges = data.get("charges", {}).get("data") if data.get("charges") else None
            if charges:
                charge_id = charges[0].get("id", "")
            mark_order_paid(order, reference=data.get("id", ""), charge_id=charge_id)
        return True, "Order marked paid."

    if event_type == "payment_intent.payment_failed":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order:
            payment = get_or_create_payment(order)
            payment.state = Payment.State.FAILED
            payment.save(update_fields=["state", "updated_at"])
        return True, "Payment failure recorded."

    if event_type == "charge.refunded":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order:
            order.payment_status = Order.PaymentStatus.REFUNDED
            order.save(update_fields=["payment_status", "updated_at"])
        return True, "Refund recorded."

    return False, f"Unhandled event: {event_type}"
