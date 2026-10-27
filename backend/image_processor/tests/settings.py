"""Isolated upload tests: in-memory DB, no production settings or task broker.

Run from backend: python -m django test image_processor.tests
    --settings=image_processor.tests.settings
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
SECRET_KEY = "isolated-upload-tests-only-not-a-deployment-secret"
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "rest_framework",
    "image_processor",
    "puma_summary",  # Verify that identical numeric batch IDs remain isolated.
    "final_summary",  # Imported by the existing shared filename utilities.
]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
ROOT_URLCONF = "image_processor.tests.urls"
MEDIA_ROOT = BASE_DIR / "unused-test-media"
USE_TZ = True
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
CELERY_BROKER_URL = "memory://"
MIGRATION_MODULES = {"puma_summary": "image_processor.tests.puma_migrations"}
IMAGE_PROCESSOR_TEST_LOCKS = True
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
