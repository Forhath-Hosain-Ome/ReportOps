"""
mailfetch/urls.py

Routing for the mailfetch app. Wire this into your project's root
urls.py with something like:

    path("mail-fetch/", include("mailfetch.urls")),

(matches the frontend client's baseURL: "/mail-fetch/")

Design notes:
- ViewSets (GmailAccountViewSet, DownloadHistoryViewSet) go through a
  DRF router -- read-only, no create/update/delete URLs exposed.
- SearchView (POST, creates a SearchJob + queues the task) and
  SearchJobViewSet (GET by id, for fetching job status) are split: the
  create action isn't a REST-standard "POST to viewset" because it does
  more than persist a row (it also kicks off Celery) -- kept explicit
  for clarity, while retrieval reuses the router like other read-only
  resources.
- OAuth and download views are routed explicitly -- they don't map onto
  REST resource semantics (OAuth is a redirect flow, download streams
  bytes), so forcing them through a router would obscure what they do.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    GmailAccountViewSet,
    DownloadHistoryViewSet,
    SearchJobViewSet,
    GoogleOAuthStartView,
    GoogleOAuthCallbackView,
    SearchView,
    DownloadSingleView,
    DownloadZipView,
)

app_name = "mail_download"

router = DefaultRouter()
router.register(r"accounts", GmailAccountViewSet, basename="gmail-account")
router.register(r"history", DownloadHistoryViewSet, basename="download-history")
router.register(r"search", SearchJobViewSet, basename="search-job")  # GET (list/retrieve) only

urlpatterns = [
    # OAuth setup -- admin-only, run once per mailbox.
    path("oauth/start/", GoogleOAuthStartView.as_view(), name="gmail-oauth-start"),
    path("oauth/callback/", GoogleOAuthCallbackView.as_view(), name="gmail-oauth-callback"),

    # Search -- POST creates a SearchJob + queues search_task(job_id).
    # GET /search/{id}/ (job status) is handled by SearchJobViewSet below
    # via the router, NOT by this path.
    path("search/", SearchView.as_view(), name="gmail-search-start"),

    # Downloads -- synchronous, stream bytes straight to the browser.
    path("download/", DownloadSingleView.as_view(), name="gmail-download-single"),
    path("download-zip/", DownloadZipView.as_view(), name="gmail-download-zip"),

    # accounts/, history/, search/{id}/ via router.
    path("", include(router.urls)),
]
