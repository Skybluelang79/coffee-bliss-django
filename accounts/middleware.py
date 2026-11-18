from urllib.parse import quote

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse


class TwoFactorMiddleware:
    """Require an emailed code for opted-in accounts when the feature is on."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            settings.TWO_FACTOR_ENABLED
            and user is not None
            and user.is_authenticated
            and getattr(user, "two_factor_enabled", False)
            and not request.session.get("2fa_verified")
        ):
            verify_url = reverse("accounts:two_factor_verify")
            path = request.path
            exempt = (
                path == verify_url
                or path == reverse("accounts:logout")
                or path == "/healthz/"
                or path.startswith(("/static/", "/media/", "/assistant/"))
            )
            if not exempt:
                from .twofactor import send_code

                if not request.session.get("2fa_code"):
                    send_code(request, user, next_url=request.get_full_path())
                return redirect(f"{verify_url}?next={quote(path)}")
        return self.get_response(request)
