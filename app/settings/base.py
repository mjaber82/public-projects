import os
from pathlib import Path
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(",")

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "django_celery_beat",
]

LOCAL_APPS = [
    "app.core",
    "app.users",
    "app.wallets",
    "app.transactions",
    "app.notifications",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "app.core.middleware.JWTAuthMiddleware",  # populates request.user from Bearer token
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "app.urls"
WSGI_APPLICATION = "app.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

AUTH_USER_MODEL = "users.User"

# Password hashing — Argon2 first
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("rest_framework_simplejwt.authentication.JWTAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"user": "60/min"},
}

# JWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", 5))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.getenv("JWT_REFRESH_TOKEN_LIFETIME_DAYS", 7))),
    "ROTATE_REFRESH_TOKENS": False,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "TOKEN_TYPE_CLAIM": "token_type",
    "USER_ID_CLAIM": "user_id",
    "USER_ID_FIELD": "public_id",
}

# Celery
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://redis:6379/2")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"

# Redis
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

# Stripe
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
STRIPE_CURRENCY = os.getenv("STRIPE_CURRENCY", "usd")
FAKE_STRIPE_CHECKOUT = os.getenv("FAKE_STRIPE_CHECKOUT", "False") == "True"

# Firebase
FIREBASE_PROJECT_ID = os.getenv("FIREBASE_PROJECT_ID")
FIREBASE_SERVICE_ACCOUNT_JSON = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
FIREBASE_WEB_API_KEY = os.getenv("FIREBASE_WEB_API_KEY")
FIREBASE_AUTH_EMULATOR_HOST = os.getenv("FIREBASE_AUTH_EMULATOR_HOST")

# Business rules
APP_IDLE_TIME = timedelta(minutes=int(os.getenv("APP_IDLE_TIME_MINUTES", 5)))
TRANSACTION_TIMEOUT_DAYS = int(os.getenv("TRANSACTION_TIMEOUT_DAYS", 30))
DAILY_SEND_LIMIT_USD = int(os.getenv("DAILY_SEND_LIMIT_USD", 5000))
MONTHLY_SEND_LIMIT_USD = int(os.getenv("MONTHLY_SEND_LIMIT_USD", 20000))
DAILY_RECEIVE_LIMIT_USD = int(os.getenv("DAILY_RECEIVE_LIMIT_USD", 10000))
MIN_TRANSFER_AMOUNT_USD = int(os.getenv("MIN_TRANSFER_AMOUNT_USD", 1))
MAX_TOPUP_AMOUNT_USD = int(os.getenv("MAX_TOPUP_AMOUNT_USD", 10000))

# Rate limiting
PENALTY_RULES = {
    0: 15 * 60,  # 15 minutes
    1: 30 * 60,  # 30 minutes
    2: 60 * 60,  # 60 minutes
    3: 24 * 60 * 60,  # 24 hours
}
MAX_PENALTY_LEVEL = 4

OTP_MAX_REQUESTS_PER_DEVICE = int(os.getenv("OTP_MAX_REQUESTS_PER_DEVICE", 5))
OTP_WINDOW_SECONDS = int(os.getenv("OTP_WINDOW_SECONDS", 3600))
OTP_LOCK_DURATION_SECONDS = int(os.getenv("OTP_LOCK_DURATION_SECONDS", 3600))
EMAIL_OTP_TTL_SECONDS = int(os.getenv("EMAIL_OTP_TTL_SECONDS", 600))

# Maintenance
IS_MAINTENANCE = os.getenv("IS_MAINTENANCE", "False") == "True"
MAINTENANCE_MESSAGE = os.getenv("MAINTENANCE_MESSAGE", "System is under maintenance.")

STATIC_URL = "/static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
