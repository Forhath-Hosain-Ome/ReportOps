from django.db import models
from mail_download.models import GmailAccount
from shared.models import BaseModel

class SearchJob(BaseModel):
    """
    One Gmail search request. Mirrors Top5Job's shape: a Status, a
    progress_percent, an error field, and a JSON result payload -- so the
    mail-fetch consumer/task can follow the exact same snapshot/event
    pattern as top_five's.
    """
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    
    account = models.ForeignKey(GmailAccount, on_delete=models.CASCADE, related_name="search_jobs")

    query = models.TextField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    progress_percent = models.PositiveSmallIntegerField(default=0)
    stage = models.CharField(max_length=50, blank=True, default="")

    # Search results, once DONE -- list of {message_id, attachment_id,
    # filename, date} dicts. Stored on the row (not just pushed over the
    # socket) so a client that loads the page after completion can still
    # GET the job and see results, same as Top5Job presumably allows.
    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    
    class Meta:
        indexes = [models.Index(fields=["created_by", "-created_at"])]

    def __str__(self):
        return f"SearchJob#{self.pk} [{self.status}]"
