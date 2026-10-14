from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db.models import Avg, Count
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Category(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="categories/", blank=True, null=True)
    icon = models.CharField(
        max_length=40, blank=True, help_text="Emoji or icon key, e.g. ☕"
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:menu") + f"?category={self.slug}"

    @property
    def product_count(self):
        return self.products.filter(is_active=True).count()


class Tag(TimeStampedModel):
    name = models.CharField(max_length=60, unique=True)
    slug = models.SlugField(max_length=80, unique=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)


class Product(TimeStampedModel):
    class Roast(models.TextChoices):
        LIGHT = "light", "Light Roast"
        MEDIUM = "medium", "Medium Roast"
        DARK = "dark", "Dark Roast"
        ESPRESSO = "espresso", "Espresso"
        NA = "na", "N/A"

    class Kind(models.TextChoices):
        DRINK = "drink", "Drink"
        BEANS = "beans", "Coffee Beans"
        FOOD = "food", "Food"
        MERCH = "merch", "Merchandise"

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT, related_name="products"
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="products")
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.DRINK)
    roast = models.CharField(max_length=12, choices=Roast.choices, default=Roast.NA)
    short_description = models.CharField(max_length=220, blank=True)
    description = models.TextField(blank=True)
    ingredients = models.TextField(blank=True)
    origin = models.CharField(max_length=160, blank=True, help_text="e.g. Colombia, Huila")
    price = models.DecimalField(
        max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    compare_at_price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        blank=True,
        null=True,
        help_text="Original price for showing discounts.",
    )
    calories = models.PositiveIntegerField(blank=True, null=True)
    caffeine_mg = models.PositiveIntegerField(blank=True, null=True)
    image = models.ImageField(upload_to="products/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_featured = models.BooleanField(default=False)
    is_new = models.BooleanField(default=False)
    stock = models.PositiveIntegerField(default=999)
    track_stock = models.BooleanField(
        default=True, help_text="Deduct stock when this product is sold."
    )
    prep_time_minutes = models.PositiveIntegerField(default=5)

    class Meta:
        ordering = ["-is_featured", "name"]
        indexes = [models.Index(fields=["slug"]), models.Index(fields=["kind"])]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base = slugify(self.name)
            slug = base
            i = 1
            while Product.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                i += 1
                slug = f"{base}-{i}"
            self.slug = slug
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:product_detail", args=[self.slug])

    @property
    def discount_percent(self):
        if self.compare_at_price and self.compare_at_price > self.price:
            return round(
                (self.compare_at_price - self.price) / self.compare_at_price * 100
            )
        return 0

    @property
    def in_stock(self):
        return self.stock > 0 and self.is_active

    @property
    def rating(self):
        return self.reviews.filter(is_approved=True).aggregate(avg=Avg("rating"))[
            "avg"
        ]

    @property
    def rating_display(self):
        value = self.rating
        return round(value, 1) if value else None

    @property
    def review_count(self):
        return self.reviews.filter(is_approved=True).count()


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="gallery"
    )
    image = models.ImageField(upload_to="products/gallery/")
    alt_text = models.CharField(max_length=160, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.product.name} image {self.pk}"


class Review(TimeStampedModel):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="reviews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews"
    )
    order = models.ForeignKey(
        "orders.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviews",
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    title = models.CharField(max_length=140, blank=True)
    body = models.TextField()
    is_approved = models.BooleanField(default=True)
    is_verified_purchase = models.BooleanField(default=False)
    helpful_votes = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "user"], name="unique_review_per_user_product"
            )
        ]

    def __str__(self):
        return f"{self.product.name} — {self.rating}★ by {self.user}"


class Coupon(TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENT = "percent", "Percentage"
        FIXED = "fixed", "Fixed amount"

    code = models.CharField(max_length=40, unique=True)
    description = models.CharField(max_length=200, blank=True)
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    value = models.DecimalField(max_digits=8, decimal_places=2)
    minimum_spend = models.DecimalField(
        max_digits=8, decimal_places=2, default=0
    )
    max_uses = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    used_count = models.PositiveIntegerField(default=0)
    per_user_limit = models.PositiveIntegerField(default=1)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True

    def discount_for(self, subtotal):
        subtotal = Decimal(subtotal)
        if subtotal < self.minimum_spend:
            return Decimal("0.00")
        if self.discount_type == self.DiscountType.PERCENT:
            return (subtotal * self.value / Decimal("100")).quantize(Decimal("0.01"))
        return min(self.value, subtotal)


class SubscriptionPlan(TimeStampedModel):
    """Coffee subscription tiers (the 'Coffee Club')."""

    class Interval(models.TextChoices):
        WEEKLY = "weekly", "Weekly"
        BIWEEKLY = "biweekly", "Every 2 weeks"
        MONTHLY = "monthly", "Monthly"

    name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True, blank=True)
    tagline = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=8, decimal_places=2)
    interval = models.CharField(
        max_length=12, choices=Interval.choices, default=Interval.MONTHLY
    )
    bags_per_delivery = models.PositiveIntegerField(default=1)
    perks = models.TextField(
        blank=True, help_text="One perk per line, shown as a checklist."
    )
    is_popular = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def perk_list(self):
        return [p.strip() for p in self.perks.splitlines() if p.strip()]


class BlogPost(TimeStampedModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="posts",
    )
    excerpt = models.CharField(max_length=300, blank=True)
    cover_image = models.ImageField(upload_to="blog/", blank=True, null=True)
    body = models.TextField()
    is_published = models.BooleanField(default=True)
    published_at = models.DateTimeField(default=timezone.now)
    read_minutes = models.PositiveIntegerField(default=4)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.title)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("store:blog_detail", args=[self.slug])


class StoreLocation(TimeStampedModel):
    name = models.CharField(max_length=140)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=120)
    phone = models.CharField(max_length=40, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, blank=True, null=True)
    opening_hours = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["city", "name"]

    def __str__(self):
        return f"{self.name} ({self.city})"


class NewsletterSubscriber(TimeStampedModel):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    source = models.CharField(max_length=60, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class Favorite(TimeStampedModel):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="favorited_by"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "product"], name="unique_favorite_per_user_product"
            )
        ]

    def __str__(self):
        return f"{self.user} ♥ {self.product}"
