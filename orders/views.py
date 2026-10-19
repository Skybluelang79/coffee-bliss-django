from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payments
from .cart import Cart
from .forms import CartEmailForm, CheckoutForm, OrderFeedbackForm, ReservationForm
from .models import (
    GiftCard,
    GiftCardTransaction,
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    Reservation,
)


def cart_detail(request):
    cart = Cart(request)
    return render(request, "orders/cart.html", {"cart": cart})


@require_POST
def cart_add(request, product_id):
    from store.models import Product

    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id, is_active=True)
    if not product.in_stock:
        messages.error(request, f"Sorry, {product.name} is out of stock.")
        return redirect(product.get_absolute_url())
    try:
        quantity = max(1, int(request.POST.get("quantity", 1)))
    except (TypeError, ValueError):
        quantity = 1
    options = {}
    size = request.POST.get("size")
    milk = request.POST.get("milk")
    extras = request.POST.getlist("extras")
    if size:
        options["size"] = size
    if milk:
        options["milk"] = milk
    if extras:
        options["extras"] = extras
    cart.add(product, quantity=quantity, options=options)
    messages.success(request, f"Added {quantity} × {product.name} to your cart.")
    if request.POST.get("buy_now"):
        return redirect("orders:checkout")
    return redirect(request.POST.get("next") or reverse("orders:cart"))


@require_POST
def cart_update(request, product_id):
    cart = Cart(request)
    try:
        quantity = int(request.POST.get("quantity", 1))
    except (TypeError, ValueError):
        quantity = 1
    cart.update(product_id, quantity)
    messages.info(request, "Cart updated.")
    return redirect("orders:cart")


@require_POST
def cart_remove(request, product_id):
    cart = Cart(request)
    cart.remove(product_id)
    messages.info(request, "Item removed from cart.")
    return redirect("orders:cart")


@require_POST
def apply_coupon(request):
    from store.models import Coupon

    cart = Cart(request)
    code = request.POST.get("code", "").strip()
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if coupon and coupon.is_valid:
        cart.set_coupon(coupon)
        messages.success(request, f"Promo code {coupon.code} applied!")
    else:
        cart.set_coupon(None)
        messages.error(request, "That promo code is invalid or expired.")
    return redirect("orders:cart")


@require_POST
def apply_gift_card(request):
    cart = Cart(request)
    card, error = GiftCard.lookup(request.POST.get("code", ""))
    if card:
        cart.set_gift_card(card.code)
        messages.success(request, f"Gift card {card.code} applied!")
    else:
        cart.set_gift_card(None)
        messages.error(request, error)
    return redirect(request.POST.get("next") or reverse("orders:cart"))


@require_POST
def remove_gift_card(request):
    cart = Cart(request)
    cart.set_gift_card(None)
    messages.info(request, "Gift card removed.")
    return redirect("orders:cart")


@require_POST
def capture_cart_email(request):
    from .recovery import capture_email

    cart = Cart(request)
    if not len(cart):
        messages.info(request, "Add something to your cart first.")
        return redirect("orders:cart")
    form = CartEmailForm(request.POST)
    if form.is_valid():
        capture_email(request, form.cleaned_data["email"])
        messages.success(
            request, "Saved! We'll email you if you leave something behind."
        )
    else:
        messages.error(request, "Please enter a valid email address.")
    return redirect("orders:cart")


@login_required
def checkout(request):
    cart = Cart(request)
    if not len(cart):
        messages.info(request, "Your cart is empty — add something delicious first.")
        return redirect("store:menu")

    initial = {"fulfillment": Order.Fulfillment.PICKUP}
    if request.user.is_authenticated:
        initial["customer_name"] = request.user.get_full_name() or request.user.get_short_name()
        initial["customer_phone"] = request.user.phone
        default_address = request.user.addresses.filter(is_default=True).first()
        if default_address:
            initial["delivery_address"] = default_address.one_line
    if cart.get_coupon():
        initial["coupon_code"] = cart.get_coupon().code

    if request.method == "POST":
        form = CheckoutForm(request.POST)
        if form.is_valid():
            order = _create_order(request, cart, form)
            method = form.cleaned_data.get("payment_method") or "card"
            cart.clear()

            if order.total <= 0:
                payments.simulate_success(
                    order, user=request.user if request.user.is_authenticated else None
                )
                messages.success(
                    request,
                    f"Order {order.number} placed — fully covered by your gift card! ☕",
                )
                return redirect("orders:order_confirmation", number=order.number)

            if method == "cash":
                payments.simulate_success(order, user=request.user if request.user.is_authenticated else None)
                messages.success(request, f"Order {order.number} placed! Pay on {order.get_fulfillment_display().lower()}.")
                return redirect("orders:order_confirmation", number=order.number)

            # Card: always take the payment step (the demo gateway renders
            # automatically when no Stripe keys are configured).
            return redirect("orders:payment", number=order.number)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = CheckoutForm(initial=initial)

    return render(request, "orders/checkout.html", {"cart": cart, "form": form})


