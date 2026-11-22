from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from shared.view import _get_active_object

from mail_download.models import GmailAccount
from mail_download.serializers import  SearchRequestSerializer

from services.mail_download import downloader


class SearchView(APIView):
    """
    POST /api/mailfetch/download-zip/
    {account_id, attachments: [{message_id, attachment_id, filename}, ...]}

    Synchronous -- fine at the validated cap of 50 (real usage is under
    ~15). Revisit (move to Celery + a "your zip is ready" notification)
    only as a deliberate decision if usage patterns change to routinely
    cover 50+ attachments -- see the cap note in serializers.py.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SearchRequestSerializer(data=request.data)
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
            # Already logged to DownloadHistory as "failed" inside the
            # service layer -- the client just needs to know it didn't work.
            return Response({"detail": "Failed to fetch attachment."}, status=502)

        response = HttpResponse(file_bytes, content_type="application/octet-stream")
        response["Content-Disposition"] = f'attachment; filename="{data["filename"]}"'
        return response

