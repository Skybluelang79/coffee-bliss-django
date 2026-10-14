from decimal import Decimal

from django.test import TestCase, override_settings

from accounts.models import User
from inventory.models import Ingredient, RecipeItem, StockMovement
from inventory.services import adjust_ingredient, consume_for_order, restock, restore_for_order
from orders.models import Order, OrderItem
from store.models import Category, Product

FAST = override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])


class InventoryServiceTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="Coffee", icon="☕")
        self.product = Product.objects.create(
            name="Caramel Latte",
            category=self.category,
            kind=Product.Kind.DRINK,
            price=Decimal("4.75"),
            track_stock=False,
        )
        self.beans = Ingredient.objects.create(
            name="Beans", unit=Ingredient.Unit.GRAM, stock=Decimal("1000"),
            reorder_level=Decimal("100"), cost_per_unit=Decimal("0.02"),
        )
        self.milk = Ingredient.objects.create(
            name="Milk", unit=Ingredient.Unit.MILLILITRE, stock=Decimal("5000"),
            reorder_level=Decimal("500"), cost_per_unit=Decimal("0.001"),
        )
        RecipeItem.objects.create(product=self.product, ingredient=self.beans, quantity=Decimal("18"))
        RecipeItem.objects.create(product=self.product, ingredient=self.milk, quantity=Decimal("200"))

    def _order(self, qty=2):
        order = Order.objects.create(customer_name="Test", fulfillment=Order.Fulfillment.PICKUP)
        OrderItem.objects.create(
            order=order, product=self.product, name=self.product.name,
            unit_price=self.product.price, quantity=qty,
        )
        return order.recalculate()

    def test_consume_deducts_recipe_ingredients(self):
        order = self._order(qty=2)
        consume_for_order(order)
        self.beans.refresh_from_db(); self.milk.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("964"))  # 1000 - 18*2
        self.assertEqual(self.milk.stock, Decimal("4600"))  # 5000 - 200*2
        self.assertTrue(Order.objects.get(pk=order.pk).stock_consumed)

    def test_consume_is_idempotent(self):
        order = self._order(qty=1)
        consume_for_order(order)
        consume_for_order(order)  # should be a no-op
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("982"))

    def test_restore_puts_stock_back(self):
        order = self._order(qty=2)
        consume_for_order(order)
        restore_for_order(order)
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("1000"))
        self.assertFalse(Order.objects.get(pk=order.pk).stock_consumed)

    def test_restock_and_movement_logged(self):
        restock(self.beans, Decimal("500"), reason="Delivery")
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("1500"))
        movement = StockMovement.objects.filter(ingredient=self.beans, kind=StockMovement.Kind.PURCHASE).first()
        self.assertEqual(movement.quantity, Decimal("500"))

    def test_adjust_sets_absolute_value(self):
        adjust_ingredient(self.beans, Decimal("42"), reason="Count")
        self.beans.refresh_from_db()
        self.assertEqual(self.beans.stock, Decimal("42"))

    def test_low_stock_flag(self):
        self.beans.stock = Decimal("50")
        self.beans.save()
        self.assertTrue(self.beans.is_low)


@FAST
class InventoryViewTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            email="staff@example.com", password="pw", role=User.Role.STAFF, is_staff=True
        )
        self.customer = User.objects.create_user(email="c@example.com", password="pw")
        Ingredient.objects.create(name="Beans", unit=Ingredient.Unit.GRAM, stock=Decimal("10"))

    def test_inventory_requires_staff(self):
        self.client.login(email="c@example.com", password="pw")
        response = self.client.get("/inventory/")
        self.assertEqual(response.status_code, 302)

    def test_inventory_page_renders_for_staff(self):
        self.client.login(email="staff@example.com", password="pw")
        response = self.client.get("/inventory/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inventory")
