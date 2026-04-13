from .base import *

DEBUG = True

# SQLite — zero setup for local development
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# Print emails to console instead of sending them
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Allow all CORS origins locally
CORS_ALLOW_ALL_ORIGINS = True

# Sentry disabled in dev
SENTRY_DSN = None
