from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from mail_download.serializers import SearchJobSerializer
from mail_download.models import SearchJob

class SearchJobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/mailfetch/search/{id}/ -- lets a client that loads the page
    after a search already completed (or after a missed WebSocket event)
    fetch the job's current state directly, same fallback your other
    job-based features presumably support via their own job endpoints.
    Filtered by request.user since a SearchJob belongs to whoever
    triggered it -- unlike GmailAccount, this IS a per-user resource.
    """
    serializer_class = SearchJobSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return SearchJob.objects.filter(user=self.request.user).order_by("-created_at")