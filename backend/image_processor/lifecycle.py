"""Image-specific durable lifecycle; HTTP and Celery share these transitions."""
import logging
import uuid
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from kombu.serialization import dumps
from rest_framework.exceptions import ValidationError

from image_processor.coordination import batch_lock, execution_write, StaleExecution
from image_processor.models import (
    FolderBatch, FolderReport, FolderImage, ProcessingAttempt, ImageOutcome,
    FolderFailedPDF, OperationalSettings,
)
from image_processor.output_paths import validate_docx, OutputPathError
from image_processor.upload_paths import contained_upload_path

logger = logging.getLogger(__name__)
TERMINAL = {"COMPLETED", "PARTIAL", "FAILED"}
DELIVERABLE = {"COMPLETED", "PARTIAL"}
LEASE_SECONDS = 1800  # Exceeds the existing 1500 second hard task deadline.


def publication_lease_expired(batch):
    """The existing retry expiry rule, also used by publication retention."""
    return bool(batch.status == "PENDING" and batch.lease_expires_at
                and batch.lease_expires_at <= timezone.now())


class LifecycleError(Exception):
    def __init__(self, code, message, status=409):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)


def create_intake(user, root, manifest, options):
    """No worker discovery: this transaction defines the entire intended job."""
    snapshot = OperationalSettings.snapshot()
    grouped = {}
    for item in manifest:
        parent = str(Path(item["relative_path"]).parent).replace("\\", "/")
        grouped.setdefault(parent, []).append(item)
    if not grouped:
        raise ValidationError("No accepted images found.")
    with transaction.atomic():
        batch = FolderBatch.objects.create(
            created_by=user, source_folder=str(root), staging_id=uuid.UUID(root.name),
            total_folders=len(grouped), submitted_images=len(manifest),
            settings_snapshot=snapshot, job_options=options,
            expires_at=timezone.now() + timedelta(hours=snapshot["retention_hours"]),
        )
        reports = []
        for folder, items in sorted(grouped.items()):
            report = FolderReport.objects.create(
                batch=batch, created_by=user, folder_name=folder,
                submitted_images=len(items),
            )
            FolderImage.objects.bulk_create([FolderImage(report=report, **item) for item in items])
            reports.append(report.pk)
        batch.manifest_reports = reports
        request_dispatch(batch, reports)
        return batch


def request_dispatch(batch, report_ids):
    """Caller holds the batch row lock (or owns the newly inserted batch)."""
    batch.dispatch_generation += 1
    batch.dispatch_token = uuid.uuid4()
    batch.dispatch_state = "REQUESTED"
    batch.status = "PENDING"
    batch.intended_reports = list(report_ids)
    batch.active_run_token = None
    batch.lease_expires_at = timezone.now() + timedelta(seconds=120)
    batch.processing_finished_at = None
    batch.last_error_code = ""
    batch.error_log = ""
    batch.save()
    for report in batch.reports.filter(pk__in=report_ids):
        ProcessingAttempt.objects.create(
            report=report, generation=batch.dispatch_generation,
            dispatch_token=batch.dispatch_token,
        )
        report.status = "PENDING"
        report.current_attempt = None
        report.pdf_output_path = ""
        report.successful_images = report.failed_images = report.image_count = 0
        report.error_message = ""
        report.save()
    reports = list(batch.reports.all())
    batch.processed_folders = sum(r.status == "COMPLETED" for r in reports)
    batch.partial_reports = sum(r.status == "PARTIAL" for r in reports)
    batch.failed_folders = sum(r.status == "FAILED" for r in reports)
    batch.successful_images = sum(r.successful_images for r in reports)
    batch.failed_images = sum(r.failed_images for r in reports)
    batch.save(update_fields=["processed_folders", "partial_reports", "failed_folders", "successful_images", "failed_images"])


