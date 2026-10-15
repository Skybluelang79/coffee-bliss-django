from datetime import timedelta

from django.contrib import admin, messages
from django.shortcuts import redirect, render
from django.urls import path
from django.utils import timezone
from django.utils.html import format_html

from .forms import GiftCardGenerateForm
from .models import (
    AbandonedCart,
    GiftCard,
    GiftCardTransaction,
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


class GiftCardTransactionInline(admin.TabularInline):
    model = GiftCardTransaction
    extra = 0
    can_delete = False
    readonly_fields = ("kind", "amount", "balance_after", "order", "note", "created_at")


@admin.register(GiftCard)
class GiftCardAdmin(admin.ModelAdmin):
    list_display = (
        "code",
        "balance",
        "initial_balance",
        "state_label",
        "recipient_email",
        "purchaser",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "created_at")
    search_fields = ("code", "recipient_email", "recipient_name", "purchaser__email", "note")
    readonly_fields = ("code", "balance", "created_at", "updated_at")
    inlines = [GiftCardTransactionInline]
    actions = ["generate_cards", "disable_cards", "enable_cards"]
    fieldsets = (
        ("Card", {"fields": ("code", "initial_balance", "balance", "is_active", "expires_at")}),
        ("Recipient", {"fields": ("recipient_name", "recipient_email", "message")}),
        ("Internal", {"fields": ("purchaser", "note", "created_at", "updated_at")}),
    )

    def get_urls(self):
        custom = [
            path(
                "generate/",
                self.admin_site.admin_view(self.generate_view),
                name="orders_giftcard_generate",
            )
        ]
        return custom + super().get_urls()

    @admin.action(description="Generate gift cards…")
    def generate_cards(self, request, queryset):
        return redirect("admin:orders_giftcard_generate")

    def generate_view(self, request):
        if request.method == "POST":
            form = GiftCardGenerateForm(request.POST)
            if form.is_valid():
                created = self._create_cards(form.cleaned_data)
                self.message_user(request, f"Generated {created} gift card(s).")
                return redirect("admin:orders_giftcard_changelist")
        else:
            form = GiftCardGenerateForm()
        context = {
            **self.admin_site.each_context(request),
            "title": "Generate gift cards",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/orders/giftcard/generate.html", context)

    def _create_cards(self, data):
        expires_at = None
        if data.get("expires_in_days"):
            expires_at = timezone.now() + timedelta(days=data["expires_in_days"])
        email = data.get("recipient_email") or ""
        note = data.get("note", "")
        for _ in range(data["quantity"]):
            card = GiftCard.objects.create(
                initial_balance=data["amount"],
                balance=data["amount"],
                recipient_email=email,
                expires_at=expires_at,
                note=note,
            )
            GiftCardTransaction.objects.create(
                gift_card=card,
                kind=GiftCardTransaction.Kind.ISSUE,
                amount=data["amount"],
                balance_after=card.balance,
                note="Issued",
            )
        return data["quantity"]

    @admin.action(description="Disable selected gift cards")
    def disable_cards(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} gift card(s) disabled.")

    @admin.action(description="Enable selected gift cards")
    def enable_cards(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} gift card(s) enabled.")


@admin.register(GiftCardTransaction)
class GiftCardTransactionAdmin(admin.ModelAdmin):
    list_display = ("gift_card", "kind", "amount", "balance_after", "order", "created_at")
    list_filter = ("kind", "created_at")
    search_fields = ("gift_card__code", "order__number", "note")
    readonly_fields = ("gift_card", "order", "kind", "amount", "balance_after", "note", "created_at")


@admin.register(AbandonedCart)
class AbandonedCartAdmin(admin.ModelAdmin):
    list_display = (
        "recipient_email",
        "item_count",
        "subtotal",
        "status",
        "reminders_sent",
        "last_reminder_at",
        "updated_at",
    )
    list_filter = ("status", "reminders_sent", "updated_at")
    search_fields = ("email", "user__email", "session_key")
    readonly_fields = (
        "session_key",
        "user",
        "email",
        "items",
        "item_count",
        "subtotal",
        "status",
        "order",
        "reminders_sent",
        "last_reminder_at",
        "recovered_at",
        "created_at",
        "updated_at",
    )
    date_hierarchy = "updated_at"
    actions = ["send_reminder", "mark_recovered", "expire_carts"]

    @admin.action(description="Send recovery email now")
    def send_reminder(self, request, queryset):
        from .recovery import send_recovery_email

        sent = 0
        skipped = 0
        for cart in queryset:
            if cart.recipient_email and cart.status == AbandonedCart.Status.OPEN:
                if send_recovery_email(cart):
                    sent += 1
            else:
                skipped += 1
        self.message_user(request, f"Sent {sent} reminder(s); skipped {skipped}.")

    @admin.action(description="Mark as recovered")
    def mark_recovered(self, request, queryset):
        updated = queryset.update(
            status=AbandonedCart.Status.RECOVERED, recovered_at=timezone.now()
        )
        self.message_user(request, f"{updated} cart(s) marked as recovered.")

    @admin.action(description="Mark as expired")
    def expire_carts(self, request, queryset):
        updated = queryset.update(status=AbandonedCart.Status.EXPIRED)
        self.message_user(request, f"{updated} cart(s) expired.")


admin.site.register(Payment)
admin.site.register(OrderStatusHistory)
