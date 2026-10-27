import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection, connections
from django.test import TransactionTestCase

from image_processor.coordination import batch_lock
from image_processor.models import ProcessingAttempt
from image_processor.routing import websocket_urlpatterns
from image_processor.tests.test_reliability import ReliabilityFixture
from puma_summary.models import InspectionBatch
from puma_summary.routing import websocket_urlpatterns as puma_routes


class IntegrationTests(TransactionTestCase):
    setUp = ReliabilityFixture.setUp
    make_batch = ReliabilityFixture.make_batch
    publish = ReliabilityFixture.publish
    run_worker = ReliabilityFixture.run_worker

    def test_retention_deletes_without_holding_a_database_transaction(self):
        import shutil
        from datetime import timedelta
        from django.utils import timezone
        from image_processor.models import FolderBatch
        from image_processor.tasks.cleanup_task import cleanup_temp_dirs_task
        batch = self.make_batch()
        self.run_worker(batch)
        FolderBatch.objects.filter(pk=batch.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        remove = shutil.rmtree
        def delete(path):
            self.assertFalse(connection.in_atomic_block)
            self.assertIsNotNone(FolderBatch.objects.get(pk=batch.pk).maintenance_token)
            remove(path)
        with patch("image_processor.tasks.cleanup_task.shutil.rmtree", side_effect=delete):
            self.assertEqual(cleanup_temp_dirs_task()["removed"], 2)

    def test_registered_task_processes_real_queued_dispatch(self):
        from celery import Celery
        from celery.contrib.testing.worker import start_worker
        from image_processor.lifecycle import publish_dispatch
        from image_processor.models import FolderBatch
        from image_processor.tasks import process_defect_docx_task, process_folder_task
        self.assertIs(process_defect_docx_task, process_folder_task)
        batch = self.make_batch()
        FolderBatch.objects.filter(pk=batch.pk).update(dispatch_state="REQUESTED")
        app = Celery("image_lifecycle_test", broker=os.environ.get("IMAGE_TEST_BROKER_URL", "memory://"), backend="cache+memory://")
        app.conf.task_default_queue = "image_processor"
        task = app.tasks["image_processor.process_defect_docx"]
        with start_worker(app, pool="solo", perform_ping_check=False, queues=["image_processor"]):
            publish_dispatch(batch.pk, batch.dispatch_generation, batch.dispatch_token, task)
            batch.refresh_from_db()
            result = app.AsyncResult(batch.celery_task_id).get(timeout=15)
        self.assertEqual(result["status"], "COMPLETED")

    def test_websocket_owner_authentication_numeric_collision_and_snapshot(self):
        batch = self.make_batch()
        InspectionBatch.objects.create(pk=batch.pk, created_by=self.user, total_pdfs=99)
        other = User.objects.create_user(username="other")
        router = URLRouter(websocket_urlpatterns + puma_routes)
        async def exercise():
            for user, code in ((AnonymousUser(), 4401), (other, 4404)):
                denied = WebsocketCommunicator(router, f"/ws/image/batches/{batch.pk}/progress/")
                denied.scope["user"] = user
                connected, close_code = await denied.connect()
                self.assertFalse(connected)
                self.assertEqual(close_code, code)
                await denied.disconnect()
            image = WebsocketCommunicator(router, f"/ws/image/batches/{batch.pk}/progress/")
            image.scope["user"] = self.user
            puma = WebsocketCommunicator(router, f"/ws/batches/{batch.pk}/progress/")
            puma.scope["user"] = self.user
            self.assertTrue((await image.connect())[0])
            self.assertTrue((await puma.connect())[0])
            self.assertEqual((await image.receive_json_from())["total"], 1)
            self.assertEqual((await puma.receive_json_from())["total"], 99)
            await get_channel_layer().group_send(f"batch_{batch.pk}", {
                "type": "batch.progress", "batch_id": batch.pk, "status": "PROCESSING",
                "processed": 0, "total": 99, "failed": 0, "progress_percent": 0, "success_rate": 0,
            })
            self.assertEqual((await puma.receive_json_from())["total"], 99)
            self.assertTrue(await image.receive_nothing(timeout=0.05))
            await image.disconnect()
            await puma.disconnect()
        async_to_sync(exercise)()

    @skipUnless(connection.vendor == "postgresql", "Requires independent PostgreSQL sessions")
    def test_advisory_lock_blocks_other_sessions_and_duplicate_worker(self):
        batch = self.make_batch()
        def other_session():
            try:
                with batch_lock(batch.pk) as acquired:
                    return acquired
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with batch_lock(batch.pk) as acquired:
                self.assertTrue(acquired)
                self.assertFalse(pool.submit(other_session).result(timeout=5))
                self.assertIn("ignored", self.run_worker(batch))
            self.assertTrue(pool.submit(other_session).result(timeout=5))
        self.run_worker(batch)
        self.assertEqual(ProcessingAttempt.objects.filter(report__batch=batch).count(), 1)

    @skipUnless(connection.vendor == "postgresql", "Requires PostgreSQL session fencing")
    def test_lost_coordination_session_fences_terminal_writes(self):
        from image_processor.lifecycle import claim_execution, fail_execution
        from image_processor.coordination import StaleExecution
        batch = self.make_batch()
        with batch_lock(batch.pk):
            owned = claim_execution(batch.pk, batch.dispatch_generation, batch.dispatch_token)
            with patch.object(connection, "_image_batch_locks", {batch.pk: -1}):
                with self.assertRaises(StaleExecution):
                    fail_execution(owned)


class MigrationSafetyTests(TransactionTestCase):
    def test_duplicate_preflight_blocks_constraint_without_rewriting_rows(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        executor.migrate([("image_processor", "0002_reliability")])
        apps = executor.loader.project_state([("image_processor", "0002_reliability")]).apps
        Batch = apps.get_model("image_processor", "FolderBatch")
        Report = apps.get_model("image_processor", "FolderReport")
        batch = Batch.objects.create()
        first = Report.objects.create(batch=batch, folder_name="duplicate")
        extra = Report.objects.create(batch=batch, folder_name="duplicate")
        try:
            with self.assertRaisesRegex(RuntimeError, "reviewed reconciliation"):
                MigrationExecutor(connection).migrate([("image_processor", "0003_report_identity")])
            self.assertEqual(Report.objects.filter(batch=batch).count(), 2)
            self.assertTrue(Report.objects.filter(pk=first.pk).exists())
        finally:
            extra.delete()
            MigrationExecutor(connection).migrate([("image_processor", "0003_report_identity")])
