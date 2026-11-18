from django.core.management.base import BaseCommand
from django.utils import timezone

from orders import payments, subscription_billing as billing
from orders.models import Subscription, SubscriptionDelivery


class Command(BaseCommand):
    help = "Create and settle due Coffee Club deliveries."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        today = timezone.now().date()
        due = Subscription.objects.filter(
            status=Subscription.Status.ACTIVE, next_delivery__lte=today
        ).select_related("user", "plan", "address")
        settled = skipped = invoiced = 0

        for subscription in due:
            delivery = billing.get_or_create_delivery(
                subscription, subscription.next_delivery or today
            )
            if delivery.status in {
                SubscriptionDelivery.Status.PAID,
                SubscriptionDelivery.Status.FULFILLED,
            }:
                continue

            if subscription.skip_next:
                if not dry_run:
                    delivery.status = SubscriptionDelivery.Status.SKIPPED
                    delivery.save(update_fields=["status"])
                    subscription.advance_delivery()
                skipped += 1
                continue

            if subscription.provider == Subscription.Provider.SIMULATED:
                if dry_run:
                    settled += 1
                    continue
                order = billing.create_delivery_order(subscription, delivery)
                payments.simulate_success(order, user=subscription.user)
                billing.settle_delivery(
                    delivery,
                    reference=order.payments.first().reference,
                    user=subscription.user,
                )
                billing.send_subscription_email("delivery", subscription, order=order)
                settled += 1
                continue

            if subscription.provider == Subscription.Provider.PAYSTACK:
                if dry_run:
                    invoiced += 1
                    continue
                order = billing.ensure_invoice_order(subscription, delivery)
                billing.send_subscription_email(
                    "invoice",
                    subscription,
                    invoice_url=billing.paystack_invoice_url(order),
                )
                invoiced += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Coffee Club: {settled} settled, {invoiced} invoiced, "
                f"{skipped} skipped (dry run: {dry_run})."
            )
        )
