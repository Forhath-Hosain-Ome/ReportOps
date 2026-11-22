from django.db import models
from encrypted_model_fields.fields import EncryptedTextField
from shared.models import BaseModel


class GmailAccount(BaseModel):
    """
    One company mailbox (e.g. uniqlo@pqcbd.com), configured once by an
    admin via OAuth, shared across all permitted users.

    Replaces: gmail_accounts table + client_secret.json + tokens/*.pickle
    Token data is encrypted at rest rather than an unencrypted pickle file.
    """
    email_address = models.EmailField(unique=True)
    label = models.CharField(max_length=100, blank=True)  # friendly name for the dropdown

    # OAuth token material — encrypted, never exposed via API serializers.
    access_token = EncryptedTextField()
    refresh_token = EncryptedTextField()
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.JSONField(default=list)

    is_active = models.BooleanField(default=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "mail_download"
        indexes = [models.Index(fields=["is_active"])]

    def __str__(self):
        return self.label or self.email_address
