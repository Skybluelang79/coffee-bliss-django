from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import (
    LoginView,
    PasswordChangeView,
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from orders.models import Order
from store.models import Review

from .forms import (
    LoginForm,
    SignUpForm,
    ProfileForm,
    AddressForm,
    CoffeePasswordChangeForm,
    CoffeePasswordResetForm,
    CoffeeSetPasswordForm,
)
from .models import Address, LoyaltyTransaction


class CoffeeLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(0)
        messages.success(self.request, f"Welcome back, {self.request.user.get_short_name()}!")
        return response


def signup_view(request):
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    LoyaltyTransaction.objects.create(
                        user=user,
                        points=user.loyalty_points,
                        reason=LoyaltyTransaction.Reason.SIGNUP,
                        note="Welcome bonus",
                    )
            except IntegrityError:
                # Duplicate email (e.g. a concurrent submit that raced past validation).
                form.add_error("email", "An account with this email already exists.")
            else:
                login(request, user)
                messages.success(
                    request,
                    f"Welcome to Coffee Bliss! You've earned {user.loyalty_points} loyalty beans.",
                )
                return redirect("accounts:dashboard")
        messages.error(request, "Please fix the errors below.")
    else:
        form = SignUpForm()
    return render(request, "accounts/signup.html", {"form": form})


@require_POST
def logout_view(request):
    logout(request)
    messages.info(request, "You have been signed out. See you soon!")
    return redirect("store:home")


@login_required
def dashboard(request):
    """Customer account overview."""
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items")
        .order_by("-created_at")
    )
    loyalty = request.user.loyalty_transactions.all()[:10]
    reviews = Review.objects.filter(user=request.user).select_related("product")
    context = {
        "orders": orders,
        "recent_orders": orders[:5],
        "loyalty": loyalty,
        "reviews": reviews,
        "addresses": request.user.addresses.all(),
        "stats": {
            "total_orders": orders.count(),
            "points": request.user.loyalty_points,
            "reward_value": request.user.redeem_value(),
            "reviews": reviews.count(),
        },
    }
    return render(request, "accounts/dashboard.html", context)


@login_required
def profile_view(request):
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Profile updated.")
            return redirect("accounts:profile")
    else:
        form = ProfileForm(instance=request.user)
    return render(request, "accounts/profile.html", {"form": form})


@login_required
def address_list(request):
    addresses = request.user.addresses.all()
    if request.method == "POST":
        form = AddressForm(request.POST)
        if form.is_valid():
            address = form.save(commit=False)
            address.user = request.user
            address.save()
            messages.success(request, "Address saved.")
            return redirect("accounts:addresses")
    else:
        form = AddressForm(initial={"recipient": request.user.get_full_name()})
    return render(
        request,
        "accounts/addresses.html",
        {"addresses": addresses, "form": form},
    )


@login_required
@require_POST
def address_delete(request, pk):
    address = get_object_or_404(Address, pk=pk, user=request.user)
    address.delete()
    messages.info(request, "Address removed.")
    return redirect("accounts:addresses")


@login_required
def order_detail(request, number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__product"),
        number=number,
        user=request.user,
    )
    return render(request, "accounts/order_detail.html", {"order": order})


class CoffeePasswordChangeView(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = CoffeePasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def form_valid(self, form):
        response = super().form_valid(form)
        update_session_auth_hash(self.request, form.user)
        messages.success(self.request, "Password changed successfully.")
        return response


class CoffeePasswordResetView(PasswordResetView):
    template_name = "accounts/password_reset.html"
    form_class = CoffeePasswordResetForm
    email_template_name = "emails/password_reset.txt"
    html_email_template_name = "emails/password_reset.html"
    subject_template_name = "emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")
    extra_email_context = {"site_name": settings.SITE_NAME}

    def form_valid(self, form):
        messages.info(
            self.request,
            "If an account matches that email, a reset link is on its way.",
        )
        return super().form_valid(form)


class CoffeePasswordResetDoneView(PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class CoffeePasswordResetConfirmView(PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = CoffeeSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class CoffeePasswordResetCompleteView(PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
