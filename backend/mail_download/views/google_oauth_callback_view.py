from django.core.cache import cache
from rest_framework.permissions import IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from mail_download.serializers import GmailAccountSerializer
from services.mail_download import gmail_oauth



class GoogleOAuthCallbackView(APIView):
    """Admin-only callback. Creates/updates the GmailAccount row for
    whichever mailbox was just authorized; `connected_by` is recorded for
    audit only, not as an access-control owner."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        state = request.GET.get("state")
        admin_id = cache.get(f"oauth_state:{state}")
        if not admin_id or admin_id != request.user.id:
            return Response({"detail": "Invalid or expired OAuth state."}, status=400)

        account = gmail_oauth.exchange_code_for_account(
            connected_by=request.user,
            authorization_response_url=request.build_absolute_uri(),
            state=state,
        )
        cache.delete(f"oauth_state:{state}")
        return Response(GmailAccountSerializer(account).data, status=201)
