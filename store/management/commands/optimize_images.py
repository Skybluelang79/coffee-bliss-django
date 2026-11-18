from django.conf import settings
from django.core.management.base import BaseCommand

from accounts.models import User
from store.images import optimize_image
from store.models import BlogPost, Category, Product, ProductImage


class Command(BaseCommand):
    help = "Resize and recompress uploaded product, blog and avatar images."

    def handle(self, *args, **options):
        fields = []
        fields += [(item, "image") for item in Product.objects.exclude(image="")]
        fields += [(item, "image") for item in ProductImage.objects.exclude(image="")]
        fields += [(item, "image") for item in Category.objects.exclude(image="")]
        fields += [
            (item, "cover_image")
            for item in BlogPost.objects.exclude(cover_image="")
        ]
        if "accounts" in settings.INSTALLED_APPS:
            fields += [(item, "avatar") for item in User.objects.exclude(avatar="")]

        changed = sum(optimize_image(getattr(item, field)) for item, field in fields)
        self.stdout.write(
            self.style.SUCCESS(f"Optimized {changed} of {len(fields)} images.")
        )
