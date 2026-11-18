#!/usr/bin/env bash
# Render build step for Coffee Bliss.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Create or promote a real administrator when credentials are provided.
if [ -n "${DJANGO_SUPERUSER_EMAIL:-}" ] && [ -n "${DJANGO_SUPERUSER_PASSWORD:-}" ]; then
  python manage.py bootstrap_admin
fi

# Ensure the documented demo accounts exist without duplicating catalog/orders.
if [ "${BOOTSTRAP_DEMO_ACCOUNTS:-0}" = "1" ] || [ "${BOOTSTRAP_DEMO_ACCOUNTS:-}" = "true" ]; then
  python manage.py bootstrap_demo_accounts
fi

# Demo data is opt-in. Production deployments must provision real data or run
# the seed command themselves with SEED_DEMO_DATA=1 after reviewing credentials.
if [ "${SEED_DEMO_DATA:-0}" = "1" ] || [ "${SEED_DEMO_DATA:-}" = "true" ]; then
  python manage.py seed
fi
