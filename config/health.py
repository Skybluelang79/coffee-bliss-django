from django.db import connection
from django.http import JsonResponse


def healthz(request):
    """Lightweight liveness/readiness probe for uptime monitors."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        database = "ok"
    except Exception:
        database = "error"
    healthy = database == "ok"
    return JsonResponse(
        {"status": "ok" if healthy else "error", "database": database},
        status=200 if healthy else 503,
    )
