"""Real PostgreSQL locks, separate thread connections; skipped on SQLite."""
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import (claim_job, claim_maintenance, cleanup_expired_jobs,
    create_job, generate_job, recover_dispatches, recover_processing_jobs, advance, StaleRun)
from .helpers import raw_workbook, summary_workbook, upload
from .test_lifecycle import identity


class DisposablePostgresFixture(TransactionTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(); self.addCleanup(self.directory.cleanup)
        self.media = Path(self.directory.name) / "media"; self.media.mkdir()
        self.setting = override_settings(MEDIA_ROOT=self.media); self.setting.enable(); self.addCleanup(self.setting.disable)
        self.user = get_user_model().objects.create_user(username="owner")

    def make_job(self):
        with patch("inspection_summary.services.publish_inspection_summary_job"):
            job = create_job(self.user, upload(summary_workbook()), upload(raw_workbook()))
        Job.objects.filter(pk=job.pk).update(dispatch_state="QUEUED")
        job.refresh_from_db(); return job

    def race(self, action):
        gate = Barrier(2)
        def run():
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return action()
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run) for _ in range(2)]
            return [f.result(timeout=30) for f in futures]

    def expire(self, job):
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1),
            publication_lease_expires_at=timezone.now() - timedelta(seconds=1))


@skipUnless(connection.vendor == "postgresql", "Real disposable PostgreSQL required; SQLite is not concurrency evidence.")
class PostgreSQLConcurrencyTests(DisposablePostgresFixture):
    def test_two_workers_claim_exactly_one_processing_owner(self):
        job = self.make_job()
        results = self.race(lambda: claim_job(*identity(job)))
        self.assertEqual(sum(r is not None for r in results), 1)
        job.refresh_from_db(); self.assertEqual(job.status, "PROCESSING")
        self.assertEqual(job.run_token, next(r.run_token for r in results if r))

    def test_old_generation_rejected_after_recovery(self):
        job = self.make_job(); old = identity(job)
        Job.objects.filter(pk=job.pk).update(dispatch_state="UNKNOWN", publication_lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async"):
            self.assertEqual(recover_dispatches(), 1)
        self.assertTrue(all(r is None for r in self.race(lambda: claim_job(*old))))
        job.refresh_from_db(); self.assertIsNotNone(claim_job(*identity(job)))

    def test_two_cleanup_claims_exactly_one_maintenance_owner(self):
        job = self.make_job(); self.expire(job)
        results = self.race(lambda: claim_maintenance(job.pk))
        self.assertEqual(sum(r is not None for r in results), 1)
        job.refresh_from_db(); self.assertEqual(job.maintenance_token, next(r.maintenance_token for r in results if r))

    def test_two_full_cleanup_workers_delete_exactly_once(self):
        job = self.make_job(); self.expire(job)
        results = self.race(cleanup_expired_jobs)
        self.assertEqual(sum(r["removed"] for r in results), 1)
        self.assertFalse(storage.job_root(job.pk).exists())

    def test_cleanup_races_processing_worker_no_deletion(self):
        job = self.make_job(); writing = Event(); release = Event()
        from inspection_summary.writer import write_report
        def pause(*args):
            write_report(*args); writing.set()
            if not release.wait(timeout=15): raise TimeoutError("test synchronization")
        def run():
            close_old_connections()
            try: return generate_job(*identity(job))
            finally: close_old_connections()
        with patch("inspection_summary.services.write_report", side_effect=pause), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(run)
            try:
                self.assertTrue(writing.wait(timeout=15)); self.expire(job)
                self.assertEqual(cleanup_expired_jobs()["removed"], 0)
                self.assertTrue(storage.job_root(job.pk).exists())
            finally: release.set()
            self.assertEqual(future.result(timeout=15), {"ignored": True})

    def test_terminal_state_cannot_regress(self):
        job = self.make_job(); generate_job(*identity(job))
        self.assertTrue(all(r is None for r in self.race(lambda: claim_job(*identity(job)))))
        job.refresh_from_db(); self.assertEqual((job.status, job.dispatch_state), ("COMPLETED", "TERMINAL"))

    def test_stale_run_has_no_final_publication_authority(self):
        job = self.make_job(); replacement = uuid.uuid4()
        from inspection_summary.writer import write_report
        def supersede(*args):
            write_report(*args)
            def replace():
                close_old_connections()
                try: Job.objects.filter(pk=job.pk).update(run_token=replacement)
                finally: close_old_connections()
            with ThreadPoolExecutor(max_workers=1) as pool: pool.submit(replace).result(timeout=10)
        with patch("inspection_summary.services.write_report", side_effect=supersede):
            self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        job.refresh_from_db(); self.assertEqual(job.run_token, replacement)
        self.assertFalse(storage.output_path(job.pk).exists())

    def test_duplicate_delivery_after_completed_ignored(self):
        job = self.make_job(); generate_job(*identity(job)); original = storage.output_path(job.pk).read_bytes()
        self.assertEqual(self.race(lambda: generate_job(*identity(job))), [{"ignored": True}, {"ignored": True}])
        self.assertEqual(storage.output_path(job.pk).read_bytes(), original)


    def stale_execution(self, job):
        Job.objects.filter(pk=job.pk).update(processing_lease_expires_at=timezone.now() - timedelta(seconds=1))

    def test_concurrent_stale_processing_recovery_has_one_new_generation(self):
        job = self.make_job(); old = identity(job); claim_job(*old); self.stale_execution(job)
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async") as send:
            results = self.race(recover_processing_jobs)
        self.assertEqual(sum(results), 1); send.assert_called_once()
        job.refresh_from_db(); self.assertEqual(job.dispatch_generation, old[1] + 1)
        self.assertEqual(job.status, "PENDING"); self.assertIsNone(job.run_token)
        self.assertEqual(generate_job(*old), {"ignored": True})

    def test_stale_worker_finalization_races_execution_recovery(self):
        job = self.make_job(); old = identity(job); verified = Event(); gate = Barrier(2)
        from inspection_summary.writer import verify_report
        def pause_finalizer(*args):
            verify_report(*args); verified.set(); gate.wait(timeout=15)
        def execute():
            close_old_connections()
            try: return generate_job(*old)
            finally: close_old_connections()
        with patch("inspection_summary.services.verify_report", side_effect=pause_finalizer), patch(
                "inspection_summary.tasks.generate_inspection_summary.apply_async"), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(execute)
            self.assertTrue(verified.wait(timeout=15)); self.stale_execution(job); gate.wait(timeout=15)
            self.assertEqual(recover_processing_jobs(), 1)
            self.assertEqual(future.result(timeout=15), {"ignored": True})
        self.assertFalse(storage.output_path(job.pk).exists())
        job.refresh_from_db(); self.assertEqual(generate_job(*identity(job))["status"], "COMPLETED")

    def test_old_run_cannot_write_after_recovery_new_claim(self):
        job = self.make_job(); old_owner = claim_job(*identity(job)); self.stale_execution(job)
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async"): recover_processing_jobs()
        job.refresh_from_db(); new_owner = claim_job(*identity(job))
        with self.assertRaises(StaleRun): advance(old_owner, "LATE_WRITE")
        job.refresh_from_db(); self.assertEqual(job.run_token, new_owner.run_token)
        self.assertEqual(job.stage, "VALIDATING")

    def test_cleanup_race_revokes_stale_expired_execution_before_delete(self):
        job = self.make_job(); old = identity(job); claim_job(*old); self.stale_execution(job); self.expire(job)
        results = self.race(cleanup_expired_jobs)
        self.assertEqual(sum(r["removed"] for r in results), 1)
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")
        self.assertIsNone(job.run_token); self.assertIsNotNone(job.input_deleted_at)
        self.assertFalse(storage.job_root(job.pk).exists())
        self.assertEqual(generate_job(*old), {"ignored": True})

    def test_recovered_completed_job_never_regresses_again(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale_execution(job)
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async"): recover_processing_jobs()
        job.refresh_from_db(); generate_job(*identity(job)); original = storage.output_path(job.pk).read_bytes()
        self.stale_execution(job)
        self.assertEqual(self.race(recover_processing_jobs), [0, 0])
        job.refresh_from_db(); self.assertEqual(job.status, "COMPLETED")
        self.assertEqual(storage.output_path(job.pk).read_bytes(), original)
