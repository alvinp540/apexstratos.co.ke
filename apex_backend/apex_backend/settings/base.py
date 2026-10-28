
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from dotenv import load_dotenv
from django.core.exceptions import ImproperlyConfigured


# --------------------------------------------------
# PROJECT PATHS AND ENVIRONMENT
# --------------------------------------------------

# base.py is inside apex_backend/settings/
# This resolves to the directory containing manage.py.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

load_dotenv(BASE_DIR / ".env")

IS_VERCEL = bool(os.environ.get("VERCEL"))


def env_bool(name, default=False):
    """Read a boolean environment variable."""
    value = os.environ.get(name)

    if value is None:
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    """Read a comma-separated environment variable."""
    value = os.environ.get(name, default)

    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


DEBUG = env_bool("DEBUG", default=not IS_VERCEL)
MAIN_CONTEST_TIME_LIMIT_ENABLED = env_bool(
    "MAIN_CONTEST_TIME_LIMIT_ENABLED",
    default=True,
)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "").strip()

if not SECRET_KEY:
    if IS_VERCEL or not DEBUG:
        raise ImproperlyConfigured(
            "Set DJANGO_SECRET_KEY in your environment."
        )

    # Local development only. Set a real key in your .env file.
    SECRET_KEY = "local-development-only-insecure-key-change-me"


# --------------------------------------------------
# HOSTS, CORS AND CSRF
# --------------------------------------------------

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    default=(
        "localhost,127.0.0.1,api.apexstratos.courses,"
        "apexstratos.courses,www.apexstratos.courses,"
        ".vercel.app"
    ),
)

FRONTEND_URL = os.environ.get(
    "FRONTEND_URL",
    "http://localhost:5173",
).rstrip("/")

CORS_ALLOWED_ORIGINS = env_list(
    "CORS_ALLOWED_ORIGINS",
    default=(
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://apexstratos.courses,"
        "https://www.apexstratos.courses,"
        "https://apexstratos.co.ke,"
        "https://www.apexstratos.co.ke"
    ),
)

CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    default=(
        "http://localhost:5173,"
        "http://127.0.0.1:5173,"
        "https://apexstratos.courses,"
        "https://www.apexstratos.courses,"
        "https://apexstratos.co.ke,"
        "https://www.apexstratos.co.ke"
    ),
)

CORS_ALLOW_CREDENTIALS = True


# --------------------------------------------------
# APPLICATIONS
# --------------------------------------------------

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
    "django_filters",
    "cloudinary",
    "cloudinary_storage",

    # Local applications
    "apps.accounts",
    "apps.profiles",
    "apps.trust_engine",
    "apps.cohorts",
    "apps.rankings",
    "apps.vendor",
    "apps.router",
    "apps.escrow",
    "apps.notifications",
    "apps.analytics",
    "apps.fraud",
    "apps.social",
]


# --------------------------------------------------
# MIDDLEWARE
# --------------------------------------------------

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


# --------------------------------------------------
# URLS, TEMPLATES AND SERVER INTERFACES
# --------------------------------------------------

ROOT_URLCONF = "apex_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "apex_backend.wsgi.application"
ASGI_APPLICATION = "apex_backend.asgi.application"

AUTH_USER_MODEL = "accounts.User"


# --------------------------------------------------
# POSTGRESQL DATABASE
# --------------------------------------------------

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if not DATABASE_URL:
    raise ImproperlyConfigured(
        "DATABASE_URL is required. Configure your local PostgreSQL "
        "connection in .env or your production database URL in Vercel."
    )

parsed_database_url = urlparse(DATABASE_URL)

if parsed_database_url.scheme not in {"postgres", "postgresql"}:
    raise ImproperlyConfigured(
        "DATABASE_URL must use the PostgreSQL scheme."
    )

if not parsed_database_url.hostname or not parsed_database_url.path.strip("/"):
    raise ImproperlyConfigured(
        "DATABASE_URL must include a database host and database name."
    )

DATABASES = {
    "default": dj_database_url.parse(
        DATABASE_URL,
        conn_max_age=0 if IS_VERCEL else 60,
        conn_health_checks=True,
        ssl_require=IS_VERCEL,
    )
}


# --------------------------------------------------
# PASSWORD VALIDATION
# --------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "UserAttributeSimilarityValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "MinimumLengthValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "CommonPasswordValidator"
        ),
    },
    {
        "NAME": (
            "django.contrib.auth.password_validation."
            "NumericPasswordValidator"
        ),
    },
]


