import os
import random

from django.conf import settings

from .models import Address, LoyaltyTransaction, User

ADMIN_EMAIL = "admin@coffeebliss.test"
ADMIN_PASSWORD = "admin12345"
STAFF_EMAIL = "staff@coffeebliss.test"
STAFF_PASSWORD = "staff12345"
CUSTOMER_PASSWORD = "demo12345"
CUSTOMER_EMAILS = [f"customer{i}@example.com" for i in range(1, 9)]

DEMO_LOGINS = [
    {"label": "Admin", "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    {"label": "Staff", "email": STAFF_EMAIL, "password": STAFF_PASSWORD},
    {"label": "Customer", "email": CUSTOMER_EMAILS[0], "password": CUSTOMER_PASSWORD},
]

_TRUE_VALUES = {"1", "true", "yes"}


def demo_accounts_enabled():
    if settings.DEBUG:
        return True
    return any(
        os.environ.get(name, "").strip().lower() in _TRUE_VALUES
        for name in ("BOOTSTRAP_DEMO_ACCOUNTS", "SEED_DEMO_DATA")
    )


def _set_fields(user, **fields):
    changed = False
    for name, value in fields.items():
        if getattr(user, name) != value:
            setattr(user, name, value)
            changed = True
    return changed


def _ensure_user(email, password, **attributes):
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email).order_by("pk").first()
    if user is None:
        user = User.objects.create_user(email=email, password=password, **attributes)
        return user, True

    changed = _set_fields(user, email=email, **attributes)
    if not user.check_password(password):
        user.set_password(password)
        changed = True
    if changed:
        user.save()
    return user, False


def ensure_demo_accounts():
    admin, _ = _ensure_user(
        ADMIN_EMAIL,
        ADMIN_PASSWORD,
        first_name="Ada",
        last_name="Bliss",
        role=User.Role.ADMIN,
        is_staff=True,
        is_superuser=True,
        is_active=True,
    )
    _ensure_user(
        STAFF_EMAIL,
        STAFF_PASSWORD,
        first_name="Sam",
        last_name="Barista",
        role=User.Role.STAFF,
        is_staff=True,
        is_superuser=False,
        is_active=True,
    )

    for index, email in enumerate(CUSTOMER_EMAILS, start=1):
        user, created = _ensure_user(
            email,
            CUSTOMER_PASSWORD,
            first_name=random.choice(
                ["Mia", "Leo", "Zoe", "Kai", "Ava", "Noah", "Ivy", "Eli"]
            ),
            last_name=random.choice(["Bean", "Roast", "Crema", "Mocha", "Latte"]),
            phone=f"+1 555 0{index:03d}",
            role=User.Role.CUSTOMER,
            is_staff=False,
            is_superuser=False,
            is_active=True,
            newsletter_opt_in=True,
        )
        if created:
            Address.objects.create(
                user=user,
                label="home",
                recipient=user.get_full_name(),
                line1=f"{random.randint(1, 300)} Roastery Lane",
                city=random.choice(["Bean Town", "Roastville", "Crema City"]),
                state="CA",
                postal_code=f"9{random.randint(1000, 9999)}",
                is_default=True,
            )
            LoyaltyTransaction.objects.create(
                user=user, points=100, reason="signup", note="Welcome bonus"
            )

    return admin
