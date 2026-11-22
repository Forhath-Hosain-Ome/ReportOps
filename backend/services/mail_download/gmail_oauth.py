from django.conf import settings
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow

from mail_download.models import GmailAccount

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def _client_config() -> dict:
    """Build the OAuth client config from settings instead of a per-mailbox
    client_secret.json file. One registered app, used by all your users."""
    return {
        "web": {
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.GOOGLE_OAUTH_REDIRECT_URI],
        }
    }


def build_authorization_url(state: str) -> str:
    """Step 1: send the user to Google's consent screen.
    `state` should be a signed/random token you mint and store against the
    requesting user, then verify in the callback (CSRF protection)."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    auth_url, _ = flow.authorization_url(
        access_type="offline",       # request a refresh_token
        include_granted_scopes="true",
        prompt="consent",            # force refresh_token on reconnect too
    )
    return auth_url


def exchange_code_for_account(connected_by, authorization_response_url: str, state: str) -> GmailAccount:
    """Step 2 — CORRECTED (v2): upserts by `email_address` alone, since
    GmailAccount is a shared resource now, not owned by whoever ran the
    consent flow. `connected_by` is recorded purely for audit ("which
    admin authorized this mailbox"), not as an access-control owner.
    Run this once per mailbox (3 times total for your 3 accounts), not
    once per regular user."""
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, state=state)
    flow.redirect_uri = settings.GOOGLE_OAUTH_REDIRECT_URI
    flow.fetch_token(authorization_response=authorization_response_url)

    creds = flow.credentials
    email_address = _get_email_from_credentials(creds)

    account, _created = GmailAccount.objects.update_or_create(
        email_address=email_address,
        defaults=dict(
            access_token=creds.token,
            refresh_token=creds.refresh_token,
            token_expiry=creds.expiry,
            scopes=list(creds.scopes or SCOPES),
            connected_by=connected_by,
            is_active=True,
        ),
    )
    return account


def _get_email_from_credentials(creds: Credentials) -> str:
    """Call the userinfo endpoint once to learn which mailbox was authorized."""
    import google.auth.transport.requests
    import requests as _requests  # local import keeps this concern isolated

    req = google.auth.transport.requests.Request()
    creds.refresh(req) if creds.expired else None
    resp = _requests.get(
        "https://www.googleapis.com/oauth2/v2/userinfo",
        headers={"Authorization": f"Bearer {creds.token}"},
    )
    resp.raise_for_status()
    return resp.json()["email"]


def get_valid_credentials(account: GmailAccount) -> Credentials:
    """Equivalent of the desktop app's token-refresh branch in
    get_gmail_credentials(). Always call this before building a Gmail API
    client — it transparently refreshes and persists a new access token
    if the old one expired."""
    creds = Credentials(
        token=account.access_token,
        refresh_token=account.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_OAUTH_CLIENT_ID,
        client_secret=settings.GOOGLE_OAUTH_CLIENT_SECRET,
        scopes=account.scopes or SCOPES,
    )
    creds.expiry = account.token_expiry

    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            account.access_token = creds.token
            account.token_expiry = creds.expiry
            account.save(update_fields=["access_token", "token_expiry"])
        else:
            raise PermissionError(
                f"GmailAccount {account.id} has no usable refresh_token; "
                "user must reconnect via OAuth."
            )

    return creds
