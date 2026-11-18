"""Card payment integration (Paystack and Stripe).

Paystack is preferred for NGN card payments. When neither Paystack nor Stripe
is configured the platform falls back to a simulated gateway so the whole
flow still works out of the box.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F, Q, Sum

from .models import GiftCardTransaction, Order, OrderStatusHistory, Payment

logger = logging.getLogger(__name__)

PAYSTACK_API_BASE = "https://api.paystack.co"

try:  # stripe is optional at import time
    import stripe
except Exception:  # pragma: no cover
    stripe = None


def is_configured() -> bool:
    """Whether Stripe is ready to accept card payments."""
    return bool(settings.STRIPE_SECRET_KEY) and stripe is not None


def is_paystack_configured() -> bool:
    """Whether Paystack is ready to accept card payments."""
    return bool(settings.PAYSTACK_SECRET_KEY)


def any_provider_configured() -> bool:
    return is_paystack_configured() or is_configured()


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


def available_providers() -> list[str]:
    """Card providers that can be offered on the payment page."""
    providers: list[str] = []
    if is_paystack_configured():
        providers.append("paystack")
    if is_configured() and settings.STRIPE_PUBLISHABLE_KEY:
        providers.append("stripe")
    return providers


# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------


def _order_email(order: Order) -> str:
    if order.user_id and order.user and order.user.email:
        return order.user.email
    return order.guest_email or settings.DEFAULT_FROM_EMAIL


def _paystack_request(method: str, path: str, payload: dict | None = None) -> dict:
    """Call the Paystack API with the secret key from settings."""
    if not is_paystack_configured():
        raise RuntimeError("Paystack is not configured.")

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{PAYSTACK_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        logger.warning("Paystack API error %s: %s", exc.code, detail)
        raise RuntimeError(f"Paystack request failed ({exc.code}).") from exc
    except urllib.error.URLError as exc:
        logger.warning("Paystack API unreachable: %s", exc.reason)
        raise RuntimeError("Could not reach Paystack.") from exc

    result = json.loads(body) if body else {}
    if not result.get("status"):
        raise RuntimeError(result.get("message") or "Paystack request failed.")
    return result


def create_paystack_transaction(
    order: Order,
    *,
    callback_url: str = "",
    payment: Payment | None = None,
) -> dict:
    """Initialize a Paystack transaction and return its checkout details."""
    payment = payment or get_or_create_payment(order)
    reference = f"CBPS-{order.number}-{uuid.uuid4().hex[:10]}"
    payload = {
        "email": _order_email(order),
        "amount": _to_minor_units(order.total),
        "currency": str(settings.PAYSTACK_CURRENCY).upper(),
        "reference": reference,
        "channels": ["card"],
        "metadata": {"order_number": order.number, "order_id": str(order.pk)},
    }
    if callback_url:
        payload["callback_url"] = callback_url

    result = _paystack_request("POST", "/transaction/initialize", payload)
    data = result["data"]

    payment.paystack_reference = data["reference"]
    payment.reference = data["reference"]
    payment.save(update_fields=["paystack_reference", "reference", "updated_at"])
    return {
        "authorization_url": data["authorization_url"],
        "access_code": data.get("access_code", ""),
        "reference": data["reference"],
    }


def verify_paystack_transaction(reference: str) -> dict:
    """Fetch a transaction from Paystack to confirm its final status."""
    result = _paystack_request(
        "GET", f"/transaction/verify/{urllib.parse.quote(reference, safe='')}"
    )
    return result["data"]


def _validate_paystack_data(order: Order, data: dict) -> tuple[bool, str | None]:
    if str(data.get("status", "")).lower() != "success":
        return False, "Payment was not successful."
    if str(data.get("currency", "")).upper() != str(settings.PAYSTACK_CURRENCY).upper():
        return False, "Payment currency does not match the order."
    try:
        paid_amount = int(data.get("amount") or 0)
    except (TypeError, ValueError):
        paid_amount = 0
    if paid_amount < _to_minor_units(order.total):
        return False, "Payment amount is less than the order total."
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    if str(metadata.get("order_number") or "") != order.number:
        return False, "Payment does not belong to this order."
    return True, None


def _find_paystack_order(data: dict) -> Order | None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    order_number = metadata.get("order_number")
    if order_number:
        order = Order.objects.filter(number=order_number).first()
        if order:
            return order

    reference = data.get("reference")
    if reference:
        payment = (
            Payment.objects.select_related("order")
            .filter(Q(reference=reference) | Q(paystack_reference=reference))
            .first()
        )
        if payment:
            return payment.order
    return None


def _record_paystack_success(order: Order, data: dict) -> None:
    reference = str(data.get("reference") or "")
    payment = get_or_create_payment(order)
    payment.paystack_reference = reference
    payment.reference = reference
    payment.save(update_fields=["paystack_reference", "reference", "updated_at"])
    mark_order_paid(order, reference=reference)


def verify_paystack_payment(order: Order, reference: str) -> tuple[bool, str | None]:
    """Verify a Paystack reference server-side and mark the order paid."""
    if not is_paystack_configured():
        return False, "Paystack is not configured."
    if not reference:
        return False, "Missing payment reference."

    try:
        data = verify_paystack_transaction(reference)
    except Exception:
        logger.exception("Paystack verification failed for order %s", order.number)
        return False, "We couldn't verify your payment. Please try again."

    valid, error = _validate_paystack_data(order, data)
    if not valid:
        return False, error

    if order.payment_status == Order.PaymentStatus.PAID:
        return True, None
    if order.payment_status == Order.PaymentStatus.REFUNDED:
        return False, "This order has already been refunded."

    _record_paystack_success(order, data)
    return True, None


def handle_paystack_webhook(payload: bytes, signature: str):
    """Verify and process a Paystack webhook. Returns (handled, message)."""
    if not is_paystack_configured():
        return False, "Paystack not configured."
    if not signature:
        return False, "Missing signature."

    expected = hmac.new(
        settings.PAYSTACK_SECRET_KEY.encode("utf-8"), payload, hashlib.sha512
    ).hexdigest()
    if not hmac.compare_digest(expected, signature):
        return False, "Invalid signature."

    try:
        event = json.loads(payload)
    except (TypeError, ValueError):
        return False, "Invalid payload."

    event_type = event.get("event", "")
    data = event.get("data") or {}

    if event_type == "charge.success":
        order = _find_paystack_order(data)
        if order is None:
            logger.warning("Paystack webhook for unknown order: %s", data.get("reference"))
            return True, "Unknown order."
        valid, error = _validate_paystack_data(order, data)
        if not valid:
            logger.warning("Paystack webhook rejected: %s", error)
            return False, error or "Invalid payment."
        if order.payment_status == Order.PaymentStatus.PAID:
            return True, "Payment already recorded."
        if order.payment_status == Order.PaymentStatus.REFUNDED:
            return True, "Order already refunded."
        _record_paystack_success(order, data)
        return True, "Order marked paid."

    if event_type == "charge.failed":
        order = _find_paystack_order(data)
        if order:
            payment = get_or_create_payment(order)
            if not payment.is_successful:
                payment.state = Payment.State.FAILED
                payment.save(update_fields=["state", "updated_at"])
        return True, "Payment failure recorded."

    return True, f"Ignored event: {event_type}"


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


def reverse_loyalty(order: Order):
    """Return redeemed points and remove rewards for a cancelled/refunded order."""
    if not order.user_id:
        return
    user = order.user
    with transaction.atomic():
        if order.points_used:
            user.add_loyalty_points(
                order.points_used, "adjustment", order=order
            )
            order.points_used = 0
            order.save(update_fields=["points_used"])
        if order.points_earned:
            user.add_loyalty_points(
                -order.points_earned, "adjustment", order=order
            )
            order.points_earned = 0
            order.save(update_fields=["points_earned"])


def release_coupon(order: Order):
    """Give a coupon use back when an order is cancelled or fully refunded."""
    if not order.coupon_id:
        return
    order.coupon.__class__.objects.filter(
        pk=order.coupon_id, used_count__gt=0
    ).update(used_count=F("used_count") - 1)


def mark_order_paid(order: Order, *, reference: str = "", charge_id: str = "", user=None):
    """Mark an order and its payment as paid, then confirm the order."""
    payment = get_or_create_payment(order)
    if order.payment_status == Order.PaymentStatus.PAID and payment.is_successful:
        # Webhooks and callbacks can both report the same payment.
        return payment
    if order.payment_status == Order.PaymentStatus.REFUNDED or order.status in {
        Order.Status.CANCELLED,
        Order.Status.REFUNDED,
    }:
        logger.warning("Ignoring payment for closed order %s", order.number)
        return payment
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

    # Reward points once, at the moment the money is actually collected.
    if order.user_id and not order.points_earned:
        earned = int(order.total * settings.LOYALTY_POINTS_PER_DOLLAR)
        if earned:
            order.points_earned = earned
            order.save(update_fields=["points_earned"])
            order.user.add_loyalty_points(earned, "order", order=order)

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

    outstanding = payment.amount - payment.refunded_amount
    amount = Decimal(amount) if amount is not None else outstanding
    amount = max(Decimal("0.00"), min(amount, outstanding))
    is_full = amount >= outstanding
    if amount <= 0 and not is_full:
        return False, "Refund amount must be greater than zero."

    if amount > 0 and payment.paystack_reference:
        if not is_paystack_configured():
            return False, "Paystack is not configured."
        try:
            _paystack_request(
                "POST",
                "/refund",
                {
                    "transaction": payment.paystack_reference,
                    "amount": _to_minor_units(amount),
                },
            )
        except Exception as exc:
            logger.exception("Paystack refund failed")
            return False, str(exc)
    elif amount > 0 and is_configured() and payment.stripe_payment_intent_id:
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
    if is_full:
        payment.state = Payment.State.REFUNDED
        payment.is_successful = False
        order.payment_status = Order.PaymentStatus.REFUNDED
        order.status = Order.Status.REFUNDED
    else:
        order.payment_status = Order.PaymentStatus.PAID
    payment.save()
    order.save(update_fields=["payment_status", "status", "updated_at"])

    if is_full:
        from inventory.services import restore_for_order

        restore_for_order(order, user=user)
        reverse_loyalty(order)
        release_coupon(order)

    # Return the portion of any applied gift card. Full refunds restore the
    # whole contribution, including orders paid entirely by gift card.
    if order.gift_card_id and order.gift_card_amount:
        if is_full:
            target = order.gift_card_amount
        elif payment.amount > 0:
            target = (
                order.gift_card_amount
                * (payment.refunded_amount / payment.amount)
            ).quantize(Decimal("0.01"))
        else:
            target = Decimal("0.00")
        already = (
            GiftCardTransaction.objects.filter(
                order=order,
                gift_card=order.gift_card,
                kind=GiftCardTransaction.Kind.REFUND,
            ).aggregate(total=Sum("amount"))["total"]
            or Decimal("0.00")
        )
        credit = max(Decimal("0.00"), target - already)
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
        order=order,
        status=order.status,
        changed_by=user,
        note=f"Refunded {amount}",
    )
    return True, None


def _stripe_payment_matches(order: Order, data: dict) -> tuple[bool, str | None]:
    try:
        amount = int(data.get("amount") or 0)
    except (TypeError, ValueError):
        return False, "Invalid payment amount."
    currency = str(data.get("currency") or "").lower()
    if currency and currency != str(settings.STRIPE_CURRENCY).lower():
        return False, "Payment currency does not match the order."
    if amount < _to_minor_units(order.total):
        return False, "Payment amount is less than the order total."
    return True, None


def handle_webhook_event(payload: bytes, sig_header: str):
    """Verify and process a Stripe webhook. Returns (handled: bool, message: str)."""
    if not is_configured():
        return False, "Stripe not configured."
    if not settings.STRIPE_WEBHOOK_SECRET:
        logger.error("Stripe webhook secret is not configured; rejecting event.")
        return False, "Stripe webhook secret is not configured."

    client = _client()
    try:
        event = client.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except Exception as exc:  # signature verification failed
        logger.warning("Stripe webhook rejected: %s", exc)
        return False, "Invalid signature."

    event_type = event["type"] if isinstance(event, dict) else event.type
    data = event["data"]["object"] if isinstance(event, dict) else event.data.object

    if event_type in {"checkout.session.completed", "invoice.paid", "invoice.payment_failed"}:
        from . import subscription_billing

        return subscription_billing.handle_stripe_subscription_event(event_type, data)

    if event_type == "payment_intent.succeeded":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order is None:
            logger.warning("Stripe event for unknown order: %s", order_number)
            return True, "Unknown order."
        if order.payment_status != Order.PaymentStatus.PAID:
            valid, error = _stripe_payment_matches(order, data)
            if not valid:
                logger.warning("Stripe webhook rejected: %s", error)
                return False, error or "Invalid payment."
            charge_id = ""
            charges = data.get("charges", {}).get("data") if data.get("charges") else None
            if charges:
                charge_id = charges[0].get("id", "")
            mark_order_paid(order, reference=data.get("id", ""), charge_id=charge_id)
        return True, "Order marked paid."

    if event_type == "payment_intent.payment_failed":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order and order.payment_status == Order.PaymentStatus.UNPAID:
            payment = get_or_create_payment(order)
            payment.state = Payment.State.FAILED
            payment.save(update_fields=["state", "updated_at"])
        return True, "Payment failure recorded."

    if event_type == "charge.refunded":
        order_number = (data.get("metadata") or {}).get("order_number")
        order = Order.objects.filter(number=order_number).first()
        if order:
            payment = order.payments.filter(is_successful=True).first()
            if payment:
                try:
                    refunded = Decimal(data.get("amount_refunded") or 0) / 100
                except (TypeError, ValueError):
                    refunded = payment.refunded_amount
                if refunded > payment.refunded_amount:
                    previous = payment.refunded_amount
                    payment.refunded_amount = refunded
                    is_full = refunded >= payment.amount
                    if is_full:
                        payment.state = Payment.State.REFUNDED
                        payment.is_successful = False
                        order.payment_status = Order.PaymentStatus.REFUNDED
                        order.status = Order.Status.REFUNDED
                        from inventory.services import restore_for_order

                        restore_for_order(order)
                        reverse_loyalty(order)
                        release_coupon(order)
                    else:
                        order.payment_status = Order.PaymentStatus.PAID
                    payment.save()
                    order.save(
                        update_fields=["payment_status", "status", "updated_at"]
                    )
                    OrderStatusHistory.objects.create(
                        order=order,
                        status=order.status,
                        note=f"Stripe refund {refunded - previous}",
                    )
        return True, "Refund recorded."

    return False, f"Unhandled event: {event_type}"
