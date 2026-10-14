from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import User
from inventory.models import Ingredient, RecipeItem
from orders.models import Order, Payment
from store.models import Category, Coupon, Product

FAST = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


class CartAndCheckoutTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Espresso", category=self.category, kind=Product.Kind.DRINK, price=Decimal("3.00")
        )
        self.user = User.objects.create_user(
            email="buyer@example.com", password="testpass123"
        )

    def test_add_to_cart(self):
        response = self.client.post(
            reverse("orders:cart_add", args=[self.product.id]), {"quantity": 2}
        )
        self.assertRedirects(response, reverse("orders:cart"))
        cart = self.client.session.get("coffee_cart")
        self.assertEqual(cart[str(self.product.id)]["quantity"], 2)

    def test_checkout_creates_order(self):
        self.client.login(email="buyer@example.com", password="testpass123")
        self.client.post(reverse("orders:cart_add", args=[self.product.id]), {"quantity": 3})
        response = self.client.post(
            reverse("orders:checkout"),
            {
                "fulfillment": "pickup",
                "customer_name": "Test Buyer",
                "customer_phone": "555",
                "note": "",
                "coupon_code": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.user, self.user)
        self.assertEqual(order.items.count(), 1)
        self.assertEqual(order.subtotal, Decimal("9.00"))
        # loyalty points earned (10 per dollar)
        self.user.refresh_from_db()
        self.assertGreater(self.user.loyalty_points, 0)

    def test_coupon_applied(self):
        Coupon.objects.create(
            code="SAVE10", discount_type="percent", value=Decimal("10"), minimum_spend=0
        )
        self.client.post(reverse("orders:cart_add", args=[self.product.id]), {"quantity": 10})
        response = self.client.post(reverse("orders:apply_coupon"), {"code": "SAVE10"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.session.get("coffee_coupon"), "SAVE10")

    def test_order_number_generated(self):
        order = Order.objects.create(customer_name="Walk In")
        self.assertTrue(order.number.startswith("CB"))


@FAST
@override_settings(STRIPE_SECRET_KEY="", STRIPE_PUBLISHABLE_KEY="")
class PaymentFlowTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Latte", category=self.category, kind=Product.Kind.DRINK,
            price=Decimal("4.00"), track_stock=False,
        )
        self.beans = Ingredient.objects.create(
            name="Beans", unit=Ingredient.Unit.GRAM, stock=Decimal("1000"),
            cost_per_unit=Decimal("0.02"),
        )
        RecipeItem.objects.create(product=self.product, ingredient=self.beans, quantity=Decimal("20"))
        self.user = User.objects.create_user(email="buyer@example.com", password="pw")

    def _place_order(self, method="card"):
        self.client.login(email="buyer@example.com", password="pw")
        self.client.post(reverse("orders:cart_add", args=[self.product.pk]), {"quantity": 2})
        return self.client.post(
            reverse("orders:checkout"),
            {
                "fulfillment": "pickup",
                "payment_method": method,
                "customer_name": "Buyer",
                "customer_phone": "555",
                "coupon_code": "",
            },
        )

    def test_card_checkout_simulated_marks_paid(self):
        response = self._place_order("card")
        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        # inventory consumed via recipe
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("960"))

    def test_cash_checkout_marks_paid(self):
        self._place_order("cash")
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_refund_restores_stock(self):
        from orders import payments

        self._place_order("card")
        order = Order.objects.get()
        ok, error = payments.refund_order(order)
        self.assertTrue(ok, error)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("1000"))

    def test_webhook_unconfigured_returns_400(self):
        response = self.client.post(
            reverse("orders:stripe_webhook"), data="{}", content_type="application/json"
        )
        self.assertEqual(response.status_code, 400)


@FAST
class KitchenDisplayTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pw", role=User.Role.STAFF, is_staff=True
        )
        self.customer = User.objects.create_user(email="c@example.com", password="pw")

    def test_kds_requires_staff(self):
        self.client.login(email="c@example.com", password="pw")
        response = self.client.get(reverse("dashboard:staff_kds"))
        self.assertEqual(response.status_code, 302)

    def test_kds_renders_for_staff(self):
        self.client.login(email="staff@example.com", password="pw")
        response = self.client.get(reverse("dashboard:staff_kds"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kitchen display")


@FAST
class KitchenConsumerTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="kds-staff@example.com", password="pw",
            role=User.Role.STAFF, is_staff=True,
        )
        self.customer = User.objects.create_user(email="kds-c@example.com", password="pw")

    def _communicator(self, user):
        from channels.testing import WebsocketCommunicator

        from orders.consumers import KitchenConsumer

        async def app(scope, receive, send):
            scope["user"] = user
            await KitchenConsumer.as_asgi()(scope, receive, send)

        return WebsocketCommunicator(app, "/ws/kitchen/")

    async def test_staff_connects_and_receives_updates(self):
        from channels.layers import get_channel_layer

        communicator = self._communicator(self.staff)
        connected, _ = await communicator.connect()
        self.assertTrue(connected)
        greeting = await communicator.receive_json_from()
        self.assertEqual(greeting["type"], "connected")

        await get_channel_layer().group_send(
            "kitchen",
            {"type": "order.update", "order": {"number": "CB-TEST", "status": "pending", "items": []}},
        )
        message = await communicator.receive_json_from()
        self.assertEqual(message["type"], "order.update")
        self.assertEqual(message["order"]["number"], "CB-TEST")
        await communicator.disconnect()

    async def test_anonymous_is_rejected(self):
        communicator = self._communicator(self.customer)
        connected, _ = await communicator.connect()
        self.assertFalse(connected)



