from django import forms

from store.models import Coupon, StoreLocation

from .models import Order, Reservation


class CheckoutForm(forms.Form):
    fulfilment_choices = Order.Fulfillment.choices

    fulfillment = forms.ChoiceField(
        choices=Order.Fulfillment.choices,
        initial=Order.Fulfillment.PICKUP,
        widget=forms.HiddenInput(),
    )
    payment_method = forms.ChoiceField(
        choices=(("card", "Credit / debit card"), ("cash", "Cash / pay later")),
        initial="card",
        required=False,
        widget=forms.HiddenInput(),
    )
    customer_name = forms.CharField(
        max_length=160,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Full name"}),
    )
    customer_phone = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Phone number"}),
    )
    location = forms.ModelChoiceField(
        queryset=StoreLocation.objects.filter(is_active=True),
        required=False,
        empty_label="Select a pickup location",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    delivery_address = forms.CharField(
        max_length=300,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "Street address, city, ZIP"}
        ),
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={"class": "form-input", "rows": 2, "placeholder": "Notes (optional)"}
        ),
    )
    coupon_code = forms.CharField(
        max_length=40,
        required=False,
        widget=forms.TextInput(
            attrs={"class": "form-input", "placeholder": "Promo code"}
        ),
    )

    def clean_coupon_code(self):
        code = self.cleaned_data.get("coupon_code", "").strip()
        if not code:
            return ""
        coupon = Coupon.objects.filter(code__iexact=code).first()
        if not coupon or not coupon.is_valid:
            raise forms.ValidationError("This promo code is invalid or expired.")
        return coupon.code

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("fulfillment") == Order.Fulfillment.DELIVERY and not cleaned.get(
            "delivery_address"
        ):
            self.add_error("delivery_address", "A delivery address is required.")
        return cleaned


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ("name", "email", "phone", "location", "date", "time", "party_size", "note")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-input"}),
            "email": forms.EmailInput(attrs={"class": "form-input"}),
            "phone": forms.TextInput(attrs={"class": "form-input"}),
            "location": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"class": "form-input", "type": "date"}),
            "time": forms.TimeInput(attrs={"class": "form-input", "type": "time"}),
            "party_size": forms.NumberInput(attrs={"class": "form-input", "min": 1, "max": 20}),
            "note": forms.Textarea(attrs={"class": "form-input", "rows": 2}),
        }

    def clean_party_size(self):
        size = self.cleaned_data["party_size"]
        if size < 1:
            raise forms.ValidationError("Party size must be at least 1.")
        return size
