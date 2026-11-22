"""Real prefork worker bootstrap for deterministic kill/restart tests only."""
import os
import time
from pathlib import Path

os.environ["DJANGO_SETTINGS_MODULE"] = "inspection_summary.tests.settings_worker"

import django
from celery import Celery

django.setup()

app = Celery("inspection_summary_restart", broker="redis://127.0.0.1:56375/14",
             backend="redis://127.0.0.1:56375/15")
app.conf.update(task_always_eager=False, task_default_queue="celery",
                task_store_errors_even_if_ignored=True, broker_connection_retry_on_startup=False)
app.set_default()
app.set_current()
app.autodiscover_tasks(["inspection_summary"], force=True)

if os.environ.get("INSPECTION_SUMMARY_PAUSE_AFTER_WRITE") == "1":
    from django.conf import settings
    from inspection_summary import services

    original_write = services.write_report

    def pause_after_real_write(*args):
        original_write(*args)
        marker = Path(settings.MEDIA_ROOT).parent / "worker-is-writing"
        marker.write_text(str(os.getpid()), encoding="ascii")
        # A real worker has claimed and written its actual temporary XLSX. The
        # parent test kills its process group here; no exception simulates death.
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            time.sleep(0.05)

    services.write_report = pause_after_real_write
