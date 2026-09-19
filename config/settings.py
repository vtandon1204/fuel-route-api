"""
Django settings for the Fuel Route Optimizer API.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Core / security
# ---------------------------------------------------------------------------

SECRET_KEY = os.environ.get(
    "DJANGO_SECRET_KEY",
    "django-insecure-local-dev-key-do-not-use-in-production",
)

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "routing",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# I18N
# ---------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
}

# ---------------------------------------------------------------------------
# Caching
#
# Geocoding and routing results are cached so that repeated requests for the
# same start/finish pair don't re-hit the external APIs. A simple file-based
# cache is used so it survives across the dev server's autoreload, with no
# extra services (e.g. Redis) required to run this project. Swap LOCATION
# for a Redis backend in production.
# ---------------------------------------------------------------------------

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": BASE_DIR / "var" / "cache",
        "TIMEOUT": 60 * 60 * 24 * 30,  # 30 days: road geometry/geocodes don't change often
    }
}

# ---------------------------------------------------------------------------
# App-specific settings (fuel route planner)
# ---------------------------------------------------------------------------

# Assumed vehicle constraints, per the assignment spec.
VEHICLE_MAX_RANGE_MILES = float(os.environ.get("VEHICLE_MAX_RANGE_MILES", 500))
VEHICLE_MPG = float(os.environ.get("VEHICLE_MPG", 10))

# Safety margin subtracted from the max range so a stop is never planned
# right at the theoretical empty-tank line (mirrors how a real driver
# would not run the tank down to fumes).
VEHICLE_RANGE_SAFETY_MARGIN_MILES = float(
    os.environ.get("VEHICLE_RANGE_SAFETY_MARGIN_MILES", 25)
)

# How far (in miles) a fuel station may sit from the route polyline and
# still be considered "along the route".
FUEL_STATION_CORRIDOR_MILES = float(os.environ.get("FUEL_STATION_CORRIDOR_MILES", 5))

# Data files bundled with the repo (see data/README.md).
FUEL_PRICES_CSV = BASE_DIR / "data" / "fuel_prices.csv"
US_CITIES_CSV = BASE_DIR / "data" / "us_cities.csv"

# Routing/geocoding providers - both free, keyless, public services.
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
NOMINATIM_BASE_URL = os.environ.get(
    "NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org"
)
# Nominatim's usage policy requires a descriptive User-Agent identifying the app.
HTTP_USER_AGENT = os.environ.get(
    "HTTP_USER_AGENT", "fuel-route-api/1.0 (backend-take-home-assessment)"
)
EXTERNAL_HTTP_TIMEOUT_SECONDS = float(os.environ.get("EXTERNAL_HTTP_TIMEOUT_SECONDS", 10))
