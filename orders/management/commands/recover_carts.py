"""Send recovery emails to customers who left items in their cart.

Usage:
    python manage.py recover_carts
    python manage.py recover_carts --hours 12 --max-reminders 3
    python manage.py recover_carts --dry-run
"""

from django.conf import settings
from django.core.management.base import BaseCommand

from orders.recovery import run_recovery


class Command(BaseCommand):
    help = "Email customers who abandoned their cart before checking out."

    def add_arguments(self, parser):
        parser.add_argument(
            "--hours",
            type=int,
            default=settings.CART_RECOVERY_HOURS,
            help="Only remind carts idle for at least this many hours.",
        )
        parser.add_argument(
            "--max-reminders",
            type=int,
            default=settings.CART_RECOVERY_MAX_REMINDERS,
            help="Skip carts that have already received this many reminders.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Send at most this many emails this run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would be sent without sending anything.",
        )

    def handle(self, *args, **options):
        sent, considered = run_recovery(
            hours=options["hours"],
            max_reminders=options["max_reminders"],
            dry_run=options["dry_run"],
            limit=options["limit"],
        )
        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] {considered} cart(s) eligible for a reminder."
                )
            )
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Sent {sent} recovery email(s) out of {considered} eligible cart(s)."
            )
        )
