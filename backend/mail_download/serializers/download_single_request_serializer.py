from rest_framework import serializers


class DownloadSingleRequestSerializer(serializers.Serializer):
    """Query params for DownloadSingleView -- validated instead of pulled
    raw from request.GET."""
    account_id = serializers.IntegerField()
    message_id = serializers.CharField(max_length=64)
    attachment_id = serializers.CharField(max_length=128)
    filename = serializers.CharField(max_length=255)