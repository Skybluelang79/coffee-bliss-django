# Coffee Bliss operations runbook

## Deploy

1. Merge to `main`; GitHub Actions runs lint, migration check and the test suite.
2. Render auto-deploys the `coffee-bliss` web service from `render.yaml`.
   To force a specific commit: `render deploys create <service-id> --commit <sha> --wait --confirm`.
3. `build.sh` installs dependencies, collects static files and migrates. Full
   demo data is never seeded automatically; set `SEED_DEMO_DATA=1` explicitly
   only for throwaway environments.
4. `BOOTSTRAP_DEMO_ACCOUNTS=1` creates or repairs the documented demo logins
   without adding catalogue/orders. Disable it outside demo deployments.
5. To bootstrap a real administrator, set `DJANGO_SUPERUSER_EMAIL` and
   `DJANGO_SUPERUSER_PASSWORD` in the service environment. `build.sh` creates
   the account if it does not exist; existing passwords are not overwritten.
6. Confirm `/healthz/` returns `{"status": "ok", "database": "ok"}`.

## Configuration

- Required: `SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, `SITE_URL`.
- Payments: `PAYSTACK_PUBLIC_KEY` / `PAYSTACK_SECRET_KEY` (preferred for NGN) or
  `STRIPE_SECRET_KEY` / `STRIPE_PUBLISHABLE_KEY` / `STRIPE_WEBHOOK_SECRET`.
- AI assistant: `AI_ENABLED`, `AI_API_KEY`, `AI_BASE_URL`, `AI_MODEL`. With no key,
  the assistant uses its offline responder.
- Monitoring: `SENTRY_DSN` (optional), `LOG_LEVEL` (default `INFO`).
- Scale (optional): `REDIS_URL` enables Redis cache, `CELERY_BROKER_URL` enables queued
  subscription/cart emails. Uncomment `django-redis`/`celery` in `requirements.txt`
  when using them. `TWO_FACTOR_ENABLED=true` enforces emailed codes for opted-in users.

## Scheduled jobs

Coffee Club renewals must run once a day (Render cron job or system cron):

```cron
0 6 * * * cd /app && python manage.py renew_subscriptions
```

`--dry-run` reports what would happen without charging or emailing customers.

## Backups

```powershell
python manage.py backup_db --output C:\backups\coffee-bliss.sqlite3
```

Postgres backups use `pg_dump` and must be installed on the host. Store backups
off-site and test restores regularly. For Postgres restore: `psql "$DATABASE_URL" < backup.dump`.

## Incidents

- Check `/healthz/` first, then `render logs --service <service-id>`.
- Sentry captures unhandled exceptions when `SENTRY_DSN` is configured.
- Failed subscription charges set status to `Payment issue`; customers can update
  payment details from their Coffee Club dashboard once the provider is reachable.
- Roll back by deploying the previous known-good commit; database migrations are
  additive and backward-compatible where possible.

## Email

Set a real SMTP backend in production. Subscription invoices, welcome messages
and delivery confirmations use `templates/emails/subscription_*.{txt,html}`.
