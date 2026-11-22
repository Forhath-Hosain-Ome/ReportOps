"""Abandoned publication recovery and retention, through existing boundaries."""
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.utils import timezone

from image_processor.coordination import batch_lock
from image_processor.models import FolderBatch, ProcessingAttempt
from image_processor.retention_paths import output_directory_for_batch
from image_processor.tasks.cleanup_task import cleanup_temp_dirs_task
from image_processor.tests.test_reliability import ReliabilityFixture


class AbandonedPublicationTests(ReliabilityFixture):
    def pending_publication(self, state, *, retention_expired=False, lease_expired=True):
        batch = self.make_batch()
        FolderBatch.objects.filter(pk=batch.pk).update(
            status="PENDING", dispatch_state=state,
            lease_expires_at=timezone.now() + timedelta(minutes=-1 if lease_expired else 10),
            expires_at=timezone.now() + timedelta(hours=-1 if retention_expired else 24),
        )
        ProcessingAttempt.objects.filter(report__batch=batch).update(status="REQUESTED")
        batch.refresh_from_db()
        return batch

    def assert_expired_recovery(self, state):
        batch = self.pending_publication(state)
        old_token = batch.dispatch_token
        old_attempt = batch.reports.get().attempts.get()
        with patch("image_processor.lifecycle.publish_dispatch") as publish:
            response = self.client.post(f"/image/folder/batches/{batch.pk}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 202, response.data)
        batch.refresh_from_db()
        old_attempt.refresh_from_db()
        self.assertEqual(batch.dispatch_generation, 2)
        self.assertNotEqual(batch.dispatch_token, old_token)
        self.assertEqual(old_attempt.status, "FAILED")
        self.assertEqual(old_attempt.error_code, "DISPATCH_SUPERSEDED")
        self.assertEqual(batch.reports.get().attempts.count(), 2)
        publish.assert_called_once_with(batch.pk, 2, batch.dispatch_token)
        self.publish(batch)
        self.assertEqual(self.run_worker(batch)["status"], "COMPLETED")

    def test_expired_requested_publication_recovers_without_reupload(self):
        self.assert_expired_recovery("REQUESTED")

    def test_expired_publishing_publication_recovers_without_reupload(self):
        self.assert_expired_recovery("PUBLISHING")

    def test_unrecovered_expired_publications_are_cleaned_with_historical_dispatch_identity(self):
        for state in ("REQUESTED", "PUBLISHING"):
            with self.subTest(state=state):
                batch = self.pending_publication(state, retention_expired=True)
                token = batch.dispatch_token
                output = output_directory_for_batch(batch)
                output.mkdir(parents=True)
                (output / "uncommitted.docx").write_bytes(b"uncommitted output")
                sibling = self.staging / str(uuid.uuid4())
                sibling.mkdir()
                counts = cleanup_temp_dirs_task()
                batch.refresh_from_db()
                self.assertEqual(counts["removed"], 2)
                self.assertEqual(counts["errors"], 0)
                self.assertFalse(Path(batch.source_folder).exists())
                self.assertFalse(output.exists())
                self.assertTrue(sibling.exists())
                self.assertEqual(batch.dispatch_token, token)
                self.assertIsNotNone(batch.source_deleted_at)
                self.assertIsNotNone(batch.output_deleted_at)
                self.assertIsNone(batch.maintenance_token)

    def test_live_or_missing_publication_lease_blocks_recovery_and_cleanup(self):
        for state in ("REQUESTED", "PUBLISHING"):
            for missing in (False, True):
                with self.subTest(state=state, missing=missing):
                    batch = self.pending_publication(state, lease_expired=False)
                    if missing:
                        FolderBatch.objects.filter(pk=batch.pk).update(lease_expires_at=None)
                    response = self.client.post(f"/image/folder/batches/{batch.pk}/retry/", {}, format="json")
                    self.assertEqual(response.status_code, 409)
                    self.assertEqual(response.data["code"], "DISPATCH_ACTIVE")
                    FolderBatch.objects.filter(pk=batch.pk).update(expires_at=timezone.now() - timedelta(hours=1))
                    with patch("image_processor.tasks.cleanup_task.shutil.rmtree") as remove:
                        cleanup_temp_dirs_task()
                    remove.assert_not_called()
                    batch.refresh_from_db()
                    self.assertTrue(Path(batch.source_folder).is_dir())
                    self.assertIsNone(batch.source_deleted_at)

    def test_publication_cleanup_preserves_execution_and_retention_guards(self):
        for state in ("REQUESTED", "PUBLISHING"):
            batch = self.pending_publication(state, retention_expired=True)
            for field in ("active_run_token", "maintenance_token"):
                FolderBatch.objects.filter(pk=batch.pk).update(**{field: uuid.uuid4()})
                with patch("image_processor.tasks.cleanup_task.shutil.rmtree") as remove:
                    cleanup_temp_dirs_task()
                remove.assert_not_called()
                FolderBatch.objects.filter(pk=batch.pk).update(**{field: None})
            with batch_lock(batch.pk), patch("image_processor.tasks.cleanup_task.shutil.rmtree") as remove:
                cleanup_temp_dirs_task()
            remove.assert_not_called()
            FolderBatch.objects.filter(pk=batch.pk).update(expires_at=timezone.now() + timedelta(hours=1))
            with patch("image_processor.tasks.cleanup_task.shutil.rmtree") as remove:
                cleanup_temp_dirs_task()
            remove.assert_not_called()
            self.assertTrue(Path(batch.source_folder).is_dir())

    def test_abandoned_publication_deletion_failure_releases_maintenance_ownership(self):
        for state in ("REQUESTED", "PUBLISHING"):
            with self.subTest(state=state):
                batch = self.pending_publication(state, retention_expired=True)
                output_directory_for_batch(batch).mkdir(parents=True)
                with patch("image_processor.tasks.cleanup_task.shutil.rmtree", side_effect=PermissionError()):
                    counts = cleanup_temp_dirs_task()
                batch.refresh_from_db()
                self.assertEqual(counts["removed"], 0)
                self.assertGreaterEqual(counts["errors"], 2)
                self.assertIsNone(batch.source_deleted_at)
                self.assertIsNone(batch.output_deleted_at)
                self.assertIsNone(batch.maintenance_token)
