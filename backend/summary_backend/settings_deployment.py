"""Explicit settings for isolated deployment-readiness stacks."""
import os
from pathlib import Path
from urllib.parse import quote


def required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required deployment configuration is missing: {name}")
    return value


def secret(name):
    value = Path(required(name + "_FILE")).read_text().strip()
    if not value:
        raise RuntimeError(f"Empty deployment secret: {name}")
    return value


# The encrypted model package reads this while the base settings/apps load.
os.environ["FIELD_ENCRYPTION_KEY"] = secret("FIELD_ENCRYPTION_KEY")
os.environ.setdefault("REDIS_HOST", "redis")
os.environ.setdefault("REDIS_PORT", "6379")
from .settings import *  # noqa: E402,F403

SECRET_KEY = secret("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = [part.strip() for part in required("DJANGO_ALLOWED_HOSTS").split(",")]
if "*" in ALLOWED_HOSTS or any(not host for host in ALLOWED_HOSTS):
    raise RuntimeError("Deployment hosts must be explicit.")
CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [required("PUBLIC_ORIGIN")]
CSRF_TRUSTED_ORIGINS = [required("PUBLIC_ORIGIN")]
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = required("PUBLIC_ORIGIN").startswith("https://")
CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql",
    "NAME": required("POSTGRES_DB"), "USER": required("POSTGRES_USER"),
    "PASSWORD": secret("POSTGRES_PASSWORD"), "HOST": "postgres", "PORT": "5432",
}}
redis_password = quote(secret("REDIS_PASSWORD"), safe="")
CELERY_BROKER_URL = f"redis://:{redis_password}@redis:6379/0"
CHANNEL_LAYERS = {"default": {"BACKEND": "channels_redis.core.RedisChannelLayer",
                              "CONFIG": {"hosts": [f"redis://:{redis_password}@redis:6379/1"]}}}
SIMPLE_JWT = {**SIMPLE_JWT, "SIGNING_KEY": SECRET_KEY}  # noqa: F405
IMAGE_PROCESSOR_STAGING_ROOT = "/tmp/batch_uploads"
# Stream errors without request URLs: WebSocket query strings contain JWTs.
LOGGING = {"version": 1, "disable_existing_loggers": False,
           "handlers": {"console": {"class": "logging.StreamHandler"}},
           "root": {"handlers": ["console"], "level": "WARNING"}}
