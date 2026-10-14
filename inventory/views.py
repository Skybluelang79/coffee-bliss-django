from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.db.models import F, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from store.models import Product

from .forms import AdjustForm, IngredientForm, RecipeItemForm, RestockForm, WasteForm
from .models import Ingredient, RecipeItem, StockMovement
from .services import adjust_ingredient, restock


def staff_required(view):
    return user_passes_test(
        lambda u: u.is_authenticated and u.is_staff_member, login_url="accounts:login"
    )(view)


@staff_required
def inventory_home(request):
    query = request.GET.get("q", "")
    ingredients = Ingredient.objects.select_related("supplier")
    if query:
        ingredients = ingredients.filter(Q(name__icontains=query) | Q(sku__icontains=query))

    low = Ingredient.objects.filter(is_active=True, stock__lte=F("reorder_level"))
    out = Ingredient.objects.filter(is_active=True, stock__lte=0)
    total_value = Ingredient.objects.aggregate(
        v=Sum(F("stock") * F("cost_per_unit"))
    )["v"] or 0

    context = {
        "ingredients": ingredients,
        "query": query,
        "low_count": low.count(),
        "out_count": out.count(),
        "total_value": total_value,
        "low_stock": low.select_related("supplier")[:10],
        "recent_movements": StockMovement.objects.select_related(
            "ingredient", "product", "created_by"
        )[:15],
        "form": IngredientForm(),
    }
    return render(request, "dashboard/inventory.html", context)


@staff_required
def ingredient_detail(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    movements = ingredient.movements.select_related("created_by", "order")[:50]
    return render(
        request,
        "dashboard/ingredient_detail.html",
        {
            "ingredient": ingredient,
            "movements": movements,
            "restock_form": RestockForm(),
            "adjust_form": AdjustForm(initial={"new_stock": ingredient.stock}),
            "waste_form": WasteForm(),
        },
    )


@staff_required
def ingredient_create(request):
    if request.method == "POST":
        form = IngredientForm(request.POST)
        if form.is_valid():
            ingredient = form.save()
            messages.success(request, f"Added ingredient {ingredient.name}.")
            return redirect("inventory:detail", pk=ingredient.pk)
    else:
        form = IngredientForm()
    return render(request, "dashboard/ingredient_form.html", {"form": form, "title": "Add ingredient"})


@staff_required
def ingredient_edit(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    if request.method == "POST":
        form = IngredientForm(request.POST, instance=ingredient)
        if form.is_valid():
            form.save()
            messages.success(request, "Ingredient updated.")
            return redirect("inventory:detail", pk=ingredient.pk)
    else:
        form = IngredientForm(instance=ingredient)
    return render(request, "dashboard/ingredient_form.html", {"form": form, "title": "Edit ingredient"})


@staff_required
@require_POST
def ingredient_restock(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    form = RestockForm(request.POST)
    if form.is_valid():
        restock(
            ingredient,
            form.cleaned_data["quantity"],
            reason=form.cleaned_data.get("reason", ""),
            user=request.user,
        )
        messages.success(request, f"Restocked {form.cleaned_data['quantity']} {ingredient.unit}.")
    else:
        messages.error(request, "Invalid restock quantity.")
    return redirect("inventory:detail", pk=pk)


@staff_required
@require_POST
def ingredient_adjust(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    form = AdjustForm(request.POST)
    if form.is_valid():
        adjust_ingredient(
            ingredient,
            form.cleaned_data["new_stock"],
            reason=form.cleaned_data.get("reason", ""),
            user=request.user,
        )
        messages.success(request, "Stock adjusted.")
    else:
        messages.error(request, "Invalid adjustment.")
    return redirect("inventory:detail", pk=pk)


@staff_required
@require_POST
def ingredient_waste(request, pk):
    ingredient = get_object_or_404(Ingredient, pk=pk)
    form = WasteForm(request.POST)
    if form.is_valid():
        qty = form.cleaned_data["quantity"]
        ingredient.stock = max(Decimal("0"), ingredient.stock - qty)
        ingredient.save(update_fields=["stock", "updated_at"])
        StockMovement.objects.create(
            ingredient=ingredient,
            kind=StockMovement.Kind.WASTE,
            quantity=-qty,
            unit=ingredient.unit,
            reason=form.cleaned_data.get("reason", "Waste"),
            created_by=request.user,
        )
        messages.info(request, f"Recorded {qty} {ingredient.unit} waste.")
    return redirect("inventory:detail", pk=pk)


@staff_required
def movements(request):
    qs = StockMovement.objects.select_related("ingredient", "product", "created_by", "order")
    kind = request.GET.get("kind")
    if kind:
        qs = qs.filter(kind=kind)
    return render(
        request,
        "dashboard/movements.html",
        {"movements": qs[:200], "kinds": StockMovement.Kind.choices, "selected": kind},
    )


@staff_required
def recipe_list(request):
    products = Product.objects.filter(is_active=True).prefetch_related("recipe_items__ingredient")
    return render(request, "dashboard/recipes.html", {"products": products})


@staff_required
def recipe_edit(request, slug):
    product = get_object_or_404(Product, slug=slug)
    if request.method == "POST":
        form = RecipeItemForm(request.POST)
        if form.is_valid():
            item, created = RecipeItem.objects.update_or_create(
                product=product,
                ingredient=form.cleaned_data["ingredient"],
                defaults={"quantity": form.cleaned_data["quantity"]},
            )
            messages.success(request, "Recipe updated.")
            return redirect("inventory:recipe_edit", slug=product.slug)
    else:
        form = RecipeItemForm()
    return render(
        request,
        "dashboard/recipe_edit.html",
        {"product": product, "form": form, "items": product.recipe_items.select_related("ingredient")},
    )


@staff_required
@require_POST
def recipe_delete(request, slug, pk):
    product = get_object_or_404(Product, slug=slug)
    RecipeItem.objects.filter(product=product, pk=pk).delete()
    messages.info(request, "Recipe line removed.")
    return redirect("inventory:recipe_edit", slug=product.slug)
