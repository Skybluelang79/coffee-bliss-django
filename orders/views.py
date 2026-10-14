from django.conf import settings
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import payments
from .cart import Cart
from .forms import CheckoutForm, ReservationForm
from .models import Order, OrderItem, OrderStatusHistory, Reservation


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

            if method == "cash":
                payments.simulate_success(order, user=request.user if request.user.is_authenticated else None)
                messages.success(request, f"Order {order.number} placed! Pay on {order.get_fulfillment_display().lower()}.")
                return redirect("orders:order_confirmation", number=order.number)

            if payments.is_configured():
                return redirect("orders:payment", number=order.number)

            # Simulated card gateway (no Stripe keys configured).
            payments.simulate_success(order, user=request.user if request.user.is_authenticated else None)
            messages.success(request, f"Order {order.number} placed! We're on it. ☕")
            return redirect("orders:order_confirmation", number=order.number)
        messages.error(request, "Please fix the highlighted fields.")
    else:
        form = CheckoutForm(initial=initial)

    return render(request, "orders/checkout.html", {"cart": cart, "form": form})


def _create_order(request, cart, form):
    data = form.cleaned_data
    order = Order(
        user=request.user if request.user.is_authenticated else None,
        guest_email="" if request.user.is_authenticated else request.POST.get("guest_email", ""),
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
    return order


def payment_page(request, number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), number=number)
    if order.payment_status == Order.PaymentStatus.PAID:
        return redirect("orders:order_confirmation", number=order.number)
    intent = payments.create_payment_intent(order)
    return render(
        request,
        "orders/payment.html",
        {
            "order": order,
            "client_secret": intent["client_secret"],
            "payment_intent_id": intent["payment_intent_id"],
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "simulated": intent["simulated"],
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
        Order.objects.prefetch_related("items", "history"), number=number
    )
    return render(request, "orders/track.html", {"order": order})


def track_lookup(request):
    number = request.GET.get("number", "").strip().upper()
    if number:
        return redirect("orders:track", number=number)
    messages.info(request, "Enter an order number to track it.")
    return redirect("store:home")


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
