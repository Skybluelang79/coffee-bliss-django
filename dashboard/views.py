from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from accounts.models import User
from config.redirects import safe_redirect
from orders.models import AbandonedCart, Order, OrderStatusHistory, Payment, Reservation
from store.models import Coupon, NewsletterSubscriber, Product, Review


def staff_required(view):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_staff_member, login_url="accounts:login"
    )(view)


def manager_required(view):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_manager, login_url="accounts:login"
    )(view)


@staff_required
def staff_home(request):
    """Live operations board for staff."""
    today = timezone.now().date()
    active_statuses = [
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.OUT_FOR_DELIVERY,
    ]
    context = {
        "new_orders": Order.objects.filter(status=Order.Status.PENDING).prefetch_related("items")[:20],
        "active_orders": Order.objects.filter(status__in=active_statuses).prefetch_related("items")[
            :30
        ],
        "today_orders": Order.objects.filter(
            status__in=active_statuses, created_at__date=today
        ).count(),
        "today_reservations": Reservation.objects.filter(
            date=today, status__in=[Reservation.Status.PENDING, Reservation.Status.CONFIRMED]
        ).select_related("table"),
        "revenue_today": Order.objects.filter(
            created_at__date=today, payment_status=Order.PaymentStatus.PAID
        ).aggregate(total=Coalesce(Sum("total"), Decimal("0")))["total"],
        "pending_reviews": Review.objects.filter(is_approved=False).count(),
        "low_stock": Product.objects.filter(is_active=True, stock__lt=10).order_by("stock")[:10],
        "statuses": Order.Status.choices,
    }
    return render(request, "dashboard/staff_home.html", context)


@staff_required
def staff_orders(request):
    status = request.GET.get("status")
    orders = Order.objects.prefetch_related("items").select_related("user")
    if status:
        orders = orders.filter(status=status)
    return render(
        request,
        "dashboard/staff_orders.html",
        {"orders": orders[:100], "statuses": Order.Status.choices, "selected": status},
    )


@staff_required
@require_POST
def staff_update_status(request, number):
    order = get_object_or_404(Order, number=number)
    new_status = request.POST.get("status")
    valid = {choice[0] for choice in Order.Status.choices}
    if new_status == order.status:
        messages.info(request, f"Order {order.number} is already {order.get_status_display().lower()}.")
        return safe_redirect(request, "dashboard:staff_orders")
    if new_status in valid:
        from orders import payments as payment_service
        from inventory.services import restore_for_order

        if new_status == Order.Status.REFUNDED:
            ok, error = payment_service.refund_order(order, user=request.user)
            if not ok:
                messages.error(request, error or "Refund could not be processed.")
                return safe_redirect(request, "dashboard:staff_orders")
        else:
            was_final = order.status in {
                Order.Status.CANCELLED,
                Order.Status.REFUNDED,
            }
            order.status = new_status
            if new_status == Order.Status.COMPLETED:
                order.completed_at = timezone.now()
            if new_status == Order.Status.CANCELLED:
                restore_for_order(order, user=request.user)
                if not was_final:
                    payment_service.reverse_loyalty(order)
                    payment_service.release_coupon(order)
                if order.gift_card_id and order.gift_card_amount:
                    from orders.models import GiftCardTransaction

                    credited = order.gift_card.credit(order.gift_card_amount)
                    GiftCardTransaction.objects.create(
                        gift_card=order.gift_card,
                        order=order,
                        kind=GiftCardTransaction.Kind.REFUND,
                        amount=credited,
                        balance_after=order.gift_card.balance,
                        note=f"Cancelled order {order.number}",
                    )
            order.save(update_fields=["status", "completed_at", "updated_at"])
            OrderStatusHistory.objects.create(
                order=order, status=new_status, changed_by=request.user, note="Staff update"
            )
        messages.success(request, f"Order {order.number} → {order.get_status_display()}")
    return safe_redirect(request, "dashboard:staff_orders")


