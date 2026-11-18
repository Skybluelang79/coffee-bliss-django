import os
from io import StringIO
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import SignUpForm
from .models import User


class AccountTests(TestCase):
    def test_signup_creates_customer_with_bonus(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ada@example.com",
                "phone": "123",
                "password1": "S3curePass!23",
                "password2": "S3curePass!23",
                "newsletter_opt_in": "on",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(email="ada@example.com")
        self.assertEqual(user.role, User.Role.CUSTOMER)
        self.assertEqual(user.loyalty_points, 100)

    def test_login_with_email(self):
        User.objects.create_user(email="x@example.com", password="testpass123")
        self.assertTrue(self.client.login(email="x@example.com", password="testpass123"))

    def test_login_with_email_is_case_insensitive(self):
        User.objects.create_user(email="x@example.com", password="testpass123")
        self.assertTrue(self.client.login(email="X@Example.COM", password="testpass123"))

    def test_signup_rejects_duplicate_email(self):
        User.objects.create_user(email="ada@example.com", password="testpass123")
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "ADA@example.com",
                "password1": "S3curePass!23",
                "password2": "S3curePass!23",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email__iexact="ada@example.com").count(), 1)

    def test_signup_handles_email_race_without_crash(self):
        User.objects.create_user(email="ada@example.com", password="testpass123")
        # Bypass the form-level uniqueness check to simulate a concurrent submit
        # that raced past it; the view must degrade gracefully, not 500.
        with mock.patch.object(
            SignUpForm, "clean_email", lambda self: self.cleaned_data["email"]
        ):
            response = self.client.post(
                reverse("accounts:signup"),
                {
                    "first_name": "Ada",
                    "last_name": "Lovelace",
                    "email": "ada@example.com",
                    "password1": "S3curePass!23",
                    "password2": "S3curePass!23",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.filter(email__iexact="ada@example.com").count(), 1)
    def test_signup_redirects_to_next_after_success(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "next@example.com",
                "password1": "S3curePass!23",
                "password2": "S3curePass!23",
                "next": "/orders/checkout/",
            },
        )
        self.assertRedirects(response, "/orders/checkout/", fetch_redirect_response=False)

    def test_signup_ignores_offsite_next(self):
        response = self.client.post(
            reverse("accounts:signup"),
            {
                "first_name": "Ada",
                "last_name": "Lovelace",
                "email": "evil-next@example.com",
                "password1": "S3curePass!23",
                "password2": "S3curePass!23",
                "next": "https://evil.example.com/steal",
            },
        )
        self.assertRedirects(response, reverse("accounts:dashboard"))

    def test_logout_get_is_not_allowed(self):
        User.objects.create_user(email="bye@example.com", password="testpass123")
        self.client.login(email="bye@example.com", password="testpass123")
        response = self.client.get(reverse("accounts:logout"))
        self.assertEqual(response.status_code, 405)

    def test_logout_post_signs_out_and_redirects_home(self):
        User.objects.create_user(email="bye@example.com", password="testpass123")
        self.client.login(email="bye@example.com", password="testpass123")
        response = self.client.post(reverse("accounts:logout"))
        self.assertRedirects(response, reverse("store:home"))
        self.assertIsNone(self.client.session.get("_auth_user_id"))

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)


