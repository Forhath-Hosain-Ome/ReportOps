
from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from shared.view import _get_active_object

from mail_download.models import GmailAccount
from mail_download.serializers import (
    DownloadSingleRequestSerializer,
)
from services.mail_download import downloader


class DownloadSingleView(APIView):
    """
    GET /api/mailfetch/download/?account_id=&message_id=&attachment_id=&filename=

    Synchronous. Streams the attachment straight to the browser response
    -- no server-side copy is kept.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = DownloadSingleRequestSerializer(data=request.GET)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            account = _get_active_object(data["account_id"])
        except GmailAccount.DoesNotExist:
            return Response({"detail": "Gmail account not found."}, status=404)

        try:
            file_bytes = downloader.download_single(
                user=request.user, account=account,
                message_id=data["message_id"],
                attachment_id=data["attachment_id"],
                filename=data["filename"],
            )
        except Exception:
            # Already logged to DownloadHistory as "failed" in the service
            # layer -- the client just needs to know it didn't work.
            return Response({"detail": "Failed to fetch attachment."}, status=502)

        response = HttpResponse(file_bytes, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{data["filename"]}"'
        return response