@staff_required
@require_POST
def staff_mark_paid(request, number):
    """Record cash (or other offline) payment collected by staff."""
    from orders import payments as payment_service

    order = get_object_or_404(Order, number=number)
    if order.payment_status == Order.PaymentStatus.PAID:
        messages.info(request, f"Order {order.number} is already paid.")
    elif order.payment_status == Order.PaymentStatus.REFUNDED or order.status in {
        Order.Status.CANCELLED,
        Order.Status.REFUNDED,
    }:
        messages.error(request, "Closed orders cannot be marked paid.")
    else:
        payment = payment_service.get_or_create_payment(
            order, method=Payment.Method.CASH
        )
        payment.method = Payment.Method.CASH
        payment.save(update_fields=["method", "updated_at"])
        payment_service.mark_order_paid(
            order,
            reference=payment.reference or f"CASH-{order.number}",
            user=request.user,
        )
        messages.success(request, f"Payment recorded for order {order.number}.")
    return safe_redirect(request, "dashboard:staff_orders")


@staff_required
def staff_kds(request):
    """Kitchen Display System — live board driven over WebSockets."""
    active_statuses = [
        Order.Status.PENDING,
        Order.Status.CONFIRMED,
        Order.Status.PREPARING,
        Order.Status.READY,
        Order.Status.OUT_FOR_DELIVERY,
    ]
    # Only surface the last 24 hours so old demo/backlogged orders don't flood
    # the live board.
    cutoff = timezone.now() - timedelta(hours=24)
    orders = (
        Order.objects.filter(status__in=active_statuses, placed_at__gte=cutoff)
        .prefetch_related("items")
        .order_by("placed_at")
    )
    from orders.realtime import serialize_order

    return render(
        request,
        "dashboard/kds.html",
        {
            "orders": orders,
            "orders_json": [serialize_order(o) for o in orders],
            "statuses": Order.Status.choices,
            "now": timezone.now().strftime("%H:%M:%S"),
        },
    )


@staff_required
def staff_reservations(request):
    status = request.GET.get("status")
    reservations = Reservation.objects.select_related("table", "location")
    if status:
        reservations = reservations.filter(status=status)
    return render(
        request,
        "dashboard/staff_reservations.html",
        {
            "reservations": reservations[:100],
            "statuses": Reservation.Status.choices,
            "selected": status,
        },
    )


@staff_required
@require_POST
def staff_update_reservation(request, pk):
    reservation = get_object_or_404(Reservation, pk=pk)
    new_status = request.POST.get("status")
    valid = {choice[0] for choice in Reservation.Status.choices}
    if new_status in valid:
        reservation.status = new_status
        reservation.save(update_fields=["status"])
        messages.success(request, f"Reservation updated to {reservation.get_status_display()}.")
    return safe_redirect(request, "dashboard:staff_reservations")


