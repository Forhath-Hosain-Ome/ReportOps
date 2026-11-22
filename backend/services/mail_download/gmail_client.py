from datetime import datetime
from dataclasses import dataclass

from googleapiclient.discovery import build

from mail_download.models import GmailAccount
from .gmail_oauth import get_valid_credentials


@dataclass
class AttachmentRef:
    message_id: str
    attachment_id: str
    filename: str
    date: str


def build_query(subject: str = "", report_date: str = "", attachment_contains: str = "") -> str:
    """Direct port of build_gmail_query() — this logic was already clean
    and has no UI dependency, so it survives almost unchanged."""
    parts = []
    if subject.strip():
        parts.append(f"subject:{subject.strip()}")
    if attachment_contains.strip():
        parts.append(f"filename:{attachment_contains.strip()}")
    if report_date.strip():
        try:
            dt = datetime.strptime(report_date.strip(), "%m/%d/%Y")
            parts.append(f"after:{dt.strftime('%Y/%m/%d')}")
        except ValueError:
            pass
    parts.append("has:attachment")
    return " ".join(parts)


def _gmail_service(account: GmailAccount):
    creds = get_valid_credentials(account)
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def search_attachments(account: GmailAccount, query: str, max_results: int = 100,
                        on_progress=None) -> list[AttachmentRef]:
    """Replaces _search()'s Gmail-API portion + _extract_attachments().
    Returns plain data; the caller decides what to do with it.

    `on_progress`, if given, is called as on_progress(current, total) after
    each message is processed -- this is the ONLY hook into Celery/
    WebSocket concerns. gmail_client.py stays free of Celery/Channels
    imports; tasks.py supplies the callback that pushes over the channel
    layer. This replaced an earlier version of tasks.py that reimplemented
    this entire loop inline using _gmail_service()/_extract_attachments()
    directly -- that was duplicated logic with no real benefit; this
    callback hook is the fix."""
    service = _gmail_service(account)

    results = service.users().messages().list(
        userId="me", q=query, maxResults=max_results
    ).execute()
    messages = results.get("messages", [])
    total = len(messages)

    found: list[AttachmentRef] = []
    for i, msg in enumerate(messages):
        msg_data = service.users().messages().get(
            userId="me", id=msg["id"], format="full"
        ).execute()

        headers = msg_data.get("payload", {}).get("headers", [])
        date_str = next((h["value"] for h in headers if h["name"].lower() == "date"), "")

        found.extend(_extract_attachments(msg_data, msg["id"], date_str))

        if on_progress is not None:
            on_progress(i + 1, total)

    return found


def _extract_attachments(msg_data: dict, message_id: str, date_str: str) -> list[AttachmentRef]:
    """Direct port of _extract_attachments(), minus the Treeview insert —
    that's a presentation concern that now belongs to the API response /
    frontend, not this function."""
    refs: list[AttachmentRef] = []

    def process_parts(parts):
        for part in parts:
            filename = part.get("filename", "")
            attachment_id = part.get("body", {}).get("attachmentId")
            if filename and attachment_id:
                refs.append(AttachmentRef(
                    message_id=message_id,
                    attachment_id=attachment_id,
                    filename=filename,
                    date=date_str,
                ))
            if "parts" in part:
                process_parts(part["parts"])

    payload = msg_data.get("payload", {})
    if "parts" in payload:
        process_parts(payload["parts"])

    return refs


def fetch_attachment_bytes(account: GmailAccount, message_id: str, attachment_id: str) -> bytes:
    """Replaces the attachment-fetch + base64-decode lines inside
    download_thread()."""
    import base64

    service = _gmail_service(account)
    attachment = service.users().messages().attachments().get(
        userId="me", messageId=message_id, id=attachment_id
    ).execute()
    return base64.urlsafe_b64decode(attachment["data"])
