from rest_framework import serializers

from mail_download.models import DownloadHistory


class DownloadHistorySerializer(serializers.ModelSerializer):
    account_label = serializers.SerializerMethodField()

    class Meta:
        model = DownloadHistory
        fields = [
            "id", "created_by", "account_label", "filename",
            "status", "error", "created_at",
        ]
        read_only_fields = fields

    def get_account_label(self, obj):
        return obj.account.label or obj.account.email_address
