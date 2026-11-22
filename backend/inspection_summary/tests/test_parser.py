from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase
import openpyxl

from inspection_summary.parser import parse_inspection_workbook, parse_ordinary_sheet
from inspection_summary.workbook_security import WorkbookValidationError
from .helpers import ordinary, raw_workbook, summary_workbook


class ParserTests(SimpleTestCase):
    def parse(self, wb):
        with TemporaryDirectory() as directory:
            source, raw = Path(directory) / "summary.xlsx", Path(directory) / "raw.xlsx"
            wb.save(source)
            raw_workbook().save(raw)
            return parse_inspection_workbook(source, raw)

    def test_visible_sheet_order_and_inline_independence(self):
        wb = summary_workbook()
        ordinary(wb, "INLINE-SPL", defects=3)
        ordinary(wb, "INLINE")
        blocks = self.parse(wb)
        self.assertEqual([b.report_name for b in blocks], ["Final", "INLINE-SPL", "INLINE", "100%"])
        self.assertEqual([len(b.defect_schema) for b in blocks[:-1]], [2, 3, 2])

    def test_hidden_and_very_hidden_ignored(self):
        wb = summary_workbook()
        for name, visibility in [("Hidden", "hidden"), ("VeryHidden", "veryHidden")]:
            wb.create_sheet(name).sheet_state = visibility
        self.assertEqual([b.report_name for b in self.parse(wb)], ["Final", "100%"])

    def test_recognized_renamed_sheet_parses(self):
        wb = summary_workbook()
        wb.active.title = "New inspection stage"
        self.assertEqual(self.parse(wb)[0].report_name, "New inspection stage")

    def test_unknown_visible_sheet_fails(self):
        wb = summary_workbook()
        wb.create_sheet("Unsupported")
        with self.assertRaisesRegex(WorkbookValidationError, "header band"):
            self.parse(wb)

    def test_empty_recognized_sheet_creates_empty_block(self):
        wb = openpyxl.Workbook(); wb.remove(wb.active)
        ordinary(wb, "Empty", count=0)
        block = self.parse(wb)[0]
        self.assertTrue(block.empty_state)
        self.assertEqual(block.inspection_count, 0)
        self.assertIsNone(block.inspected_qty)
        self.assertIsNone(block.defect_qty)

    def test_missing_values_and_personnel_remain_missing(self):
        wb = summary_workbook()
        wb.active["F4"] = None
        wb.active["J4"] = None
        blocks = self.parse(wb)
        self.assertIsNone(blocks[0].inspected_qty)
        self.assertEqual(blocks[0].personnel, [])
        self.assertTrue(all(d.ratio is None for d in blocks[0].top_defects))

    def test_uncached_required_formula_fails(self):
        wb = summary_workbook(); wb.active["F4"] = "=50+50"
        with self.assertRaises(WorkbookValidationError) as caught:
            self.parse(wb)
        self.assertEqual(caught.exception.code, "FORMULA_VALUE_UNAVAILABLE")

    def test_100_percent_uses_raw_and_source_position(self):
        wb = summary_workbook()
        hundred = wb.create_sheet("100%", 0)
        hundred["A1"] = "#REF!"  # Must never be consumed.
        ordinary(wb, "Last")
        blocks = self.parse(wb)
        self.assertEqual([b.report_name for b in blocks], ["100%", "Final", "Last"])
        self.assertEqual(blocks[0].inspected_qty, 300)

    def test_duplicate_100_percent_rejected(self):
        wb = summary_workbook(); wb.create_sheet("100%"); wb.create_sheet("100% ")
        with self.assertRaises(WorkbookValidationError) as caught:
            self.parse(wb)
        self.assertEqual(caught.exception.code, "DUPLICATE_100_PERCENT")

    def test_deterministic_top_five_ties_use_column_order(self):
        wb = summary_workbook(); wb.active["J4"] = 2; wb.active["J5"] = 2
        self.assertEqual([d.label for d in self.parse(wb)[0].top_defects], ["Defect 0", "Defect 1"])

    def test_invalid_quantity_and_missing_date_fail(self):
        for cell, value in [("F4", True), ("F4", -1), ("F4", 1.5), ("B4", None)]:
            with self.subTest(cell=cell, value=value):
                wb = summary_workbook(); wb.active[cell] = value
                with self.assertRaises(WorkbookValidationError): self.parse(wb)
