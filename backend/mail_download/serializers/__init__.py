"""
mail_download/serializers.py

Design notes:
- GmailAccountSerializer: token fields are NEVER included, same rule as
  admin.py. This serializer is what the dropdown-of-3-mailboxes endpoint
  returns to the browser -- if access_token/refresh_token leaked into
  this, you'd be shipping live Gmail credentials to every logged-in
  user's browser dev tools. read_only_fields is not enough protection
  here -- the fields must be ABSENT from `fields`, not just read-only,
  because read-only fields are still serialized for output.
- DownloadHistorySerializer: plain read-only mirror of the audit model,
  used by the history list view.
- AttachmentRefSerializer / SearchRequestSerializer / DownloadZipRequestSerializer:
  these aren't ModelSerializers because they don't correspond to stored
  models -- they validate the shapes that flow between frontend <-> views
  <-> services (search filters in, attachment refs out, zip request in).
  Validating these explicitly (rather than trusting request.data.get(...)
  blindly, as the view sketches did) catches malformed requests before
  they reach the Gmail API or the zip-building code.
"""
from .attachment_ref_serializer import AttachmentRefSerializer
from .download_history_serializer import DownloadHistorySerializer
from .download_single_request_serializer import DownloadSingleRequestSerializer
from .download_zip_request_serializer import DownloadZipRequestSerializer
from .gmail_account_serializer import GmailAccountSerializer
from .search_job_serializer import SearchJobSerializer
from .search_request_serializer import SearchRequestSerializer
from .gmail_account_serializer  import GmailAccountSerializer
from .search_request_serializer import SearchRequestSerializer