def publish_dispatch(batch_id, generation, token, task=None):
    from image_processor.tasks import process_folder_task
    task = task or process_folder_task
    batch = FolderBatch.objects.get(pk=batch_id)
    args = (batch_id, batch.source_folder, batch.job_options.get("date", ""))
    kwargs = {**batch.job_options, "dispatch_generation": generation, "dispatch_token": str(token)}
    kwargs.pop("date", None)
    try:
        dumps({"args": args, "kwargs": kwargs}, serializer="json")
    except Exception:
        _publication_result(batch_id, generation, token, "FAILED", "DISPATCH_PREFLIGHT_FAILED")
        return "FAILED"
    # Claim the publication once. Never hold a row lock across broker I/O.
    with transaction.atomic():
        current = FolderBatch.objects.select_for_update().get(pk=batch_id)
        if (current.dispatch_generation != generation or str(current.dispatch_token) != str(token)
                or current.dispatch_state != "REQUESTED"):
            return current.dispatch_state
        current.dispatch_state = "PUBLISHING"
        current.save(update_fields=["dispatch_state"])
    try:
        result = task.delay(*args, **kwargs)
    except Exception:
        # A transport exception is not proof that the broker rejected the job.
        _publication_result(batch_id, generation, token, "UNKNOWN", "DISPATCH_OUTCOME_UNKNOWN")
        return "UNKNOWN"
    _publication_result(batch_id, generation, token, "QUEUED", "", str(result.id))
    return "QUEUED"


def _publication_result(batch_id, generation, token, state, error, task_id=""):
    with transaction.atomic():
        batch = FolderBatch.objects.select_for_update().get(pk=batch_id)
        if (batch.dispatch_generation != generation or str(batch.dispatch_token) != str(token)
                or batch.dispatch_state not in {"REQUESTED", "PUBLISHING"}):
            return
        batch.dispatch_state = state
        batch.last_error_code = error
        batch.celery_task_id = task_id
        batch.save(update_fields=["dispatch_state", "last_error_code", "celery_task_id"])
        if state == "QUEUED":
            ProcessingAttempt.objects.filter(
                report__batch=batch, generation=generation, dispatch_token=token, status="REQUESTED",
            ).update(status="QUEUED")


def claim_execution(batch_id, generation, token):
    if not generation or not token:
        return None
    with transaction.atomic():
        batch = FolderBatch.objects.select_for_update().get(pk=batch_id)
        if (batch.dispatch_generation != generation or str(batch.dispatch_token) != str(token)
                or batch.dispatch_state not in {"PUBLISHING", "QUEUED"}
                or batch.active_run_token or batch.maintenance_token or batch.status != "PENDING"):
            return None
        batch.active_run_token = uuid.uuid4()
        batch.status = batch.dispatch_state = "PROCESSING"
        batch.processing_started_at = timezone.now()
        batch.lease_expires_at = timezone.now() + timedelta(seconds=LEASE_SECONDS)
        batch.save()
        # The entire intended set is fenced into this run in the claim transaction.
        ProcessingAttempt.objects.filter(
            report__batch=batch, generation=generation, dispatch_token=token,
            status__in=["REQUESTED", "QUEUED"], report_id__in=batch.intended_reports,
        ).update(status="PROCESSING", run_token=batch.active_run_token, stage="INITIALIZING")
        batch.reports.filter(pk__in=batch.intended_reports).update(status="PROCESSING")
        return batch


