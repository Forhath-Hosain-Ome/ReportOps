# backend/image_processor/views/folder_upload_view.py
import logging
import os
import uuid
import errno
import shutil
from pathlib import Path, PurePosixPath

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db import transaction

from image_processor.serializers import FolderUploadSerializer
from image_processor.archive_upload import ArchiveValidationError, stage_archive
from image_processor.output_paths import OutputPathError, validate_report_date
from image_processor.models import FolderBatch
from image_processor.lifecycle import create_intake, publish_dispatch
from image_processor.retention_paths import staging_root
from image_processor.tasks import process_folder_task
from utils import normalize_filename
from image_processor.upload_paths import (
    open_upload_file,
    validate_upload_destinations,
    validate_preparation_destinations,
    contained_upload_path,
)

logger = logging.getLogger(__name__)


class FolderUploadView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes     = [MultiPartParser, FormParser]

    def dispatch(self, request, *args, **kwargs):
        try:
            return super().dispatch(request, *args, **kwargs)
        except RuntimeError as e:
            if "cannot schedule new futures after interpreter shutdown" in str(e):
                return Response(
                    {"detail": "Server is shutting down"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            raise

    def post(self, request):
        files           = request.FILES.getlist("files")
        paths           = request.POST.getlist("paths") or request.POST.getlist("paths[]")
        try:
            date = validate_report_date(request.POST.get("date", ""))
        except OutputPathError:
            return Response({"code": "invalid_date", "detail": "Use a valid YYYY-MM-DD date or leave it blank."}, status=400)
        style           = request.POST.get("style", "").strip()
        is_renamed_file = request.POST.get("is_renamed_file") == "true"
        archives = request.FILES.getlist("archive")
        if "archive" in request.data and (
            len(archives) != 1 or len(request.data.getlist("archive")) != 1
            or "files" in request.data or "paths" in request.data or "paths[]" in request.data
        ):
            return Response({"code": "invalid_upload_mode", "detail": "Submit one archive or files with paths."}, status=400)

        paths = [p.replace("\\", "/") for p in paths]

        # ── Validate + normalize filenames via serializer ─────────────────
        serializer = FolderUploadSerializer(
            data={
                "files":           files,
                "paths":           paths,
                "style":           style,
                "is_renamed_file": is_renamed_file,
            }
        )
        if archives:
            try:
                style = serializer.fields["style"].run_validation(style)
                style = serializer.validate_style(style)
            except ValidationError:
                return Response({"code": "invalid_archive", "detail": "Invalid archive style."}, status=400)
        elif not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_files = [] if archives else serializer.validated_data["files"]
        normalized_paths = [] if archives else serializer.validated_data["paths"]
        style = style if archives else serializer.validated_data["style"]

        # Preserve the existing saved filenames and logical folder identities.
        # Plan flat uploads in their final folder, eliminating unsafe renames.
        destinations = [
            str(PurePosixPath(path).parent / normalize_filename(file_obj.name))
            for file_obj, path in zip(validated_files, normalized_paths)
        ]
        if all("/" not in path for path in destinations):
            destinations = [f"{style or 'uploaded'}/{path}" for path in destinations]
        try:
            validate_upload_destinations(destinations)
            validate_preparation_destinations(destinations)
        except ValidationError:
            return Response({"code": "upload_destination_conflict", "detail": "Upload names conflict."}, status=400)

        upload_base = staging_root()
        root_created = False
        intake_committed = False

        try:
            upload_base.mkdir(parents=True, exist_ok=True)
            root = contained_upload_path(upload_base, str(uuid.uuid4()))
            temp_dir = str(root)
            # Never reuse a pre-existing directory or follow a planted root link.
            root.mkdir(mode=0o700)
            root_created = True
            manifest = []
            if archives:
                manifest = stage_archive(archives[0], root, style)
            for file_obj, relative_path in zip(validated_files, destinations):
                with open_upload_file(root, relative_path) as dest:
                    for chunk in file_obj.chunks():
                        dest.write(chunk)
                manifest.append({"relative_path": relative_path, "original_filename": file_obj.name})

            # ── Discover folders ──────────────────────────────────────────
            folders = sorted({str(PurePosixPath(item["relative_path"]).parent) for item in manifest})

            # ── Create FolderBatch ────────────────────────────────────────
            batch = create_intake(request.user, root, manifest, {
                "date": date, "is_renamed_file": is_renamed_file,
            })
            intake_committed = True

            # ── Fire Celery task after DB commit ──────────────────────────
            def on_commit_callback():
                publish_dispatch(batch.pk, batch.dispatch_generation, batch.dispatch_token, process_folder_task)

            transaction.on_commit(on_commit_callback)
            batch.refresh_from_db()

            return Response(
                {
                    "batch_id":      batch.id,
                    "total_folders": len(folders),
                    "submitted_images": len(manifest),
                    "dispatch_state": batch.dispatch_state,
                    "message": (
                        f"Uploaded {len(archives) or len(files)} file(s) into "
                        f"{len(folders)} folder(s). Processing started."
                    ),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception as exc:
            try:
                if root_created and not intake_committed:
                    shutil.rmtree(temp_dir)
            except OSError:
                logger.warning("Image upload cleanup failed")
            if isinstance(exc, ArchiveValidationError):
                return Response(exc.detail, status=status.HTTP_400_BAD_REQUEST)
            invalid = isinstance(exc, (ValidationError, FileExistsError)) or (
                isinstance(exc, OSError)
                and exc.errno in (errno.ELOOP, errno.ENOTDIR, errno.EINVAL, errno.ENAMETOOLONG)
            )
            code = "invalid_upload_destination" if invalid else "upload_failed"
            if isinstance(exc, FileExistsError):
                code = "upload_destination_conflict"
            # Exception text/tracebacks can disclose paths: record only safe categories.
            logger.warning("Image upload failed code=%s error_type=%s", code, type(exc).__name__)
            if invalid:
                return Response(
                    {"code": code, "detail": "Invalid or conflicting upload destination."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"code": code, "error": "Upload failed. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
