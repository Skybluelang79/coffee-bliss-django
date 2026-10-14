"""Inventory business logic: consuming, restoring and restocking.

These helpers are called from order lifecycle code and from the dashboards.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models import F

from .models import Ingredient, StockMovement


def _record(**kwargs):
    return StockMovement.objects.create(**kwargs)


@transaction.atomic
def consume_for_order(order, user=None):
    """Deduct ingredient + product stock for a confirmed order.

    Idempotent: guarded by order.stock_consumed.
    Returns a dict summary of ingredient shortfalls (for low-stock warnings).
    """
    if order.stock_consumed:
        return {}

    shortfalls = {}
    for item in order.items.select_related("product"):
        product = item.product
        if product is None:
            continue
        qty = Decimal(item.quantity)

        # Product-level stock (cups, retail bags, merch).
        if product.track_stock:
            product.stock = max(0, product.stock - int(qty))
            product.save(update_fields=["stock"])
            _record(
                product=product,
                kind=StockMovement.Kind.SALE,
                quantity=-qty,
                unit="ea",
                reason=f"Order {order.number}",
                order=order,
                created_by=user,
            )

        # Ingredient consumption via recipe.
        for line in product.recipe_items.select_related("ingredient"):
            ingredient = line.ingredient
            used = line.quantity * qty
            ingredient.stock = max(Decimal("0"), ingredient.stock - used)
            ingredient.save(update_fields=["stock", "updated_at"])
            _record(
                ingredient=ingredient,
                kind=StockMovement.Kind.SALE,
                quantity=-used,
                unit=ingredient.unit,
                unit_cost=ingredient.cost_per_unit,
                reason=f"Order {order.number} · {product.name}",
                order=order,
                created_by=user,
            )
            if ingredient.is_low:
                shortfalls[ingredient.name] = ingredient.stock

    order.stock_consumed = True
    order.save(update_fields=["stock_consumed"])
    return shortfalls


@transaction.atomic
def restore_for_order(order, user=None):
    """Put stock back when an order is cancelled/refunded after consumption."""
    if not order.stock_consumed:
        return
    for item in order.items.select_related("product"):
        product = item.product
        if product is None:
            continue
        qty = Decimal(item.quantity)
        if product.track_stock:
            product.stock = product.stock + int(qty)
            product.save(update_fields=["stock"])
            _record(
                product=product,
                kind=StockMovement.Kind.RETURN,
                quantity=qty,
                unit="ea",
                reason=f"Order {order.number} cancelled",
                order=order,
                created_by=user,
            )
        for line in product.recipe_items.select_related("ingredient"):
            ingredient = line.ingredient
            back = line.quantity * qty
            ingredient.stock = ingredient.stock + back
            ingredient.save(update_fields=["stock", "updated_at"])
            _record(
                ingredient=ingredient,
                kind=StockMovement.Kind.RETURN,
                quantity=back,
                unit=ingredient.unit,
                reason=f"Order {order.number} cancelled",
                order=order,
                created_by=user,
            )
    order.stock_consumed = False
    order.save(update_fields=["stock_consumed"])


@transaction.atomic
def restock(ingredient, quantity, *, kind=StockMovement.Kind.PURCHASE, reason="", user=None, unit_cost=None):
    quantity = Decimal(quantity)
    ingredient.stock = ingredient.stock + quantity
    ingredient.save(update_fields=["stock", "updated_at"])
    return _record(
        ingredient=ingredient,
        kind=kind,
        quantity=quantity,
        unit=ingredient.unit,
        unit_cost=unit_cost if unit_cost is not None else ingredient.cost_per_unit,
        reason=reason or "Restock",
        created_by=user,
    )


@transaction.atomic
def adjust_ingredient(ingredient, new_stock, *, reason="", user=None):
    new_stock = Decimal(new_stock)
    delta = new_stock - ingredient.stock
    ingredient.stock = new_stock
    ingredient.save(update_fields=["stock", "updated_at"])
    return _record(
        ingredient=ingredient,
        kind=StockMovement.Kind.ADJUSTMENT,
        quantity=delta,
        unit=ingredient.unit,
        reason=reason or "Manual adjustment",
        created_by=user,
    )


def low_stock_ingredients():
    return Ingredient.objects.filter(is_active=True, stock__lte=F("reorder_level"))
