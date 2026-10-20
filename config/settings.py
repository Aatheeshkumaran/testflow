"""TestFlow settings. Development defaults; override via environment variables for production."""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("TESTFLOW_DEBUG", "1") == "1"
SECRET_KEY = os.environ.get("TESTFLOW_SECRET_KEY", "dev-only-insecure-key-change-me")
if not DEBUG and SECRET_KEY.startswith("dev-only"):
    raise ImproperlyConfigured("Set TESTFLOW_SECRET_KEY when TESTFLOW_DEBUG=0.")
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    "testflow-seven.vercel.app",
]
CSRF_TRUSTED_ORIGINS = [
    "https://testflow-seven.vercel.app",
]
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "accounts",
    "portal",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "accounts.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [{
    "BACKEND": "django.template.backends.django.DjangoTemplates",
    "DIRS": [BASE_DIR / "templates"],
    "APP_DIRS": True,
    "OPTIONS": {
        "context_processors": [
            "django.template.context_processors.debug",
            "django.template.context_processors.request",
            "django.contrib.auth.context_processors.auth",
            "django.contrib.messages.context_processors.messages",
            "accounts.context_processors.identity",
        ],
    },
}]

# SQLite for local work. Set TESTFLOW_DB=postgres (+ TESTFLOW_DB_NAME/USER/PASSWORD/HOST/PORT) later.
if os.environ.get("TESTFLOW_DB") == "postgres":
    DATABASES = {"default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("TESTFLOW_DB_NAME", "testflow"),
        "USER": os.environ.get("TESTFLOW_DB_USER", ""),
        "PASSWORD": os.environ.get("TESTFLOW_DB_PASSWORD", ""),
        "HOST": os.environ.get("TESTFLOW_DB_HOST", "localhost"),
        "PORT": os.environ.get("TESTFLOW_DB_PORT", "5432"),
    }}
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGOUT_REDIRECT_URL = "login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- TestFlow business rules (all tunable here) -------------------------------------------
TF_ATTENTION_THRESHOLD = 50      # student average below this % is flagged "needs attention"
TF_MARKS_GRACE_DAYS = 2          # days after a test is completed in which marks must be entered
TF_MIN_TESTS_FOR_RANKING = 3     # a mentor needs this many due tests in the period to be ranked
TF_MIN_BATCH_SAMPLE = 3          # minimum students with results before a batch average is shown
TF_MAX_UPLOAD_MB = 2             # profile image size limit
TF_ALERT_SYNC_SECONDS = 300      # how often alerts are re-evaluated when pages load

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
