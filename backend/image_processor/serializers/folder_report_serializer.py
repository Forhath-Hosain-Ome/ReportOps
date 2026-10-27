from rest_framework import serializers
from image_processor.models import FolderReport
from image_processor.models import ProcessingAttempt, ImageOutcome


class ImageOutcomeSerializer(serializers.ModelSerializer):
    original_filename = serializers.CharField(source="image.original_filename")
    relative_path = serializers.CharField(source="image.relative_path")

    class Meta:
        model = ImageOutcome
        fields = ["id", "original_filename", "relative_path", "status", "stage", "failure_reason"]


class AttemptSerializer(serializers.ModelSerializer):
    outcomes = ImageOutcomeSerializer(many=True, read_only=True)
    folder_name = serializers.CharField(source="report.folder_name")
    reason = serializers.CharField(source="error_message")

    class Meta:
        model = ProcessingAttempt
        fields = ["id", "report_id", "folder_name", "generation", "status", "stage", "error_code",
                  "reason", "output_path", "created_at", "finished_at", "outcomes"]


# ─────────────────────────────────────────────────────────────────────────────
#  FOLDER REPORT
# ─────────────────────────────────────────────────────────────────────────────

class FolderReportSerializer(serializers.ModelSerializer):
    """
    Full folder report detail.
    """
    # Resolved from batch FK — read-only convenience field
    created_by = serializers.SerializerMethodField()
    attempts = AttemptSerializer(many=True, read_only=True)

    class Meta:
        model  = FolderReport
        fields = [
            "id",
            "batch",
            "folder_name",
            "pdf_output_path",
            "status",
            "error_message",
            "image_count",
            "metadata",
            "submitted_images", "successful_images", "failed_images", "current_attempt_id", "attempts",
            "created_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}


class FolderReportListSerializer(serializers.ModelSerializer):
    """
    Lightweight version for list endpoints — omits metadata
    to keep response size small when paginating 50+ rows.
    """
    created_by = serializers.SerializerMethodField()

    class Meta:
        model  = FolderReport
        fields = [
            "id",
            "batch",
            "folder_name",
            "pdf_output_path",
            "status",
            "error_message",
            "image_count",
            "submitted_images", "successful_images", "failed_images", "current_attempt_id",
            "created_by",
            "created_at",
        ]
        read_only_fields = fields

    def get_created_by(self, obj):
        user = obj.batch.created_by
        if user is None:
            return None
        return {"id": user.pk, "username": user.username}
