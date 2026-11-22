"""
mail_download/models.py

CORRECTED design (v2):
- GmailAccount is now a SHARED, admin-managed resource — one row per
  company mailbox (3 fixed accounts: uniqlo@pqcbd.com etc.), NOT owned by
  a single user. Any permitted logged-in user can select one from a
  dropdown and search/download through it. This matches the desktop app's
  original model much more closely than v1 did.
- The OAuth consent flow for each mailbox is run ONCE by an admin (you),
  not once per teammate. Refresh tokens live server-side, encrypted,
  shared across all users of the app.
- "Who is allowed to use this app at all" is a separate, simpler concern
  handled by Django's is_active/is_staff or a permission/group — NOT by a
  user FK on GmailAccount. Don't conflate "owns this resource" with
  "allowed to use this resource."
- DownloadHistory keeps a `user` FK purely for "who downloaded what" audit
  trail — that's still per-user, just not ownership of the account.
"""

from .gmail_account import GmailAccount
from .download_history import DownloadHistory
from .search_job import SearchJob