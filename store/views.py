from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .forms import ContactForm, NewsletterForm, ReviewForm
from .models import (
    BlogPost,
    Category,
    Favorite,
    NewsletterSubscriber,
    Product,
    Review,
    StoreLocation,
    SubscriptionPlan,
)


def home(request):
    featured = (
        Product.objects.filter(is_active=True, is_featured=True)
        .select_related("category")[:8]
    )
    if not featured:
        featured = Product.objects.filter(is_active=True).select_related("category")[:8]
    best_sellers = (
        Product.objects.filter(is_active=True)
        .annotate(sold=Count("order_items"))
        .order_by("-sold", "-is_featured", "name")[:8]
    )
    if not best_sellers:
        best_sellers = Product.objects.filter(is_active=True).select_related("category")[:8]
    context = {
        "featured_products": featured,
        "new_arrivals": Product.objects.filter(is_active=True, is_new=True)[:4],
        "best_sellers": best_sellers,
        "categories": Category.objects.filter(is_active=True)[:6],
        "plans": SubscriptionPlan.objects.filter(is_active=True)[:3],
        "posts": BlogPost.objects.filter(is_published=True)[:3],
        "testimonials": Review.objects.filter(is_approved=True, rating__gte=4)
        .select_related("user", "product")[:6],
        "stats": {
            "products": Product.objects.filter(is_active=True).count(),
            "reviews": Review.objects.filter(is_approved=True).count(),
            "avg_rating": round(
                Review.objects.filter(is_approved=True).aggregate(a=Avg("rating"))["a"]
                or 4.9,
                1,
            ),
            "locations": StoreLocation.objects.filter(is_active=True).count(),
        },
    }
    return render(request, "store/home.html", context)


def menu(request):
    products = Product.objects.filter(is_active=True).select_related("category")
    category_slug = request.GET.get("category")
    kind = request.GET.get("kind")
    roast = request.GET.get("roast")
    query = request.GET.get("q")
    sort = request.GET.get("sort", "featured")

    if category_slug:
        products = products.filter(category__slug=category_slug)
    if kind:
        products = products.filter(kind=kind)
    if roast:
        products = products.filter(roast=roast)
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
        )

    sort_map = {
        "price_asc": "price",
        "price_desc": "-price",
        "newest": "-created_at",
        "rating": "-created_at",
        "name": "name",
        "featured": "-is_featured",
    }
    products = products.order_by(sort_map.get(sort, "-is_featured"))

    paginator = Paginator(products, 9)
    page = paginator.get_page(request.GET.get("page"))

    context = {
        "page_obj": page,
        "products": page.object_list,
        "categories": Category.objects.filter(is_active=True),
        "selected_category": category_slug,
        "selected_kind": kind,
        "selected_roast": roast,
        "query": query or "",
        "sort": sort,
        "kinds": Product.Kind.choices,
        "roasts": Product.Roast.choices,
        "total": paginator.count,
    }
    return render(request, "store/menu.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.select_related("category").prefetch_related(
            "gallery", "tags", "reviews__user"
        ),
        slug=slug,
        is_active=True,
    )
    related = (
        Product.objects.filter(category=product.category, is_active=True)
        .exclude(pk=product.pk)[:4]
    )
    reviews = product.reviews.filter(is_approved=True).select_related("user")
    can_review = (
        request.user.is_authenticated
        and not reviews.filter(user=request.user).exists()
    )
    is_favorite = (
        request.user.is_authenticated
        and Favorite.objects.filter(user=request.user, product=product).exists()
    )
    brew_guides = product.brew_guides.filter(is_published=True).prefetch_related(
        "steps"
    )
    barista_notes = product.barista_notes.filter(is_published=True)
    context = {
        "product": product,
        "related": related,
        "reviews": reviews,
        "review_form": ReviewForm(),
        "can_review": can_review,
        "is_favorite": is_favorite,
        "rating_breakdown": _rating_breakdown(product),
        "brew_guides": brew_guides,
        "barista_notes": barista_notes,
    }
    return render(request, "store/product_detail.html", context)


