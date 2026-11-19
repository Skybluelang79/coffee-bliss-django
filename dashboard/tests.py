from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User


class DashboardAccessTests(TestCase):
    def setUp(self):
        cache.clear()
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

    def test_customer_cannot_access_ai_insights(self):
        self.client.login(email="c@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_insights"))
        self.assertEqual(response.status_code, 302)

    def test_staff_cannot_access_ai_insights(self):
        self.client.login(email="s@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_insights"))
        self.assertEqual(response.status_code, 302)

    @override_settings(AI_API_KEY="", AI_ENABLED=True)
    def test_manager_can_access_ai_insights(self):
        self.client.login(email="m@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_insights"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Executive brief")
        self.assertContains(response, "Local analysis")
        self.assertContains(response, reverse("dashboard:refresh_admin_insights"))

    def test_refresh_insights_requires_post_and_manager(self):
        url = reverse("dashboard:refresh_admin_insights")
        self.client.login(email="m@example.com", password="testpass123")
        self.assertEqual(self.client.get(url).status_code, 405)
        response = self.client.post(url)
        self.assertRedirects(response, reverse("dashboard:admin_insights"))

    def test_manager_nav_and_footer_links_are_named(self):
        self.client.login(email="m@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:admin_home"))
        self.assertContains(response, reverse("dashboard:admin_insights"))
        self.assertContains(response, reverse("staff_portal"))
        self.assertContains(response, reverse("api:docs"))
        self.assertContains(response, reverse("store:legal", args=["privacy"]))

    def test_staff_portal_routes_staff_to_operations(self):
        self.client.login(email="s@example.com", password="testpass123")
        response = self.client.get(reverse("staff_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Operations")

    def test_staff_portal_routes_manager_to_analytics(self):
        self.client.login(email="m@example.com", password="testpass123")
        response = self.client.get(reverse("staff_portal"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Business dashboard")
