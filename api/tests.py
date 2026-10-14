from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from accounts.models import User
from store.models import Category, Product


class ApiTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="API Latte", category=self.category, kind=Product.Kind.DRINK, price=Decimal("5.00")
        )

    def test_product_list(self):
        response = self.client.get("/api/products/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_register_and_me(self):
        response = self.client.post(
            "/api/auth/register/",
            {"email": "api@example.com", "first_name": "A", "last_name": "B", "password": "strongpass123"},
        )
        self.assertEqual(response.status_code, 201)
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["email"], "api@example.com")

    def test_cart_endpoint(self):
        response = self.client.post(
            "/api/cart/", {"product_id": self.product.id, "quantity": 2}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["items"][0]["quantity"], 2)

    def test_schema_available(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, 200)
