from decimal import Decimal

from django.db import migrations

NAIRA_MULTIPLIER = Decimal("1000")
MAX_USD_PRICE = Decimal("100")
MAX_USD_COST = Decimal("10")


def convert_prices(apps, schema_editor):
    Product = apps.get_model("store", "Product")
    for product in Product.objects.all():
        fields = []
        if product.price is not None and product.price < MAX_USD_PRICE:
            product.price = product.price * NAIRA_MULTIPLIER
            fields.append("price")
        if (
            product.compare_at_price is not None
            and product.compare_at_price < MAX_USD_PRICE
        ):
            product.compare_at_price = product.compare_at_price * NAIRA_MULTIPLIER
            fields.append("compare_at_price")
        if fields:
            product.save(update_fields=fields)

    SubscriptionPlan = apps.get_model("store", "SubscriptionPlan")
    for plan in SubscriptionPlan.objects.all():
        if plan.price < MAX_USD_PRICE:
            plan.price = plan.price * NAIRA_MULTIPLIER
            plan.save(update_fields=["price"])

    Coupon = apps.get_model("store", "Coupon")
    for coupon in Coupon.objects.all():
        fields = []
        if coupon.discount_type == "fixed" and coupon.value < MAX_USD_PRICE:
            coupon.value = coupon.value * NAIRA_MULTIPLIER
            fields.append("value")
        if coupon.minimum_spend < MAX_USD_PRICE:
            coupon.minimum_spend = coupon.minimum_spend * NAIRA_MULTIPLIER
            fields.append("minimum_spend")
        if fields:
            coupon.save(update_fields=fields)

    Ingredient = apps.get_model("inventory", "Ingredient")
    for ingredient in Ingredient.objects.all():
        if ingredient.cost_per_unit < MAX_USD_COST:
            ingredient.cost_per_unit = ingredient.cost_per_unit * NAIRA_MULTIPLIER
            ingredient.save(update_fields=["cost_per_unit"])


class Migration(migrations.Migration):
    dependencies = [
        ("store", "0003_baristanote_brewguide_brewstep_and_more"),
        ("inventory", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(convert_prices, migrations.RunPython.noop),
    ]
