from django import forms

from .models import Ingredient, RecipeItem, StockMovement, Supplier


class IngredientForm(forms.ModelForm):
    class Meta:
        model = Ingredient
        fields = (
            "name", "sku", "unit", "stock", "reorder_level",
            "par_level", "cost_per_unit", "supplier", "is_active",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "sku": forms.TextInput(attrs={"class": "form-input"}),
            "unit": forms.Select(attrs={"class": "form-select"}),
            "stock": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "reorder_level": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "par_level": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
            "cost_per_unit": forms.NumberInput(attrs={"class": "form-input", "step": "0.0001"}),
            "supplier": forms.Select(attrs={"class": "form-select"}),
        }


class RestockForm(forms.Form):
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=3, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
    )
    reason = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. Weekly delivery"}),
    )


class AdjustForm(forms.Form):
    new_stock = forms.DecimalField(
        max_digits=12, decimal_places=3,
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
    )
    reason = forms.CharField(
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Reason for adjustment"}),
    )


class WasteForm(forms.Form):
    quantity = forms.DecimalField(
        max_digits=12, decimal_places=3, min_value=0,
        widget=forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
    )
    reason = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "e.g. spilled / expired"}),
    )


class RecipeItemForm(forms.ModelForm):
    class Meta:
        model = RecipeItem
        fields = ("ingredient", "quantity")
        widgets = {
            "ingredient": forms.Select(attrs={"class": "form-select"}),
            "quantity": forms.NumberInput(attrs={"class": "form-input", "step": "0.001"}),
        }
