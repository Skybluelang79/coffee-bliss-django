from django.test import TestCase
from django.urls import reverse

from accounts.models import User


class DashboardAccessTests(TestCase):
    def setUp(self):
        self.customer = User.objects.create_user(
            email="c@example.com", password="testpass123", role=User.Role.CUSTOMER
        )
        self.staff = User.objects.create_user(
            email="s@example.com", password="testpass123", role=User.Role.STAFF, is_staff=True
        )
        self.manager = User.objects.create_user(
            email="m@example.com", password="testpass123", role=User.Role.MANAGER, is_staff=True
        )

    def test_staff_board_requires_staff(self):
        self.client.login(email="c@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:staff_home"))
        self.assertEqual(response.status_code, 302)

    def test_staff_can_access_board(self):
        self.client.login(email="s@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:staff_home"))
        self.assertEqual(response.status_code, 200)

    def test_manager_can_access_analytics(self):
        self.client.login(email="m@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_home"))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_access_analytics(self):
        self.client.login(email="s@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_home"))
        self.assertEqual(response.status_code, 302)