def authoritative_path(report):
    attempt = report.current_attempt
    if (report.status not in DELIVERABLE or not attempt or attempt.report_id != report.pk
            or attempt.status != report.status or not attempt.finished_at
            or attempt.output_path != report.pdf_output_path):
        raise OutputPathError("Report has no valid authoritative artifact.")
    outcomes = list(attempt.outcomes.values("image_id", "status"))
    images = set(report.images.values_list("pk", flat=True))
    succeeded = sum(row["status"] == "SUCCEEDED" for row in outcomes)
    failed = sum(row["status"] == "FAILED" for row in outcomes)
    if ({row["image_id"] for row in outcomes} != images or len(outcomes) != report.submitted_images
            or succeeded + failed != report.submitted_images or not succeeded
            or succeeded != report.successful_images or failed != report.failed_images
            or (report.status == "COMPLETED" and failed) or (report.status == "PARTIAL" and not failed)):
        raise OutputPathError("Artifact outcome accounting is invalid.")
    from image_processor.retention_paths import output_root
    from image_processor.output_paths import output_path
    path = validate_docx(report.pdf_output_path)
    try:
        expected_parent = output_path(output_root(), f"{report.batch_id}/{report.pk}/{attempt.pk}")
    except (ValueError, OSError) as exc:
        raise OutputPathError("Invalid authoritative output root.") from exc
    if path.parent != expected_parent:
        raise OutputPathError("Artifact does not belong to this report attempt.")
    return path


def invalidate_missing_authority(report):
    """Read/download validation can revoke present authority, never attempt history."""
    if report.status not in DELIVERABLE:
        return
    with batch_lock(report.batch_id) as acquired:
        if not acquired:
            return  # An active worker reconciles the same check before completion.
        with transaction.atomic():
            batch = FolderBatch.objects.select_for_update().get(pk=report.batch_id)
            if batch.active_run_token or batch.maintenance_token:
                return
            current = FolderReport.objects.select_for_update(of=("self",)).select_related("current_attempt").get(pk=report.pk)
            try:
                authoritative_path(current)
                return
            except (OutputPathError, OSError):
                current.status, current.current_attempt, current.pdf_output_path = "FAILED", None, ""
                current.error_message = "Authoritative artifact is missing or invalid."
                current.save()
            if batch.status in TERMINAL:
                states = list(batch.reports.values_list("status", flat=True))
                batch.processed_folders = states.count("COMPLETED")
                batch.partial_reports = states.count("PARTIAL")
                batch.failed_folders = states.count("FAILED")
                batch.status = "PARTIAL" if batch.processed_folders + batch.partial_reports else "FAILED"
                batch.last_error_code = "ARTIFACT_UNAVAILABLE"
                batch.save()


def finish_report(batch, attempt_id, results, relative_output=""):
    """Success outcomes and all authority writes either commit together or roll back."""
    if relative_output:
        validate_docx(relative_output)
    with execution_write(batch.pk, batch.dispatch_generation, batch.dispatch_token,
                         batch.active_run_token, attempt_id) as (locked, attempt):
        report = FolderReport.objects.select_for_update().get(pk=attempt.report_id, batch=locked)
        expected = set(report.images.values_list("pk", flat=True))
        if {row["image_id"] for row in results} != expected or len(results) != len(expected):
            raise RuntimeError("Image outcome manifest mismatch.")
        succeeded = sum(row["status"] == "SUCCEEDED" for row in results)
        failed = sum(row["status"] == "FAILED" for row in results)
        if succeeded + failed != report.submitted_images or bool(succeeded) != bool(relative_output):
            raise RuntimeError("Invalid report accounting or deliverable.")
        ImageOutcome.objects.bulk_create([ImageOutcome(attempt=attempt, **row) for row in results])
        state = ("PARTIAL" if failed else "COMPLETED") if succeeded else "FAILED"
        attempt.status, attempt.stage = state, "FINISHED"
        attempt.output_path = relative_output
        attempt.error_code = "IMAGE_FAILURE" if failed else ""
        attempt.finished_at = timezone.now()
        attempt.save()
        report.status = state
        report.current_attempt = attempt if relative_output else None
        report.pdf_output_path = relative_output
        report.successful_images = report.image_count = succeeded
        report.failed_images = failed
        report.error_message = "Some accepted images could not be prepared." if failed else ""
        report.save()
        if failed:
            FolderFailedPDF.objects.create(batch=locked, folder_name=report.folder_name, reason=report.error_message)
        reports = list(locked.reports.all())
        locked.processed_folders = sum(r.status == "COMPLETED" for r in reports)
        locked.partial_reports = sum(r.status == "PARTIAL" for r in reports)
        locked.failed_folders = sum(r.status == "FAILED" for r in reports)
        locked.successful_images = sum(r.successful_images for r in reports)
        locked.failed_images = sum(r.failed_images for r in reports)
        locked.save(update_fields=["processed_folders", "partial_reports", "failed_folders",
                                   "successful_images", "failed_images"])


