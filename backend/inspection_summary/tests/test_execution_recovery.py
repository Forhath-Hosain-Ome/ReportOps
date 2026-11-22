from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import (PROCESSING_LEASE_SECONDS, TASK_HARD_LIMIT, claim_job,
    cleanup_expired_jobs, generate_job, recover_processing_jobs)
from inspection_summary.tasks import generate_inspection_summary
from .helpers import JobFixture
from .test_lifecycle import identity


class ExecutionLeaseTests(JobFixture):
    def stale(self, job):
        Job.objects.filter(pk=job.pk).update(processing_lease_expires_at=timezone.now() - timedelta(seconds=1))

    def recover(self):
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async") as send:
            with self.captureOnCommitCallbacks(execute=True): count = recover_processing_jobs()
        return count, send

    def test_claim_assigns_separate_execution_lease_beyond_hard_limit(self):
        job = self.make_job(); old_publication = job.publication_lease_expires_at
        owned = claim_job(*identity(job))
        self.assertGreater(PROCESSING_LEASE_SECONDS, TASK_HARD_LIMIT)
        self.assertAlmostEqual((owned.processing_lease_expires_at - owned.processing_started_at).total_seconds(), 1800, delta=1)
        self.assertEqual(owned.publication_lease_expires_at, old_publication)
        self.assertEqual(self.recover()[0], 0)

    def test_abandoned_run_recovers_new_identity_and_one_authoritative_output(self):
        job = self.make_job(); old = identity(job); old_run = claim_job(*old).run_token; self.stale(job)
        count, send = self.recover(); self.assertEqual(count, 1); send.assert_called_once()
        job.refresh_from_db()
        self.assertEqual(job.status, "PENDING"); self.assertIsNone(job.run_token)
        self.assertIsNone(job.processing_lease_expires_at)
        self.assertEqual(job.dispatch_generation, old[1] + 1); self.assertNotEqual(str(job.dispatch_token), old[2])
        self.assertEqual(generate_job(*old), {"ignored": True})
        self.assertEqual(generate_job(*identity(job))["status"], "COMPLETED")
        original = storage.output_path(job.pk).read_bytes()
        self.assertEqual(generate_job(*old), {"ignored": True})
        self.assertEqual(storage.output_path(job.pk).read_bytes(), original)
        self.assertNotEqual(job.run_token, old_run)
        self.assertEqual(len(list(storage.job_root(job.pk).glob("output/Result.xlsx"))), 1)

    def test_late_old_executor_cannot_publish_after_recovery(self):
        job = self.make_job(); old = identity(job)
        from inspection_summary.writer import write_report
        def revoke_while_writing(*args):
            write_report(*args); self.stale(job)
            self.assertEqual(self.recover()[0], 1)
        with patch("inspection_summary.services.write_report", side_effect=revoke_while_writing):
            self.assertEqual(generate_job(*old), {"ignored": True})
        self.assertFalse(storage.output_path(job.pk).exists())
        job.refresh_from_db(); self.assertEqual(generate_job(*identity(job))["status"], "COMPLETED")

    def test_expired_stale_execution_terminalized_before_cleanup(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale(job)
        storage.input_path(job.pk, "raw").unlink()
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)
        job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("FAILED", "JOB_EXPIRED"))
        self.assertIsNone(job.run_token); self.assertIsNotNone(job.input_deleted_at)
        self.assertFalse(storage.job_root(job.pk).exists())

    def test_missing_retained_source_terminalized_without_republication(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale(job)
        storage.input_path(job.pk, "raw").unlink()
        count, send = self.recover(); self.assertEqual(count, 1); send.assert_not_called()
        job.refresh_from_db(); self.assertEqual((job.status, job.error_code), ("FAILED", "SOURCE_UNAVAILABLE"))

    def test_changed_source_is_not_republished(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale(job)
        with storage.input_path(job.pk, "raw").open("ab") as stream: stream.write(b"changed")
        self.recover(); job.refresh_from_db()
        self.assertEqual((job.status, job.error_code), ("FAILED", "INPUT_CHANGED"))

    def test_cleanup_never_revokes_a_live_processing_lease(self):
        job = self.make_job(); owned = claim_job(*identity(job))
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_expired_jobs()["removed"], 0)
        job.refresh_from_db(); self.assertEqual(job.run_token, owned.run_token)
        self.assertTrue(storage.job_root(job.pk).exists())

    def test_owned_retention_expiry_during_execution_reaches_terminal(self):
        job = self.make_job()
        from inspection_summary.writer import write_report
        def expire_while_writing(*args):
            write_report(*args)
            Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        with patch("inspection_summary.services.write_report", side_effect=expire_while_writing):
            self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        job.refresh_from_db(); self.assertEqual((job.status, job.error_code), ("FAILED", "JOB_EXPIRED"))
        self.assertIsNone(job.run_token); self.assertEqual(cleanup_expired_jobs()["removed"], 1)

    def test_expired_execution_lease_rejects_final_publication(self):
        job = self.make_job()
        from inspection_summary.writer import write_report
        def expire_lease(*args): write_report(*args); self.stale(job)
        with patch("inspection_summary.services.write_report", side_effect=expire_lease):
            self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        self.assertFalse(storage.output_path(job.pk).exists())
        self.assertEqual(self.recover()[0], 1)

    def test_unexpected_recovery_storage_error_is_observable(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale(job)
        with patch("inspection_summary.services.validated_inputs", side_effect=PermissionError("private")):
            with self.assertRaises(PermissionError):
                with self.captureOnCommitCallbacks(execute=True): recover_processing_jobs()
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")
        self.assertNotIn("private", str(job.error_detail))

    def test_permission_error_during_execution_remains_unexpected(self):
        job = self.make_job(); failure = PermissionError("private")
        with patch("inspection_summary.services.validated_inputs", side_effect=failure):
            with self.assertRaises(PermissionError) as raised: generate_inspection_summary.run(*identity(job))
        self.assertIs(raised.exception, failure)
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")


    def test_recovery_persistence_error_preserves_original_exception(self):
        job = self.make_job(); claim_job(*identity(job)); self.stale(job)
        failure = PermissionError("original storage failure")
        with patch("inspection_summary.services.validated_inputs", side_effect=failure), patch(
                "inspection_summary.services._terminalize_recovery", side_effect=RuntimeError("database")):
            with self.assertRaises(PermissionError) as raised:
                with self.captureOnCommitCallbacks(execute=True): recover_processing_jobs()
        self.assertIs(raised.exception, failure)

    def test_legacy_missing_execution_lease_has_bounded_fallback(self):
        job = self.make_job(); claim_job(*identity(job))
        Job.objects.filter(pk=job.pk).update(processing_lease_expires_at=None,
            processing_started_at=timezone.now() - timedelta(hours=1),
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")
