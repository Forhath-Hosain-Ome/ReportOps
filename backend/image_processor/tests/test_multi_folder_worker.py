from image_processor.tests.test_reliability import ReliabilityFixture
from docx import Document
from image_processor.lifecycle import authoritative_path


class MultiFolderWorkerTests(ReliabilityFixture):
    def test_nested_reports_and_corrupt_image_are_independent(self):
        batch = self.make_batch({"A/nested/one.png": True, "B/nested/one.png": True, "C/nested/one.png": False})
        self.run_worker(batch)
        batch.refresh_from_db()
        self.assertEqual(batch.status, "PARTIAL")
        self.assertEqual(batch.processed_folders, 2)
        self.assertEqual(batch.failed_folders, 1)
        self.assertEqual(set(batch.reports.values_list("folder_name", flat=True)), {"A/nested", "B/nested", "C/nested"})
        for report in batch.reports.filter(status="COMPLETED"):
            self.assertEqual(len(Document(authoritative_path(report)).inline_shapes), 1)
