"""
Django settings for Coffee Bliss.

A professional, full-stack coffee shop platform serving customers, staff
and administrators.
"""

from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, True),
    SECRET_KEY=(str, "django-insecure-coffee-bliss-change-me-in-production"),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1", "testserver"]),
    SITE_NAME=(str, "Coffee Bliss"),
)

# Load a local .env file if present.
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
SITE_NAME = env("SITE_NAME")

# Render injects these at runtime. Use them to trust the public host and to
# build absolute links (e.g. in recovery emails) without hard-coding a domain.
RENDER_EXTERNAL_HOSTNAME = env("RENDER_EXTERNAL_HOSTNAME", default="")
RENDER_EXTERNAL_URL = env("RENDER_EXTERNAL_URL", default="")
if RENDER_EXTERNAL_HOSTNAME and RENDER_EXTERNAL_HOSTNAME not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(RENDER_EXTERNAL_HOSTNAME)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third party
    "rest_framework",
    "drf_spectacular",
    "channels",
    # Local apps
    "accounts",
    "store",
    "orders",
    "inventory",
    "dashboard",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "orders.middleware.CartRecoveryMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "store.context_processors.site_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": env.db(
        "DATABASE_URL",
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:dashboard"
LOGOUT_REDIRECT_URL = "store:home"

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 12,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Coffee Bliss API",
    "DESCRIPTION": "REST API for the Coffee Bliss coffee platform.",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# Business rules (defaults tuned for the Nigerian market)
CURRENCY_SYMBOL = env("CURRENCY_SYMBOL", default="₦")
CURRENCY_CODE = env("CURRENCY_CODE", default="NGN")
TAX_RATE = env.float("TAX_RATE", default=0.075)
DELIVERY_FEE = env.float("DELIVERY_FEE", default=1500.00)
FREE_DELIVERY_THRESHOLD = env.float("FREE_DELIVERY_THRESHOLD", default=25000.00)
LOYALTY_POINTS_PER_DOLLAR = env.int("LOYALTY_POINTS_PER_DOLLAR", default=1)
LOYALTY_POINT_VALUE = env.float("LOYALTY_POINT_VALUE", default=0.05)

# Realtime (Django Channels). Uses an in-memory layer in development so it
# works with zero extra services. Point at Redis in production:
#   CHANNEL_LAYER_BACKEND=channels_redis.core.RedisChannelLayer
#   CHANNEL_LAYER_HOSTS=redis://127.0.0.1:6379/0
_channel_backend = env(
    "CHANNEL_LAYER_BACKEND", default="channels.layers.InMemoryChannelLayer"
)
if _channel_backend == "channels_redis.core.RedisChannelLayer":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": _channel_backend,
            "CONFIG": {"hosts": env.list("CHANNEL_LAYER_HOSTS", default=["redis://127.0.0.1:6379/0"])},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": _channel_backend}}

# Stripe payments. Leave the secret key blank to run in simulated mode.
STRIPE_PUBLISHABLE_KEY = env("STRIPE_PUBLISHABLE_KEY", default="")
STRIPE_SECRET_KEY = env("STRIPE_SECRET_KEY", default="")
STRIPE_WEBHOOK_SECRET = env("STRIPE_WEBHOOK_SECRET", default="")
STRIPE_CURRENCY = env("STRIPE_CURRENCY", default="ngn")

# Paystack payments (preferred for NGN card payments). Leave the secret key
# blank to disable Paystack.
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_CURRENCY = env("PAYSTACK_CURRENCY", default=CURRENCY_CODE)

# Kitchen display system
KDS_ENABLED = env.bool("KDS_ENABLED", default=True)

# Email (console backend for development)
EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="hello@coffeebliss.test")

# Order status notifications. Set SMS_BACKEND to "module.callable" to enable
# text messages (the callable receives ``phone`` and ``message``).
ORDER_NOTIFICATIONS_ENABLED = env.bool("ORDER_NOTIFICATIONS_ENABLED", default=True)
SMS_BACKEND = env("SMS_BACKEND", default="")

# Rough delivery buffer (minutes) added to the ETA for delivery orders.
DELIVERY_ETA_BUFFER = env.int("DELIVERY_ETA_BUFFER", default=15)

# Absolute base URL used when building links in outbound emails.
SITE_URL = env("SITE_URL", default=RENDER_EXTERNAL_URL or "http://127.0.0.1:8000")

# Origins allowed to send unsafe (POST) requests, e.g. the Render HTTPS URL.
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
if RENDER_EXTERNAL_URL and RENDER_EXTERNAL_URL not in CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS.append(RENDER_EXTERNAL_URL)

# Abandoned-cart recovery
CART_RECOVERY_HOURS = env.int("CART_RECOVERY_HOURS", default=6)
CART_RECOVERY_MAX_REMINDERS = env.int("CART_RECOVERY_MAX_REMINDERS", default=2)

MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
