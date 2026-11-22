"""Explicit, disposable PostgreSQL target; never uses deployment credentials."""
from .settings import *  # noqa: F403

DATABASES = {"default": {
    "ENGINE": "django.db.backends.postgresql", "NAME": "image_phase1_tests",
    "USER": "postgres", "PASSWORD": "local-tests-only", "HOST": "127.0.0.1", "PORT": "55438",
}}
IMAGE_PROCESSOR_TEST_LOCKS = False