def _rating_breakdown(product):
    total = product.review_count or 1
    breakdown = []
    for score in range(5, 0, -1):
        count = product.reviews.filter(is_approved=True, rating=score).count()
        breakdown.append(
            {"stars": score, "count": count, "percent": round(count / total * 100)}
        )
    return breakdown


@require_POST
def add_review(request, slug):
    product = get_object_or_404(Product, slug=slug, is_active=True)
    if not request.user.is_authenticated:
        messages.info(request, "Please sign in to leave a review.")
        return redirect("accounts:login")
    form = ReviewForm(request.POST)
    if form.is_valid():
        review = form.save(commit=False)
        review.product = product
        review.user = request.user
        review.is_verified_purchase = product.order_items.filter(
            order__user=request.user, order__status="completed"
        ).exists()
        review.save()
        request.user.add_loyalty_points(25, "review")
        messages.success(request, "Thanks for your review! +25 beans earned.")
    else:
        messages.error(request, "Please correct the review form.")
    return redirect(product.get_absolute_url())


@require_POST
def toggle_favorite(request, slug):
    product = get_object_or_404(Product, slug=slug)
    if not request.user.is_authenticated:
        messages.info(request, "Sign in to save favorites.")
        return redirect("accounts:login")
    favorite, created = Favorite.objects.get_or_create(
        user=request.user, product=product
    )
    if not created:
        favorite.delete()
        messages.info(request, f"Removed {product.name} from favorites.")
    else:
        messages.success(request, f"Saved {product.name} to favorites.")
    return redirect(product.get_absolute_url())


def categories(request):
    return render(
        request,
        "store/categories.html",
        {"categories": Category.objects.filter(is_active=True)},
    )


def locations(request):
    return render(
        request,
        "store/locations.html",
        {"locations": StoreLocation.objects.filter(is_active=True)},
    )


def subscriptions(request):
    return render(
        request,
        "store/subscriptions.html",
        {"plans": SubscriptionPlan.objects.filter(is_active=True)},
    )


def blog(request):
    posts = BlogPost.objects.filter(is_published=True)
    paginator = Paginator(posts, 6)
    page = paginator.get_page(request.GET.get("page"))
    return render(request, "store/blog.html", {"page_obj": page, "posts": page.object_list})


def blog_detail(request, slug):
    post = get_object_or_404(BlogPost, slug=slug, is_published=True)
    return render(
        request,
        "store/blog_detail.html",
        {
            "post": post,
            "related": BlogPost.objects.filter(is_published=True)
            .exclude(pk=post.pk)[:3],
        },
    )


def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            send_mail(
                subject=f"[{settings.SITE_NAME}] {form.cleaned_data['subject']}",
                message=f"From: {form.cleaned_data['name']} <{form.cleaned_data['email']}>\n\n"
                f"{form.cleaned_data['message']}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[settings.DEFAULT_FROM_EMAIL],
                fail_silently=True,
            )
            messages.success(request, "Message sent! We'll brew up a reply shortly.")
            return redirect("store:contact")
    else:
        form = ContactForm()
    return render(request, "store/contact.html", {"form": form})


@require_POST
def subscribe(request):
    form = NewsletterForm(request.POST)
    if form.is_valid():
        email = form.cleaned_data["email"]
        obj, created = NewsletterSubscriber.objects.get_or_create(email=email)
        if created:
            if request.user.is_authenticated:
                request.user.newsletter_opt_in = True
                request.user.save(update_fields=["newsletter_opt_in"])
            messages.success(request, "You're on the list! Welcome to the club. ☕")
        else:
            messages.info(request, "You're already subscribed.")
    else:
        messages.error(request, "Please enter a valid email address.")
    return redirect(request.META.get("HTTP_REFERER", reverse("store:home")))


def about(request):
    return render(
        request,
        "store/about.html",
        {"locations": StoreLocation.objects.filter(is_active=True)},
    )
