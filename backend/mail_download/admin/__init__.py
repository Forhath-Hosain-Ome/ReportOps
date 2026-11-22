"""
mailfetch/admin.py

Design notes:
- GmailAccount: token fields (access_token, refresh_token) are NEVER
  shown, even to superusers, in any editable or readable form in the
  list/detail view. EncryptedTextField stores ciphertext in the DB, but
  Django admin would happily render the decrypted value in a form widget
  if you just listed the field normally -- so they're excluded entirely.
  A custom "Reconnect via OAuth" action covers the only legitimate reason
  an admin touches this row's credentials.
- Nobody should be able to create/edit a GmailAccount by typing tokens
  into a form field -- the only valid way to populate one is the OAuth
  exchange. So add/change of token fields is blocked; the row still shows
  up for visibility (is_active toggle, audit fields) and deletion.
- DownloadHistory: read-only audit log. No add, no edit, no delete via
  admin -- if you need to purge old rows, do it with a management command
  / data retention job, not by clicking around in admin.
"""
from .gmail_account_admin import GmailAccountAdmin
from .download_history_admin import DownloadHistoryAdmin
