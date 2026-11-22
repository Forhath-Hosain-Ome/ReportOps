from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from image_processor.models import FolderBatch, ProcessingAttempt
from image_processor.serializers.folder_report_serializer import AttemptSerializer


class LogsPagination(PageNumberPagination):
    page_size = 20


class FolderBatchLogsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AttemptSerializer
    pagination_class = LogsPagination

    def get_queryset(self):
        self.batch = get_object_or_404(FolderBatch, pk=self.kwargs["pk"], created_by=self.request.user)
        return ProcessingAttempt.objects.filter(report__batch=self.batch).select_related("report").prefetch_related("outcomes__image").order_by("-created_at", "pk")

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data.update(batch_id=self.batch.pk, status=self.batch.status,
                             last_error_code=self.batch.last_error_code, error_log=self.batch.error_log)
        return response
