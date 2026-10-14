from decimal import Decimal

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from accounts.models import User, Address
from orders.models import Order, OrderItem, Reservation, Subscription, Table
from store.models import (
    BlogPost,
    Category,
    Coupon,
    Product,
    ProductImage,
    Review,
    StoreLocation,
    SubscriptionPlan,
)


class CategorySerializer(serializers.ModelSerializer):
    product_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Category
        fields = ("id", "name", "slug", "description", "icon", "product_count")


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ("id", "image", "alt_text", "sort_order")


class ReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Review
        fields = ("id", "user", "rating", "title", "body", "is_verified_purchase", "created_at")
        read_only_fields = ("is_verified_purchase",)


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(), source="category", write_only=True
    )
    gallery = ProductImageSerializer(many=True, read_only=True)
    rating = serializers.FloatField(read_only=True)
    review_count = serializers.IntegerField(read_only=True)
    discount_percent = serializers.IntegerField(read_only=True)
    in_stock = serializers.BooleanField(read_only=True)

    class Meta:
        model = Product
        fields = (
            "id",
            "name",
            "slug",
            "category",
            "category_id",
            "kind",
            "roast",
            "short_description",
            "description",
            "origin",
            "price",
            "compare_at_price",
            "calories",
            "caffeine_mg",
            "image",
            "gallery",
            "rating",
            "review_count",
            "discount_percent",
            "is_featured",
            "is_new",
            "in_stock",
        )


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = (
            "id",
            "label",
            "recipient",
            "phone",
            "line1",
            "line2",
            "city",
            "state",
            "postal_code",
            "country",
            "is_default",
        )


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ("id", "email", "first_name", "last_name", "phone", "role", "loyalty_points")
        read_only_fields = ("role", "loyalty_points")


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = ("email", "first_name", "last_name", "phone", "password")

    def create(self, validated_data):
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.role = User.Role.CUSTOMER
        user.loyalty_points = 100
        user.save()
        return user


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = ("id", "product", "name", "unit_price", "quantity", "options", "line_total")
        read_only_fields = ("name", "unit_price")

    @extend_schema_field(serializers.DecimalField(max_digits=10, decimal_places=2))
    def get_line_total(self, obj):
        return obj.line_total


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    status_color = serializers.CharField(read_only=True)

    class Meta:
        model = Order
        fields = (
            "id",
            "number",
            "status",
            "status_color",
            "payment_status",
            "fulfillment",
            "customer_name",
            "customer_phone",
            "delivery_address",
            "subtotal",
            "discount",
            "delivery_fee",
            "tax",
            "loyalty_discount",
            "points_used",
            "points_earned",
            "total",
            "item_count",
            "items",
            "placed_at",
        )
        read_only_fields = ("number", "subtotal", "discount", "tax", "total", "points_earned")


class ReservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Reservation
        fields = (
            "id",
            "name",
            "email",
            "phone",
            "location",
            "table",
            "party_size",
            "date",
            "time",
            "status",
            "note",
            "created_at",
        )
        read_only_fields = ("status", "created_at")


class SubscriptionPlanSerializer(serializers.ModelSerializer):
    perk_list = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = SubscriptionPlan
        fields = (
            "id",
            "name",
            "slug",
            "tagline",
            "description",
            "price",
            "interval",
            "bags_per_delivery",
            "perk_list",
            "is_popular",
        )


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = SubscriptionPlanSerializer(read_only=True)

    class Meta:
        model = Subscription
        fields = ("id", "plan", "status", "grind", "next_delivery", "started_at")


class BlogPostSerializer(serializers.ModelSerializer):
    class Meta:
        model = BlogPost
        fields = ("id", "title", "slug", "excerpt", "cover_image", "published_at", "read_minutes")


class StoreLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreLocation
        fields = ("id", "name", "address", "city", "phone", "latitude", "longitude", "opening_hours")


class CouponSerializer(serializers.ModelSerializer):
    class Meta:
        model = Coupon
        fields = (
            "code",
            "description",
            "discount_type",
            "value",
            "minimum_spend",
            "valid_until",
        )
