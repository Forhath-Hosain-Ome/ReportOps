"""A current delivery cannot disappear merely because execution is coordinated."""
import os
import time
import uuid
from unittest import skipUnless
from unittest.mock import patch

from celery.exceptions import Reject, Retry
from django.db import connection
from django.test import TransactionTestCase

from image_processor import lifecycle
from image_processor.coordination import batch_lock
from image_processor.models import FolderBatch, ImageOutcome, ProcessingAttempt
from image_processor.tasks import process_folder_task
from image_processor.tests.test_reliability import ReliabilityFixture


class LockDeliveryTests(ReliabilityFixture):
    def test_current_busy_delivery_retries_instead_of_completing(self):
        batch = self.make_batch()
        with batch_lock(batch.pk), patch.object(process_folder_task, "retry", side_effect=Retry()) as retry:
            with self.assertRaises(Retry):
                self.run_worker(batch)
        self.assertEqual(retry.call_args.kwargs["countdown"], 60)
        self.assertEqual(retry.call_args.kwargs["max_retries"], 2)
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.dispatch_state), ("PENDING", "QUEUED"))
        self.assertIsNone(batch.active_run_token)
        self.assertFalse(ImageOutcome.objects.exists())

    def test_redelivery_then_duplicate_produces_one_attempt_artifact_and_outcome(self):
        batch = self.make_batch()
        with batch_lock(batch.pk), patch.object(process_folder_task, "retry", side_effect=Retry()):
            with self.assertRaises(Retry):
                self.run_worker(batch)
        self.assertEqual(self.run_worker(batch)["status"], "COMPLETED")
        self.assertIn("ignored", self.run_worker(batch))
        self.assertEqual(ProcessingAttempt.objects.filter(report__batch=batch).count(), 1)
        self.assertEqual(ImageOutcome.objects.filter(attempt__report__batch=batch).count(), 1)
        self.assertEqual(len(list((self.output / str(batch.pk)).rglob("*.docx"))), 1)

    def test_busy_stale_generation_or_token_is_discarded_without_retry(self):
        batch = self.make_batch()
        for generation, token in ((0, batch.dispatch_token), (batch.dispatch_generation, uuid.uuid4()),
                                  (batch.dispatch_generation, "not-a-uuid")):
            with batch_lock(batch.pk), patch.object(process_folder_task, "retry") as retry:
                result = process_folder_task.run(batch.pk, batch.source_folder,
                    dispatch_generation=generation, dispatch_token=str(token))
            self.assertIn("ignored", result)
            retry.assert_not_called()
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.dispatch_state), ("PENDING", "QUEUED"))

    def test_busy_duplicate_of_an_active_run_does_not_change_ownership(self):
        batch = self.make_batch()
        with batch_lock(batch.pk):
            owned = lifecycle.claim_execution(batch.pk, batch.dispatch_generation, batch.dispatch_token)
            with patch.object(process_folder_task, "retry") as retry:
                self.assertIn("ignored", self.run_worker(batch))
            retry.assert_not_called()
        batch.refresh_from_db()
        self.assertEqual(batch.active_run_token, owned.active_run_token)
        self.assertEqual(batch.status, "PROCESSING")

    def test_backoff_is_bounded(self):
        batch = self.make_batch()
        process_folder_task.push_request(retries=1)
        try:
            with batch_lock(batch.pk), patch.object(process_folder_task, "retry", side_effect=Retry()) as retry:
                with self.assertRaises(Retry):
                    self.run_worker(batch)
        finally:
            process_folder_task.pop_request()
        self.assertEqual(retry.call_args.kwargs["countdown"], 120)
        self.assertEqual(retry.call_args.kwargs["max_retries"], 2)
        self.assertTrue(process_folder_task.acks_late)

    def test_exhaustion_is_an_explicit_recoverable_dispatch_failure(self):
        batch = self.make_batch()
        process_folder_task.push_request(retries=2)
        try:
            with batch_lock(batch.pk), self.assertRaisesRegex(RuntimeError, "lock retries exhausted"):
                self.run_worker(batch)
        finally:
            process_folder_task.pop_request()
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.dispatch_state), ("PENDING", "FAILED"))
        self.assertEqual(batch.last_error_code, "DISPATCH_LOCK_RETRY_EXHAUSTED")
        self.assertEqual(batch.reports.get().attempts.get().status, "QUEUED")
        self.assertIsNone(batch.active_run_token)
        self.assertFalse(ImageOutcome.objects.exists())
        with patch("image_processor.lifecycle.publish_dispatch"):
            response = self.client.post(f"/image/folder/batches/{batch.pk}/retry/", {}, format="json")
        self.assertEqual(response.status_code, 202)
        batch.refresh_from_db()
        self.assertEqual(batch.dispatch_generation, 2)
        self.publish(batch)
        self.assertEqual(self.run_worker(batch)["status"], "COMPLETED")

    def test_retry_publish_failure_is_explicitly_recoverable(self):
        batch = self.make_batch()
        with batch_lock(batch.pk), patch.object(process_folder_task, "retry", side_effect=Reject("broker failure", requeue=False)):
            with self.assertRaises(Reject):
                self.run_worker(batch)
        batch.refresh_from_db()
        self.assertEqual(batch.dispatch_state, "FAILED")
        self.assertEqual(batch.last_error_code, "DISPATCH_LOCK_RETRY_PUBLISH_FAILED")
        self.assertFalse(ImageOutcome.objects.exists())

    def test_failure_compare_and_swap_cannot_overwrite_new_dispatch_or_run(self):
        batch = self.make_batch()
        old_generation, old_token = batch.dispatch_generation, batch.dispatch_token
        FolderBatch.objects.filter(pk=batch.pk).update(dispatch_generation=old_generation+1, dispatch_token=uuid.uuid4())
        self.assertFalse(lifecycle.fail_unclaimed_dispatch(batch.pk, old_generation, old_token, "TEST"))
        batch.refresh_from_db()
        owned = lifecycle.claim_execution(batch.pk, batch.dispatch_generation, batch.dispatch_token)
        self.assertIsNotNone(owned)
        self.assertFalse(lifecycle.fail_unclaimed_dispatch(batch.pk, batch.dispatch_generation, batch.dispatch_token, "TEST"))
        batch.refresh_from_db()
        self.assertEqual(batch.active_run_token, owned.active_run_token)
        self.assertEqual(batch.dispatch_state, "PROCESSING")

    def test_publishing_failure_preserves_maintenance_and_rejects_late_publisher(self):
        batch = self.make_batch()
        maintenance = uuid.uuid4()
        FolderBatch.objects.filter(pk=batch.pk).update(dispatch_state="PUBLISHING", maintenance_token=maintenance)
        self.assertTrue(lifecycle.dispatch_needs_delivery(batch.pk, batch.dispatch_generation, batch.dispatch_token))
        self.assertTrue(lifecycle.fail_unclaimed_dispatch(batch.pk, batch.dispatch_generation, batch.dispatch_token,
                                                        "DISPATCH_LOCK_RETRY_EXHAUSTED"))
        lifecycle._publication_result(batch.pk, batch.dispatch_generation, batch.dispatch_token, "QUEUED", "", "late")
        batch.refresh_from_db()
        self.assertEqual(batch.dispatch_state, "FAILED")
        self.assertEqual(batch.maintenance_token, maintenance)
        self.assertIsNone(batch.active_run_token)


