from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer


class ImageBatchProgressConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4401)
            return
        self.batch_id = int(self.scope["url_route"]["kwargs"]["pk"])
        snapshot = await self.snapshot(user.pk)
        if snapshot is None:
            await self.close(code=4404)
            return
        self.group_name = f"image_batch_{self.batch_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json(snapshot)

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    @database_sync_to_async
    def snapshot(self, user_id):
        from image_processor.models import FolderBatch
        from image_processor.progress import progress_payload
        batch = FolderBatch.objects.filter(pk=self.batch_id, created_by_id=user_id).first()
        return progress_payload(batch) if batch else None

    async def batch_progress(self, event):
        await self.send_json({**event, "event": "progress"})

    async def batch_complete(self, event):
        await self.send_json({**event, "event": "complete"})

    async def batch_error(self, event):
        await self.send_json({**event, "event": "error"})
