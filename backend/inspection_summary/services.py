"""An indivisible owner-scoped report job; all publication is run-token fenced."""
import hashlib
import logging
import os
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from kombu.exceptions import EncodeError, OperationalError
from kombu.serialization import dumps

from . import storage
from .models import InspectionSummaryJob as Job
from .parser import parse_inspection_workbook
from .workbook_security import WorkbookValidationError, validate_workbook
from .writer import verify_report, write_report

logger = logging.getLogger(__name__)
TASK_HARD_LIMIT = 1500
PUBLICATION_LEASE_SECONDS = 120
MAINTENANCE_LEASE_SECONDS = 300
PROCESSING_LEASE_SECONDS = 1800  # Beyond the 1500-second hard worker deadline.


class StaleRun(Exception):
    pass


def create_job(user, inspection_summary=None, raw=None):
    if inspection_summary is None and raw is None:
        raise WorkbookValidationError("INVALID_INPUTS", "At least one Inspection Summary or 100% workbook is required.")
    identifier = uuid.uuid4()
    root_created = False
    try:
        storage.make_directory("inspection_summary")
        storage.job_root(identifier).mkdir(mode=0o700)
        root_created = True
        summary_path, summary_hash = (storage.save_input(identifier,"inspection_summary",inspection_summary) if inspection_summary is not None else (storage.key(identifier,"input/inspection_summary.xlsx"),""))
        raw_path, raw_hash = (storage.save_input(identifier,"raw",raw) if raw is not None else (storage.key(identifier,"input/raw.xlsx"),""))
        with transaction.atomic():
            job = Job.objects.create(
                id=identifier, created_by=user, inspection_summary_name=inspection_summary.name if inspection_summary is not None else "",
                raw_name=raw.name if raw is not None else "", inspection_summary_path=summary_path, raw_path=raw_path,
                inspection_summary_sha256=summary_hash, raw_sha256=raw_hash,
                expires_at=timezone.now() + timedelta(hours=24), stage="QUEUED",
                publication_lease_expires_at=timezone.now() + timedelta(seconds=PUBLICATION_LEASE_SECONDS))
            identity = (job.pk, job.dispatch_generation, str(job.dispatch_token))
            transaction.on_commit(lambda: publish_inspection_summary_job(*identity))
        return Job.objects.get(pk=job.pk)
    except Exception:
        # A committed row owns its files, including uncertain broker outcomes.
        if root_created and not Job.objects.filter(pk=identifier).exists():
            storage.remove_job(identifier)
        raise


def _dispatch_result(job_id, generation, token, state, error=""):
    # Conditional result write: never regress a worker or a newer generation.
    updates = {"dispatch_state": state, "last_error_code": error}
    if state == Job.Dispatch.TERMINAL:
        updates.update(status=Job.Status.FAILED, stage="FAILED", error_code=error,
                       error_detail={"detail": "Report dispatch preflight failed."},
                       processing_finished_at=timezone.now())
    return Job.objects.filter(pk=job_id, dispatch_generation=generation, dispatch_token=token,
                              status=Job.Status.PENDING, dispatch_state=Job.Dispatch.PUBLISHING,
                              run_token=None, maintenance_token=None).update(**updates)


def publish_inspection_summary_job(job_id, generation, token):
    from .tasks import generate_inspection_summary
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if (job.status != Job.Status.PENDING or job.dispatch_state != Job.Dispatch.REQUESTED
                or job.dispatch_generation != generation or str(job.dispatch_token) != str(token)
                or job.maintenance_token or job.run_token or job.expires_at <= timezone.now()):
            return "IGNORED"
        job.dispatch_state = Job.Dispatch.PUBLISHING
        job.publication_lease_expires_at = timezone.now() + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
        job.task_id = str(token)
        job.save(update_fields=["dispatch_state", "publication_lease_expires_at", "task_id"])
    args = [str(job_id), generation, str(token)]
    try:
        dumps({"args": args}, serializer="json")  # Definitely before broker I/O.
    except (EncodeError, TypeError, ValueError):
        _dispatch_result(job_id, generation, token, Job.Dispatch.TERMINAL, "DISPATCH_PREFLIGHT_FAILED")
        return "FAILED"
    except Exception:
        _dispatch_result(job_id, generation, token, Job.Dispatch.TERMINAL, "DISPATCH_PREFLIGHT_FAILED")
        logger.error("Inspection Summary unexpected dispatch preflight failure")
        raise
    try:
        generate_inspection_summary.apply_async(args=args, task_id=str(token), queue="celery",
                                               serializer="json", retry=False)
    except Exception as exc:
        _dispatch_result(job_id, generation, token, Job.Dispatch.UNKNOWN, "DISPATCH_OUTCOME_UNKNOWN")
        logger.error("Inspection Summary publication uncertain (%s)", type(exc).__name__)
        if not isinstance(exc, (OperationalError, OSError, TimeoutError)):
            raise
        return "UNKNOWN"
    _dispatch_result(job_id, generation, token, Job.Dispatch.QUEUED)
    return "QUEUED"