class LoginPageTests(TestCase):
    def test_login_page_has_enhanced_features(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertContains(response, reverse("accounts:password_reset"))
        self.assertContains(response, "data-pw-toggle")
        self.assertContains(response, reverse("orders:track_lookup"))

    def test_demo_credentials_hidden_when_debug_off(self):
        # The test runner forces DEBUG=False, so demo credentials must not leak.
        response = self.client.get(reverse("accounts:login"))
        self.assertNotContains(response, "admin@coffeebliss.test")


class PasswordResetTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="ada@example.com", password="testpass123", first_name="Ada"
        )

    def test_reset_pages_render(self):
        for name in ("password_reset", "password_reset_done", "password_reset_complete"):
            response = self.client.get(reverse(f"accounts:{name}"))
            self.assertEqual(response.status_code, 200)

    def test_reset_sends_branded_email(self):
        from django.core import mail

        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            response = self.client.post(
                reverse("accounts:password_reset"), {"email": "ada@example.com"}
            )
        self.assertRedirects(response, reverse("accounts:password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Coffee Bliss", mail.outbox[0].subject)
        self.assertIn("password-reset", mail.outbox[0].body)

    def test_full_reset_flow_sets_new_password(self):
        from django.core import mail
        import re

        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            self.client.post(
                reverse("accounts:password_reset"), {"email": "ada@example.com"}
            )
        body = mail.outbox[0].body
        link = re.search(r"http://testserver/accounts/password-reset/\S+", body).group(0)

        # Visiting the emailed link redirects to the internal set-password URL.
        response = self.client.get(link, follow=True)
        set_url = response.request["PATH_INFO"]
        self.assertTrue(set_url.endswith("/set-password/"))

        response = self.client.post(
            set_url, {"new_password1": "NewBrew!2026", "new_password2": "NewBrew!2026"}
        )
        self.assertRedirects(response, reverse("accounts:password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("NewBrew!2026"))
        self.assertTrue(self.client.login(email="ada@example.com", password="NewBrew!2026"))

    def test_reused_link_shows_invalid_page(self):
        from django.core import mail
        import re

        with self.settings(
            EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend"
        ):
            self.client.post(
                reverse("accounts:password_reset"), {"email": "ada@example.com"}
            )
        link = re.search(
            r"http://testserver/accounts/password-reset/\S+", mail.outbox[0].body
        ).group(0)

        first = self.client.get(link, follow=True)
        self.client.post(
            first.request["PATH_INFO"],
            {"new_password1": "NewBrew!2026", "new_password2": "NewBrew!2026"},
        )

        response = self.client.get(link, follow=True)
        self.assertContains(response, "no longer")


@override_settings(TWO_FACTOR_ENABLED=True)
class TwoFactorTests(TestCase):
    def test_opted_in_account_requires_code(self):
        user = User.objects.create_user(
            email="secure@example.com",
            password="testpass123",
            two_factor_enabled=True,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("2fa/verify/", response["Location"])
        self.assertEqual(len(mail.outbox), 1)

        code = self.client.session["2fa_code"]
        verified = self.client.post(
            reverse("accounts:two_factor_verify"),
            {"code": code, "next": reverse("accounts:dashboard")},
        )
        self.assertEqual(verified.status_code, 302)
        self.assertEqual(
            self.client.get(reverse("accounts:dashboard")).status_code, 200
        )


class BootstrapAdminTests(TestCase):
    @mock.patch.dict(
        os.environ,
        {
            "DJANGO_SUPERUSER_EMAIL": "Owner@Example.com",
            "DJANGO_SUPERUSER_PASSWORD": "strong-bootstrap-pass",
        },
    )
    def test_creates_admin_from_environment(self):
        call_command("bootstrap_admin", verbosity=0)
        user = User.objects.get(email="owner@example.com")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("strong-bootstrap-pass"))

    @mock.patch.dict(
        os.environ,
        {
            "DJANGO_SUPERUSER_EMAIL": "existing@example.com",
            "DJANGO_SUPERUSER_PASSWORD": "new-pass",
        },
    )
    def test_existing_account_password_is_not_overwritten(self):
        User.objects.create_user(
            email="existing@example.com", password="original-pass"
        )
        call_command("bootstrap_admin", verbosity=0)
        user = User.objects.get(email="existing@example.com")
        self.assertTrue(user.check_password("original-pass"))
        self.assertTrue(user.is_superuser)


class AdminLoginTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            email="owner@example.com", password="StrongAdmin!2026"
        )

    def test_admin_login_accepts_email_in_any_case(self):
        response = self.client.post(
            reverse("admin:login"),
            {
                "username": "OWNER@EXAMPLE.COM",
                "password": "StrongAdmin!2026",
                "next": reverse("admin:index"),
            },
        )
        self.assertRedirects(response, reverse("admin:index"), fetch_redirect_response=False)
        self.assertEqual(int(self.client.session["_auth_user_id"]), self.admin.pk)


class BootstrapDemoAccountsTests(TestCase):
    @mock.patch.dict(os.environ, {"BOOTSTRAP_DEMO_ACCOUNTS": "1"})
    def test_repairs_existing_demo_accounts(self):
        admin = User.objects.create_user(
            email="admin@coffeebliss.test",
            password="stale-password",
            role=User.Role.CUSTOMER,
            is_staff=False,
            is_superuser=False,
        )
        customer = User.objects.create_user(
            email="customer1@example.com", password="stale-password"
        )

        call_command("bootstrap_demo_accounts", verbosity=0, stdout=StringIO())

        admin.refresh_from_db()
        customer.refresh_from_db()
        self.assertTrue(admin.check_password("admin12345"))
        self.assertEqual(admin.role, User.Role.ADMIN)
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)
        self.assertTrue(customer.check_password("demo12345"))
        self.assertTrue(
            self.client.login(email="ADMIN@COFFEEBLISS.TEST", password="admin12345")
        )

    @mock.patch.dict(
        os.environ,
        {"BOOTSTRAP_DEMO_ACCOUNTS": "0", "SEED_DEMO_DATA": "0"},
    )
    def test_refuses_without_opt_in(self):
        with self.assertRaises(CommandError):
            call_command("bootstrap_demo_accounts", verbosity=0, stdout=StringIO())
