from pathlib import Path

from django.utils import timezone
from rest_framework import serializers

from . import storage
from .models import InspectionSummaryJob
from .workbook_security import MAX_WORKBOOK_BYTES, WorkbookValidationError, validate_workbook


class JobUploadSerializer(serializers.Serializer):
    inspection_summary = serializers.FileField(max_length=255, allow_empty_file=False, required=False)
    raw = serializers.FileField(max_length=255, allow_empty_file=False, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one Inspection Summary or 100% workbook is required.")
        for kind, uploaded in attrs.items():
            if Path(uploaded.name).suffix.lower() != ".xlsx" or uploaded.size > MAX_WORKBOOK_BYTES:
                raise serializers.ValidationError({kind: "Use a nonempty .xlsx workbook no larger than 50 MB."})
            try:
                validate_workbook(uploaded, input=kind)
            except WorkbookValidationError as exc:
                raise serializers.ValidationError({kind: {"code": exc.code, **exc.detail}}) from exc
        return attrs


class JobSerializer(serializers.ModelSerializer):
    job_id = serializers.UUIDField(source="pk")
    error = serializers.SerializerMethodField()
    download_ready = serializers.SerializerMethodField()

    class Meta:
        model = InspectionSummaryJob
        fields = ["job_id", "status", "stage", "sheet_manifest", "error", "download_ready", "expires_at"]

    def get_error(self, obj):
        return {"code": obj.error_code, **obj.error_detail} if obj.error_code else None

    def get_download_ready(self, obj):
        if (obj.status != obj.Status.COMPLETED or obj.expires_at <= timezone.now()
                or obj.output_deleted_at or obj.output_path != storage.key(obj.pk, "output/Result.xlsx")):
            return False
        try:
            return storage.resolve_stored_path(obj.output_path).is_file()
        except (ValueError, OSError):
            return False
