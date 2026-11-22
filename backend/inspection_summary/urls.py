from django.urls import path

from .views import JobCreateView, JobDetailView, JobDownloadView, JobPreviewView

app_name = "inspection_summary"
urlpatterns = [
    path("jobs/", JobCreateView.as_view(), name="job-create"),
    path("jobs/<uuid:pk>/", JobDetailView.as_view(), name="job-detail"),
    path("jobs/<uuid:pk>/preview/", JobPreviewView.as_view(), name="job-preview"),
    path("jobs/<uuid:pk>/download/", JobDownloadView.as_view(), name="job-download"),
]