def _create_order(request, cart, form):
    data = form.cleaned_data
    order = Order(
        user=request.user if request.user.is_authenticated else None,
        guest_email="",
        fulfillment=data["fulfillment"],
        location=data.get("location"),
        customer_name=data["customer_name"],
        customer_phone=data.get("customer_phone", ""),
        delivery_address=data.get("delivery_address", ""),
        note=data.get("note", ""),
        points_used=cart.points_used if request.user.is_authenticated else 0,
        loyalty_discount=cart.loyalty_discount if request.user.is_authenticated else 0,
    )
    if data.get("coupon_code"):
        from store.models import Coupon

        order.coupon = Coupon.objects.filter(code__iexact=data["coupon_code"]).first()

    gift_card = cart.get_gift_card()
    if gift_card and gift_card.is_usable:
        order.gift_card = gift_card

    order.save()
    for line in cart:
        OrderItem.objects.create(
            order=order,
            product=line["product"],
            name=line["product"].name,
            unit_price=line["unit_price"],
            quantity=line["quantity"],
            options=line["options"],
        )
    order = order.recalculate()
    order.save()
    order.notify_email = True
    order.ensure_estimated_ready_at()

    # Redeem the gift card now that the order total is known.
    if order.gift_card_id and order.gift_card_amount:
        applied = order.gift_card.redeem(order.gift_card_amount)
        if applied != order.gift_card_amount:
            order.gift_card_amount = applied
            order.save(update_fields=["gift_card_amount"])
        GiftCardTransaction.objects.create(
            gift_card=order.gift_card,
            order=order,
            kind=GiftCardTransaction.Kind.REDEMPTION,
            amount=-applied,
            balance_after=order.gift_card.balance,
            note=f"Applied to order {order.number}",
        )

    # Redeem loyalty points
    if order.points_used and request.user.is_authenticated:
        request.user.add_loyalty_points(-order.points_used, "redemption", order=order)

    # Earn loyalty points
    if request.user.is_authenticated:
        earned = int(order.total * settings.LOYALTY_POINTS_PER_DOLLAR)
        order.points_earned = earned
        order.save(update_fields=["points_earned"])
        request.user.add_loyalty_points(earned, "order", order=order)

    # Create a pending payment record; confirmation happens via Stripe/cash.
    payments.get_or_create_payment(order, method=data.get("payment_method", "card"))

    OrderStatusHistory.objects.create(
        order=order,
        status=Order.Status.PENDING,
        changed_by=request.user if request.user.is_authenticated else None,
        note="Order placed",
    )

    if order.coupon:
        order.coupon.used_count += 1
        order.coupon.save(update_fields=["used_count"])

    from .recovery import mark_cart_recovered

    mark_cart_recovered(request, order)
    return order


def payment_page(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:order_confirmation", number=order.number)

    provider_error = ""
    intent = None
    use_stripe = payments.is_configured() and bool(settings.STRIPE_PUBLISHABLE_KEY)
    if use_stripe:
        try:
            intent = payments.create_payment_intent(order)
        except Exception as exc:  # bad keys, unsupported currency, network…
            import logging

            logging.getLogger(__name__).warning(
                "Payment intent failed for %s: %s", order.number, exc
            )
            provider_error = (
                "We couldn't reach the payment provider, so the demo gateway "
                "below is ready to use — no real money moves in demo mode."
            )
    if intent is None:
        intent = payments.create_payment_intent(order, force_simulated=True)
    return render(
        request,
        "orders/payment.html",
        {
            "order": order,
            "client_secret": intent["client_secret"],
            "payment_intent_id": intent["payment_intent_id"],
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "simulated": intent["simulated"],
            "provider_error": provider_error,
            "currency": settings.CURRENCY_SYMBOL,
        },
    )


@require_POST
def payment_simulate(request, number):
    """Demo gateway: mark a simulated card payment as successful."""
    order = get_object_or_404(Order, number=number)
    if not payments.is_configured():
        payments.simulate_success(order, user=request.user if request.user.is_authenticated else None)
        messages.success(request, f"Payment received for order {order.number}.")
        return redirect("orders:order_confirmation", number=order.number)
    return redirect("orders:payment", number=order.number)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    handled, message = payments.handle_webhook_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""))
    from django.http import HttpResponse

    return HttpResponse(message, status=200 if handled else 400)


