"""Opt-in disposable localhost PostgreSQL ONLY; never imports deployment settings."""
import os
from django.core.exceptions import ImproperlyConfigured
from .settings import *  # noqa: F403

if os.environ.get("INSPECTION_SUMMARY_DISPOSABLE_POSTGRES") != "1":
    raise ImproperlyConfigured("Set INSPECTION_SUMMARY_DISPOSABLE_POSTGRES=1 for an owned disposable server.")
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "HOST": "127.0.0.1",
    "PORT": "55475", "NAME": "inspection_summary_r75", "USER": "inspection_summary_r75",
    "PASSWORD": "disposable-r75-only", "CONN_MAX_AGE": 0,
    "OPTIONS": {"connect_timeout": 3}, "TEST": {"NAME": "test_inspection_summary_r75"}}}
