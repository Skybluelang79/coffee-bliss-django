from datetime import datetime
from pathlib import Path
import os
import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a consistent database backup (SQLite or Postgres)."

    def add_arguments(self, parser):
        parser.add_argument("--output", help="Destination file path.")

    def handle(self, *args, **options):
        config = settings.DATABASES["default"]
        engine = config["ENGINE"]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        default_name = f"coffee-bliss-{stamp}.{'dump' if 'postgres' in engine else 'sqlite3'}"
        destination = Path(options["output"] or default_name).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        if "postgres" in engine:
            url = os.environ.get("DATABASE_URL") or config["NAME"]
            try:
                subprocess.run(
                    ["pg_dump", str(url), "-f", str(destination)], check=True
                )
            except (OSError, subprocess.CalledProcessError) as exc:
                raise CommandError(f"pg_dump failed: {exc}") from exc
        elif "sqlite" in engine:
            import sqlite3

            source = str(config["NAME"])
            if not Path(source).exists():
                raise CommandError(f"SQLite database not found: {source}")
            with sqlite3.connect(source) as origin:
                with sqlite3.connect(str(destination)) as target:
                    origin.backup(target)
        else:
            raise CommandError(f"Unsupported database engine: {engine}")

        self.stdout.write(self.style.SUCCESS(f"Backup written to {destination}"))
