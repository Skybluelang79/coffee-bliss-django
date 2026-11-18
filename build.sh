#!/usr/bin/env bash
# Render build step for Coffee Bliss.
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input

# Demo data is opt-in. Production deployments must provision real data or run
# the seed command themselves with SEED_DEMO_DATA=1 after reviewing credentials.
if [ "${SEED_DEMO_DATA:-0}" = "1" ] || [ "${SEED_DEMO_DATA:-}" = "true" ]; then
  python manage.py seed
fi
