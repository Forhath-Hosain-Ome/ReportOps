"""Isolated tests: never import deployment settings or secrets."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = "isolated-inspection-summary-tests-only"
INSTALLED_APPS = ["django.contrib.auth", "django.contrib.contenttypes", "rest_framework", "inspection_summary"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "inspection_summary.tests.urls"
USE_TZ = True
MEDIA_ROOT = BASE_DIR / "unused-test-media"
REST_FRAMEWORK = {"DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
                  "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"]}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_BROKER_URL = "memory://"
