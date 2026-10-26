from django.db import models
from django.contrib.auth.models import User
from .folder_batch_model import FolderBatch
from shared.models import BaseModel
from django.utils import timezone


class FolderReport(BaseModel):
    """
    One row per folder that was processed.
    Stores present DOCX authority; PDF conversion happens on demand.
    """
    batch = models.ForeignKey(
        FolderBatch, on_delete=models.CASCADE, related_name="reports"
    )

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="folder_reports",
    )

    # Which folder this came from (relative path)
    folder_name = models.CharField(max_length=512)

    # Compatibility field name: the authoritative DOCX path relative to MEDIA_ROOT.
    pdf_output_path = models.CharField(max_length=512, blank=True)

    # Status of this specific folder processing
    class Status(models.TextChoices):
        PENDING    = "PENDING",    "Pending"
        PROCESSING = "PROCESSING", "Processing"
        COMPLETED  = "COMPLETED",  "Completed"
        PARTIAL    = "PARTIAL",    "Partial"
        FAILED     = "FAILED",     "Failed"

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )

    # Error message if processing failed
    error_message = models.TextField(blank=True)

    # Number of images in the folder
    image_count = models.PositiveIntegerField(default=0)

    # Processing metadata (stored as JSON string)
    metadata = models.TextField(blank=True)
    submitted_images = models.PositiveIntegerField(default=0)
    successful_images = models.PositiveIntegerField(default=0)
    failed_images = models.PositiveIntegerField(default=0)
    current_attempt = models.ForeignKey(
        "image_processor.ProcessingAttempt", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="authoritative_reports",
    )

    class Meta:
        constraints = [models.UniqueConstraint(fields=["batch", "folder_name"], name="image_report_identity")]
        ordering = ["-created_at", "folder_name"]
        verbose_name = "Folder Report"
        verbose_name_plural = "Folder Reports"

    def __str__(self):
        return f"{self.folder_name} | {self.status} | Batch #{self.batch_id}"

    @property
    def created_by_user(self):
        """Convenience accessor — delegates to the parent batch."""
        return self.batch.created_by
