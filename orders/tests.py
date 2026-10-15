from decimal import Decimal
from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from inventory.models import Ingredient, RecipeItem
from orders.models import (
    AbandonedCart,
    GiftCard,
    GiftCardTransaction,
    Order,
    Payment,
)
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
class GiftCardTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Latte",
            category=self.category,
            kind=Product.Kind.DRINK,
            price=Decimal("10.00"),
            track_stock=False,
        )
        self.user = User.objects.create_user(email="gift@example.com", password="pw")

    def _add_to_cart(self, quantity=1):
        self.client.post(
            reverse("orders:cart_add", args=[self.product.pk]), {"quantity": quantity}
        )

    def _checkout(self):
        return self.client.post(
            reverse("orders:checkout"),
            {
                "fulfillment": "pickup",
                "payment_method": "card",
                "customer_name": "Buyer",
                "customer_phone": "555",
                "coupon_code": "",
            },
        )

    def test_code_generated(self):
        card = GiftCard.objects.create(initial_balance=Decimal("10.00"), balance=Decimal("10.00"))
        self.assertTrue(card.code.startswith("CB-"))
        self.assertEqual(card.state, GiftCard.State.ACTIVE)

    def test_apply_gift_card_to_session(self):
        card = GiftCard.objects.create(initial_balance=Decimal("20.00"), balance=Decimal("20.00"))
        self._add_to_cart()
        response = self.client.post(reverse("orders:apply_gift_card"), {"code": card.code})
        self.assertRedirects(response, reverse("orders:cart"))
        self.assertEqual(self.client.session.get("coffee_gift_card"), card.code)

    def test_invalid_gift_card_rejected(self):
        self._add_to_cart()
        self.client.post(reverse("orders:apply_gift_card"), {"code": "CB-NOPE-NOPE-NOPE"})
        self.assertIsNone(self.client.session.get("coffee_gift_card"))

    def test_checkout_partial_gift_card(self):
        card = GiftCard.objects.create(initial_balance=Decimal("5.00"), balance=Decimal("5.00"))
        self.client.login(email="gift@example.com", password="pw")
        self._add_to_cart(quantity=2)  # subtotal 20 + 7.5% tax = 21.50
        self.client.post(reverse("orders:apply_gift_card"), {"code": card.code})
        self._checkout()

        order = Order.objects.get()
        self.assertEqual(order.gift_card, card)
        self.assertEqual(order.gift_card_amount, Decimal("5.00"))
        self.assertEqual(order.total, Decimal("16.50"))
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        card.refresh_from_db()
        self.assertEqual(card.balance, Decimal("0.00"))
        tx = GiftCardTransaction.objects.get(kind=GiftCardTransaction.Kind.REDEMPTION)
        self.assertEqual(tx.amount, Decimal("-5.00"))

    def test_checkout_fully_covered_by_gift_card(self):
        card = GiftCard.objects.create(initial_balance=Decimal("50.00"), balance=Decimal("50.00"))
        self.client.login(email="gift@example.com", password="pw")
        self._add_to_cart(quantity=1)  # subtotal 10 + tax 0.75 = 10.75
        self.client.post(reverse("orders:apply_gift_card"), {"code": card.code})
        response = self._checkout()

        self.assertEqual(response.status_code, 302)
        order = Order.objects.get()
        self.assertEqual(order.total, Decimal("0.00"))
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        card.refresh_from_db()
        self.assertEqual(card.balance, Decimal("39.25"))

    def test_refund_returns_gift_card_balance(self):
        from orders import payments

        card = GiftCard.objects.create(initial_balance=Decimal("5.00"), balance=Decimal("5.00"))
        self.client.login(email="gift@example.com", password="pw")
        self._add_to_cart(quantity=2)
        self.client.post(reverse("orders:apply_gift_card"), {"code": card.code})
        self._checkout()
        order = Order.objects.get()

        ok, error = payments.refund_order(order)
        self.assertTrue(ok, error)
        card.refresh_from_db()
        self.assertEqual(card.balance, Decimal("5.00"))
        self.assertTrue(
            GiftCardTransaction.objects.filter(kind=GiftCardTransaction.Kind.REFUND).exists()
        )


@FAST
@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class CartRecoveryTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Latte",
            category=self.category,
            kind=Product.Kind.DRINK,
            price=Decimal("4.00"),
            track_stock=False,
        )
        self.user = User.objects.create_user(email="recover@example.com", password="pw")

    def _add_to_cart(self, quantity=1):
        self.client.post(
            reverse("orders:cart_add", args=[self.product.pk]), {"quantity": quantity}
        )

    def test_cart_is_tracked(self):
        self._add_to_cart(quantity=2)
        cart = AbandonedCart.objects.get(status=AbandonedCart.Status.OPEN)
        self.assertEqual(cart.item_count, 2)
        self.assertEqual(cart.subtotal, Decimal("8.00"))
        self.assertEqual(len(cart.items), 1)

    def test_capture_email(self):
        self._add_to_cart()
        response = self.client.post(
            reverse("orders:capture_cart_email"), {"email": "guest@example.com"}
        )
        self.assertRedirects(response, reverse("orders:cart"))
        cart = AbandonedCart.objects.get(status=AbandonedCart.Status.OPEN)
        self.assertEqual(cart.email, "guest@example.com")

    def test_logged_in_email_is_captured(self):
        self.client.login(email="recover@example.com", password="pw")
        self._add_to_cart()
        cart = AbandonedCart.objects.get(status=AbandonedCart.Status.OPEN)
        self.assertEqual(cart.recipient_email, "recover@example.com")

    def test_checkout_marks_cart_recovered(self):
        self.client.login(email="recover@example.com", password="pw")
        self._add_to_cart()
        self.client.post(
            reverse("orders:checkout"),
            {
                "fulfillment": "pickup",
                "payment_method": "cash",
                "customer_name": "Buyer",
                "customer_phone": "555",
                "coupon_code": "",
            },
        )
        cart = AbandonedCart.objects.get()
        self.assertEqual(cart.status, AbandonedCart.Status.RECOVERED)
        self.assertIsNotNone(cart.order)

    def test_command_sends_reminder(self):
        self._add_to_cart()
        cart = AbandonedCart.objects.get(status=AbandonedCart.Status.OPEN)
        AbandonedCart.objects.filter(pk=cart.pk).update(
            email="guest@example.com",
            updated_at=timezone.now() - timedelta(hours=8),
        )
        call_command("recover_carts", "--hours", "6", verbosity=0)

        cart.refresh_from_db()
        self.assertEqual(cart.reminders_sent, 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("cart", mail.outbox[0].body.lower())

    def test_recent_cart_not_reminded(self):
        self._add_to_cart()
        cart = AbandonedCart.objects.get(status=AbandonedCart.Status.OPEN)
        AbandonedCart.objects.filter(pk=cart.pk).update(email="guest@example.com")
        call_command("recover_carts", "--hours", "6", verbosity=0)
        self.assertEqual(len(mail.outbox), 0)


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