# --------------------------------------------------
# DJANGO REST FRAMEWORK
# --------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": (
        "utils.pagination.StandardResultsPagination"
    ),
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "100/hour",
        "user": "1000/hour",
    },
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
}


# --------------------------------------------------
# JWT AUTHENTICATION
# --------------------------------------------------

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}


# --------------------------------------------------
# REDIS AND DJANGO CHANNELS
# --------------------------------------------------

REDIS_URL = os.environ.get("REDIS_URL", "").strip()

if REDIS_URL:
    parsed_redis_url = urlparse(REDIS_URL)

    if parsed_redis_url.scheme not in {"redis", "rediss"}:
        raise ImproperlyConfigured(
            "REDIS_URL must use redis:// or rediss://. "
            "An Upstash REST URL is not a Redis protocol URL."
        )

    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [REDIS_URL],
            },
        }
    }
else:
    # Suitable for local development and API-only use.
    # Not shared between separate server instances.
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }


# --------------------------------------------------
# STATIC FILES AND MEDIA
# --------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": os.environ.get("CLOUDINARY_CLOUD_NAME", ""),
    "API_KEY": os.environ.get("CLOUDINARY_API_KEY", ""),
    "API_SECRET": os.environ.get("CLOUDINARY_API_SECRET", ""),
}

cloudinary_configured = all(CLOUDINARY_STORAGE.values())

STORAGES = {
    "default": {
        "BACKEND": (
            "cloudinary_storage.storage.MediaCloudinaryStorage"
            if cloudinary_configured
            else "django.core.files.storage.FileSystemStorage"
        ),
    },
    "staticfiles": {
        "BACKEND": (
            "whitenoise.storage.CompressedManifestStaticFilesStorage"
        ),
    },
}


# --------------------------------------------------
# LANGUAGE AND TIME ZONE
# --------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------
# EMAIL
# --------------------------------------------------

if os.environ.get("EMAIL_HOST_USER") and os.environ.get("EMAIL_HOST_PASSWORD"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
else:
    EMAIL_BACKEND = (
        "django.core.mail.backends.console.EmailBackend"
        if DEBUG
        else "django.core.mail.backends.smtp.EmailBackend"
    )

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", default=False)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL",
    "APEX Platform <noreply@apexstratos.courses>",
)
REQUIRE_EMAIL_VERIFICATION = env_bool(
    "REQUIRE_EMAIL_VERIFICATION",
    default=bool(EMAIL_HOST_USER),
)


# --------------------------------------------------
# CELERY
# --------------------------------------------------

# Configure a real Redis broker before running Celery workers.
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE


# --------------------------------------------------
# STRIPE PAYMENTS
# --------------------------------------------------

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")


# --------------------------------------------------
# M-PESA PAYMENTS
# --------------------------------------------------

MPESA_CONSUMER_KEY = os.environ.get("MPESA_CONSUMER_KEY", "")
MPESA_CONSUMER_SECRET = os.environ.get("MPESA_CONSUMER_SECRET", "")
MPESA_SHORTCODE = os.environ.get("MPESA_SHORTCODE", "")
MPESA_PASSKEY = os.environ.get("MPESA_PASSKEY", "")
MPESA_CALLBACK_URL = os.environ.get("MPESA_CALLBACK_URL", "")
MPESA_ENV = os.environ.get("MPESA_ENV", "sandbox")


# --------------------------------------------------
# WHATSAPP CLOUD API
# --------------------------------------------------

WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.environ.get(
    "WHATSAPP_PHONE_NUMBER_ID", ""
)
WHATSAPP_API_VERSION = os.environ.get(
    "WHATSAPP_API_VERSION", "v20.0"
)


# --------------------------------------------------
# PLATFORM SETTINGS
# --------------------------------------------------

PLATFORM_FEE_PERCENT = float(
    os.environ.get("PLATFORM_FEE_PERCENT", "10")
)


# --------------------------------------------------
# HTTPS / PROXY SECURITY
# --------------------------------------------------

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

SECURE_SSL_REDIRECT = env_bool(
    "SECURE_SSL_REDIRECT",
    default=False,
)

SECURE_HSTS_SECONDS = int(
    os.environ.get("SECURE_HSTS_SECONDS", "0")
)

SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=False,
)

SECURE_HSTS_PRELOAD = env_bool(
    "SECURE_HSTS_PRELOAD",
    default=False,
)
