from django import forms

from .models import Review, NewsletterSubscriber


class ReviewForm(forms.ModelForm):
    rating = forms.ChoiceField(
        choices=[(i, f"{i} ★") for i in range(5, 0, -1)],
        widget=forms.RadioSelect(attrs={"class": "star-radio"}),
    )

    class Meta:
        model = Review
        fields = ("rating", "title", "body")
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "form-input", "placeholder": "Summarize your experience"}
            ),
            "body": forms.Textarea(
                attrs={
                    "class": "form-input",
                    "rows": 4,
                    "placeholder": "What did you love about it?",
                }
            ),
        }


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ("email",)
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": "form-input",
                    "placeholder": "you@example.com",
                    "autocomplete": "email",
                }
            )
        }


class ContactForm(forms.Form):
    name = forms.CharField(
        max_length=120,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Your name"}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(
            attrs={"class": "form-input", "placeholder": "you@example.com"}
        )
    )
    subject = forms.CharField(
        max_length=160,
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "Subject"}),
    )
    message = forms.CharField(
        widget=forms.Textarea(
            attrs={"class": "form-input", "rows": 5, "placeholder": "How can we help?"}
        )
    )
