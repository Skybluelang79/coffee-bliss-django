import hashlib
import hmac
import json
from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch

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
    OrderItem,
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

    def test_checkout_requires_sign_in(self):
        self.client.post(reverse("orders:cart_add", args=[self.product.id]), {"quantity": 1})
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)
        self.assertIn("next", response.url)


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

    def _pay(self):
        """Complete the demo-gateway payment step for the only order."""
        order = Order.objects.get()
        self.client.post(reverse("orders:payment_simulate", args=[order.number]))
        order.refresh_from_db()
        return order

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

        order = self._pay()
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
        self._pay()
        order = Order.objects.get()

        ok, error = payments.refund_order(order)
        self.assertTrue(ok, error)
        card.refresh_from_db()
        self.assertEqual(card.balance, Decimal("5.00"))
        self.assertTrue(
            GiftCardTransaction.objects.filter(kind=GiftCardTransaction.Kind.REFUND).exists()
        )

    def test_partial_refund_credits_gift_card_proportionally(self):
        from orders import payments

        card = GiftCard.objects.create(initial_balance=Decimal("5.00"), balance=Decimal("5.00"))
        self.client.login(email="gift@example.com", password="pw")
        self._add_to_cart(quantity=2)  # total after gift card = 21.50 - 5.00 = 16.50
        self.client.post(reverse("orders:apply_gift_card"), {"code": card.code})
        self._checkout()
        self._pay()
        order = Order.objects.get()

        ok, error = payments.refund_order(order, amount=Decimal("8.25"))  # half of 16.50
        self.assertTrue(ok, error)
        card.refresh_from_db()
        self.assertEqual(card.balance, Decimal("2.50"))


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
        # Card checkout stops at the payment step (demo gateway in dev).
        self.assertEqual(response.url, reverse("orders:payment", args=[order.number]))
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

        page = self.client.get(response.url)
        self.assertContains(page, "Demo payment gateway")

        self.client.post(reverse("orders:payment_simulate", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        # inventory consumed via recipe
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("960"))

    def test_payment_page_falls_back_when_provider_fails(self):
        self._place_order("card")
        order = Order.objects.get()
        fake_intent = {
            "client_secret": "secret",
            "payment_intent_id": "pi_broken",
            "simulated": False,
        }
        with self.settings(
            STRIPE_SECRET_KEY="sk_test_bad",
            STRIPE_PUBLISHABLE_KEY="pk_test_bad",
        ):
            with patch(
                "orders.views.payments.is_configured", return_value=True
            ), patch(
                "orders.views.payments.create_payment_intent",
                side_effect=[Exception("provider down"), fake_intent],
            ):
                page = self.client.get(reverse("orders:payment", args=[order.number]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "demo gateway")

    def test_cash_checkout_marks_paid(self):
        self._place_order("cash")
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)

    def test_refund_restores_stock(self):
        from orders import payments

        self._place_order("card")
        order = Order.objects.get()
        self.client.post(reverse("orders:payment_simulate", args=[order.number]))
        order.refresh_from_db()
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
@override_settings(
    STRIPE_SECRET_KEY="",
    STRIPE_PUBLISHABLE_KEY="",
    PAYSTACK_SECRET_KEY="sk_test_paystack",
    PAYSTACK_PUBLIC_KEY="pk_test_paystack",
    PAYSTACK_CURRENCY="NGN",
)
class PaystackPaymentTests(TestCase):
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

    def _place_order(self):
        self.client.login(email="buyer@example.com", password="pw")
        self.client.post(reverse("orders:cart_add", args=[self.product.pk]), {"quantity": 2})
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

    def _payload(self, order, reference="PS-REF-1", amount=None):
        return {
            "status": "success",
            "reference": reference,
            "amount": int(order.total * 100) if amount is None else amount,
            "currency": "NGN",
            "metadata": {"order_number": order.number},
        }

    def test_payment_page_offers_paystack(self):
        self._place_order()
        order = Order.objects.get()
        page = self.client.get(reverse("orders:payment", args=[order.number]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Pay with Paystack")
        self.assertNotContains(page, "Demo payment gateway")

    def test_initialize_redirects_to_paystack_checkout(self):
        self._place_order()
        order = Order.objects.get()

        def fake_request(method, path, payload=None):
            return {
                "status": True,
                "data": {
                    "authorization_url": "https://checkout.paystack.com/test",
                    "access_code": "access",
                    "reference": payload["reference"],
                },
            }

        with patch("orders.payments._paystack_request", side_effect=fake_request) as api:
            response = self.client.post(
                reverse("orders:paystack_initialize", args=[order.number])
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "https://checkout.paystack.com/test")
        args = api.call_args.args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/transaction/initialize")
        self.assertEqual(args[2]["amount"], int(order.total * 100))
        self.assertEqual(args[2]["currency"], "NGN")
        self.assertEqual(args[2]["email"], "buyer@example.com")
        self.assertEqual(args[2]["channels"], ["card"])
        payment = order.payments.get()
        self.assertTrue(payment.paystack_reference.startswith("CBPS-"))

    def test_callback_marks_order_paid(self):
        self._place_order()
        order = Order.objects.get()
        data = self._payload(order, reference="PS-REF-CALLBACK")
        with patch(
            "orders.payments.verify_paystack_transaction", return_value=data
        ):
            response = self.client.get(
                reverse("orders:paystack_callback", args=[order.number])
                + "?reference=PS-REF-CALLBACK"
            )

        self.assertRedirects(
            response, reverse("orders:order_confirmation", args=[order.number])
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.payments.get().paystack_reference, "PS-REF-CALLBACK")
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("960"))

    def test_callback_rejects_wrong_amount(self):
        self._place_order()
        order = Order.objects.get()
        data = self._payload(order, reference="PS-REF-LOW", amount=100)
        with patch(
            "orders.payments.verify_paystack_transaction", return_value=data
        ):
            response = self.client.get(
                reverse("orders:paystack_callback", args=[order.number])
                + "?reference=PS-REF-LOW"
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn(
            reverse("orders:payment", args=[order.number]), response.url
        )
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("1000"))

    def test_webhook_marks_order_paid(self):
        self._place_order()
        order = Order.objects.get()
        payload = json.dumps(
            {"event": "charge.success", "data": self._payload(order, "PS-REF-HOOK")}
        ).encode()
        signature = hmac.new(
            b"sk_test_paystack", payload, hashlib.sha512
        ).hexdigest()

        response = self.client.post(
            reverse("orders:paystack_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.PAID)
        self.assertEqual(order.payments.get().paystack_reference, "PS-REF-HOOK")

    def test_webhook_rejects_bad_signature(self):
        self._place_order()
        order = Order.objects.get()
        payload = json.dumps(
            {"event": "charge.success", "data": self._payload(order, "PS-REF-BAD")}
        ).encode()

        response = self.client.post(
            reverse("orders:paystack_webhook"),
            data=payload,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE="nope",
        )

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

    def test_demo_gateway_is_disabled_when_paystack_configured(self):
        self._place_order()
        order = Order.objects.get()
        self.client.post(reverse("orders:payment_simulate", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)

    def test_refund_uses_paystack(self):
        from orders import payments

        self._place_order()
        order = Order.objects.get()
        data = self._payload(order, reference="PS-REF-REFUND")
        with patch("orders.payments.verify_paystack_transaction", return_value=data):
            self.client.get(
                reverse("orders:paystack_callback", args=[order.number])
                + "?reference=PS-REF-REFUND"
            )
        order.refresh_from_db()

        with patch(
            "orders.payments._paystack_request",
            return_value={"status": True, "data": {}},
        ) as api:
            ok, error = payments.refund_order(order)

        self.assertTrue(ok, error)
        args = api.call_args.args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "/refund")
        self.assertEqual(args[2]["transaction"], "PS-REF-REFUND")
        self.assertEqual(args[2]["amount"], int(order.total * 100))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("1000"))


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


@FAST
@override_settings(
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    STRIPE_SECRET_KEY="",
    STRIPE_PUBLISHABLE_KEY="",
)
class TrackingTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Flat White",
            category=self.category,
            kind=Product.Kind.DRINK,
            price=Decimal("4.50"),
            prep_time_minutes=6,
        )
        self.user = User.objects.create_user(
            email="tracker@example.com", password="trackpass123"
        )
        self.other = User.objects.create_user(
            email="stranger@example.com", password="nope12345"
        )

    def _order(self, status=Order.Status.PENDING, paid=False, fulfillment="pickup"):
        order = Order.objects.create(
            user=self.user,
            customer_name="Tracker",
            customer_phone="5551234",
            fulfillment=fulfillment,
            notify_email=True,
        )
        OrderItem.objects.create(
            order=order,
            product=self.product,
            name=self.product.name,
            unit_price=self.product.price,
            quantity=2,
        )
        order = order.recalculate()
        order.save()
        order.ensure_estimated_ready_at()
        if paid:
            order.payment_status = Order.PaymentStatus.PAID
            order.save(update_fields=["payment_status"])
            Payment.objects.create(
                order=order,
                method=Payment.Method.CARD,
                amount=order.total,
                state=Payment.State.SUCCEEDED,
                is_successful=True,
            )
        if status != Order.Status.PENDING:
            order.status = status
            order.save(update_fields=["status", "updated_at"])
        return order

    def test_track_page_renders_with_eta(self):
        order = self._order()
        order.estimated_ready_at = None
        order.save(update_fields=["estimated_ready_at"])
        response = self.client.get(reverse("orders:track", args=[order.number]))
        self.assertEqual(response.status_code, 200)
        order.refresh_from_db()
        self.assertIsNotNone(order.estimated_ready_at)
        self.assertContains(response, order.number)

    def test_status_endpoint_json(self):
        order = self._order(status=Order.Status.PREPARING)
        response = self.client.get(reverse("orders:track_status", args=[order.number]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], Order.Status.PREPARING)
        self.assertIn("steps", data)
        self.assertEqual(len(data["steps"]), 5)
        self.assertIn("courier", data)

    def test_cancel_unpaid_order(self):
        order = self._order()
        self.client.login(email="tracker@example.com", password="trackpass123")
        response = self.client.post(reverse("orders:cancel", args=[order.number]))
        self.assertRedirects(response, reverse("orders:track", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_cancel_requires_ownership(self):
        order = self._order()
        self.client.login(email="stranger@example.com", password="nope12345")
        response = self.client.post(reverse("orders:cancel", args=[order.number]))
        self.assertEqual(response.status_code, 404)
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.CANCELLED)

    def test_cancel_not_allowed_when_ready(self):
        order = self._order(status=Order.Status.READY)
        self.client.login(email="tracker@example.com", password="trackpass123")
        self.client.post(reverse("orders:cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertNotEqual(order.status, Order.Status.CANCELLED)

    def test_cancel_paid_order_refunds(self):
        order = self._order(paid=True)
        self.client.login(email="tracker@example.com", password="trackpass123")
        self.client.post(reverse("orders:cancel", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.payment_status, Order.PaymentStatus.REFUNDED)

    def test_reorder_populates_cart(self):
        order = self._order()
        self.client.login(email="tracker@example.com", password="trackpass123")
        response = self.client.post(reverse("orders:reorder", args=[order.number]))
        self.assertRedirects(response, reverse("orders:cart"))
        cart = self.client.session.get("coffee_cart")
        self.assertIn(str(self.product.pk), cart)
        self.assertEqual(cart[str(self.product.pk)]["quantity"], 2)

    def test_receipt_owner_only(self):
        order = self._order(status=Order.Status.COMPLETED)
        url = reverse("orders:receipt", args=[order.number])
        self.assertEqual(self.client.get(url).status_code, 302)  # anon → login
        self.client.login(email="stranger@example.com", password="nope12345")
        self.assertEqual(self.client.get(url).status_code, 404)
        self.client.login(email="tracker@example.com", password="trackpass123")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, order.number)

    def test_rate_and_tip_completed_order(self):
        order = self._order(status=Order.Status.COMPLETED, paid=True)
        total_before = order.total
        self.client.login(email="tracker@example.com", password="trackpass123")
        response = self.client.post(
            reverse("orders:rate", args=[order.number]),
            {"rating": 5, "feedback": "Delicious", "tip": "2.00"},
        )
        self.assertRedirects(response, reverse("orders:track", args=[order.number]))
        order.refresh_from_db()
        self.assertEqual(order.rating, 5)
        self.assertEqual(order.feedback, "Delicious")
        self.assertEqual(order.tip, Decimal("2.00"))
        self.assertEqual(order.total, total_before + Decimal("2.00"))
        self.assertTrue(
            order.payments.filter(reference=f"TIP-{order.number}").exists()
        )

    def test_rate_rejected_before_completion(self):
        order = self._order(status=Order.Status.PREPARING)
        self.client.login(email="tracker@example.com", password="trackpass123")
        self.client.post(reverse("orders:rate", args=[order.number]), {"rating": 4})
        order.refresh_from_db()
        self.assertIsNone(order.rating)

    def test_notify_pref_unsubscribe_via_token(self):
        order = self._order()
        token = order.notification_token()
        response = self.client.get(reverse("orders:notify_pref"), {"token": token, "off": "1"})
        self.assertRedirects(response, reverse("orders:track", args=[order.number]))
        order.refresh_from_db()
        self.assertFalse(order.notify_email)

    def test_status_change_sends_email(self):
        order = self._order()
        with self.captureOnCommitCallbacks(execute=True):
            order.status = Order.Status.CONFIRMED
            order.save(update_fields=["status", "updated_at"])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(order.number, mail.outbox[0].subject)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_track_lookup_by_email_lists_orders(self):
        self._order()
        response = self.client.get(reverse("orders:track_lookup"), {"number": self.user.email})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CB")

    def test_track_lookup_by_number_redirects(self):
        order = self._order()
        response = self.client.get(reverse("orders:track_lookup"), {"number": order.number.lower()})
        self.assertRedirects(response, reverse("orders:track", args=[order.number]))

    def test_courier_live_flag(self):
        order = self._order(status=Order.Status.OUT_FOR_DELIVERY, fulfillment="delivery")
        self.assertFalse(order.courier_is_live)
        order.courier_lat = Decimal("40.000000")
        order.courier_lng = Decimal("-73.000000")
        order.courier_updated_at = timezone.now()
        order.save()
        self.assertTrue(order.courier_is_live)




