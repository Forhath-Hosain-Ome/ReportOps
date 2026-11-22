from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from mail_download.models import GmailAccount
from mail_download.serializers import  GmailAccountSerializer



class GmailAccountViewSet(viewsets.ReadOnlyModelViewSet):
    """Powers the mailbox dropdown. Shared across all permitted users --
    deliberately NOT filtered by request.user."""
    serializer_class = GmailAccountSerializer
    permission_classes = [IsAuthenticated]
    queryset = GmailAccount.objects.filter(is_active=True)