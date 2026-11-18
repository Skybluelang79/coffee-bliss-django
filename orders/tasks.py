from config.tasks import task


@task("orders.send_subscription_email")
def send_subscription_email_task(template_prefix, subscription_id, extra=None):
    from . import subscription_billing
    from .models import Subscription

    subscription = Subscription.objects.get(pk=subscription_id)
    subscription_billing._send_subscription_email(
        template_prefix, subscription, **(extra or {})
    )


@task("orders.send_cart_recovery_email")
def send_recovery_email_task(abandoned_id, site_url=None):
    from . import recovery
    from .models import AbandonedCart

    abandoned = AbandonedCart.objects.get(pk=abandoned_id)
    recovery._send_recovery_email(abandoned, site_url=site_url)


@task("orders.renew_subscriptions")
def renew_subscriptions_task(dry_run=False):
    from django.core.management import call_command

    call_command("renew_subscriptions", dry_run=dry_run)
