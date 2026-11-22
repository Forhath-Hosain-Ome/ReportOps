from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from mail_download.models import DownloadHistory
from mail_download.serializers import DownloadHistorySerializer


class DownloadHistoryViewSet(viewsets.ReadOnlyModelViewSet):

    """Replaces _show_history()'s popup window. Filtered by request.user
    -- an audit lens ("what have I downloaded"), not the per-user scoping
    that GmailAccount deliberately lacks."""
    serializer_class = DownloadHistorySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DownloadHistory.objects.filter(
            user=self.request.user
        ).select_related("account").order_by("-downloaded_at")