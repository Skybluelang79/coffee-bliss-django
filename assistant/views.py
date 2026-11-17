import json
import time

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .services import MAX_MESSAGE_CHARS, ask_assistant, is_configured

HISTORY_KEYS = {
    "customer": "assistant_customer_history",
    "staff": "assistant_staff_history",
}
RATE_KEYS = {
    "customer": "assistant_customer_rate",
    "staff": "assistant_staff_rate",
}


def _payload(request):
    try:
        data = json.loads(request.body or "{}")
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _rate_limited(request, surface):
    limit = max(1, int(getattr(settings, "AI_RATE_LIMIT", 20)))
    window = max(1, int(getattr(settings, "AI_RATE_WINDOW_MINUTES", 10))) * 60
    now = time.time()
    key = RATE_KEYS[surface]
    hits = [stamp for stamp in request.session.get(key, []) if now - stamp < window]
    if len(hits) >= limit:
        request.session[key] = hits
        return True
    hits.append(now)
    request.session[key] = hits
    return False


def _history(request, surface):
    history = request.session.get(HISTORY_KEYS[surface], [])
    return history if isinstance(history, list) else []


def _chat(request, surface):
    if surface == "staff" and not getattr(request.user, "is_staff_member", False):
        return JsonResponse(
            {"detail": "Staff access is required for this assistant."}, status=403
        )

    if _rate_limited(request, surface):
        return JsonResponse(
            {"detail": "You are sending messages too quickly. Please wait a moment."},
            status=429,
        )

    data = _payload(request)
    if data is None:
        return JsonResponse({"detail": "Invalid JSON body."}, status=400)

    message = str(data.get("message") or "").strip()
    if not message:
        return JsonResponse({"detail": "Please enter a message."}, status=400)
    if len(message) > MAX_MESSAGE_CHARS:
        return JsonResponse(
            {"detail": f"Please keep messages under {MAX_MESSAGE_CHARS} characters."},
            status=400,
        )

    history = _history(request, surface)
    result = ask_assistant(surface, message, history, request.user)

    history = history + [
        {"role": "user", "content": message},
        {"role": "assistant", "content": result["reply"]},
    ]
    max_messages = max(2, int(getattr(settings, "AI_MAX_HISTORY", 12)))
    request.session[HISTORY_KEYS[surface]] = history[-max_messages:]

    return JsonResponse(
        {
            "reply": result["reply"],
            "source": result["source"],
            "configured": is_configured(),
        }
    )


@require_POST
def customer_chat(request):
    return _chat(request, "customer")


@require_POST
def staff_chat(request):
    return _chat(request, "staff")


@require_POST
def customer_reset(request):
    request.session.pop(HISTORY_KEYS["customer"], None)
    return JsonResponse({"detail": "Conversation cleared."})


@require_POST
def staff_reset(request):
    if not getattr(request.user, "is_staff_member", False):
        return JsonResponse(
            {"detail": "Staff access is required for this assistant."}, status=403
        )
    request.session.pop(HISTORY_KEYS["staff"], None)
    return JsonResponse({"detail": "Conversation cleared."})
