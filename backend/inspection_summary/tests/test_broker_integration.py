"""Opt-in REAL Redis/Celery + PostgreSQL. No eager mode or production settings.

Start owned disposable localhost services on PG 55475 and Redis 56375, then set
INSPECTION_SUMMARY_DISPOSABLE_POSTGRES=1 and INSPECTION_SUMMARY_REAL_BROKER=1.
Run this module with inspection_summary.tests.settings_postgresql.
"""
import io
import os
import time
from unittest import skipUnless
from unittest.mock import patch

import openpyxl
from celery import Celery, current_app
from celery.contrib.testing.worker import start_worker
from django.db import connection
from rest_framework.test import APIClient

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import recover_dispatches
from inspection_summary.tasks import generate_inspection_summary
from .helpers import raw_workbook, summary_workbook, upload
from .test_lifecycle import identity
from . import test_postgresql as pg
from .runtime_cleanup import DatabaseClosingWorker, assert_no_worker_sessions


@skipUnless(os.environ.get("INSPECTION_SUMMARY_REAL_BROKER") == "1" and connection.vendor == "postgresql",
            "Owned real Redis worker and disposable PostgreSQL required; never eager mode.")
class RealBrokerTests(pg.DisposablePostgresFixture):
    # Inherit setup only; concurrency methods remain in their dedicated suite.
    def setUp(self):
        super().setUp()
        previous = current_app._get_current_object()
        self.addCleanup(previous.set_current)
        self.addCleanup(previous.set_default)
        self.app = Celery("inspection_summary_r75", broker="redis://127.0.0.1:56375/14",
                          backend="redis://127.0.0.1:56375/15")
        self.app.conf.update(task_always_eager=False, task_default_queue="celery",
            task_store_errors_even_if_ignored=True, broker_connection_retry_on_startup=False,
            worker_hijack_root_logger=False)
        self.addCleanup(self.app.close)
        self.app.set_current()
        self.app.set_default()
        self.app.autodiscover_tasks(["inspection_summary"], force=True)
        self.worker_context = start_worker(self.app, pool="solo", concurrency=1, perform_ping_check=False,
                                          shutdown_timeout=15, WorkController=DatabaseClosingWorker)
        self.worker = self.worker_context.__enter__()
        self.addCleanup(self.stop_worker)
        self.client = APIClient(); self.client.force_authenticate(self.user)

    def stop_worker(self):
        try:
            # Celery requests shutdown and joins the thread, raising on timeout.
            self.worker_context.__exit__(None, None, None)
            self.assertFalse(self.worker.worker_thread.is_alive())
            self.assertTrue(self.worker.database_closed)
        finally:
            self.app.backend.client.connection_pool.disconnect()
            self.app.close()
        assert_no_worker_sessions(self)

    def wait_terminal(self, job):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            job.refresh_from_db()
            if job.status in {"COMPLETED", "FAILED"}: return job
            time.sleep(0.05)
        self.fail("Real worker did not reach terminal state")

    def post(self):
        response = self.client.post("/inspection-summary/jobs/", {
            "inspection_summary": upload(summary_workbook()), "raw": upload(raw_workbook())}, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        return Job.objects.get(pk=response.data["job_id"])

    def test_real_upload_commit_queue_worker_status_download_and_duplicate(self):
        self.assertFalse(self.app.conf.task_always_eager)
        job = self.wait_terminal(self.post()); self.assertEqual(job.status, "COMPLETED")
        status = self.client.get(f"/inspection-summary/jobs/{job.pk}/"); self.assertTrue(status.data["download_ready"])
        response = self.client.get(f"/inspection-summary/jobs/{job.pk}/download/")
        self.assertEqual(response.status_code, 200)
        contents = b"".join(response.streaming_content); response.close()
        wb = openpyxl.load_workbook(io.BytesIO(contents)); self.assertEqual(wb.sheetnames, ["QC Dashboard", "Analysis", "Summary", "100%"]); wb.close()
        duplicate = generate_inspection_summary.apply_async(args=[str(job.pk), *identity(job)[1:]], ignore_result=False)
        self.assertEqual(duplicate.get(timeout=30), {"ignored": True})
        self.assertEqual(storage.output_path(job.pk).read_bytes(), contents)

    def test_real_accepted_publication_exception_recoverable(self):
        from datetime import timedelta
        from django.utils import timezone
        original = generate_inspection_summary.apply_async
        def accept_then_raise(**kwargs):
            original(**kwargs)
            raise OSError("simulated lost publisher confirmation")
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async", side_effect=accept_then_raise):
            job = self.post()
        # Worker may already have claimed. Otherwise recover UNKNOWN with a new identity.
        job.refresh_from_db()
        if job.status == "PENDING":
            Job.objects.filter(pk=job.pk).update(publication_lease_expires_at=timezone.now()-timedelta(seconds=1))
            recover_dispatches()
        self.assertEqual(self.wait_terminal(job).status, "COMPLETED")

    def test_real_worker_exception_is_celery_failure(self):
        with patch("inspection_summary.services.parse_inspection_workbook", side_effect=RuntimeError("injected")):
            job = self.wait_terminal(self.post())
            self.assertEqual(job.status, "FAILED")
            result = self.app.AsyncResult(job.task_id)
            deadline = time.monotonic() + 10
            while result.state != "FAILURE" and time.monotonic() < deadline: time.sleep(0.05)
            self.assertEqual(result.state, "FAILURE")

    def test_real_missing_input_after_dispatch_is_observable_failure(self):
        with patch("inspection_summary.services.publish_inspection_summary_job"):
            job = self.post()
        storage.input_path(job.pk, "raw").unlink()
        from inspection_summary.services import publish_inspection_summary_job
        publish_inspection_summary_job(*identity(job))
        self.assertEqual(self.wait_terminal(job).status, "FAILED")
        result = self.app.AsyncResult(str(job.dispatch_token))
        deadline = time.monotonic() + 10
        while result.state != "FAILURE" and time.monotonic() < deadline: time.sleep(0.05)
        self.assertEqual(result.state, "FAILURE")

    def test_real_worker_optional_sources_and_structured_schema(self):
        from .test_dynamic_contract import structured_workbook
        for field, workbook, sheets in [
            ('inspection_summary', summary_workbook(), ['Analysis','Summary']),
            ('hundred_percent', structured_workbook(60), ['Analysis','Summary','100%']),
        ]:
            with self.subTest(field=field):
                response = self.client.post('/inspection-summary/jobs/', {field: upload(workbook)}, format='multipart')
                self.assertEqual(response.status_code, 202, response.data)
                job = self.wait_terminal(Job.objects.get(pk=response.data['job_id']))
                self.assertEqual(job.status, 'COMPLETED', job.error_detail)
                preview = self.client.get(f'/inspection-summary/jobs/{job.pk}/preview/')
                self.assertEqual(preview.status_code, 200, preview.data)
                self.assertEqual(preview.data['overview']['sections'], sheets)
                if field == 'hundred_percent':
                    self.assertEqual(preview.data['reconciliation']['defect_field_count'], 60)