def recover_dispatches():
    """Internal recovery; old deliveries lose authority before a new publish."""
    recovered = 0
    candidates = Job.objects.filter(status=Job.Status.PENDING, expires_at__gt=timezone.now(),
        dispatch_state__in=[Job.Dispatch.REQUESTED, Job.Dispatch.PUBLISHING, Job.Dispatch.UNKNOWN],
        publication_lease_expires_at__lte=timezone.now()).values_list("pk", flat=True)
    for identifier in candidates.iterator():
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=identifier)
            if (job.status != Job.Status.PENDING or job.run_token or job.maintenance_token
                    or job.expires_at <= timezone.now()
                    or job.dispatch_state not in {Job.Dispatch.REQUESTED, Job.Dispatch.PUBLISHING, Job.Dispatch.UNKNOWN}
                    or not job.publication_lease_expires_at or job.publication_lease_expires_at > timezone.now()):
                continue
            job.dispatch_generation += 1
            job.dispatch_token = uuid.uuid4()
            job.dispatch_state = Job.Dispatch.REQUESTED
            job.publication_lease_expires_at = timezone.now() + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
            job.last_error_code = ""
            job.task_id = ""
            job.save(update_fields=["dispatch_generation", "dispatch_token", "dispatch_state",
                                   "publication_lease_expires_at", "last_error_code", "task_id"])
            identity = (job.pk, job.dispatch_generation, str(job.dispatch_token))
            transaction.on_commit(lambda identity=identity: publish_inspection_summary_job(*identity))
            recovered += 1
    return recovered


def claim_job(job_id, generation, token):
    try:
        parsed = uuid.UUID(str(token))
    except (ValueError, TypeError, AttributeError):
        return None
    if type(generation) is not int or generation < 1 or str(parsed) != str(token):
        return None
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=job_id)
        if (job.status != Job.Status.PENDING or job.expires_at <= timezone.now()
                or job.dispatch_generation != generation or job.dispatch_token != parsed
                or job.dispatch_state not in {Job.Dispatch.PUBLISHING, Job.Dispatch.QUEUED}
                or job.run_token or job.maintenance_token):
            return None
        job.status = Job.Status.PROCESSING
        job.dispatch_state = Job.Dispatch.PROCESSING
        job.run_token = uuid.uuid4()
        job.stage = "VALIDATING"
        job.processing_started_at = timezone.now()
        job.processing_lease_expires_at = timezone.now() + timedelta(seconds=PROCESSING_LEASE_SECONDS)
        job.save(update_fields=["status", "dispatch_state", "run_token", "stage", "processing_started_at",
                                "processing_lease_expires_at"])
        return job


def advance(job, stage):
    if not Job.objects.filter(pk=job.pk, status=Job.Status.PROCESSING, run_token=job.run_token,
            dispatch_generation=job.dispatch_generation, dispatch_token=job.dispatch_token,
            dispatch_state=Job.Dispatch.PROCESSING, maintenance_token=None,
            processing_lease_expires_at__gt=timezone.now(), expires_at__gt=timezone.now()).update(stage=stage):
        raise StaleRun()