@skipUnless(connection.vendor == "postgresql" and os.environ.get("IMAGE_TEST_BROKER_URL", "").startswith("redis://"),
            "Requires PostgreSQL and an explicitly isolated Redis broker")
class RedisLockDeliveryTests(TransactionTestCase):
    setUp = ReliabilityFixture.setUp
    make_batch = ReliabilityFixture.make_batch
    publish = ReliabilityFixture.publish

    def test_real_redis_contention_retries_then_processes_once(self):
        from celery import Celery
        from celery.contrib.testing.worker import start_worker

        batch = self.make_batch()
        FolderBatch.objects.filter(pk=batch.pk).update(dispatch_state="REQUESTED")
        queue = "image_lock_test_" + uuid.uuid4().hex
        app = Celery("image_lock_delivery_test", broker=os.environ["IMAGE_TEST_BROKER_URL"], backend="cache+memory://")
        app.conf.update(task_default_queue=queue, worker_prefetch_multiplier=1,
                        task_routes={"image_processor.process_defect_docx": {"queue": queue}})
        task = app.tasks["image_processor.process_defect_docx"]
        self.addCleanup(app.close)
        def delete_queue():
            with app.connection_for_write() as broker:
                broker.channel().queue_delete(queue)
        self.addCleanup(delete_queue)
        with start_worker(app, pool="solo", perform_ping_check=False, queues=[queue], shutdown_timeout=20):
            with batch_lock(batch.pk) as acquired:
                self.assertTrue(acquired)
                lifecycle.publish_dispatch(batch.pk, batch.dispatch_generation, batch.dispatch_token, task)
                batch.refresh_from_db()
                result = app.AsyncResult(batch.celery_task_id)
                deadline = time.monotonic() + 15
                while result.state != "RETRY" and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertEqual(result.state, "RETRY")
                batch.refresh_from_db()
                self.assertEqual((batch.status, batch.dispatch_state), ("PENDING", "QUEUED"))
                self.assertFalse(ImageOutcome.objects.filter(attempt__report__batch=batch).exists())
            # Use the real production 60-second retry interval, not a patched retry.
            completed = result.get(timeout=90)
            self.assertEqual(completed["status"], "COMPLETED")
            duplicate = task.apply_async(args=[batch.pk, batch.source_folder], kwargs={
                "dispatch_generation": batch.dispatch_generation, "dispatch_token": str(batch.dispatch_token)})
            self.assertIn("ignored", duplicate.get(timeout=15))
            # Exhaustion is also a real worker failure, with an immediately
            # recoverable dispatch rather than invented processing outcomes.
            exhausted = self.make_batch()
            with batch_lock(exhausted.pk):
                failure = task.apply_async(args=[exhausted.pk, exhausted.source_folder], kwargs={
                    "dispatch_generation": exhausted.dispatch_generation,
                    "dispatch_token": str(exhausted.dispatch_token)}, retries=2)
                error = failure.get(timeout=15, propagate=False)
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(failure.state, "FAILURE")
            exhausted.refresh_from_db()
            self.assertEqual((exhausted.status, exhausted.dispatch_state), ("PENDING", "FAILED"))
            self.assertEqual(exhausted.last_error_code, "DISPATCH_LOCK_RETRY_EXHAUSTED")
            self.assertFalse(ImageOutcome.objects.filter(attempt__report__batch=exhausted).exists())
            with patch("image_processor.lifecycle.publish_dispatch"):
                recovered = lifecycle.retry_batch(exhausted.pk, self.user)
            lifecycle.publish_dispatch(recovered.pk, recovered.dispatch_generation, recovered.dispatch_token, task)
            recovered.refresh_from_db()
            self.assertEqual(app.AsyncResult(recovered.celery_task_id).get(timeout=15)["status"], "COMPLETED")
            recovered.refresh_from_db()
            self.assertEqual((recovered.status, recovered.dispatch_state), ("COMPLETED", "TERMINAL"))
            self.assertEqual(recovered.dispatch_generation, 2)
            self.assertEqual(ProcessingAttempt.objects.filter(report__batch=recovered).count(), 2)
            self.assertEqual(ImageOutcome.objects.filter(attempt__report__batch=recovered).count(), 1)
        batch.refresh_from_db()
        self.assertEqual((batch.status, batch.dispatch_state), ("COMPLETED", "TERMINAL"))
        self.assertIsNone(batch.active_run_token)
        self.assertEqual(ProcessingAttempt.objects.filter(report__batch=batch).count(), 1)
        self.assertEqual(ImageOutcome.objects.filter(attempt__report__batch=batch).count(), 1)
        self.assertEqual(len(list((self.output / str(batch.pk)).rglob("*.docx"))), 1)
