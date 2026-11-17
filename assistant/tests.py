import json
from decimal import Decimal
from unittest import mock

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from assistant.services import (
    ask_assistant,
    build_customer_context,
    local_reply,
)
from store.models import Category, Product


class AssistantViewTests(TestCase):
    def post_chat(self, url, message):
        return self.client.post(
            url,
            data=json.dumps({"message": message}),
            content_type="application/json",
        )

    def test_customer_chat_uses_offline_responder(self):
        response = self.post_chat(reverse("assistant:customer_chat"), "hello")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "local")
        self.assertIn("menu", data["reply"].lower())

    def test_chat_requires_post_and_json(self):
        url = reverse("assistant:customer_chat")
        self.assertEqual(self.client.get(url).status_code, 405)
        bad = self.client.post(url, data="not-json", content_type="application/json")
        self.assertEqual(bad.status_code, 400)
        empty = self.post_chat(url, "   ")
        self.assertEqual(empty.status_code, 400)
        long = self.post_chat(url, "x" * 1001)
        self.assertEqual(long.status_code, 400)

    def test_staff_chat_requires_staff_role(self):
        password = "testpass123"
        User.objects.create_user(
            email="c@example.com", password=password, role=User.Role.CUSTOMER
        )
        staff = User.objects.create_user(
            email="s@example.com", password=password, role=User.Role.STAFF, is_staff=True
        )
        url = reverse("assistant:staff_chat")
        self.client.login(email="c@example.com", password=password)
        self.assertEqual(self.post_chat(url, "stock?").status_code, 403)
        self.client.login(email="s@example.com", password=password)
        response = self.post_chat(url, "stock?")
        self.assertEqual(response.status_code, 200)
        self.assertIn("ingredient", response.json()["reply"].lower())
        self.assertTrue(staff.is_staff_member)

    @override_settings(AI_RATE_LIMIT=1)
    def test_rate_limit_applies_per_surface(self):
        url = reverse("assistant:customer_chat")
        self.assertEqual(self.post_chat(url, "hi").status_code, 200)
        self.assertEqual(self.post_chat(url, "hi again").status_code, 429)

    def test_reset_clears_session_history(self):
        key = "assistant_customer_history"
        self.post_chat(reverse("assistant:customer_chat"), "hello")
        self.assertTrue(self.client.session.get(key))
        response = self.client.post(reverse("assistant:customer_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(key, self.client.session)


class AssistantWidgetTests(TestCase):
    def test_customer_widget_is_on_storefront(self):
        response = self.client.get(reverse("store:home"))
        self.assertContains(response, 'data-surface="customer"')
        self.assertContains(response, "Ask Bean")

    def test_staff_widget_is_on_staff_dashboard(self):
        User.objects.create_user(
            email="s@example.com",
            password="testpass123",
            role=User.Role.STAFF,
            is_staff=True,
        )
        self.client.login(email="s@example.com", password="testpass123")
        response = self.client.get(reverse("dashboard:staff_home"))
        self.assertContains(response, 'data-surface="staff"')
        self.assertNotContains(response, 'data-surface="customer"')

    @override_settings(AI_ENABLED=False)
    def test_widget_can_be_disabled(self):
        response = self.client.get(reverse("store:home"))
        self.assertNotContains(response, "data-assistant")


class AssistantServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Category.objects.create(name="Coffee", icon="☕")
        cls.product = Product.objects.create(
            name="House Blend Beans",
            category=category,
            kind=Product.Kind.BEANS,
            price=Decimal("9000.00"),
            short_description="A smooth everyday roast",
        )

    def test_context_uses_live_catalogue_data(self):
        context = build_customer_context()
        self.assertIn("House Blend Beans", context)
        self.assertIn("₦9,000.00", context)

    def test_bean_question_matches_menu_not_loyalty(self):
        reply = local_reply("customer", "do you sell coffee beans?")
        self.assertIn("House Blend Beans", reply)
        self.assertNotIn("beans, worth", reply)

    @override_settings(AI_API_KEY="test-key")
    def test_configured_service_uses_chat_completion(self):
        with mock.patch(
            "assistant.services._chat_completion", return_value="Fresh beans daily!"
        ) as completion:
            result = ask_assistant("customer", "What beans do you have?", [], None)
        self.assertEqual(result, {"reply": "Fresh beans daily!", "source": "ai"})
        system = completion.call_args.args[0][0]["content"]
        self.assertIn("House Blend Beans", system)

    @override_settings(AI_API_KEY="test-key")
    def test_api_errors_fall_back_to_local_reply(self):
        with mock.patch(
            "assistant.services._chat_completion", side_effect=RuntimeError("boom")
        ):
            result = ask_assistant("customer", "hello", [], None)
        self.assertEqual(result["source"], "local")
        self.assertTrue(result["reply"])