def order_confirmation(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    return render(request, "orders/confirmation.html", {"order": order})


def track_order(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items", "history").select_related(
            "location", "user"
        ),
        number=number,
    )
    if order.estimated_ready_at is None:
        order.ensure_estimated_ready_at()
    is_owner = request.user.is_authenticated and (
        order.user_id == request.user.id or request.user.is_staff_member
    )
    return render(
        request,
        "orders/track.html",
        {
            "order": order,
            "steps": order.timeline(),
            "eta_seconds": order.eta_seconds_left,
            "is_owner": is_owner,
            "rating_choices": [5, 4, 3, 2, 1],
        },
    )


def track_status(request, number):
    """JSON snapshot used by the live-updating tracking page."""
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    return JsonResponse(
        {
            "number": order.number,
            "status": order.status,
            "status_display": order.get_status_display(),
            "status_color": order.status_color,
            "updated_at": order.updated_at.isoformat(),
            "eta_seconds": order.eta_seconds_left,
            "eta_minutes": order.eta_minutes,
            "estimated_ready_at": order.estimated_ready_at.isoformat()
            if order.estimated_ready_at
            else None,
            "ready_at": order.ready_at.isoformat() if order.ready_at else None,
            "progress": order.progress_percent,
            "is_late": order.is_late,
            "is_open": order.is_open,
            "steps": order.timeline(),
            "can_cancel": order.can_cancel,
            "can_rate": order.can_rate,
            "courier": {
                "name": order.courier_name,
                "phone": order.courier_phone,
                "vehicle": order.courier_vehicle,
                "live": order.courier_is_live,
                "lat": float(order.courier_lat) if order.courier_lat is not None else None,
                "lng": float(order.courier_lng) if order.courier_lng is not None else None,
            },
        }
    )


def track_lookup(request):
    """Look up a single order number, or list every order for an email."""
    query = (request.GET.get("number") or request.GET.get("q") or "").strip()
    if query:
        if "@" in query:
            orders = (
                Order.objects.filter(
                    Q(guest_email__iexact=query) | Q(user__email__iexact=query)
                )
                .select_related("user")
                .prefetch_related("items")
                .order_by("-created_at")
            )
            return render(
                request,
                "orders/track_results.html",
                {"query": query, "email": query, "orders": orders},
            )
        return redirect("orders:track", number=query.upper())
    return render(request, "orders/track_lookup.html")


def _get_owned_order(request, number):
    """Fetch an order the current user owns (staff may access any order)."""
    order = get_object_or_404(Order.objects.select_related("user"), number=number)
    if not (
        request.user.is_authenticated
        and (order.user_id == request.user.id or request.user.is_staff_member)
    ):
        raise Http404("Order not found")
    return order


@login_required
@require_POST
def cancel_order(request, number):
    order = _get_owned_order(request, number)
    if not order.can_cancel:
        messages.error(
            request,
            "This order can no longer be cancelled online — our team is already on it.",
        )
        return redirect("orders:track", number=order.number)

    user = request.user
    if order.payment_status == Order.PaymentStatus.PAID:
        ok, error = payments.refund_order(order, user=user)
        if ok:
            messages.success(
                request, f"Order {order.number} cancelled — your refund is on the way."
            )
        else:
            messages.error(
                request,
                "We couldn't process the refund automatically. Our team will follow up.",
            )
        return redirect("orders:track", number=order.number)

    # Unpaid order: cancel outright, returning any reserved stock/balance.
    from inventory.services import restore_for_order

    restore_for_order(order, user=user)
    if order.gift_card_id and order.gift_card_amount:
        credited = order.gift_card.credit(order.gift_card_amount)
        GiftCardTransaction.objects.create(
            gift_card=order.gift_card,
            order=order,
            kind=GiftCardTransaction.Kind.REFUND,
            amount=credited,
            balance_after=order.gift_card.balance,
            note=f"Cancelled order {order.number}",
        )
    order.status = Order.Status.CANCELLED
    order.save(update_fields=["status", "updated_at"])
    OrderStatusHistory.objects.create(
        order=order,
        status=Order.Status.CANCELLED,
        changed_by=user,
        note="Cancelled by customer",
    )
    messages.success(request, f"Order {order.number} has been cancelled.")
    return redirect("orders:track", number=order.number)


