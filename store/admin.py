from django.contrib import admin
from django.utils.html import format_html

from .models import (
    BlogPost,
    Category,
    Coupon,
    Favorite,
    NewsletterSubscriber,
    Product,
    ProductImage,
    Review,
    StoreLocation,
    SubscriptionPlan,
    Tag,
)


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 1


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "icon", "sort_order", "product_count", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "thumb",
        "name",
        "category",
        "kind",
        "roast",
        "price",
        "stock",
        "is_featured",
        "is_active",
    )
    list_editable = ("price", "stock", "is_featured", "is_active")
    list_filter = ("kind", "roast", "category", "is_featured", "is_active")
    search_fields = ("name", "description", "origin")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [ProductImageInline]
    filter_horizontal = ("tags",)
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Basics", {"fields": ("name", "slug", "category", "tags", "kind", "roast")}),
        ("Copy", {"fields": ("short_description", "description", "ingredients", "origin")}),
        ("Pricing & inventory", {"fields": ("price", "compare_at_price", "stock")}),
        ("Details", {"fields": ("calories", "caffeine_mg", "prep_time_minutes")}),
        ("Media", {"fields": ("image",)}),
        ("Visibility", {"fields": ("is_active", "is_featured", "is_new")}),
        ("Timestamps", {"fields": ("created_at", "updated_at")}),
    )

    @admin.display(description="")
    def thumb(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width:44px;height:44px;border-radius:8px;object-fit:cover;" />',
                obj.image.url,
            )
        return "☕"


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("product", "user", "rating", "is_approved", "is_verified_purchase", "created_at")
    list_filter = ("rating", "is_approved", "is_verified_purchase")
    search_fields = ("product__name", "user__email", "body")
    actions = ["approve_reviews", "reject_reviews"]

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        updated = queryset.update(is_approved=True)
        self.message_user(request, f"{updated} review(s) approved.")

    @admin.action(description="Hide selected reviews")
    def reject_reviews(self, request, queryset):
        updated = queryset.update(is_approved=False)
        self.message_user(request, f"{updated} review(s) hidden.")


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ("code", "discount_type", "value", "minimum_spend", "used_count", "is_valid", "is_active")
    list_filter = ("discount_type", "is_active")
    search_fields = ("code",)
    readonly_fields = ("used_count",)

    @admin.display(boolean=True, description="Currently valid")
    def is_valid(self, obj):
        return obj.is_valid


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    list_display = ("name", "price", "interval", "bags_per_delivery", "is_popular", "is_active")
    list_editable = ("price", "is_popular", "is_active")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "author", "is_published", "published_at", "read_minutes")
    list_filter = ("is_published", "published_at")
    search_fields = ("title", "body")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(StoreLocation)
class StoreLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "phone", "opening_hours", "is_active")
    list_editable = ("is_active",)
    search_fields = ("name", "city", "address")


@admin.register(NewsletterSubscriber)
class NewsletterSubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "source", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("email",)


admin.site.register(Favorite)
admin.site.site_header = "Coffee Bliss Administration"
admin.site.site_title = "Coffee Bliss"
admin.site.index_title = "Back office"
