#!/usr/bin/env bash
# Render build step for Coffee Bliss.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Seed demo data only when the database is empty. The seed command is
# idempotent for the catalog but adds fresh orders on each run, so we guard it.
python manage.py shell -c "from store.models import Product; raise SystemExit(0 if Product.objects.exists() else 1)" || python manage.py seed
