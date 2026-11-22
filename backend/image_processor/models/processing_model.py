import uuid
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class OperationalSettings(models.Model):
    # A single stable row; callers never accept a client-selected settings id.
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    retention_hours = models.PositiveIntegerField(default=24, validators=[MinValueValidator(1), MaxValueValidator(720)])
    image_width_px = models.PositiveIntegerField(default=325, validators=[MinValueValidator(32), MaxValueValidator(4096)])
    image_height_px = models.PositiveIntegerField(default=265, validators=[MinValueValidator(32), MaxValueValidator(4096)])

    @classmethod
    def snapshot(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return {name: getattr(obj, name) for name in ("retention_hours", "image_width_px", "image_height_px")}


class FolderImage(models.Model):
    report = models.ForeignKey("image_processor.FolderReport", on_delete=models.CASCADE, related_name="images")
    relative_path = models.CharField(max_length=1024)
    original_filename = models.CharField(max_length=512)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["report", "relative_path"], name="image_manifest_identity")]
        ordering = ["relative_path"]


class ProcessingAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report = models.ForeignKey("image_processor.FolderReport", on_delete=models.CASCADE, related_name="attempts")
    generation = models.PositiveIntegerField()
    dispatch_token = models.UUIDField()
    run_token = models.UUIDField(null=True)
    status = models.CharField(max_length=20, default="REQUESTED")
    stage = models.CharField(max_length=40, blank=True)
    error_code = models.CharField(max_length=64, blank=True)
    error_message = models.TextField(blank=True)
    output_path = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["report", "generation"], name="image_attempt_generation")]
        ordering = ["created_at"]


class ImageOutcome(models.Model):
    attempt = models.ForeignKey(ProcessingAttempt, on_delete=models.CASCADE, related_name="outcomes")
    image = models.ForeignKey(FolderImage, on_delete=models.CASCADE, related_name="outcomes")
    status = models.CharField(max_length=12)
    stage = models.CharField(max_length=40)
    failure_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["attempt", "image"], name="image_attempt_outcome")]
