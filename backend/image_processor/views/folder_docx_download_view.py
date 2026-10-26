from django.http import FileResponse, Http404
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from image_processor.models import FolderReport
from image_processor.lifecycle import authoritative_path, invalidate_missing_authority
from image_processor.output_paths import OutputPathError, stored_output_path

# Retained import boundary; stored paths now have exactly one MEDIA_ROOT-relative contract.
def _resolve_docx_path(stored_path):
    try:
        path = stored_output_path(stored_path)
        return path if path.is_file() else None
    except (OutputPathError, OSError):
        return None


class FolderDOCXDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        try:
            report = FolderReport.objects.select_related("current_attempt").get(pk=pk, batch__created_by=request.user)
        except FolderReport.DoesNotExist:
            raise Http404("Report not found.")
        try:
            path = authoritative_path(report)
        except (OutputPathError, OSError):
            invalidate_missing_authority(report)
            return Response({"code": "ARTIFACT_UNAVAILABLE", "detail": "No valid DOCX is available."}, status=404)
        try:
            stream = open(path, "rb")
        except OSError:
            invalidate_missing_authority(report)
            return Response({"code": "ARTIFACT_UNAVAILABLE", "detail": "No valid DOCX is available."}, status=404)
        return FileResponse(stream, as_attachment=True, filename=path.name,
                            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
