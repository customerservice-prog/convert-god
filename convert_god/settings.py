from pathlib import Path
import os
import sys
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default=None):
    return os.environ.get(name, os.environ.get(f"DJANGO_{name}", default))


def env_bool(name: str, default="0") -> bool:
    return str(env(name, default)).strip().lower() in ("1", "true", "yes", "on")


def split_csv(value) -> list[str]:
    cleaned = (value or "").replace(" ", "")
    return [x for x in cleaned.split(",") if x]


SECRET_KEY = env("SECRET_KEY", "dev-only-change-me")
DEBUG = env_bool("DEBUG", "1" if ("runserver" in sys.argv) else "0")

ALLOWED_HOSTS = split_csv(env("ALLOWED_HOSTS", "127.0.0.1,localhost"))

RUNNING_TESTS = ("test" in sys.argv) or ("pytest" in sys.modules)
if DEBUG or RUNNING_TESTS:
    if "testserver" not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append("testserver")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "app",
]

# Basic auth creds (if unset, middleware is a no-op)
BASIC_AUTH_USER = env("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = env("BASIC_AUTH_PASS", "")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # Basic auth wrapper (private service)
    "app.middleware.BasicAuthMiddleware",
]

ROOT_URLCONF = "convert_god.urls"

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

WSGI_APPLICATION = "convert_god.wsgi.application"

# Database
# Default: SQLite on a persistent disk for cheapest/private deployments.
sqlite_path = env("SQLITE_PATH", "/var/data/db.sqlite3")
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": sqlite_path if not DEBUG else str(BASE_DIR / "db.sqlite3"),
        "OPTIONS": {"timeout": 20},
    }
}

# Optional: Postgres if DATABASE_URL is provided
database_url = env("DATABASE_URL")
if database_url:
    DATABASES["default"] = dj_database_url.parse(database_url, conn_max_age=600, ssl_require=False)

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

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# File storage on disk (persistent disk mount on Render)
MEDIA_ROOT = env("MEDIA_ROOT", "/var/data/media")
MEDIA_URL = "/media/"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "django.contrib.staticfiles.storage.StaticFilesStorage"
            if DEBUG
            else "whitenoise.storage.CompressedManifestStaticFilesStorage"
        )
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# CSRF
csrf_env = env("CSRF_TRUSTED_ORIGINS")
if csrf_env:
    CSRF_TRUSTED_ORIGINS = [x.strip() for x in str(csrf_env).split(",") if x.strip()]

# Production hardening
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True

    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_SAMESITE = env("CSRF_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SAMESITE = env("SESSION_COOKIE_SAMESITE", "Lax")

    SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", "0")

    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", "1")
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_REFERRER_POLICY = "same-origin"
    X_FRAME_OPTIONS = "DENY"
