"""
mailfetch/tasks.py

Rewritten to follow your project's actual pattern: the task operates on
a SearchJob row (status/progress_percent/stage/result/error fields),
pushes events to the channel layer using "mailfetch_progress" /
"mailfetch_complete" types (matching SearchJobConsumer's handler method
names), and group name "mailfetch_job_{pk}" (matching the consumer's
self.group_name). This replaces the earlier group_name-string design
entirely -- there is no more group_name parameter; the pk IS the
identifier.
"""
from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

from mail_download.models import GmailAccount, SearchJob
from services.mail_download import gmail_client


def _send(job_id: int, event_type: str, **extra):
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(f"mailfetch_job_{job_id}", {
        "type": event_type,  # "mailfetch_progress" or "mailfetch_complete"
        "job_id": job_id,
        **extra,
    })


@shared_task(bind=True)
def search_task(self, job_id: int):
    """
    Runs a Gmail search for an existing SearchJob row (created by the view
    BEFORE this task is queued -- see views.py SearchView). Replaces the
    earlier version that took (account_id, query, group_name) directly;
    now it just takes job_id and reads everything else off the row, same
    as Top5Job's worker presumably does.
    """
    job = SearchJob.objects.get(pk=job_id)
    job.status = SearchJob.Status.RUNNING
    job.stage = "searching"
    job.save(update_fields=["status", "stage"])
    _send(job.id, "mailfetch_progress", status=job.status, stage=job.stage, progress_percent=0)

    account = GmailAccount.objects.get(pk=job.account_id)

    def on_progress(current, total):
        percent = int((current / total) * 100) if total else 100
        job.progress_percent = percent
        job.stage = f"{current}/{total} messages scanned"
        job.save(update_fields=["progress_percent", "stage"])
        _send(job.id, "mailfetch_progress", status=job.status,
              stage=job.stage, progress_percent=percent)

    try:
        refs = gmail_client.search_attachments(account, job.query, on_progress=on_progress)
    except Exception as exc:
        job.status = SearchJob.Status.FAILED
        job.error = str(exc)
        job.save(update_fields=["status", "error"])
        _send(job.id, "mailfetch_complete", status=job.status)
        raise

    result = [
        {"message_id": r.message_id, "attachment_id": r.attachment_id,
         "filename": r.filename, "date": r.date}
        for r in refs
    ]
    job.status = SearchJob.Status.DONE
    job.progress_percent = 100
    job.result = result
    job.save(update_fields=["status", "progress_percent", "result"])
    _send(job.id, "mailfetch_complete", status=job.status, result=result)
    return result
