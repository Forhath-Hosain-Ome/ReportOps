import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless

from django.test import SimpleTestCase

from inspection_summary.raw_parser import parse_raw_workbook
from inspection_summary.workbook_security import WorkbookValidationError
from .helpers import raw_workbook, reference_summary


class RawTests(SimpleTestCase):
    def parse(self, wb):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "raw.xlsx"
            wb.save(path)
            return parse_raw_workbook(path)

    def test_daily_aggregation_excludes_totals(self):
        block = self.parse(raw_workbook())
        self.assertEqual(block.inspected_qty, 300)
        self.assertEqual(block.defect_qty, 12)
        self.assertEqual([d["inspected"] for d in block.daily_rows], [200, 100])
        for day in block.daily_rows:
            self.assertEqual(day["defect"], sum(day["categories"]))

    def test_dynamic_counts_and_repeated_labels_remain_separate(self):
        for count in [34, 36]:
            with self.subTest(count=count):
                self.assertEqual(len(self.parse(raw_workbook(categories=count)).defect_schema), count)
        wb = raw_workbook(); wb.active.cell(3, 10, "Defect 0")
        block = self.parse(wb)
        self.assertEqual([d.occurrence for d in block.defect_schema[:2]], [1, 2])
        self.assertEqual(block.defect_totals[:2], [12, 0])

    def test_sparse_blanks_only_under_explicit_numbered_schema(self):
        wb = raw_workbook(); wb.active.cell(5, 10).value = None
        self.assertEqual(self.parse(wb).defect_qty, 12)
        wb.active.cell(2, 10).value = None
        with self.assertRaises(WorkbookValidationError) as caught: self.parse(wb)
        self.assertEqual(caught.exception.code, "DEFECT_NUMBERING_INVALID")

    def test_sparse_marker_types_and_ordinals_are_strict(self):
        for marker in [True, False, "1", "01", 1.5, None, 2, 0]:
            with self.subTest(marker=marker):
                wb = raw_workbook(); wb.active.cell(2, 9).value = marker
                with self.assertRaises(WorkbookValidationError): self.parse(wb)
        for band in [list(range(35)), [2, 1] + list(range(3, 36))]:
            wb = raw_workbook()
            for col, value in enumerate(band, 9): wb.active.cell(2, col, value)
            with self.assertRaises(WorkbookValidationError): self.parse(wb)

    def test_dense_schema_never_zero_fills_without_marker_band(self):
        self.assertEqual(self.parse(raw_workbook(sparse=False)).defect_qty, 12)
        wb = raw_workbook(sparse=False); wb.active.cell(5, 10).value = None
        with self.assertRaises(WorkbookValidationError) as caught: self.parse(wb)
        self.assertEqual(caught.exception.code, "DEFECT_QUANTITY_INVALID")

    def test_missing_pass_is_not_derived(self):
        wb = raw_workbook(); wb.active.cell(5, 6).value = None
        self.assertIsNone(self.parse(wb).daily_rows[0]["pass"])

    def test_required_quantities_never_default_to_zero(self):
        for col in [5, 7]:
            wb = raw_workbook(); wb.active.cell(5, col).value = None
            with self.assertRaises(WorkbookValidationError): self.parse(wb)

    def test_row_reconciliation_mismatch_fails(self):
        wb = raw_workbook(); wb.active.cell(5, 7, 5)
        with self.assertRaises(WorkbookValidationError) as caught: self.parse(wb)
        self.assertEqual(caught.exception.code, "DEFECT_TOTAL_MISMATCH")

    def test_ambiguous_tables_fail(self):
        wb = raw_workbook(); wb.copy_worksheet(wb.active)
        with self.assertRaises(WorkbookValidationError): self.parse(wb)

    def test_invalid_date_fails(self):
        wb = raw_workbook(); wb.active.cell(5, 2, "10/11/26")
        with self.assertRaises(WorkbookValidationError): self.parse(wb)


@skipUnless(os.environ.get("INSPECTION_SUMMARY_REFERENCE_DIR"), "Supply external business workbooks; never commit them.")
class SuppliedWorkbookTests(SimpleTestCase):
    def test_actual_raw_acceptance_totals(self):
        block = parse_raw_workbook(Path(os.environ["INSPECTION_SUMMARY_REFERENCE_DIR"]) / "Raw.xlsx")
        self.assertEqual(block.inspection_count, 83)
        self.assertEqual(block.inspected_qty, 156132)
        self.assertEqual(block.defect_qty, 16575)
        self.assertEqual(sum(sum(day["categories"]) for day in block.daily_rows), 16575)
        self.assertEqual(len(block.defect_schema), 35)
        self.assertEqual(len(block.daily_rows), 13)
        self.assertEqual(block.pass_qty, 139557)
        self.assertEqual(block.inspection_days, 13)
        self.assertEqual(len(block.raw_rows), 83)
        self.assertEqual(len(block.raw_headers), 54)
        # Independently compare every copied prefix and defect value with source.
        import openpyxl
        from datetime import date
        source = openpyxl.load_workbook(Path(os.environ["INSPECTION_SUMMARY_REFERENCE_DIR"]) / "Raw.xlsx",
                                        data_only=True, read_only=True, keep_links=False)
        try:
            expected = []
            for row in source.active.iter_rows(min_row=6, values_only=True):
                if row[1] is None:
                    continue
                values = list(row[:54])
                values[1] = date.fromisoformat(values[1])
                values[19:] = [0 if v is None else v for v in values[19:]]
                expected.append(values)
            self.assertEqual(block.raw_rows, sorted(expected, key=lambda row: row[1]))
        finally:
            source.close()

    def test_actual_visible_blocks_and_independent_schemas(self):
        from inspection_summary.parser import parse_inspection_workbook
        folder = Path(os.environ["INSPECTION_SUMMARY_REFERENCE_DIR"])
        blocks = parse_inspection_workbook(reference_summary(folder), folder / "Raw.xlsx")
        self.assertEqual([b.report_name for b in blocks], ["Final", "Re-Final", "Random", "INLINE-SPL", "INLINE", "100%"])
        self.assertEqual([len(b.defect_schema) for b in blocks], [78, 78, 78, 78, 35, 35])
