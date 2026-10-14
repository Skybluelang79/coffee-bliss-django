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
