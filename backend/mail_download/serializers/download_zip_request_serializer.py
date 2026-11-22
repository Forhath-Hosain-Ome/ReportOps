
from rest_framework import serializers
from .attachment_ref_serializer import AttachmentRefSerializer


class DownloadZipRequestSerializer(serializers.Serializer):
    """POST body for DownloadZipView. `attachments` capped at 50 as a
    defensive limit -- real usage is under ~15, so this gives headroom
    without silently allowing an unbounded synchronous request. Bump this
    only as a deliberate decision tied to the sync-vs-async tradeoff in
    downloader.py, not by quietly raising the number."""
    account_id = serializers.IntegerField()
    attachments = AttachmentRefSerializer(many=True, allow_empty=False, max_length=50)