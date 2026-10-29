"""Build-only settings for deterministic static asset collection."""
import os
import sys

from cryptography.fernet import Fernet


if "collectstatic" not in sys.argv:
    raise RuntimeError("Build-only settings may only run collectstatic.")

os.environ["FIELD_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ.setdefault("REDIS_HOST", "localhost")
os.environ.setdefault("REDIS_PORT", "6379")

from .settings import *  # noqa: E402,F403


SECRET_KEY = "collectstatic-build-only"
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"], "level": "WARNING"},
}
