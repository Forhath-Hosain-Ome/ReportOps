from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from rest_framework.test import APIClient

from inspection_summary import storage
from inspection_summary.models import InspectionSummaryJob as Job
from inspection_summary.services import generate_job
from .helpers import JobFixture, raw_workbook, summary_workbook, upload


class ApiTests(JobFixture):
    def test_authenticated_multipart_upload_and_fixed_retention(self):
        with patch("inspection_summary.services.publish_inspection_summary_job") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/inspection-summary/jobs/", {
                    "inspection_summary": upload(summary_workbook()), "raw": upload(raw_workbook())}, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        job = Job.objects.get(pk=response.data["job_id"])
        self.assertEqual(job.created_by, self.user)
        self.assertAlmostEqual((job.expires_at - job.created_at).total_seconds(), 86400, delta=3)
        self.assertEqual(job.status, "PENDING")
        publish.assert_called_once_with(job.pk, job.dispatch_generation, str(job.dispatch_token))
        self.assertTrue(storage.input_path(job.pk, "raw").is_file())
        self.assertNotIn("input.xlsx", job.raw_path)

    def test_authentication_missing_file_corruption_and_extension(self):
        self.assertEqual(APIClient().post("/inspection-summary/jobs/", {}).status_code, 401)
        self.assertEqual(self.client.post("/inspection-summary/jobs/", {}, format="multipart").status_code, 400)
        from django.core.files.uploadedfile import SimpleUploadedFile
        for bad in [SimpleUploadedFile("bad.xlsx", b"not a workbook"), upload(raw_workbook(), "bad.xls")]:
            response = self.client.post("/inspection-summary/jobs/", {
                "inspection_summary": upload(summary_workbook()), "raw": bad}, format="multipart")
            self.assertEqual(response.status_code, 400)
        self.assertFalse(Job.objects.exists())

    def test_owner_scoped_status_and_download_no_staff_bypass(self):
        job = self.make_job(); generate_job(job.pk, job.dispatch_generation, str(job.dispatch_token))
        self.assertEqual(self.client.get(f"/inspection-summary/jobs/{job.pk}/").status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(f"/inspection-summary/jobs/{job.pk}/").status_code, 404)
        self.assertEqual(self.client.get(f"/inspection-summary/jobs/{job.pk}/download/").status_code, 404)

    def test_download_before_complete_rejected_then_streams_xlsx_once(self):
        job = self.make_job(); url = f"/inspection-summary/jobs/{job.pk}/download/"
        self.assertEqual(self.client.get(url).status_code, 409)
        self.assertEqual(generate_job(job.pk, job.dispatch_generation, str(job.dispatch_token))["status"], "COMPLETED")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Result.xlsx", response["Content-Disposition"])
        self.assertIn("spreadsheetml.sheet", response["Content-Type"])
        self.assertTrue(b"".join(response.streaming_content).startswith(b"PK"))
        response.close()

    def test_expired_download_immediately_410_without_cleanup(self):
        job = self.make_job(); generate_job(job.pk, job.dispatch_generation, str(job.dispatch_token))
        Job.objects.filter(pk=job.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertTrue(storage.output_path(job.pk).exists())
        response = self.client.get(f"/inspection-summary/jobs/{job.pk}/download/")
        self.assertEqual(response.status_code, 410)
        self.assertEqual(response.data["code"], "ARTIFACT_EXPIRED")
        self.assertFalse(self.client.get(f"/inspection-summary/jobs/{job.pk}/").data["download_ready"])

    def test_missing_output_returns_artifact_unavailable(self):
        job = self.make_job(); generate_job(job.pk, job.dispatch_generation, str(job.dispatch_token)); storage.output_path(job.pk).unlink()
        response = self.client.get(f"/inspection-summary/jobs/{job.pk}/download/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data["code"], "ARTIFACT_UNAVAILABLE")
        self.assertFalse(self.client.get(f"/inspection-summary/jobs/{job.pk}/").data["download_ready"])

    def test_stored_path_cannot_borrow_another_job_output(self):
        job = self.make_job(); other = self.make_job(); generate_job(other.pk, other.dispatch_generation, str(other.dispatch_token))
        Job.objects.filter(pk=job.pk).update(status="COMPLETED", output_path=storage.key(other.pk, "output/Result.xlsx"))
        self.assertEqual(self.client.get(f"/inspection-summary/jobs/{job.pk}/download/").status_code, 404)


    def test_actual_business_files_complete_through_upload_and_download(self):
        import io
        import os
        from pathlib import Path
        import openpyxl
        from django.core.files.uploadedfile import SimpleUploadedFile
        folder = os.environ.get("INSPECTION_SUMMARY_REFERENCE_DIR")
        if not folder:
            self.skipTest("External business files required; never commit them.")
        from .helpers import reference_summary
        root = Path(folder)
        with patch("inspection_summary.services.publish_inspection_summary_job"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post("/inspection-summary/jobs/", {
                    "inspection_summary": SimpleUploadedFile("inspection.xlsx", reference_summary(root).read_bytes()),
                    "raw": SimpleUploadedFile("raw.xlsx", (root / "Raw.xlsx").read_bytes())}, format="multipart")
        self.assertEqual(response.status_code, 202, response.data)
        identifier = response.data["job_id"]
        # Broker is mocked in this API test: explicitly simulate a queued delivery.
        Job.objects.filter(pk=identifier).update(dispatch_state=Job.Dispatch.QUEUED)
        delivered = Job.objects.get(pk=identifier)
        self.assertEqual(generate_job(identifier, delivered.dispatch_generation, str(delivered.dispatch_token))["status"], "COMPLETED")
        status = self.client.get(f"/inspection-summary/jobs/{identifier}/").data
        self.assertEqual([s["name"] for s in status["sheet_manifest"]], ["Final", "Re-Final", "Random", "INLINE-SPL", "INLINE", "100%"])
        result = self.client.get(f"/inspection-summary/jobs/{identifier}/download/")
        self.assertEqual(result.status_code, 200)
        wb = openpyxl.load_workbook(io.BytesIO(b"".join(result.streaming_content)))
        self.assertEqual(wb.sheetnames, ["QC Dashboard", "Analysis", "Summary", "100%"])
        values = [cell.value for row in wb["Summary"] for cell in row]
        self.assertIn(156132, values)
        self.assertIn(16575, values)
        self.assertEqual(len(wb.defined_names), 12)
        wb.close(); result.close()
