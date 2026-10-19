from decimal import Decimal
from datetime import timedelta
import secrets
import string

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
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
    gift_card = models.ForeignKey(
        "orders.GiftCard",
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
    gift_card_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    points_used = models.PositiveIntegerField(default=0)
    points_earned = models.PositiveIntegerField(default=0)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    placed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    stock_consumed = models.BooleanField(default=False)

    # ---- Tracking -------------------------------------------------------
    estimated_ready_at = models.DateTimeField(
        blank=True, null=True, help_text="When the order should be ready."
    )
    ready_at = models.DateTimeField(blank=True, null=True)

    # ---- Courier (delivery orders) --------------------------------------
    courier_name = models.CharField(max_length=120, blank=True)
    courier_phone = models.CharField(max_length=40, blank=True)
    courier_vehicle = models.CharField(
        max_length=80, blank=True, help_text="e.g. Scooter · CB-402"
    )
    courier_lat = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    courier_lng = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    courier_updated_at = models.DateTimeField(blank=True, null=True)

    # ---- Post-order feedback --------------------------------------------
    rating = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
    )
    feedback = models.TextField(blank=True)
    tip = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    rated_at = models.DateTimeField(blank=True, null=True)

    # ---- Notifications ---------------------------------------------------
    notify_email = models.BooleanField(
        default=True, help_text="Email the customer as the order progresses."
    )
    sms_opt_in = models.BooleanField(default=False)

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
        base = (
            self.subtotal - self.discount + self.delivery_fee + self.tax
            - self.loyalty_discount
        )
        if self.gift_card_id and self.gift_card and self.gift_card.is_usable:
            self.gift_card_amount = min(
                self.gift_card.balance, max(Decimal("0.00"), base)
            ).quantize(Decimal("0.01"))
        else:
            self.gift_card_amount = Decimal("0.00")
        self.total = max(
            Decimal("0.00"), base - self.gift_card_amount
        ).quantize(Decimal("0.01"))
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

    # ---- Tracking helpers ------------------------------------------------
    TRACK_STEPS = [
        ("received", "Order received"),
        ("confirmed", "Confirmed"),
        ("preparing", "Preparing"),
        ("ready", "Ready"),
        ("completed", "Completed"),
    ]

    # Statuses that mark each timeline step as reached.
    _STEP_REACHED = {
        "received": {
            "pending", "confirmed", "preparing", "ready", "out_for_delivery", "completed",
        },
        "confirmed": {
            "confirmed", "preparing", "ready", "out_for_delivery", "completed",
        },
        "preparing": {"preparing", "ready", "out_for_delivery", "completed"},
        "ready": {"ready", "out_for_delivery", "completed"},
        "completed": {"completed"},
    }

    @property
    def recipient_email(self):
        if self.user_id and self.user:
            return self.user.email
        return self.guest_email

    @property
    def prep_minutes(self):
        """Longest prep time across the items (fallback 5 min)."""
        values = [
            item.product.prep_time_minutes
            for item in self.items.all()
            if item.product is not None and item.product.prep_time_minutes
        ]
        return max(values) if values else 5

    @property
    def eta_minutes(self):
        """Total estimated wait, including a delivery buffer."""
        minutes = self.prep_minutes
        if self.fulfillment == self.Fulfillment.DELIVERY:
            minutes += getattr(settings, "DELIVERY_ETA_BUFFER", 15)
        return minutes

    def ensure_estimated_ready_at(self, save=True):
        if self.estimated_ready_at is None and self.placed_at:
            self.estimated_ready_at = self.placed_at + timedelta(
                minutes=self.eta_minutes
            )
            if save:
                super(Order, self).save(
                    update_fields=["estimated_ready_at", "updated_at"]
                )
        return self.estimated_ready_at

    @property
    def eta_seconds_left(self):
        """Seconds until the estimated ready time (0 once passed/closed)."""
        if self.status in {
            self.Status.COMPLETED,
            self.Status.CANCELLED,
            self.Status.REFUNDED,
        }:
            return 0
        if not self.estimated_ready_at:
            return 0
        remaining = (self.estimated_ready_at - timezone.now()).total_seconds()
        return max(0, int(remaining))

    @property
    def is_late(self):
        return bool(self.is_open and self.eta_seconds_left == 0)

    @property
    def progress_percent(self):
        """Rough 0-100 progress used by the tracking bar/map."""
        mapping = {
            self.Status.PENDING: 8,
            self.Status.CONFIRMED: 30,
            self.Status.PREPARING: 55,
            self.Status.READY: 80,
            self.Status.OUT_FOR_DELIVERY: 88,
            self.Status.COMPLETED: 100,
        }
        if self.status in {self.Status.CANCELLED, self.Status.REFUNDED}:
            return 100
        return mapping.get(self.status, 10)

    def timeline(self):
        """Ordered steps with ``done`` / ``current`` flags for the template."""
        order = [key for key, _ in self.TRACK_STEPS]
        labels = dict(self.TRACK_STEPS)
        try:
            index = order.index(self.status) if self.status in order else -1
        except ValueError:
            index = -1
        # out_for_delivery sits between ready and completed.
        reached = {
            key for key in order if self.status in self._STEP_REACHED[key]
        }
        steps = []
        for position, key in enumerate(order):
            steps.append(
                {
                    "key": key,
                    "label": labels[key],
                    "done": key in reached,
                    "current": position == index,
                }
            )
        return steps

    @property
    def can_cancel(self):
        return self.status in {self.Status.PENDING, self.Status.CONFIRMED}

    @property
    def can_reorder(self):
        return self.items.filter(product__isnull=False).exists()

    @property
    def can_rate(self):
        return self.status == self.Status.COMPLETED and self.rating is None

    @property
    def courier_is_live(self):
        return bool(
            self.courier_updated_at
            and (timezone.now() - self.courier_updated_at).total_seconds() < 300
        )

    def notification_token(self):
        from django.core import signing

        return signing.dumps({"order": self.pk, "n": self.number})

    @staticmethod
    def from_notification_token(token, max_age=60 * 60 * 24 * 365):
        from django.core import signing

        try:
            data = signing.loads(token, max_age=max_age)
        except signing.BadSignature:
            return None
        return Order.objects.filter(pk=data.get("order"), number=data.get("n")).first()


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

    @property
    def options_display(self):
        """Human-readable options, e.g. ``Large · Oat milk · Extra shot``."""
        if not self.options:
            return ""
        parts = []
        for key, value in self.options.items():
            if isinstance(value, (list, tuple)):
                parts.extend(str(v) for v in value)
            elif value:
                parts.append(str(value))
        return " · ".join(parts)


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


