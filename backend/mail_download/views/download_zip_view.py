from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from shared.view import _get_active_object

from mail_download.models import GmailAccount
from mail_download.serializers import (
    DownloadZipRequestSerializer,
)
from services.mail_download import downloader


class DownloadZipView(APIView):
    """
    POST /api/mailfetch/download-zip/
    {account_id, attachments: [{message_id, attachment_id, filename}, ...]}

    Synchronous -- fine at the validated cap of 50 (real usage is ~<=15).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = DownloadZipRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            account = _get_active_object(data["account_id"])
        except GmailAccount.DoesNotExist:
            return Response({"detail": "Gmail account not found."}, status=404)

        zip_bytes = downloader.download_as_zip(
            user=request.user, account=account,
            attachments=data["attachments"],
        )
        response = HttpResponse(zip_bytes, content_type="application/zip")
        response["Content-Disposition"] = 'attachment; filename="attachments.zip"'
        return response

