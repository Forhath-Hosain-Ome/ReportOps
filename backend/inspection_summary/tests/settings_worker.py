"""Settings for owned subprocess workers attached only to a disposable test DB."""
import os
import tempfile
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings_postgresql import *  # noqa: F403

if os.environ.get("INSPECTION_SUMMARY_WORKER_DATABASE") != "test_inspection_summary_r75":
    raise ImproperlyConfigured("Only the disposable test database is supported.")
DATABASES["default"]["NAME"] = "test_inspection_summary_r75"  # noqa: F405
MEDIA_ROOT = Path(os.environ["INSPECTION_SUMMARY_WORKER_MEDIA"]).resolve()
if (not MEDIA_ROOT.is_relative_to(Path(tempfile.gettempdir()).resolve())
        or MEDIA_ROOT.name != "media" or MEDIA_ROOT.parent == Path(tempfile.gettempdir()).resolve()):
    raise ImproperlyConfigured("Worker media must be an owned temporary test directory.")