def validated_inputs(job):
    inputs = []
    for kind, relative, expected_hash in [
        ("inspection_summary", job.inspection_summary_path, job.inspection_summary_sha256),
        ("raw", job.raw_path, job.raw_sha256),
    ]:
        if relative != storage.key(job.pk, f"input/{kind}.xlsx"):
            raise ValueError("Input identity mismatch.")
        name = job.inspection_summary_name if kind == "inspection_summary" else job.raw_name
        if not expected_hash:
            if name:
                raise ValueError("Input identity mismatch.")
            inputs.append(None)
            continue
        if not name:
            raise ValueError("Input identity mismatch.")
        path = storage.input_path(job.pk, kind)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != expected_hash:
                raise WorkbookValidationError("INPUT_CHANGED", "Retained input no longer matches its upload.", input=kind)
            stream.seek(0)
            validate_workbook(stream, input=kind)
        inputs.append(path)
    if not any(inputs):
        raise ValueError("Missing input authority.")
    return inputs


def generate_job(job_id, generation, token):
    try:
        job = claim_job(job_id, generation, token)
    except Job.DoesNotExist:
        return {"ignored": True}
    if job is None:
        return {"ignored": True}
    temporary = None
    propagating = False
    try:
        inputs = validated_inputs(job)
        advance(job, "DISCOVERING_SHEETS")
        blocks = parse_inspection_workbook(*inputs, on_stage=lambda stage: advance(job, stage))
        manifest = [{"name": b.report_name, "position": i, "source_position": b.source_index,
                     "status": "completed", "empty": b.empty_state, "kind": b.kind} for i, b in enumerate(blocks)]
        advance(job, "WRITING_RESULT")
        storage.make_directory(storage.key(job.pk, "output"))
        temporary = storage.resolve_stored_path(storage.key(job.pk, f"output/Result.{job.run_token}.tmp.xlsx"))
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(temporary, flags, 0o600), "wb") as stream:
            write_report(blocks, stream)
        advance(job, "VERIFYING_RESULT")
        verify_report(temporary, blocks)
        with transaction.atomic():
            current = Job.objects.select_for_update().get(pk=job.pk)
            if (current.status != Job.Status.PROCESSING or current.dispatch_state != Job.Dispatch.PROCESSING
                    or current.run_token != job.run_token
                    or current.maintenance_token or current.dispatch_generation != generation
                    or str(current.dispatch_token) != str(token)
                    or current.expires_at <= timezone.now()
                    or not current.processing_lease_expires_at
                    or current.processing_lease_expires_at <= timezone.now()):
                raise StaleRun()
            final = storage.output_path(job.pk)
            if storage.resolve_stored_path(storage.key(job.pk, f"output/Result.{job.run_token}.tmp.xlsx")) != temporary:
                raise ValueError("Temporary path identity mismatch.")
            os.replace(temporary, final)
            current.status = Job.Status.COMPLETED
            current.dispatch_state = Job.Dispatch.TERMINAL
            current.stage = "COMPLETED"
            current.output_path = storage.key(job.pk, "output/Result.xlsx")
            current.sheet_manifest = manifest
            current.processing_finished_at = timezone.now()
            current.run_token = None
            current.processing_lease_expires_at = None
            current.save(update_fields=["status", "dispatch_state", "stage", "output_path", "sheet_manifest", "processing_finished_at", "run_token", "processing_lease_expires_at"])
        return {"status": "COMPLETED"}
    except StaleRun:
        # An owned run that reaches retention expiry is already at an I/O-safe
        # boundary. Revoke it now; a superseded/live run is never touched.
        try:
            Job.objects.filter(pk=job.pk, status=Job.Status.PROCESSING, run_token=job.run_token,
                dispatch_generation=generation, dispatch_token=token, expires_at__lte=timezone.now(),
                maintenance_token=None).update(status=Job.Status.FAILED, dispatch_state=Job.Dispatch.TERMINAL,
                stage="FAILED", error_code="JOB_EXPIRED", error_detail={"detail": "Job expired before completion."},
                run_token=None, processing_lease_expires_at=None, processing_finished_at=timezone.now())
        except Exception:
            propagating = True
            logger.error("Inspection Summary could not terminalize expired execution")
            raise
        return {"ignored": True}
    except Exception as exc:
        propagating = not isinstance(exc, WorkbookValidationError)
        if isinstance(exc, WorkbookValidationError):
            code, detail = exc.code, exc.detail
        else:
            code = "GENERATION_FAILED"
            detail = {"input": None, "sheet": None, "cell": None,
                      "detail": "Report generation failed. Check the workbooks and submit them again."}
        logger.error("Inspection Summary execution failed: %s (%s)", code, type(exc).__name__)
        try:
            Job.objects.filter(pk=job.pk, status=Job.Status.PROCESSING, run_token=job.run_token,
                dispatch_generation=generation, dispatch_token=token, maintenance_token=None).update(
                status=Job.Status.FAILED, dispatch_state=Job.Dispatch.TERMINAL, stage="FAILED",
                error_code=code, error_detail=detail, output_path="", run_token=None, processing_lease_expires_at=None,
                processing_finished_at=timezone.now())
        except Exception:
            logger.error("Inspection Summary could not persist execution failure")
            if isinstance(exc, WorkbookValidationError):
                propagating = True
                raise
        if not isinstance(exc, WorkbookValidationError):
            raise
        return {"status": "FAILED", "code": code}
    finally:
        if temporary is not None:
            try:
                checked = storage.resolve_stored_path(storage.key(job.pk, f"output/Result.{job.run_token}.tmp.xlsx"))
                checked.unlink(missing_ok=True)
            except (ValueError, OSError):
                logger.error("Inspection Summary temporary cleanup failed")
                # Do not mask an already propagating execution exception.
                if not propagating:
                    raise


