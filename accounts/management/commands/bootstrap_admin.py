import os

from django.core.management.base import BaseCommand

from accounts.models import User


class Command(BaseCommand):
    help = "Create an administrator from DJANGO_SUPERUSER_EMAIL/PASSWORD."

    def handle(self, *args, **options):
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "").strip().lower()
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")
        if not email or not password:
            self.stdout.write("Skipping admin bootstrap; credentials are not set.")
            return

        user, created = User.objects.get_or_create(email=email)
        user.role = User.Role.ADMIN
        user.is_staff = True
        user.is_superuser = True
        if created:
            user.set_password(password)
        user.save()
        self.stdout.write(
            f"{'Created' if created else 'Ensured'} administrator {email}."
        )
