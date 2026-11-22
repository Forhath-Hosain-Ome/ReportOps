from rest_framework import serializers

from mail_download.models import SearchJob

class SearchJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchJob
        fields = ["id", "account", "query", "status", "progress_percent",
                  "stage", "result", "error", "created_at", "updated_at"]
        read_only_fields = fields