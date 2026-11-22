from rest_framework import serializers


class SearchRequestSerializer(serializers.Serializer):
    """POST body for SearchView. Mirrors the desktop app's search filters
    -- validates shape before build_query() ever sees it."""
    account_id = serializers.IntegerField()
    subject = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    report_date = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    attachment_contains = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    def validate_report_date(self, value):
        if not value:
            return value
        from datetime import datetime
        try:
            datetime.strptime(value, "%m/%d/%Y")
        except ValueError:
            raise serializers.ValidationError("report_date must be in MM/DD/YYYY format.")
        return value