def fail_execution(batch, code="EXECUTION_FAILED"):
    # Terminal attempts remain immutable, including their successful outcomes.
    with execution_write(batch.pk, batch.dispatch_generation, batch.dispatch_token,
                         batch.active_run_token) as (locked, _):
        locked.last_error_code = code
        locked.error_log = "Processing infrastructure failed. Retry while source is retained."
        locked.save(update_fields=["last_error_code", "error_log"])
        unfinished = ProcessingAttempt.objects.filter(
            report__batch=locked, generation=locked.dispatch_generation,
            dispatch_token=locked.dispatch_token, run_token=locked.active_run_token, status="PROCESSING",
        )
        report_ids = list(unfinished.values_list("report_id", flat=True))
        unfinished.update(status="FAILED", stage="INFRASTRUCTURE", error_code=code,
                          error_message="Processing infrastructure failed. Retry while source is retained.",
                          finished_at=timezone.now())
        locked.reports.filter(pk__in=report_ids).update(
            status="FAILED", current_attempt=None, pdf_output_path="",
            error_message="Processing infrastructure failed. Retry while source is retained.",
        )


def reconcile(batch):
    with execution_write(batch.pk, batch.dispatch_generation, batch.dispatch_token,
                         batch.active_run_token) as (locked, _):
        reports = list(locked.reports.select_related("current_attempt"))
        if ({r.pk for r in reports} != set(locked.manifest_reports)
                or len(reports) != locked.total_folders
                or sum(r.submitted_images for r in reports) != locked.submitted_images):
            raise RuntimeError("Batch manifest cardinality mismatch.")
        attempts = list(ProcessingAttempt.objects.filter(
            report__batch=locked, generation=locked.dispatch_generation, dispatch_token=locked.dispatch_token,
        ))
        if ({a.report_id for a in attempts} != set(locked.intended_reports)
                or any(a.status not in TERMINAL for a in attempts)
                or any(r.status not in TERMINAL for r in reports)):
            raise RuntimeError("Intended work is unfinished.")
        for report in reports:
            if report.images.count() != report.submitted_images:
                raise RuntimeError("Persisted image manifest cardinality mismatch.")
            if report.status in DELIVERABLE:
                try:
                    authoritative_path(report)
                    if report.successful_images + report.failed_images != report.submitted_images:
                        raise RuntimeError("Report accounting mismatch.")
                except OutputPathError:
                    # Invalidate present deliverability without changing audit evidence.
                    report.status = "FAILED"
                    report.current_attempt = None
                    report.pdf_output_path = ""
                    report.error_message = "Authoritative artifact is missing or invalid."
                    report.save()
        locked.processed_folders = sum(r.status == "COMPLETED" for r in reports)
        locked.partial_reports = sum(r.status == "PARTIAL" for r in reports)
        locked.failed_folders = sum(r.status == "FAILED" for r in reports)
        locked.successful_images = sum(r.successful_images for r in reports)
        locked.failed_images = sum(r.failed_images for r in reports)
        normal = all(r.successful_images + r.failed_images == r.submitted_images for r in reports)
        if normal and locked.successful_images + locked.failed_images != locked.submitted_images:
            raise RuntimeError("Batch image accounting mismatch.")
        locked.status = ("COMPLETED" if locked.processed_folders == locked.total_folders else
                         "PARTIAL" if locked.processed_folders + locked.partial_reports else "FAILED")
        locked.dispatch_state = "TERMINAL"
        locked.processing_finished_at = timezone.now()
        locked.active_run_token = None
        locked.lease_expires_at = None
        locked.save()
        return locked


