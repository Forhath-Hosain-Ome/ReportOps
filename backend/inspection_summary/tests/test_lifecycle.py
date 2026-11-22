import uuid
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from kombu.exceptions import EncodeError

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import (claim_job, claim_maintenance, cleanup_expired_jobs,
    generate_job, publish_inspection_summary_job, recover_dispatches, MAINTENANCE_LEASE_SECONDS)
from inspection_summary.tasks import generate_inspection_summary
from inspection_summary.workbook_security import WorkbookValidationError
from .helpers import JobFixture


def identity(job):
    return job.pk, job.dispatch_generation, str(job.dispatch_token)


class LifecycleTests(JobFixture):
    def requested(self):
        job = self.make_job()
        job.dispatch_state = Job.Dispatch.REQUESTED
        job.save(update_fields=["dispatch_state"])
        return job

    def expire(self, job):
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1),
            publication_lease_expires_at=timezone.now() - timedelta(seconds=1))

    def test_duplicate_task_delivery_does_not_double_publish(self):
        job = self.make_job()
        self.assertEqual(generate_job(*identity(job))["status"], "COMPLETED")
        original = storage.output_path(job.pk).read_bytes()
        self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        self.assertEqual(storage.output_path(job.pk).read_bytes(), original)

    def test_known_validation_failure_is_structured_normal_task_result(self):
        job = self.make_job()
        with patch("inspection_summary.services.parse_inspection_workbook", side_effect=WorkbookValidationError(
                "UNRECOGNIZED_VISIBLE_SHEET", "Unsupported structure.", sheet="Unknown")):
            self.assertEqual(generate_inspection_summary.run(*identity(job))["code"], "UNRECOGNIZED_VISIBLE_SHEET")
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertEqual(job.dispatch_state, "TERMINAL")
        self.assertEqual(job.error_detail["sheet"], "Unknown")
        self.assertFalse(storage.output_path(job.pk).exists())

    def test_preflight_failure_is_definite_without_broker_io(self):
        job = self.requested()
        with patch("inspection_summary.services.dumps", side_effect=EncodeError("private")), patch(
                "inspection_summary.tasks.generate_inspection_summary.apply_async") as send:
            self.assertEqual(publish_inspection_summary_job(*identity(job)), "FAILED")
        send.assert_not_called()
        job.refresh_from_db()
        self.assertEqual((job.status, job.dispatch_state, job.error_code), ("FAILED", "TERMINAL", "DISPATCH_PREFLIGHT_FAILED"))
        self.assertNotIn("private", str(job.error_detail))

    def test_accepted_message_then_transport_exception_remains_unknown(self):
        job = self.requested(); accepted = []
        def accept_then_raise(**kwargs):
            accepted.append(kwargs["args"])
            raise OSError("private broker address")
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async", side_effect=accept_then_raise):
            self.assertEqual(publish_inspection_summary_job(*identity(job)), "UNKNOWN")
        job.refresh_from_db()
        self.assertEqual((job.status, job.dispatch_state), ("PENDING", "UNKNOWN"))
        self.assertEqual(job.last_error_code, "DISPATCH_OUTCOME_UNKNOWN")
        self.assertEqual(accepted, [[str(job.pk), job.dispatch_generation, str(job.dispatch_token)]])
        self.assertEqual(generate_job(*accepted[0]), {"ignored": True})

    def test_worker_claim_before_queued_callback_cannot_regress(self):
        job = self.requested()
        def claim(**kwargs):
            self.assertIsNotNone(claim_job(*kwargs["args"]))
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async", side_effect=claim):
            publish_inspection_summary_job(*identity(job))
        job.refresh_from_db()
        self.assertEqual((job.status, job.dispatch_state), ("PROCESSING", "PROCESSING"))

    def test_worker_advance_before_unknown_callback_cannot_regress(self):
        job = self.requested()
        def claim_then_raise(**kwargs):
            claim_job(*kwargs["args"])
            raise OSError()
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async", side_effect=claim_then_raise):
            publish_inspection_summary_job(*identity(job))
        job.refresh_from_db()
        self.assertEqual((job.status, job.dispatch_state), ("PROCESSING", "PROCESSING"))

    def recovery(self, state):
        job = self.requested(); old = identity(job)
        Job.objects.filter(pk=job.pk).update(dispatch_state=state,
            publication_lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async") as send:
            with self.captureOnCommitCallbacks(execute=True):
                self.assertEqual(recover_dispatches(), 1)
        job.refresh_from_db()
        self.assertEqual(job.dispatch_generation, old[1] + 1)
        self.assertNotEqual(str(job.dispatch_token), old[2])
        self.assertEqual(job.dispatch_state, "QUEUED")
        send.assert_called_once()
        self.assertEqual(generate_job(*old), {"ignored": True})
        self.assertEqual(generate_job(*identity(job))["status"], "COMPLETED")
        self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        self.assertEqual(list(storage.job_root(job.pk).glob("output/*.xlsx")), [storage.output_path(job.pk)])

    def test_abandoned_requested_recovery_fences_old_and_completes_new(self):
        self.recovery(Job.Dispatch.REQUESTED)

    def test_abandoned_publishing_recovery_fences_old_and_completes_new(self):
        self.recovery(Job.Dispatch.PUBLISHING)

    def test_unknown_recovery_fences_old_and_completes_new(self):
        self.recovery(Job.Dispatch.UNKNOWN)

    def test_live_lease_and_terminal_state_not_recovered(self):
        job = self.requested()
        self.assertEqual(recover_dispatches(), 0)
        Job.objects.filter(pk=job.pk).update(status="FAILED", dispatch_state="TERMINAL",
            publication_lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(recover_dispatches(), 0)
        self.assertIsNone(claim_job(*identity(job)))

    def test_stale_run_cannot_publish_or_overwrite_current_authority(self):
        job = self.make_job(); replacement = uuid.uuid4()
        from inspection_summary.writer import write_report
        def supersede(*args):
            write_report(*args)
            Job.objects.filter(pk=job.pk).update(run_token=replacement)
        with patch("inspection_summary.services.write_report", side_effect=supersede):
            self.assertEqual(generate_job(*identity(job)), {"ignored": True})
        job.refresh_from_db()
        self.assertEqual(job.run_token, replacement)
        self.assertFalse(storage.output_path(job.pk).exists())

    def test_input_hash_tampering_is_business_failure(self):
        job = self.make_job()
        with storage.input_path(job.pk, "raw").open("ab") as stream: stream.write(b"tampered")
        self.assertEqual(generate_job(*identity(job))["code"], "INPUT_CHANGED")

    def test_unexpected_runtime_error_persisted_and_task_reraises_original(self):
        job = self.make_job(); failure = RuntimeError("private path")
        with patch("inspection_summary.services.write_report", side_effect=failure):
            with self.assertRaises(RuntimeError) as raised:
                generate_inspection_summary.run(*identity(job))
        self.assertIs(raised.exception, failure)
        job.refresh_from_db()
        self.assertEqual(job.status, "FAILED")
        self.assertEqual(job.error_code, "GENERATION_FAILED")
        self.assertNotIn("private", str(job.error_detail))
        self.assertFalse(storage.output_path(job.pk).exists())

    def test_storage_oserror_is_failed_and_task_raises(self):
        job = self.make_job(); storage.input_path(job.pk, "raw").unlink()
        with self.assertRaises(OSError): generate_inspection_summary.run(*identity(job))
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")

    def test_persistence_failure_does_not_mask_original_exception(self):
        job = self.make_job(); failure = RuntimeError("original")
        from django.db.models.query import QuerySet
        original_update = QuerySet.update
        def fail_persistence(query, **kwargs):
            if kwargs.get("error_code") == "GENERATION_FAILED": raise OSError("database")
            return original_update(query, **kwargs)
        with patch("inspection_summary.services.write_report", side_effect=failure), patch.object(QuerySet, "update", fail_persistence):
            with self.assertRaises(RuntimeError) as raised: generate_job(*identity(job))
        self.assertIs(raised.exception, failure)

    def test_verification_invariant_failure_raises_and_removes_temporary(self):
        job = self.make_job()
        with patch("inspection_summary.services.verify_report", side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError): generate_job(*identity(job))
        self.assertFalse(storage.output_path(job.pk).exists())
        self.assertEqual(list(storage.job_root(job.pk).glob("output/*.tmp.xlsx")), [])

    def test_cleanup_terminal_once_repeat_safe_preserves_audit(self):
        job = self.make_job(); sibling = self.make_job(); generate_job(*identity(job)); self.expire(job)
        with patch("inspection_summary.services.storage.remove_job", wraps=storage.remove_job) as delete:
            self.assertEqual(cleanup_expired_jobs()["removed"], 1)
            self.assertEqual(cleanup_expired_jobs()["removed"], 0)
        delete.assert_called_once_with(job.pk)
        self.assertTrue(storage.job_root(sibling.pk).exists())
        job.refresh_from_db()
        self.assertEqual(job.status, "COMPLETED")
        self.assertIsNotNone(job.input_deleted_at); self.assertIsNotNone(job.output_deleted_at)
        self.assertIsNone(job.maintenance_token)

    def test_second_cleanup_skips_persisted_active_maintenance(self):
        job = self.make_job(); self.expire(job)
        with storage.maintenance_lock(job.pk) as locked:
            self.assertTrue(locked); first = claim_maintenance(job.pk)
            self.assertIsNotNone(first)
            self.assertEqual(cleanup_expired_jobs()["skipped"], 1)
        self.assertEqual(cleanup_expired_jobs()["skipped"], 1)
        self.assertTrue(storage.job_root(job.pk).exists())

    def test_cleanup_missing_directory_records_truthful_markers(self):
        job = self.make_job(); self.expire(job); storage.remove_job(job.pk)
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)
        job.refresh_from_db(); self.assertIsNotNone(job.input_deleted_at)

    def test_cleanup_processing_never_deleted_even_old(self):
        job = self.make_job(); claim_job(*identity(job)); self.expire(job)
        Job.objects.filter(pk=job.pk).update(processing_started_at=timezone.now() - timedelta(days=2))
        self.assertEqual(cleanup_expired_jobs()["skipped"], 1)
        self.assertTrue(storage.job_root(job.pk).exists())

    def test_cleanup_stale_maintenance_reclaimed(self):
        job = self.make_job(); self.expire(job)
        with storage.maintenance_lock(job.pk): first = claim_maintenance(job.pk)
        Job.objects.filter(pk=job.pk).update(maintenance_started_at=timezone.now() - timedelta(seconds=MAINTENANCE_LEASE_SECONDS + 1))
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)
        job.refresh_from_db(); self.assertIsNone(job.maintenance_token)
        self.assertIsNotNone(first.maintenance_token)

    def test_cleanup_tampered_stored_path_never_deletes(self):
        job = self.make_job(); sibling = self.make_job(); self.expire(job)
        Job.objects.filter(pk=job.pk).update(raw_path=storage.key(sibling.pk, "input/raw.xlsx"))
        with self.assertRaises(ValueError): cleanup_expired_jobs()
        self.assertTrue(storage.job_root(job.pk).exists()); self.assertTrue(storage.job_root(sibling.pk).exists())

    def test_cleanup_failure_keeps_lease_and_no_deletion_markers(self):
        job = self.make_job(); self.expire(job)
        with patch("inspection_summary.storage.shutil.rmtree", side_effect=PermissionError()):
            with self.assertRaises(PermissionError): cleanup_expired_jobs()
        job.refresh_from_db()
        self.assertIsNone(job.input_deleted_at); self.assertIsNotNone(job.maintenance_token)

    def test_cleanup_fenced_finalization_does_not_mark_deletion(self):
        job = self.make_job(); self.expire(job); newer = uuid.uuid4()
        def change_owner(identifier): Job.objects.filter(pk=identifier).update(maintenance_token=newer)
        with patch("inspection_summary.services.storage.remove_job", side_effect=change_owner):
            self.assertEqual(cleanup_expired_jobs()["removed"], 0)
        job.refresh_from_db(); self.assertIsNone(job.input_deleted_at)
        self.assertEqual(job.maintenance_token, newer)


    def test_stale_lease_does_not_allow_second_deleter_while_process_lock_held(self):
        job = self.make_job(); self.expire(job)
        with storage.maintenance_lock(job.pk) as locked:
            self.assertTrue(locked); owner = claim_maintenance(job.pk)
            Job.objects.filter(pk=job.pk).update(maintenance_started_at=timezone.now() - timedelta(hours=1))
            self.assertEqual(cleanup_expired_jobs()["skipped"], 1)
            self.assertTrue(storage.job_root(job.pk).exists())
            job.refresh_from_db(); self.assertEqual(job.maintenance_token, owner.maintenance_token)
        self.assertEqual(cleanup_expired_jobs()["removed"], 1)

    def test_old_publisher_callback_cannot_overwrite_recovered_dispatch(self):
        from inspection_summary.services import _dispatch_result
        job = self.requested(); old = identity(job)
        Job.objects.filter(pk=job.pk).update(publication_lease_expires_at=timezone.now() - timedelta(seconds=1))
        with patch("inspection_summary.tasks.generate_inspection_summary.apply_async"):
            with self.captureOnCommitCallbacks(execute=True): recover_dispatches()
        self.assertEqual(_dispatch_result(*old, Job.Dispatch.UNKNOWN, "late"), 0)
        job.refresh_from_db(); self.assertEqual(job.dispatch_state, "QUEUED")
        self.assertEqual(job.last_error_code, "")

    def test_temporary_cleanup_failure_does_not_mask_original_execution_failure(self):
        from pathlib import Path
        job = self.make_job(); failure = RuntimeError("original")
        with patch("inspection_summary.services.write_report", side_effect=failure), patch.object(Path, "unlink", side_effect=OSError("cleanup")):
            with self.assertRaises(RuntimeError) as raised: generate_inspection_summary.run(*identity(job))
        self.assertIs(raised.exception, failure)
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")


    def test_cleanup_oserror_after_handled_business_error_still_raises(self):
        from pathlib import Path
        job = self.make_job()
        with patch("inspection_summary.services.write_report", side_effect=WorkbookValidationError("INVALID_WORKBOOK", "known")), patch.object(Path, "unlink", side_effect=OSError("cleanup")):
            with self.assertRaises(OSError): generate_inspection_summary.run(*identity(job))
        job.refresh_from_db(); self.assertEqual(job.status, "FAILED")
        self.assertEqual(job.error_code, "INVALID_WORKBOOK")
