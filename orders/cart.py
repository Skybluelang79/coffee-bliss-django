"""Session-backed shopping cart."""

from decimal import Decimal

from django.conf import settings

from store.models import Product


CART_SESSION_KEY = "coffee_cart"
COUPON_SESSION_KEY = "coffee_coupon"
POINTS_SESSION_KEY = "coffee_points"


class Cart:
    """A simple session-persisted cart that stores product ids and quantities."""

    def __init__(self, request):
        self.session = request.session
        self.cart = self.session.setdefault(CART_SESSION_KEY, {})

    def _key(self, product):
        return str(product.pk if hasattr(product, "pk") else product)

    def add(self, product, quantity=1, options=None, override=False):
        key = self._key(product)
        entry = self.cart.get(key, {"quantity": 0, "options": options or {}})
        if override:
            entry["quantity"] = quantity
        else:
            entry["quantity"] += quantity
        if options is not None:
            entry["options"] = options
        entry["quantity"] = min(entry["quantity"], 50)
        self.cart[key] = entry
        self.save()

    def update(self, product_id, quantity):
        key = str(product_id)
        if key in self.cart:
            if quantity > 0:
                self.cart[key]["quantity"] = min(int(quantity), 50)
            else:
                self.remove(product_id)
            self.save()

    def remove(self, product_id):
        key = str(product_id)
        if key in self.cart:
            del self.cart[key]
            self.save()

    def clear(self):
        self.session[CART_SESSION_KEY] = {}
        self.session.pop(COUPON_SESSION_KEY, None)
        self.session.pop(POINTS_SESSION_KEY, None)
        self.cart = self.session[CART_SESSION_KEY]
        self.save()

    def save(self):
        self.session.modified = True

    def __len__(self):
        return sum(item["quantity"] for item in self.cart.values())

    def __iter__(self):
        product_ids = self.cart.keys()
        products = Product.objects.filter(pk__in=product_ids).select_related("category")
        product_map = {str(p.pk): p for p in products}
        for key, item in self.cart.items():
            product = product_map.get(key)
            if not product:
                continue
            unit_price = product.price
            yield {
                "product": product,
                "quantity": item["quantity"],
                "options": item.get("options", {}),
                "unit_price": unit_price,
                "line_total": unit_price * item["quantity"],
            }

    @property
    def subtotal(self):
        return sum((line["line_total"] for line in self), Decimal("0.00"))

    @property
    def delivery_fee(self):
        if not len(self):
            return Decimal("0.00")
        if self.subtotal >= Decimal(str(settings.FREE_DELIVERY_THRESHOLD)):
            return Decimal("0.00")
        return Decimal(str(settings.DELIVERY_FEE))

    @property
    def tax(self):
        return (self.subtotal * Decimal(str(settings.TAX_RATE))).quantize(
            Decimal("0.01")
        )

    @property
    def total(self):
        return self.subtotal + self.delivery_fee + self.tax

    # ---- coupon helpers -------------------------------------------------
    def set_coupon(self, coupon):
        from store.models import Coupon

        if coupon is None:
            self.session.pop(COUPON_SESSION_KEY, None)
        else:
            self.session[COUPON_SESSION_KEY] = coupon.code if hasattr(coupon, "code") else coupon
        self.save()

    def get_coupon(self):
        from store.models import Coupon

        code = self.session.get(COUPON_SESSION_KEY)
        if not code:
            return None
        return Coupon.objects.filter(code__iexact=code).first()

    @property
    def discount(self):
        coupon = self.get_coupon()
        if coupon and coupon.is_valid:
            return coupon.discount_for(self.subtotal)
        return Decimal("0.00")

    # ---- loyalty helpers ------------------------------------------------
    def set_points(self, points):
        self.session[POINTS_SESSION_KEY] = int(points)
        self.save()

    @property
    def points_used(self):
        return int(self.session.get(POINTS_SESSION_KEY, 0))

    @property
    def loyalty_discount(self):
        return (Decimal(self.points_used) * Decimal(str(settings.LOYALTY_POINT_VALUE))).quantize(
            Decimal("0.01")
        )

    @property
    def grand_total(self):
        value = self.subtotal - self.discount + self.delivery_fee + self.tax - self.loyalty_discount
        return max(Decimal("0.00"), value.quantize(Decimal("0.01")))

    @property
    def to_free_delivery(self):
        remaining = Decimal(str(settings.FREE_DELIVERY_THRESHOLD)) - self.subtotal
        return max(Decimal("0.00"), remaining)
