from unittest import mock

from django.test import TestCase
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