def _terminalize_recovery(job, code, detail):
    return Job.objects.filter(pk=job.pk, status=Job.Status.PENDING,
        dispatch_state=Job.Dispatch.REQUESTED, dispatch_generation=job.dispatch_generation,
        dispatch_token=job.dispatch_token, run_token=None, maintenance_token=None).update(
        status=Job.Status.FAILED, dispatch_state=Job.Dispatch.TERMINAL, stage="FAILED",
        error_code=code, error_detail=detail, processing_finished_at=timezone.now())


def recover_processing_jobs(*, expired_only=False):
    """Revoke expired execution authority before validation/publishing or retention.

    No row lock spans input validation or broker I/O. REQUESTED's publication lease
    bounds a recovery crash between revocation and re-publication as well.
    """
    candidates = Job.objects.filter(status=Job.Status.PROCESSING).filter(
        Q(processing_lease_expires_at__lte=timezone.now()) | Q(processing_lease_expires_at__isnull=True))
    if expired_only:
        candidates = candidates.filter(expires_at__lte=timezone.now())
    recovered = 0
    for identifier in candidates.values_list("pk", flat=True).iterator():
        with transaction.atomic():
            job = Job.objects.select_for_update().get(pk=identifier)
            now = timezone.now()
            lease = job.processing_lease_expires_at or (
                (job.processing_started_at or job.created_at) + timedelta(seconds=PROCESSING_LEASE_SECONDS))
            if (job.status != Job.Status.PROCESSING or job.maintenance_token or lease > now
                    or (expired_only and job.expires_at > now)):
                continue
            job.run_token = None
            job.processing_lease_expires_at = None
            job.processing_finished_at = now
            job.output_path = ""
            if job.expires_at <= now:
                job.status = Job.Status.FAILED
                job.dispatch_state = Job.Dispatch.TERMINAL
                job.stage = "FAILED"
                job.error_code = "JOB_EXPIRED"
                job.error_detail = {"detail": "Job expired before completion."}
                job.save()
                recovered += 1
                continue
            job.status = Job.Status.PENDING
            job.dispatch_state = Job.Dispatch.REQUESTED
            job.dispatch_generation += 1
            job.dispatch_token = uuid.uuid4()
            job.publication_lease_expires_at = now + timedelta(seconds=PUBLICATION_LEASE_SECONDS)
            job.processing_started_at = None
            job.processing_finished_at = None
            job.stage = "QUEUED"
            job.task_id = ""
            job.last_error_code = "PROCESSING_LEASE_EXPIRED"
            job.save()
            # Bind the snapshot, not the loop variable, to the outer commit.
            transaction.on_commit(lambda job=job: _publish_recovered_job(job))
            recovered += 1
    return recovered


