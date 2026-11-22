import io
import tempfile
from pathlib import Path
from unittest.mock import patch

import openpyxl
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient


def reference_summary(folder):
    """Explicit external Input A override; never infer source from a design file."""
    import os
    return Path(os.environ["INSPECTION_SUMMARY_SOURCE_FILE"]) if os.environ.get(
        "INSPECTION_SUMMARY_SOURCE_FILE") else next(Path(folder).glob("BRANDIX*.xlsx"))


def ordinary(wb, title="Final", *, count=2, defects=2):
    ws = wb.create_sheet(title)
    ws.merge_cells(start_row=1, start_column=10, end_row=1, end_column=9 + defects)
    ws.cell(1, 10, "A: Test")
    headers = ["Factory", "Date of issue", "Inspection Type", "Item Name", "Style No",
               "Audit Qty.", "Defect Qty.", "Shipping Qty", "Person"]
    for col, value in enumerate(headers + [f"Defect {i}" for i in range(defects)], 1):
        ws.cell(2, col, value)
    ws.cell(3, 1, "合計")
    ws.cell(3, 6, "=SUM(F4:F5)")  # Uncached summary formulas are not detail data.
    for i in range(count):
        for col, value in enumerate(["Factory", f"2026-10-{i + 1:02d}", "FINAL", "Item", "Style", 100, 3, 200, None,
                                     *([1, 2] + [0] * max(0, defects - 2))], 1):
            ws.cell(4 + i, col, value)
    return ws


def raw_workbook(*, categories=35, sparse=True):
    wb = openpyxl.Workbook()
    ws = wb.active
    headers = ["Factory Name", "Inspection Date", "Style No", "Item Name", "Inspection Qty", "Pass Qty", "Defect Qty", "Inspectors"]
    for col, label in enumerate(headers + [f"Defect {i}" for i in range(categories)], 1):
        ws.cell(3, col, label)
    ws.merge_cells(start_row=1, start_column=9, end_row=1, end_column=8 + categories)
    ws.cell(1, 9, "A: Raw")
    if sparse:
        for i in range(categories):
            ws.cell(2, 9 + i, i + 1)
    ws.cell(4, 1, "合計")
    ws.cell(4, 5, 99999)  # Must not be counted.
    for r, day in [(5, "2026-10-01"), (6, "2026-10-01"), (7, "2026-10-02")]:
        values = ["Factory", day, "Style", "Item", 100, 96, 4, None, 4] + [0] * (categories - 1)
        for col, value in enumerate(values, 1):
            ws.cell(r, col, value)
    return wb


def summary_workbook():
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ordinary(wb)
    return wb


def workbook_bytes(wb):
    stream = io.BytesIO()
    wb.save(stream)
    wb.close()
    return stream.getvalue()


def upload(wb, name="input.xlsx"):
    return SimpleUploadedFile(name, workbook_bytes(wb), content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


class JobFixture(TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.media = Path(self.directory.name) / "media"
        self.media.mkdir()
        self.setting = override_settings(MEDIA_ROOT=self.media)
        self.setting.enable()
        self.addCleanup(self.setting.disable)
        self.user = get_user_model().objects.create_user(username="owner")
        self.other = get_user_model().objects.create_user(username="other", is_staff=True)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def make_job(self):
        from inspection_summary.services import create_job
        with patch("inspection_summary.services.publish_inspection_summary_job"):
            with self.captureOnCommitCallbacks(execute=True):
                job = create_job(self.user, upload(summary_workbook()), upload(raw_workbook()))
                job.dispatch_state = job.Dispatch.QUEUED
                job.save(update_fields=["dispatch_state"])
                return job
