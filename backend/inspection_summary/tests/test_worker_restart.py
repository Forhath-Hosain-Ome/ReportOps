"""Required real-process death/restart gate; no eager or injected-failure substitute."""
import io
import os
import signal
import subprocess
import sys
import time
from datetime import timedelta
from unittest import skipUnless

import openpyxl
from celery import Celery, current_app
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import (StaleRun, advance, cleanup_expired_jobs,
                                          recover_processing_jobs)
from inspection_summary.tasks import generate_inspection_summary
from . import test_postgresql as pg
from .helpers import raw_workbook, summary_workbook, upload
from .test_lifecycle import identity
from .runtime_cleanup import assert_no_worker_sessions


@skipUnless(os.name == "posix" and connection.vendor == "postgresql"
            and os.environ.get("INSPECTION_SUMMARY_REAL_BROKER") == "1",
            "Disposable PostgreSQL, Redis and Linux prefork subprocesses required.")
class RealWorkerRestartTests(pg.DisposablePostgresFixture):
    def setUp(self):
        super().setUp()
        previous = current_app._get_current_object()
        self.addCleanup(previous.set_current); self.addCleanup(previous.set_default)
        self.app = Celery("restart_test", broker="redis://127.0.0.1:56375/14",
                          backend="redis://127.0.0.1:56375/15")
        self.app.conf.update(task_always_eager=False, task_default_queue="celery",
                             task_store_errors_even_if_ignored=True)
        self.app.set_current(); self.app.set_default(); self.addCleanup(self.app.close)
        # Registered before process cleanups: LIFO joins both process groups first.
        self.addCleanup(self.close_runtime)
        self.app.autodiscover_tasks(["inspection_summary"], force=True)
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def close_runtime(self):
        self.app.backend.client.connection_pool.disconnect()
        self.app.close()
        assert_no_worker_sessions(self)

    def start_worker(self, pause=False):
        env = os.environ.copy()
        env.update(DJANGO_SETTINGS_MODULE="inspection_summary.tests.settings_worker",
                   INSPECTION_SUMMARY_WORKER_DATABASE=connection.settings_dict["NAME"],
                   INSPECTION_SUMMARY_WORKER_MEDIA=str(self.media),
                   INSPECTION_SUMMARY_PAUSE_AFTER_WRITE="1" if pause else "0",
                   PYTHONDONTWRITEBYTECODE="1")
        log = (self.media.parent / ("old-worker.log" if pause else "replacement-worker.log")).open("wb")
        self.addCleanup(log.close)
        process = subprocess.Popen([sys.executable, "-B", "-m", "celery", "-A",
            "inspection_summary.tests.worker_runtime:app", "worker", "--pool=prefork",
            "--concurrency=1", "--loglevel=WARNING", "--without-gossip", "--without-mingle",
            "--without-heartbeat", "--hostname", ("old" if pause else "replacement") + "@%h"],
            env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.addCleanup(self.kill_worker, process)
        return process

    @staticmethod
    def kill_worker(process):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=15)

    def wait_for(self, predicate, description):
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if predicate(): return
            time.sleep(0.05)
        self.fail(description)

    def test_sigkill_after_claim_and_write_recovers_and_retains_safely(self):
        old_worker = self.start_worker(pause=True)
        response = self.client.post("/inspection-summary/jobs/", {
            "inspection_summary": upload(summary_workbook()), "raw": upload(raw_workbook())}, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        job = Job.objects.get(pk=response.data["job_id"])
        self.wait_for(lambda: (self.media.parent / "worker-is-writing").exists(), "Old prefork worker never reached real write")
        job.refresh_from_db(); self.assertEqual(job.status, "PROCESSING")
        old_owner = Job.objects.get(pk=job.pk); old_identity = identity(old_owner)
        self.assertTrue(list(storage.job_root(job.pk).glob("output/*.tmp.xlsx")))
        self.kill_worker(old_worker)
        self.assertEqual(old_worker.returncode, -signal.SIGKILL)
        job.refresh_from_db(); self.assertEqual(job.status, "PROCESSING")
        self.assertEqual(job.run_token, old_owner.run_token)
        self.assertEqual(recover_processing_jobs(), 0)  # Valid lease protects it.

        Job.objects.filter(pk=job.pk).update(processing_lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.start_worker(pause=False)
        self.assertEqual(recover_processing_jobs(), 1)
        with self.assertRaises(StaleRun): advance(old_owner, "OLD_OWNER_WRITE")

        def completed():
            job.refresh_from_db()
            return job.status in {"COMPLETED", "FAILED"}
        self.wait_for(completed, "Replacement worker did not finish recovered job")
        self.assertEqual(job.status, "COMPLETED", job.error_detail)
        self.assertEqual(job.dispatch_generation, old_identity[1] + 1)
        self.assertNotEqual(str(job.dispatch_token), old_identity[2])
        duplicate = generate_inspection_summary.apply_async(
            args=[str(job.pk), old_identity[1], old_identity[2]], ignore_result=False)
        self.assertEqual(duplicate.get(timeout=30), {"ignored": True})
        response = self.client.get(f"/inspection-summary/jobs/{job.pk}/download/")
        self.assertEqual(response.status_code, 200)
        data = b"".join(response.streaming_content); response.close()
        wb = openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual(wb.sheetnames, ["QC Dashboard", "Analysis", "Summary", "100%"]); self.assertEqual(len(wb.defined_names), 4); wb.close()
        self.assertEqual(storage.output_path(job.pk).read_bytes(), data)
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)
        self.assertFalse(storage.job_root(job.pk).exists())
        self.assertEqual(self.client.get(f"/inspection-summary/jobs/{job.pk}/download/").status_code, 410)