@login_required
@require_POST
def reorder(request, number):
    order = _get_owned_order(request, number)
    cart = Cart(request)
    cart.clear()
    added = 0
    unavailable = []
    for item in order.items.select_related("product"):
        product = item.product
        if product and product.is_active and product.in_stock:
            cart.add(product, quantity=item.quantity, options=item.options or {})
            added += 1
        else:
            unavailable.append(item.name)
    if added:
        messages.success(
            request, f"Added {added} item{'' if added == 1 else 's'} from {order.number} to your cart."
        )
    if unavailable:
        messages.info(request, "Not available right now: " + ", ".join(unavailable))
    if not added:
        messages.error(request, "None of those items are available at the moment.")
        return redirect("orders:track", number=order.number)
    return redirect("orders:cart")


@login_required
def receipt(request, number):
    order = _get_owned_order(request, number)
    return render(
        request,
        "orders/receipt.html",
        {"order": order, "items": order.items.all()},
    )


@login_required
@require_POST
def rate_order(request, number):
    order = _get_owned_order(request, number)
    if order.status != Order.Status.COMPLETED and not request.user.is_staff_member:
        messages.error(request, "You can leave a rating once this order is complete.")
        return redirect("orders:track", number=order.number)

    form = OrderFeedbackForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Please pick a rating from 1 to 5 stars.")
        return redirect("orders:track", number=order.number)

    order.rating = form.cleaned_data["rating"]
    order.feedback = form.cleaned_data["feedback"]
    order.rated_at = timezone.now()
    tip = form.cleaned_data.get("tip") or 0
    fields = ["rating", "feedback", "rated_at", "updated_at"]

    if tip:
        order.tip = (order.tip or 0) + tip
        order.total = order.total + tip
        fields += ["tip", "total"]
    order.save(update_fields=fields)

    if tip:
        if order.payment_status == Order.PaymentStatus.PAID:
            Payment.objects.create(
                order=order,
                method=Payment.Method.CARD,
                amount=tip,
                state=Payment.State.SUCCEEDED,
                is_successful=True,
                reference=f"TIP-{order.number}",
            )
        else:
            order.payments.filter(state=Payment.State.PENDING).update(amount=order.total)
        OrderStatusHistory.objects.create(
            order=order,
            status=order.status,
            changed_by=request.user,
            note=f"Tip of {settings.CURRENCY_SYMBOL}{tip} added",
        )

    messages.success(
        request,
        "Thanks for the feedback — it means a lot!"
        + (f" Your {settings.CURRENCY_SYMBOL}{tip} tip is truly appreciated." if tip else ""),
    )
    return redirect("orders:track", number=order.number)


@login_required
@require_POST
def toggle_notifications(request, number):
    order = _get_owned_order(request, number)
    order.notify_email = not order.notify_email
    order.save(update_fields=["notify_email", "updated_at"])
    messages.info(
        request,
        "Status emails turned on."
        if order.notify_email
        else "Status emails turned off for this order.",
    )
    return redirect("orders:track", number=order.number)


def notify_pref(request):
    """One-click unsubscribe from order status emails (signed token)."""
    order = Order.from_notification_token(request.GET.get("token", ""))
    if order is None:
        messages.error(request, "That link is invalid or has expired.")
        return redirect("store:home")
    order.notify_email = "off" not in request.GET
    order.save(update_fields=["notify_email", "updated_at"])
    messages.info(
        request,
        f"Status emails for order {order.number} are now "
        + ("on." if order.notify_email else "off."),
    )
    return redirect("orders:track", number=order.number)



def reserve(request):
    if request.method == "POST":
        form = ReservationForm(request.POST)
        if form.is_valid():
            reservation = form.save(commit=False)
            if request.user.is_authenticated:
                reservation.user = request.user
            reservation.save()
            messages.success(
                request,
                f"Table requested for {reservation.date} at {reservation.time}. "
                "We'll confirm by email shortly!",
            )
            return redirect("orders:reservation_success", pk=reservation.pk)
    else:
        initial = {}
        if request.user.is_authenticated:
            initial = {
                "name": request.user.get_full_name(),
                "email": request.user.email,
                "phone": request.user.phone,
            }
        form = ReservationForm(initial=initial)
    return render(request, "orders/reserve.html", {"form": form})


def reservation_success(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    return render(request, "orders/reservation_success.html", {"reservation": reservation})


def order_history(request):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    orders = Order.objects.filter(user=request.user).prefetch_related("items")
    return render(request, "orders/history.html", {"orders": orders})
