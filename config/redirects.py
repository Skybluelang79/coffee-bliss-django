"""Redirect helpers that only allow same-site destinations."""

from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def safe_redirect(request, fallback, target=None):
    """Redirect to a validated same-site URL, otherwise to ``fallback``."""
    url = target or request.POST.get("next") or request.META.get("HTTP_REFERER")
    if url and url_has_allowed_host_and_scheme(
        url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return redirect(url)
    return redirect(fallback)
