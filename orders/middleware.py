"""Middleware that snapshots session carts for abandoned-cart recovery."""

import logging

from .recovery import TRACKED_PATH_PREFIX, track_cart

logger = logging.getLogger(__name__)


class CartRecoveryMiddleware:
    """Record the cart after checkout-related requests so it can be recovered."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.path.startswith(TRACKED_PATH_PREFIX):
            try:
                track_cart(request)
            except Exception:  # pragma: no cover - never break a response
                logger.exception("Cart recovery tracking failed")
        return response
