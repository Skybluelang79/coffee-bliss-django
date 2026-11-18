import hmac
import logging
from secrets import randbelow
import time

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

CODE_TTL = 300


def generate_code():
    return f"{randbelow(1_000_000):06d}"


def send_code(request, user, next_url=""):
    code = generate_code()
    request.session["2fa_code"] = code
    request.session["2fa_expires"] = time.time() + CODE_TTL
    request.session["2fa_next"] = next_url
    request.session["2fa_verified"] = False
    if settings.DEBUG:
        logger.info("2FA code for %s: %s", user.email, code)
    send_mail(
        f"{settings.SITE_NAME} sign-in code",
        f"Your sign-in code is {code}. It expires in {CODE_TTL // 60} minutes.",
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=True,
    )
    return code


def verify_code(request, code):
    expected = request.session.get("2fa_code")
    expires = request.session.get("2fa_expires", 0)
    if not expected or time.time() > expires:
        return False
    if not hmac.compare_digest(str(expected), str(code or "").strip()):
        return False
    request.session.pop("2fa_code", None)
    request.session.pop("2fa_expires", None)
    return True
