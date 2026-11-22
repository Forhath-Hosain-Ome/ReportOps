import uuid

from django.core.cache import cache
from django.http import HttpResponseRedirect
from rest_framework.permissions import IsAdminUser
from rest_framework.views import APIView

from services.mail_download import gmail_oauth


class GoogleOAuthStartView(APIView):
    """Admin-only. Run once per mailbox when first connecting it."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        state = uuid.uuid4().hex
        cache.set(f"oauth_state:{state}", request.user.id, timeout=600)
        url = gmail_oauth.build_authorization_url(state=state)
        return HttpResponseRedirect(url)
