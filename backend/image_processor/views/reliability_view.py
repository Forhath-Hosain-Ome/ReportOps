from django.http import Http404
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from image_processor.models import FolderBatch, OperationalSettings
from image_processor.lifecycle import retry_batch, LifecycleError


class RetrySerializer(serializers.Serializer):
    report_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False, required=False)


class FolderBatchRetryView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not FolderBatch.objects.filter(pk=pk, created_by=request.user).exists():
            raise Http404("Batch not found.")
        serializer = RetrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            batch = retry_batch(pk, request.user, serializer.validated_data.get("report_ids"))
        except LifecycleError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=exc.status)
        return Response({"batch_id": pk, "dispatch_state": batch.dispatch_state,
                         "generation": batch.dispatch_generation}, status=status.HTTP_202_ACCEPTED)


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OperationalSettings
        fields = ["retention_hours", "image_width_px", "image_height_px"]


class ImageSettingsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({**OperationalSettings.snapshot(), "can_manage": request.user.is_superuser is True})

    def patch(self, request):
        if request.user.is_superuser is not True:
            return Response({"detail": "Only superusers may change Image Processor settings."}, status=403)
        with transaction.atomic():
            OperationalSettings.objects.get_or_create(pk=1)
            obj = OperationalSettings.objects.select_for_update().get(pk=1)
            serializer = SettingsSerializer(obj, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save()
        return Response({**serializer.data, "can_manage": True})
