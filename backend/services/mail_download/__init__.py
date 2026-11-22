"""
services/downloader.py

CORRECTED (v2): no resolve_save_path(), no filesystem writes. The server
fetches attachment bytes from Gmail and hands them back to the view layer
as in-memory bytes; the view streams them to the browser as the HTTP
response body. Nothing touches disk on the server.

Two shapes needed now, matching your "single attachment OR whole set as
zip" requirement:
  - download_single(): returns bytes for one attachment
  - download_as_zip(): returns zip bytes for many
"""