def _publish_recovered_job(job):
    try:
        validated_inputs(job)
    except FileNotFoundError:
        _terminalize_recovery(job, "SOURCE_UNAVAILABLE", {"detail": "Retained source inputs are unavailable."})
        return
    except WorkbookValidationError as exc:
        _terminalize_recovery(job, exc.code, exc.detail)
        return
    except Exception:
        try:
            _terminalize_recovery(job, "RECOVERY_FAILED", {"detail": "Could not recover the report execution."})
        except Exception:
            logger.error("Inspection Summary could not persist recovery failure")
        logger.error("Inspection Summary recovery failed unexpectedly")
        raise
    if job.expires_at <= timezone.now():
        _terminalize_recovery(job, "JOB_EXPIRED", {"detail": "Job expired before completion."})
        return
    publish_inspection_summary_job(job.pk, job.dispatch_generation, str(job.dispatch_token))


def claim_maintenance(identifier):
    """Caller must hold storage.maintenance_lock across claim/delete/finalize."""
    with transaction.atomic():
        job = Job.objects.select_for_update().get(pk=identifier)
        now = timezone.now()
        if (job.expires_at > now or job.status == Job.Status.PROCESSING or job.run_token
                or (job.input_deleted_at and job.output_deleted_at)):
            return None
        if job.maintenance_token and ((job.maintenance_started_at or job.created_at)
                > now - timedelta(seconds=MAINTENANCE_LEASE_SECONDS)):
            return None
        if (job.dispatch_state in {Job.Dispatch.REQUESTED, Job.Dispatch.PUBLISHING, Job.Dispatch.UNKNOWN}
                and job.publication_lease_expires_at and job.publication_lease_expires_at > now):
            return None
        # Check persisted paths as well as deriving the only deletable namespace.
        if (job.inspection_summary_path != storage.key(job.pk, "input/inspection_summary.xlsx")
                or job.raw_path != storage.key(job.pk, "input/raw.xlsx")
                or job.output_path not in {"", storage.key(job.pk, "output/Result.xlsx")}):
            raise ValueError("Job storage identity mismatch")
        if job.status == Job.Status.PENDING:
            job.status = Job.Status.FAILED
            job.stage = "FAILED"
            job.error_code = "JOB_EXPIRED"
            job.error_detail = {"detail": "Job expired before completion."}
            job.processing_finished_at = now
        job.dispatch_state = Job.Dispatch.TERMINAL
        job.maintenance_token = uuid.uuid4()
        job.maintenance_started_at = now
        job.save()
        return job


def cleanup_expired_jobs():
    recover_processing_jobs(expired_only=True)
    counts = {"removed": 0, "skipped": 0, "errors": 0}
    candidates = Job.objects.filter(expires_at__lte=timezone.now()).filter(
        Q(input_deleted_at__isnull=True) | Q(output_deleted_at__isnull=True)).values_list("pk", flat=True)
    for identifier in candidates.iterator():
        # The OS lock prevents a paused old lease holder from deleting concurrently
        # after reclamation. It survives DB commits, releases on crash, and is never
        # unlinked (unlinking a lock file permits two locks on different inodes).
        with storage.maintenance_lock(identifier) as acquired:
            if not acquired:
                counts["skipped"] += 1
                continue
            job = claim_maintenance(identifier)
            if job is None:
                counts["skipped"] += 1
                continue
            try:
                if not Job.objects.filter(pk=identifier, maintenance_token=job.maintenance_token).exists():
                    counts["skipped"] += 1
                    continue
                storage.remove_job(job.pk)  # Re-resolves exact directory immediately before deletion.
                with transaction.atomic():
                    current = Job.objects.select_for_update().get(pk=identifier)
                    if current.maintenance_token != job.maintenance_token:
                        counts["skipped"] += 1
                        continue
                    current.input_deleted_at = current.input_deleted_at or timezone.now()
                    current.output_deleted_at = current.output_deleted_at or timezone.now()
                    current.output_path = ""
                    current.maintenance_token = None
                    current.maintenance_started_at = None
                    current.save(update_fields=["input_deleted_at", "output_deleted_at", "output_path",
                                                "maintenance_token", "maintenance_started_at"])
                counts["removed"] += 1
            except Exception as exc:
                # Keep the lease for bounded recovery, without falsely marking deletion.
                logger.error("Inspection Summary retention failed (%s)", type(exc).__name__)
                raise
    return counts
