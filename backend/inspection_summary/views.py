import logging

from django.http import FileResponse
from django.utils import timezone
from rest_framework.generics import RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import storage
from .models import InspectionSummaryJob
from .serializers import JobSerializer, JobUploadSerializer
from .services import create_job
from .workbook_security import validate_workbook, WorkbookValidationError


class JobCreateView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        names=set(request.FILES)
        if (not names.issubset({'inspection_summary','hundred_percent','raw'})
                or {'raw','hundred_percent'}.issubset(names)
                or any(len(request.FILES.getlist(k))!=1 or len(request.data.getlist(k))!=1 for k in names)
                or set(request.data)-names):
            return Response({'code':'INVALID_INPUTS','detail':'Submit at most one Inspection Summary and one 100% workbook; duplicate or unknown fields are not allowed.'},status=400)
        files={('raw' if k=='hundred_percent' else k):request.FILES[k] for k in names}
        serializer = JobUploadSerializer(data=files)
        serializer.is_valid(raise_exception=True)
        try:
            job = create_job(request.user, **serializer.validated_data)
        except Exception as exc:
            logging.getLogger(__name__).error("Inspection Summary intake failed (%s)", type(exc).__name__)
            return Response({"code": "UPLOAD_FAILED", "detail": "Could not store this report job."}, status=503)
        return Response({"job_id": str(job.pk), "status": job.status, "stage": job.stage,
                         "expires_at": job.expires_at.isoformat(),
                         "status_url": f"/inspection-summary/jobs/{job.pk}/"}, status=202)


class JobDetailView(RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = JobSerializer

    def get_queryset(self):
        return InspectionSummaryJob.objects.filter(created_by=self.request.user)


class JobDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        job = get_object_or_404(InspectionSummaryJob, pk=pk, created_by=request.user)
        if job.expires_at <= timezone.now():
            return Response({"code": "ARTIFACT_EXPIRED", "detail": "This generated report has expired."}, status=410)
        if job.status != job.Status.COMPLETED:
            return Response({"code": "REPORT_NOT_READY", "detail": "Report generation has not completed."}, status=409)
        stream = None
        try:
            if job.output_deleted_at or job.output_path != storage.key(job.pk, "output/Result.xlsx"):
                raise ValueError("Missing authority")
            path = storage.resolve_stored_path(job.output_path)
            stream = path.open("rb")
            validate_workbook(stream)
        except (ValueError, OSError, WorkbookValidationError):
            if stream is not None:
                stream.close()
            return Response({"code": "ARTIFACT_UNAVAILABLE", "detail": "The generated workbook is unavailable."}, status=404)
        return FileResponse(stream, as_attachment=True, filename="Result.xlsx",
                            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class JobPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        from django.shortcuts import get_object_or_404
        from .preview import build_preview
        from .preview_serializers import PreviewSerializer

        job = get_object_or_404(InspectionSummaryJob, pk=pk, created_by=request.user)
        def lifecycle_error(current):
            if current.expires_at <= timezone.now():
                return Response({"code": "ARTIFACT_EXPIRED", "detail": "This generated report has expired."}, status=410)
            if current.status != current.Status.COMPLETED:
                return Response({"code": "REPORT_NOT_READY", "detail": "Report generation has not completed."}, status=409)
            return None

        error = lifecycle_error(job)
        if error is not None:
            return error
        try:
            if (job.output_deleted_at or job.input_deleted_at
                    or job.output_path != storage.key(job.pk, "output/Result.xlsx")):
                raise ValueError("Missing authority")
            with storage.resolve_stored_path(job.output_path).open("rb") as stream:
                validate_workbook(stream)
            preview = build_preview(job)
            # Retention may elapse while reading a large source workbook.
            job.refresh_from_db()
            error = lifecycle_error(job)
            if error is not None:
                return error
            if (job.output_deleted_at or job.input_deleted_at
                    or not JobSerializer().get_download_ready(job)):
                raise ValueError("Missing authority")
            response = Response(PreviewSerializer({"job": job, **preview}).data)
            response["Cache-Control"] = "private, no-store"
            return response
        except Exception as exc:
            # This read boundary intentionally translates storage/parser failures;
            # neither source cells, internal paths nor exception text escape.
            logging.getLogger(__name__).warning("Inspection Summary preview unavailable (%s)", type(exc).__name__)
            return Response({"code": "PREVIEW_UNAVAILABLE", "detail": "The report preview is unavailable."}, status=404)
