from django.conf import settings

try:
    from celery import shared_task
except ImportError:
    shared_task = None


def task(name):
    """Register with Celery when configured, otherwise run synchronously."""

    if shared_task is not None and getattr(settings, "CELERY_BROKER_URL", ""):
        return shared_task(name=name)

    def decorator(function):
        function.task_name = name
        return function

    return decorator


def delay(function, *args, **kwargs):
    """Queue a task when Celery is available, otherwise call it directly."""

    runner = getattr(function, "delay", None)
    if runner is not None and getattr(settings, "CELERY_BROKER_URL", ""):
        return runner(*args, **kwargs)
    return function(*args, **kwargs)