def reconciliation_failed(batch):
    with execution_write(batch.pk, batch.dispatch_generation, batch.dispatch_token,
                         batch.active_run_token) as (locked, _):
        locked.status = "FAILED"
        locked.dispatch_state = "TERMINAL"
        locked.last_error_code = "BATCH_RECONCILIATION_FAILED"
        locked.processing_finished_at = timezone.now()
        locked.active_run_token = None
        locked.lease_expires_at = None
        locked.save(update_fields=["status", "dispatch_state", "last_error_code", "processing_finished_at",
                                   "active_run_token", "lease_expires_at"])


def retry_batch(batch_id, user, selected_ids=None):
    with batch_lock(batch_id) as acquired:
        if not acquired:
            raise LifecycleError("BATCH_BUSY", "Batch is processing or undergoing maintenance.")
        with transaction.atomic():
            batch = FolderBatch.objects.select_for_update().get(pk=batch_id, created_by=user)
            if batch.maintenance_token:
                raise LifecycleError("BATCH_BUSY", "Batch is undergoing maintenance.")
            stale = batch.status == "PROCESSING"
            if stale and (not batch.lease_expires_at or batch.lease_expires_at > timezone.now()):
                raise LifecycleError("LEASE_ACTIVE", "Processing lease has not expired.")
            publication_expired = publication_lease_expired(batch)
            if batch.status == "PENDING" and batch.dispatch_state not in {"FAILED", "UNKNOWN"} and not publication_expired:
                raise LifecycleError("DISPATCH_ACTIVE", "Dispatch is already active.")
            if (not batch.expires_at or batch.expires_at <= timezone.now() or batch.source_deleted_at):
                raise LifecycleError("REUPLOAD_REQUIRED", "Retained source expired. Upload the images again.", 410)
            from image_processor.retention_paths import source_directory
            try:
                source = source_directory(batch)
                if not source.is_dir():
                    raise ValueError()
            except (ValueError, OSError, ValidationError):
                raise LifecycleError("REUPLOAD_REQUIRED", "Retained source is unavailable. Upload the images again.", 410)
            reports = list(batch.reports.select_related("current_attempt"))
            unfinished = set(ProcessingAttempt.objects.filter(
                report__batch=batch, generation=batch.dispatch_generation,
                status__in=["REQUESTED", "QUEUED", "PROCESSING"],
            ).values_list("report_id", flat=True)) if stale else set()
            candidates = {r.pk for r in reports if r.status in {"FAILED", "PARTIAL"}} | unfinished
            if batch.dispatch_state in {"FAILED", "UNKNOWN"} or publication_expired:
                candidates |= set(batch.intended_reports)
            selected = (unfinished if stale else candidates) if selected_ids is None else set(selected_ids)
            if stale:
                selected |= unfinished  # Recovery must cover the entire interrupted intent.
            if (not selected and not stale) or not selected.issubset(candidates):
                raise LifecycleError("INVALID_RETRY_SELECTION", "Select failed or partial reports from this batch.", 400)
            try:
                if any(not contained_upload_path(source, path).is_file() for path in
                       FolderImage.objects.filter(report_id__in=selected).values_list("relative_path", flat=True)):
                    raise ValueError()
            except (ValueError, OSError, ValidationError):
                raise LifecycleError("REUPLOAD_REQUIRED", "Selected source images are unavailable. Upload them again.", 410)
            ProcessingAttempt.objects.filter(
                report__batch=batch, generation=batch.dispatch_generation,
                dispatch_token=batch.dispatch_token, status__in=["REQUESTED", "QUEUED", "PROCESSING"],
            ).update(status="FAILED", stage="RECOVERY", error_code="DISPATCH_SUPERSEDED",
                     error_message="Interrupted or uncertain dispatch superseded by recovery.", finished_at=timezone.now())
            batch.retry_count += 1
            request_dispatch(batch, sorted(selected))
            generation, token = batch.dispatch_generation, batch.dispatch_token
    publish_dispatch(batch_id, generation, token)
    return FolderBatch.objects.get(pk=batch_id)
