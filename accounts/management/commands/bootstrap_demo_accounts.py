from django.core.management.base import BaseCommand, CommandError

from accounts.demo import DEMO_LOGINS, demo_accounts_enabled, ensure_demo_accounts


class Command(BaseCommand):
    help = "Create or repair the documented demo user and admin accounts."

    def handle(self, *args, **options):
        if not demo_accounts_enabled():
            raise CommandError(
                "Refusing to create demo accounts while DEBUG=False. Set "
                "BOOTSTRAP_DEMO_ACCOUNTS=1 in a throwaway environment only."
            )

        ensure_demo_accounts()
        self.stdout.write(
            self.style.SUCCESS("Demo accounts are ready. Sign-in credentials:")
        )
        for account in DEMO_LOGINS:
            self.stdout.write(
                f"  {account['label']}: {account['email']} / {account['password']}"
            )
