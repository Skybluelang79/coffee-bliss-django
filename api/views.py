from django.contrib.auth import authenticate, login, logout
from django.db.models import Q
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import status, viewsets, permissions, serializers as drf_serializers
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response

from orders.cart import Cart
from orders.models import Order, Reservation, Subscription
from store.models import Category, Product, Review, StoreLocation, SubscriptionPlan

from .serializers import (
    CategorySerializer,
    OrderSerializer,
    ProductSerializer,
    RegisterSerializer,
    ReservationSerializer,
    ReviewSerializer,
    StoreLocationSerializer,
    SubscriptionPlanSerializer,
    UserSerializer,
)


class IsStaffOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return request.user.is_authenticated and request.user.is_staff_member


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsStaffOrReadOnly]
    lookup_field = "slug"
    filterset_fields = ["category__slug", "kind", "roast", "is_featured"]

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related("category").prefetch_related("gallery")
        search = self.request.query_params.get("search")
        if search:
            qs = qs.filter(Q(name__icontains=search) | Q(description__icontains=search))
        return qs

    @action(detail=True, methods=["get", "post"], permission_classes=[permissions.IsAuthenticatedOrReadOnly])
    def reviews(self, request, slug=None):
        product = self.get_object()
        if request.method == "POST":
            serializer = ReviewSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            Review.objects.update_or_create(
                product=product,
                user=request.user,
                defaults=serializer.validated_data,
            )
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        serializer = ReviewSerializer(product.reviews.filter(is_approved=True), many=True)
        return Response(serializer.data)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    lookup_field = "slug"


class SubscriptionPlanViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = SubscriptionPlan.objects.filter(is_active=True)
    serializer_class = SubscriptionPlanSerializer
    lookup_field = "slug"


class StoreLocationViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StoreLocation.objects.filter(is_active=True)
    serializer_class = StoreLocationSerializer


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    lookup_field = "number"

    def get_queryset(self):
        user = self.request.user
        if not user.is_authenticated:
            return Order.objects.none()
        if user.is_staff_member:
            return Order.objects.all().prefetch_related("items")
        return Order.objects.filter(user=user).prefetch_related("items")

    @action(detail=True, methods=["post"], permission_classes=[permissions.IsAdminUser])
    def set_status(self, request, number=None):
        order = self.get_object()
        new_status = request.data.get("status")
        valid = {c[0] for c in Order.Status.choices}
        if new_status not in valid:
            return Response({"detail": "Invalid status."}, status=400)
        order.status = new_status
        order.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(order).data)


class ReservationViewSet(viewsets.ModelViewSet):
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and user.is_staff_member:
            return Reservation.objects.all()
        if user.is_authenticated:
            return Reservation.objects.filter(user=user)
        return Reservation.objects.none()

    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(user=user)


# ---- auth endpoints -----------------------------------------------------
@extend_schema(request=RegisterSerializer, responses=UserSerializer)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def api_register(request):
    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    login(request, user)
    return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(
    request={"application/json": {"type": "object", "properties": {"email": {"type": "string"}, "password": {"type": "string"}}}},
    responses=UserSerializer,
)
@api_view(["POST"])
@permission_classes([permissions.AllowAny])
def api_login(request):
    user = authenticate(
        request,
        username=request.data.get("email"),
        password=request.data.get("password"),
    )
    if not user:
        return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
    login(request, user)
    return Response(UserSerializer(user).data)


@extend_schema(request=None, responses={200: {"type": "object", "properties": {"detail": {"type": "string"}}}})
@api_view(["POST"])
def api_logout(request):
    logout(request)
    return Response({"detail": "Logged out."})


@extend_schema(request=UserSerializer, responses=UserSerializer)
@api_view(["GET", "PATCH"])
def api_me(request):
    if not request.user.is_authenticated:
        return Response({"detail": "Authentication required."}, status=401)
    if request.method == "PATCH":
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
    return Response(UserSerializer(request.user).data)


# ---- cart endpoints -----------------------------------------------------
@extend_schema(
    request=inline_serializer(
        name="CartRequest",
        fields={
            "product_id": drf_serializers.IntegerField(),
            "quantity": drf_serializers.IntegerField(required=False, default=1),
            "remove": drf_serializers.BooleanField(required=False, default=False),
        },
    ),
    responses={200: {"type": "object", "additionalProperties": True}},
)
@api_view(["GET", "POST", "DELETE"])
@permission_classes([permissions.AllowAny])
def api_cart(request):
    cart = Cart(request)
    if request.method == "POST":
        product = Product.objects.filter(pk=request.data.get("product_id"), is_active=True).first()
        if not product:
            return Response({"detail": "Product not found."}, status=404)
        if request.data.get("remove"):
            cart.remove(product.pk)
        else:
            cart.add(product, quantity=int(request.data.get("quantity", 1)))
    if request.method == "DELETE":
        cart.clear()
    data = [
        {
            "product_id": line["product"].pk,
            "name": line["product"].name,
            "quantity": line["quantity"],
            "unit_price": str(line["unit_price"]),
            "line_total": str(line["line_total"]),
        }
        for line in cart
    ]
    return Response(
        {
            "items": data,
            "subtotal": str(cart.subtotal),
            "discount": str(cart.discount),
            "delivery_fee": str(cart.delivery_fee),
            "tax": str(cart.tax),
            "total": str(cart.grand_total),
        }
    )
