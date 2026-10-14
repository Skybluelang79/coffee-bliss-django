from django.contrib import admin
from django.utils.html import format_html

from .models import Ingredient, RecipeItem, StockMovement, Supplier


class RecipeItemInline(admin.TabularInline):
    model = RecipeItem
    extra = 1
    autocomplete_fields = ("ingredient",)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("name", "contact_name", "email", "phone", "lead_time_days", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_name", "email")


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ("name", "sku", "unit", "stock", "reorder_level", "par_level", "supplier", "stock_status")
    list_filter = ("unit", "supplier", "is_active")
    search_fields = ("name", "sku")
    list_editable = ("stock", "reorder_level", "par_level")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basics", {"fields": ("name", "sku", "unit", "supplier", "is_active")}),
        ("Stock", {"fields": ("stock", "reorder_level", "par_level", "cost_per_unit")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="Status")
    def stock_status(self, obj):
        if obj.stock <= 0:
            return format_html('<span style="color:#e05c5c;font-weight:700;">Out of stock</span>')
        if obj.is_low:
            return format_html('<span style="color:#e0a83e;font-weight:700;">Low</span>')
        return format_html('<span style="color:#4caf7d;font-weight:700;">OK</span>')


@admin.register(RecipeItem)
class RecipeItemAdmin(admin.ModelAdmin):
    list_display = ("product", "ingredient", "quantity")
    list_filter = ("product", "ingredient")
    autocomplete_fields = ("product", "ingredient")


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "kind", "ingredient", "product", "quantity", "unit", "reason", "order")
    list_filter = ("kind", "created_at")
    search_fields = ("reason", "ingredient__name", "product__name", "order__number")
    date_hierarchy = "created_at"
    readonly_fields = ("created_at",)

    def has_add_permission(self, request):
        # Movements are created through services, not manually.
        return False
