import json
import logging

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  BATCH PROGRESS CONSUMER
#  ws://host/ws/batches/<pk>/progress/
#
#  Auth: JWT passed as ?token=<access_token> in the query string.
#        The JWTAuthMiddleware (see middleware.py) resolves the user before
#        the consumer is instantiated — scope["user"] is already populated.
#
#  Channel group: "batch_<pk>"
#        The Celery task sends to this group via the channel layer.
#
#  Event shapes (JSON):
#    progress : { event, batch_id, status, stage, progress_percent,
#                 processed, total, failed, success_rate }
#    complete : { event, batch_id, status, progress_percent,
#                 processed, total, failed, success_rate,
#                 report_count, failed_details, excel_available }
#    error    : { event, batch_id, status, error_message }
# ─────────────────────────────────────────────────────────────────────────────


class BatchProgressConsumer(AsyncWebsocketConsumer):

    # ── lifecycle ──────────────────────────────────────────────────────────

    async def connect(self):
        user = self.scope.get("user")

        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            logger.warning("WS rejected — unauthenticated connection attempt.")
            await self.close(code=4401)
            return

        self.batch_pk   = self.scope["url_route"]["kwargs"]["pk"]
        self.group_name = f"batch_{self.batch_pk}"

        exists = await self._batch_exists(self.batch_pk)
        if not exists:
            logger.warning(
                "WS rejected — batch #%s not found | user: %s",
                self.batch_pk, user.username,
            )
            await self.close(code=4404)
            return

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        logger.info(
            "WS connected | batch #%s | user: %s | channel: %s",
            self.batch_pk, user.username, self.channel_name,
        )

        # Send current snapshot immediately so React renders correct initial state
        snapshot = await self._get_batch_snapshot(self.batch_pk)
        if snapshot:
            await self.send(text_data=json.dumps(snapshot))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)
            logger.info(
                "WS disconnected | batch #%s | code: %s",
                self.batch_pk, close_code,
            )

    async def receive(self, text_data=None, bytes_data=None):
        # Consumer is receive-only from the server side — React only listens.
        pass

    # ── channel layer handlers ─────────────────────────────────────────────

    async def batch_progress(self, event):
        """Handles type="batch.progress" — incremental update."""
        await self.send(text_data=json.dumps({
            "event":            "progress",
            "batch_id":         event["batch_id"],
            "status":           event["status"],
            "stage":            event.get("stage", ""),
            "progress_percent": event["progress_percent"],
            "processed":        event["processed"],
            "total":            event["total"],
            "failed":           event["failed"],
            "success_rate":     event["success_rate"],
        }))

    async def batch_complete(self, event):
        """Handles type="batch.complete" — final summary."""
        await self.send(text_data=json.dumps({
            "event":            "complete",
            "batch_id":         event["batch_id"],
            "status":           event["status"],
            "progress_percent": 100,
            "processed":        event["processed"],
            "total":            event["total"],
            "failed":           event["failed"],
            "success_rate":     event["success_rate"],
            "report_count":     event["report_count"],
            "failed_details":   event.get("failed_details", []),
            "excel_available":  event.get("excel_available", False),
        }))

    async def batch_error(self, event):
        """Handles type="batch.error" — task crash."""
        await self.send(text_data=json.dumps({
            "event":         "error",
            "batch_id":      event["batch_id"],
            "status":        "FAILED",
            "error_message": event.get("error_message", "Unknown error"),
        }))

    # ── DB helpers (sync → async) ──────────────────────────────────────────

    @database_sync_to_async
    def _batch_exists(self, pk):
        from puma_summary.models import InspectionBatch
        return InspectionBatch.objects.filter(pk=pk, created_by=self.scope["user"]).exists()

    @database_sync_to_async
    def _get_batch_snapshot(self, pk):
        from django.conf import settings
        from puma_summary.models import InspectionBatch
        from puma_summary.serializers import BatchFailedPDFSerializer
        batch = InspectionBatch.objects.filter(pk=pk, created_by=self.scope["user"]).first()
        if batch is None:
            return None
        done = batch.status in ("COMPLETED", "PARTIAL", "FAILED")
        base = {
            "batch_id": batch.pk, "status": batch.status,
            "progress_percent": batch.progress_percent,
            "processed": batch.processed_pdfs, "total": batch.total_pdfs,
            "failed": batch.failed_pdfs, "success_rate": batch.success_rate,
        }
        if done:
            return {**base, "event": "complete", "report_count": batch.reports.count(),
                    "failed_details": BatchFailedPDFSerializer(batch.batch_failed_pdfs.all(), many=True).data,
                    "excel_available": bool(batch.excel_report_path and
                        (settings.BASE_DIR / "media" / batch.excel_report_path).exists())}
        return {**base, "event": "progress", "stage": ""}