class GiftCard(models.Model):
    """A prepaid balance that can be redeemed against an order at checkout."""

    class State(models.TextChoices):
        ACTIVE = "active", "Active"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired"
        DISABLED = "disabled", "Disabled"

    code = models.CharField(max_length=32, unique=True, editable=False)
    initial_balance = models.DecimalField(max_digits=10, decimal_places=2)
    balance = models.DecimalField(max_digits=10, decimal_places=2)
    purchaser = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchased_gift_cards",
    )
    recipient_email = models.EmailField(blank=True)
    recipient_name = models.CharField(max_length=120, blank=True)
    message = models.CharField(max_length=255, blank=True)
    note = models.CharField(max_length=255, blank=True, help_text="Internal admin note.")
    is_active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["code"]), models.Index(fields=["is_active"])]

    def __str__(self):
        return f"{self.code} ({self.balance})"

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = self._generate_code()
        if self.balance is None:
            self.balance = self.initial_balance
        super().save(*args, **kwargs)

    @staticmethod
    def _generate_code():
        alphabet = string.ascii_uppercase + string.digits
        while True:
            groups = ["".join(secrets.choice(alphabet) for _ in range(4)) for _ in range(3)]
            code = "CB-" + "-".join(groups)
            if not GiftCard.objects.filter(code=code).exists():
                return code

    @property
    def is_expired(self):
        return bool(self.expires_at and self.expires_at <= timezone.now())

    @property
    def is_redeemed(self):
        return self.balance <= 0

    @property
    def is_usable(self):
        return self.is_active and not self.is_expired and self.balance > 0

    @property
    def state(self):
        if not self.is_active:
            return self.State.DISABLED
        if self.is_expired:
            return self.State.EXPIRED
        if self.is_redeemed:
            return self.State.REDEEMED
        return self.State.ACTIVE

    @property
    def state_label(self):
        return self.State(self.state).label

    @classmethod
    def lookup(cls, code):
        """Return ``(card, error)`` for a user-entered code."""
        code = (code or "").strip()
        if not code:
            return None, "Enter a gift card code."
        card = cls.objects.filter(code__iexact=code).first()
        if card is None:
            return None, "We couldn't find that gift card."
        if not card.is_active:
            return None, "That gift card has been disabled."
        if card.is_expired:
            return None, "That gift card has expired."
        if card.is_redeemed:
            return None, "That gift card has no balance left."
        return card, None

    def redeem(self, amount):
        """Deduct up to ``amount`` from the balance and return the amount used."""
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount <= 0:
            return Decimal("0.00")
        applied = min(amount, self.balance).quantize(Decimal("0.01"))
        self.balance = (self.balance - applied).quantize(Decimal("0.01"))
        self.save(update_fields=["balance", "updated_at"])
        return applied

    def credit(self, amount):
        """Return ``amount`` to the balance (used on refunds)."""
        amount = Decimal(amount).quantize(Decimal("0.01"))
        if amount <= 0:
            return Decimal("0.00")
        self.balance = (self.balance + amount).quantize(Decimal("0.01"))
        self.save(update_fields=["balance", "updated_at"])
        return amount


