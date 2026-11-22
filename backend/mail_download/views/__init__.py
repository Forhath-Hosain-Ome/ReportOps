"""
mailfetch/views.py

Thin DRF layer: every view validates input through a serializer, then
calls into services/ or tasks.py. No Gmail API calls, no file I/O, no
query-building happens here directly -- that all lives in services/.

Design recap (matches the agreed architecture):
- GmailAccountViewSet: shared list of 3 admin-configured mailboxes,
  visible to any authenticated user -- no per-user filtering.
- OAuth start/callback: admin-only, run once per mailbox at setup time.
- SearchView: kicks off search_task (Celery) and returns a group_name
  for the frontend's existing WebSocket client to subscribe to.
- DownloadSingleView / DownloadZipView: plain synchronous views,
  validated input in, bytes streamed straight to the browser response.
  No Celery, no task id, no server-side file -- nothing touches disk.
- DownloadHistoryViewSet: per-user filtered audit view ("what have I
  downloaded") -- this is an audit lens, not an ownership boundary.
"""
from .gmail_account_view_set import GmailAccountViewSet
from .download_history_view_set import DownloadHistoryViewSet
from .search_job_view_set import SearchJobViewSet
from .google_oauth_start_view import GoogleOAuthStartView
from .google_oauth_callback_view import GoogleOAuthCallbackView
from .search_view import SearchView
from .download_single_view import DownloadSingleView
from .download_zip_view import DownloadZipView