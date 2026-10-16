from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    UserCreationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
)
from django.utils.translation import gettext_lazy as _

from .models import User, Address


class StyledFormMixin:
    """Applies consistent CSS classes to all widgets."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            widget = field.widget
            existing = widget.attrs.get("class", "")
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = f"form-check {existing}".strip()
            elif isinstance(widget, (forms.Select,)):
                widget.attrs["class"] = f"form-select {existing}".strip()
            elif isinstance(widget, forms.Textarea):
                widget.attrs.setdefault("rows", 3)
                widget.attrs["class"] = f"form-input {existing}".strip()
            else:
                widget.attrs["class"] = f"form-input {existing}".strip()
            widget.attrs.setdefault("placeholder", field.label or name.title())


class LoginForm(StyledFormMixin, AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )
    password = forms.CharField(
        label=_("Password"),
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "data-caps-hint": "caps-hint-login",
            }
        ),
    )
    remember_me = forms.BooleanField(
        required=False, label=_("Remember me"), initial=True
    )


class SignUpForm(StyledFormMixin, UserCreationForm):
    first_name = forms.CharField(max_length=60, label=_("First name"))
    last_name = forms.CharField(max_length=60, label=_("Last name"))
    email = forms.EmailField(label=_("Email"))
    phone = forms.CharField(max_length=32, required=False, label=_("Phone"))
    newsletter_opt_in = forms.BooleanField(
        required=False, initial=True, label=_("Email me brew news & offers")
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        autocomplete = {
            "first_name": "given-name",
            "last_name": "family-name",
            "email": "email",
            "phone": "tel",
            "password1": "new-password",
            "password2": "new-password",
        }
        for name, value in autocomplete.items():
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("autocomplete", value)
        # Live inline validation hooks (progressive enhancement, static/js/main.js).
        self.fields["email"].widget.attrs["data-live-validate"] = "email"
        self.fields["password2"].widget.attrs.update(
            {"data-live-validate": "match", "data-match-with": "id_password1"}
        )

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("An account with this email already exists."))
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = user.email.lower()
        user.role = User.Role.CUSTOMER
        user.newsletter_opt_in = self.cleaned_data.get("newsletter_opt_in", False)
        # Welcome bonus points.
        from django.conf import settings

        user.loyalty_points = 100
        if commit:
            user.save()
        return user


class ProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "first_name",
            "last_name",
            "phone",
            "avatar",
            "newsletter_opt_in",
            "marketing_opt_in",
        )
        widgets = {"avatar": forms.ClearableFileInput(attrs={"accept": "image/*"})}


class AddressForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Address
        fields = (
            "label",
            "recipient",
            "phone",
            "line1",
            "line2",
            "city",
            "state",
            "postal_code",
            "country",
            "is_default",
        )


class CoffeePasswordChangeForm(StyledFormMixin, PasswordChangeForm):
    pass


class CoffeePasswordResetForm(StyledFormMixin, PasswordResetForm):
    email = forms.EmailField(
        label=_("Email"),
        widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
    )


class CoffeeSetPasswordForm(StyledFormMixin, SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "new_password2" in self.fields:
            self.fields["new_password2"].widget.attrs.update(
                {"data-live-validate": "match", "data-match-with": "id_new_password1"}
            )