@manager_required
def admin_home(request):
    """Executive analytics dashboard."""
    now = timezone.now()
    start = now - timedelta(days=29)
    daily = (
        Order.objects.filter(created_at__gte=start, payment_status=Order.PaymentStatus.PAID)
        .annotate(day=TruncDate("created_at"))
        .values("day")
        .annotate(revenue=Sum("total"), orders=Count("id"))
        .order_by("day")
    )
    daily_map = {row["day"]: row for row in daily}
    chart = []
    for i in range(30):
        day = (start + timedelta(days=i)).date()
        row = daily_map.get(day, {"revenue": 0, "orders": 0})
        chart.append(
            {
                "date": day.strftime("%b %d"),
                "revenue": float(row["revenue"] or 0),
                "orders": row["orders"] or 0,
            }
        )

    paid = Order.objects.filter(payment_status=Order.PaymentStatus.PAID)
    total_revenue = paid.aggregate(t=Coalesce(Sum("total"), Decimal("0")))["t"]
    max_revenue = max((row["revenue"] for row in chart), default=0) or 1
    open_carts = AbandonedCart.objects.filter(status=AbandonedCart.Status.OPEN)
    top_products = (
        Product.objects.filter(order_items__order__payment_status=Order.PaymentStatus.PAID)
        .annotate(sold=Sum("order_items__quantity"), revenue=Sum(F("order_items__quantity") * F("order_items__unit_price")))
        .order_by("-sold")[:8]
    )

    context = {
        "chart": chart,
        "total_revenue": total_revenue,
        "max_revenue": max_revenue,
        "revenue_30d": paid.filter(created_at__gte=start).aggregate(
            t=Coalesce(Sum("total"), Decimal("0"))
        )["t"],
        "orders_total": Order.objects.count(),
        "orders_30d": Order.objects.filter(created_at__gte=start).count(),
        "customers": User.objects.filter(role=User.Role.CUSTOMER).count(),
        "new_customers_30d": User.objects.filter(
            role=User.Role.CUSTOMER, date_joined__gte=start
        ).count(),
        "aov": (total_revenue / paid.count()) if paid.count() else 0,
        "status_breakdown": Order.objects.values("status").annotate(count=Count("id")),
        "top_products": top_products,
        "recent_orders": Order.objects.select_related("user")[:10],
        "subscribers": NewsletterSubscriber.objects.filter(is_active=True).count(),
        "coupons": Coupon.objects.filter(is_active=True)[:10],
        "low_stock": Product.objects.filter(is_active=True, stock__lt=10)[:10],
        "pending_reviews": Review.objects.filter(is_approved=False).select_related(
            "product", "user"
        )[:10],
        "reservations_upcoming": Reservation.objects.filter(
            date__gte=now.date(), status=Reservation.Status.CONFIRMED
        ).count(),
        "abandoned_count": open_carts.count(),
        "abandoned_value": open_carts.aggregate(
            t=Coalesce(Sum("subtotal"), Decimal("0"))
        )["t"],
        "abandoned_carts": open_carts.order_by("-updated_at")[:5],
    }
    return render(request, "dashboard/admin_home.html", context)


@manager_required
@require_POST
def send_cart_reminders(request):
    from django.conf import settings

    from orders.recovery import run_recovery

    sent, considered = run_recovery(
        hours=settings.CART_RECOVERY_HOURS,
        max_reminders=settings.CART_RECOVERY_MAX_REMINDERS,
    )
    messages.success(
        request,
        f"Sent {sent} recovery email(s) out of {considered} eligible cart(s).",
    )
    return redirect("dashboard:admin_home")


@manager_required
def customers(request):
    query = request.GET.get("q", "")
    users = User.objects.filter(role=User.Role.CUSTOMER).annotate(
        order_count=Count("orders"),
        spent=Coalesce(Sum("orders__total", filter=Q(orders__payment_status="paid")), Decimal("0")),
    )
    if query:
        users = users.filter(Q(email__icontains=query) | Q(first_name__icontains=query) | Q(last_name__icontains=query))
    return render(request, "dashboard/customers.html", {"users": users, "query": query})


@manager_required
def customer_detail(request, pk):
    user = get_object_or_404(User, pk=pk)
    orders = user.orders.prefetch_related("items")
    return render(
        request,
        "dashboard/customer_detail.html",
        {"customer": user, "orders": orders},
    )


@manager_required
def reports(request):
    period = request.GET.get("period", "30")
    days = int(period) if period.isdigit() else 30
    start = timezone.now() - timedelta(days=days)
    orders = Order.objects.filter(created_at__gte=start)
    by_status = orders.values("status").annotate(count=Count("id"), revenue=Coalesce(Sum("total"), Decimal("0")))
    by_fulfillment = orders.values("fulfillment").annotate(count=Count("id"))
    by_category = (
        Product.objects.filter(order_items__order__in=orders)
        .values("category__name")
        .annotate(sold=Sum("order_items__quantity"), revenue=Sum(F("order_items__quantity") * F("order_items__unit_price")))
        .order_by("-revenue")
    )
    return render(
        request,
        "dashboard/reports.html",
        {
            "period": period,
            "by_status": by_status,
            "by_fulfillment": by_fulfillment,
            "by_category": by_category,
            "orders": orders.count(),
            "revenue": orders.filter(payment_status="paid").aggregate(
                t=Coalesce(Sum("total"), Decimal("0"))
            )["t"],
        },
    )
