import uuid

from django.conf import settings
from django.db import models


class InspectionSummaryJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    class Dispatch(models.TextChoices):
        REQUESTED = "REQUESTED", "Requested"
        PUBLISHING = "PUBLISHING", "Publishing"
        QUEUED = "QUEUED", "Queued"
        UNKNOWN = "UNKNOWN", "Unknown"
        PROCESSING = "PROCESSING", "Processing"
        TERMINAL = "TERMINAL", "Terminal"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="inspection_summary_jobs")
    status = models.CharField(max_length=20, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    stage = models.CharField(max_length=64, blank=True)
    inspection_summary_name = models.CharField(max_length=255)
    raw_name = models.CharField(max_length=255)
    inspection_summary_path = models.CharField(max_length=512)
    raw_path = models.CharField(max_length=512)
    output_path = models.CharField(max_length=512, blank=True)
    inspection_summary_sha256 = models.CharField(max_length=64)
    raw_sha256 = models.CharField(max_length=64)
    sheet_manifest = models.JSONField(default=list)
    error_code = models.CharField(max_length=64, blank=True)
    error_detail = models.JSONField(default=dict)
    task_id = models.CharField(max_length=255, blank=True, db_index=True)
    run_token = models.UUIDField(null=True, blank=True)
    dispatch_generation = models.PositiveIntegerField(default=1)
    dispatch_token = models.UUIDField(default=uuid.uuid4)
    dispatch_state = models.CharField(max_length=20, choices=Dispatch.choices, default=Dispatch.REQUESTED)
    publication_lease_expires_at = models.DateTimeField(null=True, blank=True)
    last_error_code = models.CharField(max_length=64, blank=True)
    maintenance_token = models.UUIDField(null=True, blank=True)
    maintenance_started_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_lease_expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    processing_finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)
    input_deleted_at = models.DateTimeField(null=True, blank=True)
    output_deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "-created_at"], name="insp_sum_owner_created"),
            models.Index(fields=["status", "expires_at"], name="insp_sum_status_expiry"),
        ]
