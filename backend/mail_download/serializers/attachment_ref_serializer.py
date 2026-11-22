from rest_framework import serializers


class AttachmentRefSerializer(serializers.Serializer):
    """
    Shape of one attachment reference as it travels:
      search_task result -> WebSocket payload -> frontend selection
      -> DownloadZipRequestSerializer.attachments -> downloader.download_as_zip()

    Used to validate INCOMING attachment refs (e.g. the list the frontend
    posts back for a zip download) -- the search_task itself constructs
    these as plain dicts on the way out, since Celery results need to be
    JSON-serializable and don't need DRF validation on that side.
    """
    message_id = serializers.CharField(max_length=64)
    attachment_id = serializers.CharField(max_length=128)
    filename = serializers.CharField(max_length=255)
    date = serializers.CharField(max_length=64, required=False, allow_blank=True)