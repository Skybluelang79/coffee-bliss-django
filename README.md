# ☕ Coffee Bliss

A professional, full-stack coffee shop platform built with **Django** — featuring an
immersive **3D landing page**, **real payments**, a live **kitchen display**, **inventory
management**, role-based dashboards for customers, staff and administrators, loyalty
rewards, subscriptions, reservations and a REST API.

> **Pure bliss, poured in 3D.** Small-batch roasts, handcrafted drinks, and a
> delightful ordering experience.

---

## ✨ Highlights

### Immersive customer experience
- **3D hero page** rendered with Three.js (rotating coffee cup, steam, floating beans, parallax).
- Animated product cards with 3D tilt, glassmorphism and reveal-on-scroll.
- Full **menu** with category / type / roast filters, search, sorting and pagination.
- Rich **product pages** — options (size, milk), nutrition, tasting notes, gallery, ratings.
- **Session-based cart**, promo codes, free-delivery progress bar.
- **Checkout** for pickup, delivery or dine-in with **Stripe card payments** (or cash).
- **Order tracking** with a live status timeline and email notifications.
- **Loyalty program** — earn beans on every order & review, redeem at checkout.
- **Table reservations**, **Coffee Club subscriptions**, **favourites**, **blog/journal**,
  **reviews**, **newsletter** and **contact**.

### Real-time kitchen display (KDS)
- Live order board over **WebSockets** (Django Channels) — columns for new, confirmed,
  preparing, ready and out-for-delivery orders.
- Colour-coded preparation timers, ticket notes and one-tap status advance.
- Updates stream instantly to every open display; auto-reconnects on drop.

### Inventory management
- Track raw ingredients (beans, milk, syrups, packaging) with units, reorder & par levels.
- **Recipes / bill-of-materials** link menu items to ingredients; stock is deducted
  automatically on every confirmed sale and returned on cancellation or refund.
- Stock ledger of purchases, sales, waste, adjustments and returns.
- Low-stock & out-of-stock alerts, restock, stock-count adjustments and waste logging.

### Staff operations
- Live operations board: new orders, orders in progress, today's bookings, low-stock alerts.
- Update order status (confirmed → preparing → ready → …) with email notifications.
- Issue **refunds** (via Stripe when configured) — inventory is automatically restored.
- Manage reservations (confirm, seat, cancel, no-show) and inventory.

### Administrator / manager
- Executive analytics dashboard with 30-day revenue chart, AOV, top sellers, customer growth.
- Customer management with lifetime value and order history.
- Period reports by category, status and fulfilment.
- Full **Django admin** back office for every model with inline editing, actions and image previews.

### Developer friendly
- **Django REST Framework** API with auto-generated **OpenAPI / Swagger** docs.
- **Django Channels** for WebSockets (in-memory layer in dev, Redis-ready for production).
- **Stripe** payments with a webhook endpoint and a simulated gateway fallback.
- Custom email-based user model, roles and permissions.
- Environment-driven settings, SQLite by default (Postgres-ready).
- WhiteNoise for static files, seed command for instant demo data, test suite included.

---

## 🚀 Quick start

```powershell
# 1. Create & activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate          # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
Copy-Item .env.example .env

# 4. Set up the database
python manage.py migrate
python manage.py seed          # loads demo products, orders, users, reviews…

# 5. Run it
python manage.py runserver
```

Open <http://127.0.0.1:8000/> 🎉

### Demo accounts

| Role          | Email                       | Password     |
|---------------|-----------------------------|--------------|
| Administrator | `admin@coffeebliss.test`    | `admin12345` |
| Staff         | `staff@coffeebliss.test`    | `staff12345` |
| Customer      | `customer1@example.com`     | `demo12345`  |

---

## 🖼️ Front-page hero

The hero is text-centred over the animated Three.js scene (rotating cup, steam,
floating beans). No product image is rendered in the hero itself.

---

## 🗺️ Key URLs

