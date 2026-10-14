from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone


class Supplier(models.Model):
    name = models.CharField(max_length=160, unique=True)
    contact_name = models.CharField(max_length=160, blank=True)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=40, blank=True)
    address = models.CharField(max_length=255, blank=True)
    lead_time_days = models.PositiveIntegerField(default=3)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Ingredient(models.Model):
    """A raw material tracked in the warehouse (beans, milk, syrup, cups…)."""

    class Unit(models.TextChoices):
        GRAM = "g", "gram"
        KILOGRAM = "kg", "kilogram"
        MILLILITRE = "ml", "millilitre"
        LITRE = "l", "litre"
        EACH = "ea", "each"

    name = models.CharField(max_length=160, unique=True)
    sku = models.CharField(max_length=60, blank=True)
    unit = models.CharField(max_length=4, choices=Unit.choices, default=Unit.GRAM)
    stock = models.DecimalField(
        max_digits=12, decimal_places=3, default=0, validators=[MinValueValidator(0)]
    )
    reorder_level = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        help_text="Reorder when stock drops to or below this level.",
    )
    par_level = models.DecimalField(
        max_digits=12, decimal_places=3, default=0,
        help_text="Target stock level when reordering.",
    )
    cost_per_unit = models.DecimalField(
        max_digits=12, decimal_places=4, default=0,
        help_text="Cost per single unit of measure.",
    )
    supplier = models.ForeignKey(
        Supplier, on_delete=models.SET_NULL, null=True, blank=True, related_name="ingredients"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.stock} {self.unit})"

    @property
    def value(self):
        return (self.stock * self.cost_per_unit).quantize(Decimal("0.01"))

    @property
    def is_low(self):
        return self.stock <= self.reorder_level

    @property
    def suggested_order_quantity(self):
        if self.stock >= self.par_level:
            return Decimal("0")
        return max(Decimal("0"), self.par_level - self.stock)


class RecipeItem(models.Model):
    """Bill-of-materials line: how much of an ingredient one product consumes."""

    product = models.ForeignKey(
        "store.Product", on_delete=models.CASCADE, related_name="recipe_items"
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.PROTECT, related_name="recipe_items"
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=3, validators=[MinValueValidator(0)]
    )

    class Meta:
        unique_together = [("product", "ingredient")]
        ordering = ["product", "ingredient"]

    def __str__(self):
        return f"{self.product.name}: {self.quantity}{self.ingredient.unit} {self.ingredient.name}"


class StockMovement(models.Model):
    """Immutable ledger of every stock change for ingredients and products."""

    class Kind(models.TextChoices):
        PURCHASE = "purchase", "Purchase / restock"
        SALE = "sale", "Sale (order)"
        WASTE = "waste", "Waste / spoilage"
        ADJUSTMENT = "adjustment", "Manual adjustment"
        RETURN = "return", "Return / cancellation"

    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name="movements", null=True, blank=True
    )
    product = models.ForeignKey(
        "store.Product", on_delete=models.CASCADE, related_name="stock_movements", null=True, blank=True
    )
    kind = models.CharField(max_length=12, choices=Kind.choices)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=3, help_text="Signed: positive = in, negative = out."
    )
    unit = models.CharField(max_length=4, blank=True)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=4, default=0)
    reason = models.CharField(max_length=255, blank=True)
    order = models.ForeignKey(
        "orders.Order", on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        target = self.ingredient.name if self.ingredient else (self.product.name if self.product else "—")
        return f"{self.kind} {self.quantity} × {target}"
