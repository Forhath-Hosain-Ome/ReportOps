"""Database-owned retention coordinated with execution and retry."""
import logging
import shutil
import uuid
from celery import shared_task
from django.db import transaction
from django.utils import timezone
from image_processor.coordination import batch_lock
from image_processor.lifecycle import publication_lease_expired
from image_processor.models import FolderBatch
from image_processor.retention_paths import source_directory, output_directory_for_batch

logger = logging.getLogger(__name__)


@shared_task(name="image_processor.cleanup_temp_dirs", queue="image_processor", max_retries=0, ignore_result=True)
def cleanup_temp_dirs_task():
    counts = {"removed": 0, "absent": 0, "skipped": 0, "errors": 0}
    ids = FolderBatch.objects.filter(expires_at__lte=timezone.now()).values_list("pk", flat=True)
    for batch_id in ids.iterator():
        with batch_lock(batch_id) as acquired:
            if not acquired:
                counts["skipped"] += 1
                continue
            token = uuid.uuid4()
            with transaction.atomic():
                batch = FolderBatch.objects.select_for_update().get(pk=batch_id)
                eligible = (batch.status in {"COMPLETED", "PARTIAL", "FAILED"}
                            or (batch.status == "PENDING" and batch.dispatch_state in {"FAILED", "UNKNOWN"})
                            or (batch.dispatch_state in {"REQUESTED", "PUBLISHING"}
                                and publication_lease_expired(batch)))
                if (not eligible
                        or batch.active_run_token or batch.maintenance_token
                        or not batch.expires_at or batch.expires_at > timezone.now()):
                    counts["skipped"] += 1
                    continue
                batch.maintenance_token = token
                batch.save(update_fields=["maintenance_token"])
            try:
                for resolver, marker in ((source_directory, "source_deleted_at"),
                                         (output_directory_for_batch, "output_deleted_at")):
                    if getattr(batch, marker):
                        continue
                    try:
                        target = resolver(batch)
                        exists = target.exists()
                        if exists:
                            checked = resolver(batch)
                            if checked != target or not checked.is_dir():
                                raise ValueError("Invalid batch directory.")
                            shutil.rmtree(checked)
                        with transaction.atomic():
                            locked = FolderBatch.objects.select_for_update().get(pk=batch_id, maintenance_token=token)
                            setattr(locked, marker, timezone.now())
                            locked.save(update_fields=[marker])
                            if marker == "output_deleted_at":
                                locked.reports.filter(status__in=["COMPLETED", "PARTIAL"]).update(
                                    status="FAILED", current_attempt=None, pdf_output_path="",
                                    error_message="Artifact retention expired.",
                                )
                                locked.processed_folders = locked.partial_reports = 0
                                locked.failed_folders = locked.reports.filter(status="FAILED").count()
                                locked.status = "FAILED"
                                locked.last_error_code = "RETENTION_EXPIRED"
                                locked.save()
                        counts["removed" if exists else "absent"] += 1
                    except Exception:
                        counts["errors"] += 1
                        logger.exception("Image retention deletion failed for batch %s", batch_id)
            finally:
                FolderBatch.objects.filter(pk=batch_id, maintenance_token=token).update(maintenance_token=None)
    return counts
