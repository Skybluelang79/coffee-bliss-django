from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    Order,
    OrderItem,
    OrderStatusHistory,
    Payment,
    Reservation,
    Subscription,
    Table,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "name", "unit_price", "quantity", "options")


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("status", "note", "changed_by", "created_at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        "number",
        "customer_name",
        "status",
        "fulfillment",
        "payment_status",
        "total",
        "placed_at",
    )
    list_filter = ("status", "fulfillment", "payment_status", "placed_at")
    search_fields = ("number", "customer_name", "user__email", "guest_email")
    date_hierarchy = "placed_at"
    readonly_fields = ("number", "created_at", "updated_at", "placed_at", "completed_at")
    inlines = [OrderItemInline, PaymentInline, StatusHistoryInline]
    actions = ["mark_confirmed", "mark_preparing", "mark_completed", "mark_cancelled"]

    def _transition(self, request, queryset, status):
        for order in queryset:
            order.status = status
            order.save(update_fields=["status", "updated_at"])
            OrderStatusHistory.objects.create(
                order=order, status=status, changed_by=request.user, note="Bulk action"
            )
        self.message_user(request, f"{queryset.count()} order(s) set to {status}.")

    @admin.action(description="Mark as confirmed")
    def mark_confirmed(self, request, queryset):
        self._transition(request, queryset, Order.Status.CONFIRMED)

    @admin.action(description="Mark as preparing")
    def mark_preparing(self, request, queryset):
        self._transition(request, queryset, Order.Status.PREPARING)

    @admin.action(description="Mark as completed")
    def mark_completed(self, request, queryset):
        self._transition(request, queryset, Order.Status.COMPLETED)

    @admin.action(description="Cancel orders")
    def mark_cancelled(self, request, queryset):
        self._transition(request, queryset, Order.Status.CANCELLED)


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ("name", "date", "time", "party_size", "location", "status")
    list_filter = ("status", "date", "location")
    search_fields = ("name", "email", "phone")
    date_hierarchy = "date"
    list_editable = ("status",)


@admin.register(Table)
class TableAdmin(admin.ModelAdmin):
    list_display = ("name", "seats", "is_active")
    list_editable = ("seats", "is_active")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "plan", "status", "grind", "next_delivery", "started_at")
    list_filter = ("status", "plan")
    search_fields = ("user__email", "plan__name")


admin.site.register(Payment)
admin.site.register(OrderStatusHistory)
