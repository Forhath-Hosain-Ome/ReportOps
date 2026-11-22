from django.db import models
from .gmail_account import GmailAccount
from shared.models import BaseModel

class DownloadHistory(BaseModel):
    """
    One row per attempted attachment download — an AUDIT LOG only.
    CORRECTED (v2): there is no `saved_path` anymore. The server never
    persists the downloaded bytes — it fetches from Gmail and streams
    straight through to the user's browser response, then discards them.
    This row exists purely so "was this already downloaded" and "who
    downloaded what, when" can still be answered, matching the desktop
    app's was_downloaded()/record_download() behavior.

    Dedupe semantics decision: this keys off `account` (shared mailbox),
    not `user` — "already downloaded by ANY teammate" is almost certainly
    what you want for a shared team tool, otherwise every teammate
    re-downloads the same factory report. If you actually want
    per-user dedupe instead, add `user` into the dedupe lookup in
    downloader.py — don't add it here without deciding that first.
    """
    account = models.ForeignKey(GmailAccount, on_delete=models.CASCADE, related_name="downloads")

    message_id = models.CharField(max_length=64)
    attachment_id = models.CharField(max_length=128)
    filename = models.CharField(max_length=255)
    status = models.CharField(max_length=10, choices=[
        ("success", "Success"), ("failed", "Failed"),
    ])
    error = models.TextField(blank=True, default="")

    class Meta:
        app_label = "mail_download"
        indexes = [
            models.Index(fields=["account", "filename", "status"]),
            models.Index(fields=["created_by", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.filename} [{self.status}]"