| URL | Description |
|-----|-------------|
| `/` | 3D landing page |
| `/menu/` | Full product catalogue with filters |
| `/subscriptions/` | Coffee Club plans |
| `/orders/cart/` | Shopping cart |
| `/orders/checkout/` | Checkout |
| `/orders/payment/<number>/` | Card payment (Stripe / simulated) |
| `/orders/reserve/` | Table reservation |
| `/dashboard/staff/` | Staff operations (staff only) |
| `/dashboard/staff/kds/` | Live kitchen display (staff only) |
| `/inventory/` | Inventory dashboard (staff only) |
| `/inventory/recipes/` | Recipe / bill-of-materials editor |
| `/dashboard/admin/` | Analytics (manager/admin only) |
| `/django-admin/` | Django admin back office |
| `/api/` | REST API root |
| `/api/docs/` | Swagger UI |
| `/api/schema/` | OpenAPI schema |
| `ws://…/ws/kitchen/` | Kitchen display WebSocket (staff only) |

---

## 🔌 API overview

| Endpoint | Methods | Notes |
|----------|---------|-------|
| `/api/products/` | GET, POST, PATCH, DELETE | Catalogue (staff can write) |
| `/api/products/{slug}/reviews/` | GET, POST | Read / submit reviews |
| `/api/categories/` | GET | Categories |
| `/api/plans/` | GET | Subscription plans |
| `/api/locations/` | GET | Stores |
| `/api/orders/` | GET, POST | Your orders (staff see all) |
| `/api/reservations/` | GET, POST | Table bookings |
| `/api/cart/` | GET, POST, DELETE | Session cart |
| `/api/auth/register/` `/login/` `/logout/` `/me/` | POST/GET/PATCH | Authentication |

Session authentication with CSRF is used by default — ideal for the same-origin
web app. Swap in token/JWT auth as needed.

---

## 🧱 Project structure

```
coffee-bliss/
├── config/          # project settings, urls, asgi (Channels) / wsgi
├── accounts/        # custom user, addresses, loyalty ledger
├── store/           # catalog, reviews, coupons, plans, blog, locations
├── orders/          # cart, orders, payments (Stripe), consumers, reservations
├── inventory/       # ingredients, suppliers, recipes, stock ledger
├── dashboard/       # staff + manager/admin dashboards, KDS
├── api/             # DRF serializers, viewsets, auth & cart endpoints
├── templates/       # all HTML templates
├── static/          # css, js (hero3d.js), images
└── manage.py
```

---

## ⚙️ Configuration

All settings are environment-driven (see `.env.example`). Key knobs:

- `DATABASE_URL` — SQLite by default, e.g. `postgres://user:pass@host:5432/db`
- `TAX_RATE`, `DELIVERY_FEE`, `FREE_DELIVERY_THRESHOLD`
- `LOYALTY_POINTS_PER_DOLLAR`, `LOYALTY_POINT_VALUE`
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_CURRENCY`
- `KDS_ENABLED`, `CHANNEL_LAYER_BACKEND`, `CHANNEL_LAYER_HOSTS`

### 💳 Payments

Leave `STRIPE_SECRET_KEY` blank to run a built-in **simulated gateway** (the whole
checkout flow works with no external account). To go live, set your Stripe keys and
point a webhook at `/orders/stripe/webhook/` for the events
`payment_intent.succeeded`, `payment_intent.payment_failed` and `charge.refunded`.

### 🖥️ Real-time (KDS)

In development the in-memory channel layer handles WebSockets on a single process.
For multiple workers, run Redis and set:

```dotenv
CHANNEL_LAYER_BACKEND=channels_redis.core.RedisChannelLayer
CHANNEL_LAYER_HOSTS=redis://127.0.0.1:6379/0
```

The app is served through Daphne/ASGI, so `python manage.py runserver` also serves
the `/ws/kitchen/` WebSocket.

---

## ✅ Tests

```powershell
python manage.py test
```

Covers storefront views, cart & checkout, coupon application, loyalty accrual,
account signup/login, role-based dashboard access, the API, inventory consumption &
restoration, simulated payments & refunds, and the kitchen WebSocket consumer.

---

## 📦 Production notes

- Set `DEBUG=False` and a strong `SECRET_KEY`.
- Point `DATABASE_URL` at Postgres (uncomment `psycopg` in `requirements.txt`).
- Run `python manage.py collectstatic` (WhiteNoise serves the files).
- Configure Stripe keys + webhook secret for real card payments.
- Use Redis for the channel layer when running multiple ASGI workers.
- HTTPS, HSTS and secure cookies are enabled automatically when `DEBUG=False`.
- Serve behind Daphne/gunicorn (ASGI) + a reverse proxy.

---

Brewed with ☕ and Django.