class GiftCardTransaction(models.Model):
    """Immutable ledger of gift card balance movements."""

    class Kind(models.TextChoices):
        ISSUE = "issue", "Issued"
        REDEMPTION = "redemption", "Redeemed"
        REFUND = "refund", "Refunded"
        ADJUSTMENT = "adjustment", "Adjustment"

    gift_card = models.ForeignKey(
        GiftCard, on_delete=models.CASCADE, related_name="transactions"
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gift_card_transactions",
    )
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ISSUE)
    amount = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Signed: negative when redeemed."
    )
    balance_after = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.gift_card.code} {self.kind} {self.amount}"


class AbandonedCart(models.Model):
    """Snapshot of a session cart that was left before checkout."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        RECOVERED = "recovered", "Recovered"
        EXPIRED = "expired", "Expired"

    session_key = models.CharField(max_length=40, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="abandoned_carts",
    )
    email = models.EmailField(blank=True)
    items = models.JSONField(default=list, blank=True)
    item_count = models.PositiveIntegerField(default=0)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.OPEN
    )
    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="recovered_carts",
    )
    reminders_sent = models.PositiveIntegerField(default=0)
    last_reminder_at = models.DateTimeField(blank=True, null=True)
    recovered_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Abandoned cart"
        indexes = [
            models.Index(fields=["status", "updated_at"]),
            models.Index(fields=["session_key", "status"]),
        ]

    def __str__(self):
        return f"Cart #{self.pk} ({self.recipient_email or 'no email'})"

    @property
    def recipient_email(self):
        if self.email:
            return self.email
        if self.user_id:
            return self.user.email
        return ""

    def can_remind(self, max_reminders=2):
        return (
            self.status == self.Status.OPEN
            and bool(self.recipient_email)
            and self.reminders_sent < max_reminders
        )
