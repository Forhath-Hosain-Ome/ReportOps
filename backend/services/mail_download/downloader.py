
import io
import zipfile

from mail_download.models import DownloadHistory, GmailAccount
from .gmail_client import fetch_attachment_bytes


def already_downloaded(account: GmailAccount, filename: str) -> bool:
    """Equivalent of was_downloaded(). Keys off `account`, not `user` --
    see the dedupe-semantics note on DownloadHistory. If you want
    per-user dedupe instead, add user=... to this filter AND decide that
    explicitly, don't let it drift silently."""
    return DownloadHistory.objects.filter(
        account=account, filename=filename, status="success"
    ).exists()


def _fetch_and_record(user, account, message_id, attachment_id, filename) -> bytes:
    """Fetch one attachment's bytes from Gmail and log the attempt.
    Raises on failure (caller decides how to surface that -- see views)."""
    try:
        data = fetch_attachment_bytes(account, message_id, attachment_id)
        DownloadHistory.objects.create(
            user=user, account=account, message_id=message_id,
            attachment_id=attachment_id, filename=filename, status="success",
        )
        return data
    except Exception as exc:
        DownloadHistory.objects.create(
            user=user, account=account, message_id=message_id,
            attachment_id=attachment_id, filename=filename,
            status="failed", error=str(exc),
        )
        raise


def download_single(user, account: GmailAccount, message_id: str,
                     attachment_id: str, filename: str) -> bytes:
    """Single-attachment download.

    BUGFIX NOTE: already_downloaded() was defined above but never called
    anywhere in the original sketch -- dedupe was dead code. Not fixed
    inline here on purpose: whether "already downloaded by a teammate"
    should (a) block the download, (b) just show a warning but still let
    it through, or (c) be informational only on the search-results list
    (so the user sees a "✓ already fetched" badge before they even click)
    is a UX decision I shouldn't guess at silently. Pick one and I'll
    wire it in -- (c) is what I'd lean toward, since it lets the user
    decide rather than the backend deciding for them.

    For now this always fetches fresh, which matches current behavior
    (the bug just meant the check was never consulted) -- so nothing
    regresses, but the check is genuinely unused until you decide.
    """
    return _fetch_and_record(user, account, message_id, attachment_id, filename)


def download_as_zip(user, account: GmailAccount, attachments: list) -> bytes:
    """
    Multi-attachment download as a single ZIP. `attachments` is
    [{message_id, attachment_id, filename}, ...] -- same shape the frontend
    already has from the search results.

    Built entirely in memory (io.BytesIO) -- never touches disk, even
    temporarily. Fine for the data volumes here (Excel reports, not video
    files); revisit only if attachment sets get into the hundreds of MB.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        seen_names = set()
        for att in attachments:
            try:
                data = _fetch_and_record(
                    user, account,
                    att["message_id"], att["attachment_id"], att["filename"],
                )
            except Exception:
                continue  # already logged as failed; skip it in the zip

            # Guard against duplicate filenames across different messages
            # (e.g. two factories both attaching "report.xlsx") -- zipfile
            # silently overwrites on collision otherwise.
            name = att["filename"]
            if name in seen_names:
                stem, _, ext = name.rpartition(".")
                name = f"{stem}_{att['message_id'][:8]}.{ext}" if ext else f"{name}_{att['message_id'][:8]}"
            seen_names.add(name)

            zf.writestr(name, data)

    buffer.seek(0)
    return buffer.read()
