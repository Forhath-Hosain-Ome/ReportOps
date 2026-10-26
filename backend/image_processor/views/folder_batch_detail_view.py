import logging
import os
from pathlib import Path
from django.conf import settings
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from image_processor.models import FolderBatch
from image_processor.serializers import FolderBatchSerializer
from image_processor.lifecycle import authoritative_path, invalidate_missing_authority

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _pdf_exists(report) -> bool:
    """Check if the PDF output file exists on disk."""
    try:
        authoritative_path(report)
        return True
    except (ValueError, OSError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
#     FOLDER BATCH DETAIL
#     GET /api/folder/batches/<pk>/
#     Full batch with nested reports + failed folders.
# ─────────────────────────────────────────────────────────────────────────────

class FolderBatchDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class   = FolderBatchSerializer

    def get_queryset(self):
        return (
            FolderBatch.objects
            .prefetch_related("reports", "batch_failed_folders")
            .filter(created_by=self.request.user)
        )

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        for report in instance.reports.all():
            invalidate_missing_authority(report)
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data
        # Append live PDF availability flags for each report (not stored in DB)
        for report_data in data.get("reports", []):
            report_id = report_data.get("id")
            if report_id:
                try:
                    report = instance.reports.get(pk=report_id)
                    report_data["pdf_available"] = _pdf_exists(report)
                except Exception:
                    report_data["pdf_available"] = False
        return Response(data)
