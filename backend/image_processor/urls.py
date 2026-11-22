from django.urls import path
from image_processor.views.reliability_view import FolderBatchRetryView, ImageSettingsView
from image_processor.views import (
    FolderUploadView,
    FolderBatchListView,
    FolderBatchDetailView,
    FolderBatchLogsView,
    FolderPDFDownloadView,
    FolderReportListView,
    FolderReportDetailView,
    FolderDOCXDownloadView,
)


app_name = "image"



# ─────────────────────────────────────────────────────────────────────────────
#  Folder
#  POST   /image/folder/upload/         → upload images, create batch, fire task
#  GET    /image/folder/batches/        → paginated batch list
#  GET    /image/folder/batches/<pk>/   → full batch detail + nested reports
#  GET    /image/folder/batches/<pk>/logs/ → structured {folder_name, reason} log
# ─────────────────────────────────────────────────────────────────────────────


folder_urlpatterns = [
    path("settings/", ImageSettingsView.as_view(), name="settings"),
    path("folder/batches/<int:pk>/retry/", FolderBatchRetryView.as_view(), name="folder_batch_retry"),
    path("folder/upload/",              FolderUploadView.as_view(), name="folder_upload"),
    path("folder/batches/",             FolderBatchListView.as_view(), name="folder_batch_list"),
    path("folder/batches/<int:pk>/",    FolderBatchDetailView.as_view(), name="folder_batch_detail"),
    path("folder/batches/<int:pk>/logs/", FolderBatchLogsView.as_view(), name="folder_batch_logs"),
]

# ─────────────────────────────────────────────────────────────────────────────
#  REPORTS
#  GET    /image/folder/reports/              → paginated + filtered report list
#  GET    /image/folder/reports/<pk>/         → full report detail
#  GET    /image/folder/reports/<pk>/pdf/     → stream PDF download
#  GET    /image/folder/reports/<pk>/docx/    → stream DOCX zip download
# ─────────────────────────────────────────────────────────────────────────────

report_urlpatterns = [
    path("folder/reports/",             FolderReportListView.as_view(), name="folder_report_list"),
    path("folder/reports/<int:pk>/",    FolderReportDetailView.as_view(), name="folder_report_detail"),
    path("folder/reports/<int:pk>/pdf/", FolderPDFDownloadView.as_view(), name="folder_report_pdf_download"),
    path("folder/reports/<int:pk>/docx/", FolderDOCXDownloadView.as_view(), name="folder_report_docx_download"),
]


# ─────────────────────────────────────────────────────────────────────────────
#  COMBINED — imported by the root urls.py
#
#  In your project's config/urls.py add:
#
#      from django.urls import include, path
#      urlpatterns = [
#          path("api/", include("image_processor.urls", namespace="image")),
#      ]
# ─────────────────────────────────────────────────────────────────────────────

urlpatterns = folder_urlpatterns + report_urlpatterns
