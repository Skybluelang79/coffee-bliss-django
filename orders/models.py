from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        PREPARING = "preparing", "Preparing"
        READY = "ready", "Ready"
        OUT_FOR_DELIVERY = "out_for_delivery", "Out for delivery"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    class Fulfillment(models.TextChoices):
        PICKUP = "pickup", "Pickup"
        DELIVERY = "delivery", "Delivery"
        DINE_IN = "dine_in", "Dine in"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "Unpaid"
        PAID = "paid", "Paid"
        REFUNDED = "refunded", "Refunded"

    number = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    guest_email = models.EmailField(blank=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    payment_status = models.CharField(
        max_length=12, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID
    )
    fulfillment = models.CharField(
        max_length=12, choices=Fulfillment.choices, default=Fulfillment.PICKUP
    )
    location = models.ForeignKey(
        "store.StoreLocation",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    coupon = models.ForeignKey(
        "store.Coupon",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
    )
    customer_name = models.CharField(max_length=160)
    customer_phone = models.CharField(max_length=40, blank=True)
    delivery_address = models.CharField(max_length=300, blank=True)
    note = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    delivery_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    loyalty_discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    points_used = models.PositiveIntegerField(default=0)
    points_earned = models.PositiveIntegerField(default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    placed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    stock_consumed = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["number"]), models.Index(fields=["status"])]

    def __str__(self):
        return f"Order {self.number}"

    def save(self, *args, **kwargs):
        if not self.number:
            self.number = self._generate_number()
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_number():
        today = timezone.now().strftime("%y%m%d")
        prefix = f"CB{today}"
        last = (
            Order.objects.filter(number__startswith=prefix)
            .order_by("-number")
            .values_list("number", flat=True)
            .first()
        )
        seq = int(last[-4:]) + 1 if last else 1
        return f"{prefix}{seq:04d}"

    def recalculate(self, tax_rate=None, delivery_fee=None, free_threshold=None):
        """Recompute totals from line items. Returns self (unsaved)."""
        tax_rate = settings.TAX_RATE if tax_rate is None else tax_rate
        subtotal = sum((item.line_total for item in self.items.all()), Decimal("0"))
        self.subtotal = subtotal.quantize(Decimal("0.01"))

        if discount_from_coupon := self.coupon:
            self.discount = discount_from_coupon.discount_for(subtotal)
        else:
            self.discount = Decimal("0.00")

        if self.fulfillment == self.Fulfillment.DELIVERY:
            fee = (
                Decimal("0.00")
                if subtotal >= settings.FREE_DELIVERY_THRESHOLD
                else Decimal(str(settings.DELIVERY_FEE))
            )
            self.delivery_fee = fee
        else:
            self.delivery_fee = Decimal("0.00")

        taxable = max(Decimal("0.00"), self.subtotal - self.discount)
        self.tax = (taxable * Decimal(str(tax_rate))).quantize(Decimal("0.01"))
        self.total = (
            self.subtotal - self.discount + self.delivery_fee + self.tax
            - self.loyalty_discount
        ).quantize(Decimal("0.01"))
        if self.total < 0:
            self.total = Decimal("0.00")
        return self

    @property
    def is_open(self):
        return self.status not in {
            self.Status.COMPLETED,
            self.Status.CANCELLED,
            self.Status.REFUNDED,
        }

    @property
    def item_count(self):
        return sum(item.quantity for item in self.items.all())

    def get_absolute_url(self):
        from django.urls import reverse

        return reverse("orders:track", args=[self.number])

    @property
    def status_color(self):
        return {
            "pending": "amber",
            "confirmed": "blue",
            "preparing": "indigo",
            "ready": "teal",
            "out_for_delivery": "purple",
            "completed": "green",
            "cancelled": "red",
            "refunded": "gray",
        }.get(self.status, "gray")


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "store.Product", on_delete=models.SET_NULL, null=True, related_name="order_items"
    )
    name = models.CharField(max_length=160)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    options = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.quantity} × {self.name}"

    @property
    def line_total(self):
        return self.unit_price * self.quantity


class OrderStatusHistory(models.Model):
    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="history"
    )
    status = models.CharField(max_length=20, choices=Order.Status.choices)
    note = models.CharField(max_length=255, blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "Order status histories"

    def __str__(self):
        return f"{self.order.number} → {self.status}"


class Payment(models.Model):
    class Method(models.TextChoices):
        CARD = "card", "Credit / debit card"
        CASH = "cash", "Cash"
        WALLET = "wallet", "Digital wallet"
        LOYALTY = "loyalty", "Loyalty beans"

    class State(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REFUNDED = "refunded", "Refunded"

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE, related_name="payments"
    )
    method = models.CharField(max_length=12, choices=Method.choices, default=Method.CARD)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reference = models.CharField(max_length=80, blank=True)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    is_successful = models.BooleanField(default=False)
    stripe_payment_intent_id = models.CharField(max_length=120, blank=True)
    stripe_charge_id = models.CharField(max_length=120, blank=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.order.number} {self.method} {self.amount}"


class Table(models.Model):
    name = models.CharField(max_length=40, unique=True)
    seats = models.PositiveIntegerField(default=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.seats} seats)"


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CONFIRMED = "confirmed", "Confirmed"
        SEATED = "seated", "Seated"
        CANCELLED = "cancelled", "Cancelled"
        NO_SHOW = "no_show", "No show"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reservations",
    )
    name = models.CharField(max_length=160)
    email = models.EmailField()
    phone = models.CharField(max_length=40)
    location = models.ForeignKey(
        "store.StoreLocation", on_delete=models.SET_NULL, null=True, blank=True
    )
    table = models.ForeignKey(
        Table, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservations"
    )
    party_size = models.PositiveIntegerField(default=2)
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING
    )
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-time"]
        indexes = [models.Index(fields=["date", "status"])]

    def __str__(self):
        return f"{self.name} — {self.date} {self.time}"


class Subscription(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELLED = "cancelled", "Cancelled"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        "store.SubscriptionPlan", on_delete=models.PROTECT, related_name="subscribers"
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.ACTIVE
    )
    grind = models.CharField(max_length=60, blank=True)
    next_delivery = models.DateField(blank=True, null=True)
    started_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user} — {self.plan.name}"

    def advance_delivery(self):
        from datetime import timedelta

        mapping = {"weekly": 7, "biweekly": 14, "monthly": 30}
        days = mapping.get(self.plan.interval, 30)
        base = self.next_delivery or timezone.now().date()
        self.next_delivery = base + timedelta(days=days)
        self.save(update_fields=["next_delivery"])
