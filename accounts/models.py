from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class UserManager(BaseUserManager):
    """Manager for the email-based custom user model."""

    use_in_migrations = True

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", User.Role.ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """Custom user with roles and loyalty support.

    Login is performed with the email address rather than a username.
    """

    class Role(models.TextChoices):
        CUSTOMER = "customer", "Customer"
        STAFF = "staff", "Staff"
        MANAGER = "manager", "Manager"
        ADMIN = "admin", "Administrator"

    username = None
    email = models.EmailField("email address", unique=True)
    phone = models.CharField(max_length=32, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    role = models.CharField(
        max_length=16, choices=Role.choices, default=Role.CUSTOMER
    )
    newsletter_opt_in = models.BooleanField(default=False)
    marketing_opt_in = models.BooleanField(default=False)
    loyalty_points = models.PositiveIntegerField(default=0)
    date_joined = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        ordering = ["-date_joined"]
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    def get_short_name(self):
        return self.first_name or self.email.split("@")[0]

    @property
    def is_customer(self):
        return self.role == self.Role.CUSTOMER

    @property
    def is_staff_member(self):
        return self.role in {self.Role.STAFF, self.Role.MANAGER, self.Role.ADMIN}

    @property
    def is_manager(self):
        return self.role in {self.Role.MANAGER, self.Role.ADMIN}

    def add_loyalty_points(self, points, reason, order=None):
        """Adjust the loyalty balance and record a ledger entry."""
        self.loyalty_points = max(0, self.loyalty_points + points)
        self.save(update_fields=["loyalty_points"])
        transaction = LoyaltyTransaction.objects.create(
            user=self, points=points, reason=reason, order=order
        )
        return transaction

    def redeem_value(self):
        """Value of the current loyalty balance in account currency."""
        return Decimal(self.loyalty_points) * Decimal(str(settings.LOYALTY_POINT_VALUE))


class Address(models.Model):
    """A saved shipping/billing address for a customer."""

    class Label(models.TextChoices):
        HOME = "home", "Home"
        WORK = "work", "Work"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="addresses"
    )
    label = models.CharField(max_length=16, choices=Label.choices, default=Label.HOME)
    recipient = models.CharField(max_length=120)
    phone = models.CharField(max_length=32, blank=True)
    line1 = models.CharField(max_length=255)
    line2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=120)
    state = models.CharField(max_length=120, blank=True)
    postal_code = models.CharField(max_length=32, blank=True)
    country = models.CharField(max_length=120, default="United States")
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_default", "-created_at"]
        verbose_name_plural = "Addresses"

    def __str__(self):
        return f"{self.recipient}, {self.city}"

    def save(self, *args, **kwargs):
        if self.is_default:
            Address.objects.filter(user=self.user, is_default=True).exclude(
                pk=self.pk
            ).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def one_line(self):
        parts = [self.line1, self.line2, self.city, self.state, self.postal_code]
        return ", ".join(p for p in parts if p)


class LoyaltyTransaction(models.Model):
    """Immutable ledger of loyalty point movements."""

    class Reason(models.TextChoices):
        ORDER = "order", "Order reward"
        REDEMPTION = "redemption", "Redemption"
        SIGNUP = "signup", "Signup bonus"
        REVIEW = "review", "Review reward"
        REFERRAL = "referral", "Referral"
        ADJUSTMENT = "adjustment", "Manual adjustment"

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="loyalty_transactions"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="loyalty_transactions",
    )
    points = models.IntegerField(validators=[MinValueValidator(-100000)])
    reason = models.CharField(max_length=16, choices=Reason.choices)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        sign = "+" if self.points >= 0 else ""
        return f"{self.user.email}: {sign}{self.points} ({self.reason})"
