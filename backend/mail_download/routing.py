"""
mailfetch/routing.py

Matches your existing route shape exactly: re_path on a numeric pk.
"""
from django.urls import re_path
from mail_download.consumers import SearchJobConsumer

mail_fetch_search_ws = [
    re_path(r"^ws/mail-fetch/jobs/(?P<pk>\d+)/progress/$", SearchJobConsumer.as_asgi()),
]
