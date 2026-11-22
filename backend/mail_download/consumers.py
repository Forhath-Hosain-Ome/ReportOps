"""
mailfetch/consumers.py

Matches MailDownloadeConsumer's existing shape exactly: PK-routed,
existence check on connect, snapshot sent immediately, group name
"{app}_job_{pk}", event handler methods named "{app}_progress" /
"{app}_complete" matching the `type` used in group_send.
"""
import json

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.contrib.auth.models import AnonymousUser


class SearchJobConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        user = self.scope.get("user")
        if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.job_pk = self.scope["url_route"]["kwargs"]["pk"]
        self.group_name = f"mailfetch_job_{self.job_pk}"
        exists = await self._job_exists(self.job_pk)
        if not exists:
            await self.close(code=4404)
            return
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        snapshot = await self._get_snapshot(self.job_pk)
        if snapshot:
            await self.send(text_data=json.dumps(snapshot))

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def mailfetch_progress(self, event):
        await self.send(text_data=json.dumps({
            "event": "progress", "job_id": event["job_id"],
            "status": event["status"], "stage": event.get("stage", ""),
            "progress_percent": event.get("progress_percent", 0),
        }))

    async def mailfetch_complete(self, event):
        await self.send(text_data=json.dumps({
            "event": "complete", "job_id": event["job_id"],
            "status": event["status"], "progress_percent": 100,
            "result": event.get("result"),
        }))

    @database_sync_to_async
    def _job_exists(self, pk):
        from mail_download.models import SearchJob
        return SearchJob.objects.filter(pk=pk).exists()

    @database_sync_to_async
    def _get_snapshot(self, pk):
        from mail_download.models import SearchJob
        try:
            job = SearchJob.objects.get(pk=pk)
        except SearchJob.DoesNotExist:
            return None
        done = job.status in (SearchJob.Status.DONE, SearchJob.Status.FAILED)
        base = {"job_id": job.pk, "status": job.status, "query": job.query}
        if done:
            return {
                **base,
                "event": "complete" if job.status == SearchJob.Status.DONE else "error",
                "progress_percent": 100,
                "result": job.result,
                "error": job.error,
            }
        return {
            **base,
            "event": "progress",
            "stage": job.stage,
            "progress_percent": job.progress_percent,
        }
