from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from xml.etree import ElementTree as ET
import zipfile

import openpyxl
from django.test import SimpleTestCase

from inspection_summary.parser import DefectColumn, parse_inspection_workbook
from inspection_summary.writer import (OutputVerificationError, detail_values, ranked_groups,
                                        raw_columns, verify_report, write_report)
from inspection_summary.template_writer import detail_spec
from inspection_summary.canonical import SHEETS
from .helpers import ordinary, raw_workbook


class WorkbookWriterFixture(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def blocks(self, names=("Final",), empty=(), raw=None):
        wb = openpyxl.Workbook(); wb.remove(wb.active)
        for name in names:
            if name == "100%":
                wb.create_sheet(name)["A1"] = "#REF!"
            else:
                ordinary(wb, name, count=0 if name in empty else 2)
        source, raw_path = self.root / "source.xlsx", self.root / "raw.xlsx"
        wb.save(source); wb.close()
        raw = raw or raw_workbook(); raw.save(raw_path); raw.close()
        return parse_inspection_workbook(source, raw_path)

    def output(self, blocks):
        path = self.root / "Result.xlsx"
        write_report(blocks, path); verify_report(path, blocks)
        return path

    def titles(self, wb):
        return [wb.defined_names[n].comment for n in sorted(wb.defined_names) if n.startswith("InspectionBlock_")]


class WriterTests(WorkbookWriterFixture):
    def test_dynamic_matrix_has_no_missing_type_placeholders(self):
        cases = [
            (["Final", "100%"], (), ["Final", "100%"]),
            (["Final", "Re-Final", "Random", "100%"], (), ["Final", "Re-Final", "Random", "100%"]),
            (["INLINE-SPL", "INLINE"], (), ["INLINE-SPL", "INLINE", "100%"]),
            (["Final", "Re-Final", "INLINE"], ("Re-Final",), ["Final", "Re-Final", "INLINE", "100%"]),
            (["100%", "Renamed recognized stage"], (), ["100%", "Renamed recognized stage"]),
        ]
        for names, empty, expected in cases:
            with self.subTest(names=names):
                blocks = self.blocks(names, empty)
                wb = openpyxl.load_workbook(self.output(blocks)); ws = wb["Summary"]
                self.assertEqual(wb.sheetnames, SHEETS if "Final" in names else SHEETS[1:])
                self.assertEqual(self.titles(wb), expected)
                self.assertEqual(len(wb.defined_names), len(expected) * 2)
                self.assertEqual(sum(label == "100%" for label in self.titles(wb)), 1)
                anchors = [ws[list(wb.defined_names[n].destinations)[0][1]].row for n in sorted(wb.defined_names) if n.startswith("InspectionBlock_")]
                self.assertEqual(anchors, sorted(anchors))
                self.assertLess(ws.max_row, 80)
                if empty:
                    self.assertIn("No inspection records found for this section.", [c.value for row in ws for c in row])
                self.assertEqual(str(ws.print_area), f"'Summary'!$A$1:$M$" + str(ws.max_row + 1))
                self.assertIn(f"A{anchors[0]}:M{anchors[0]}", str(ws.merged_cells))
                wb.close()

    def test_five_distinct_ranks_keep_all_ties_and_use_defect_denominator(self):
        blocks = self.blocks(); block = blocks[0]
        block.defect_schema = [DefectColumn(i + 1, "A: Category", f"Defect {i}") for i in range(9)]
        block.defect_totals = [7, 6, 4, 4, 3, 2, 2, 1, 1]
        block.defect_qty = 30
        block.records[0].update(categories=block.defect_totals, defect=30)
        block.records[1].update(categories=[0] * 9, defect=0)
        groups = ranked_groups(block)
        self.assertEqual([qty for qty, _ in groups], [7, 6, 4, 3, 2])
        self.assertEqual([d.label for _, members in groups for d in members],
                         [f"Defect {i}" for i in range(7)])
        wb = openpyxl.load_workbook(self.output(blocks)); ws = wb["Summary"]
        row = next(c.row for line in ws for c in line if c.value == "Categories") + 1
        self.assertAlmostEqual(ws.cell(row, 6).value, 7 / 30)
        self.assertNotAlmostEqual(ws.cell(row, 6).value, 7 / block.inspected_qty)
        self.assertIn("Defect 2, Defect 3", [c.value for line in ws for c in line])
        wb.close()

    def test_large_tie_is_not_truncated_or_duplicate(self):
        blocks = self.blocks(); block = blocks[0]
        block.defect_schema = [DefectColumn(i + 1, "A", f"Tied {i}") for i in range(18)]
        block.defect_totals = [2] * 18; block.defect_qty = 36
        block.records[0].update(categories=block.defect_totals, defect=36)
        block.records[1].update(categories=[0] * 18, defect=0)
        wb = openpyxl.load_workbook(self.output(blocks)); ws = wb["Summary"]
        cells = [c.value for row in ws for c in row if isinstance(c.value, str)]
        for i in range(18):
            self.assertEqual(sum(f"Tied {i}" in text.split(", ") for text in cells), 1)
        self.assertTrue(all(d.height <= 409 for d in ws.row_dimensions.values()))
        wb.close()

    def test_unique_days_are_not_audit_count(self):
        wb = raw_workbook()
        blocks = self.blocks(raw=wb)
        self.assertEqual(blocks[-1].inspection_count, 3)
        self.assertEqual(blocks[-1].inspection_days, 2)
        out = openpyxl.load_workbook(self.output(blocks))
        values = [c.value for row in out["Summary"] for c in row]
        self.assertIn("Total: 01-Style", values); self.assertIn("(02 Days)", values)
        out.close()

    def test_raw_detail_source_values_schema_sparse_blanks_and_pass_missing(self):
        raw = raw_workbook(); raw.active.cell(5, 6).value = None
        raw.active.cell(5, 10).value = None
        raw.active.cell(5, 3).value = "=UNTRUSTED()"
        # A literal text style must remain text, not be evaluated.
        raw.active.cell(5, 3).data_type = "s"
        blocks = self.blocks(["100%", "Final"], raw=raw)
        block = blocks[0]; fields = raw_columns(block)
        self.assertEqual(len(block.raw_rows), 3)
        self.assertIsNone(block.raw_rows[0][fields["pass"]])
        self.assertEqual(block.raw_rows[0][-34], 0)
        self.assertIsNone(block.pass_qty)
        path = self.output(blocks); wb = openpyxl.load_workbook(path); ws = wb["100%"]
        self.assertEqual([ws.cell(3, i).value for i in range(5, 40)], block.raw_headers[-35:])
        self.assertEqual(ws.cell(4, 3).data_type, "s")
        self.assertIsNone(ws.cell(4, 41).value)
        self.assertEqual(ws.freeze_panes, "E4"); self.assertTrue(ws.auto_filter.ref)
        self.assertEqual(ws.print_title_rows, "$1:$3")
        self.assertEqual([d.label for d in block.defect_schema], block.raw_headers[-35:])
        self.assertEqual(sum(row[fields["inspected"]] for row in block.raw_rows), block.inspected_qty)
        wb.close()

    def test_weekly_subtotals_are_not_extra_detail_or_calendar_records(self):
        blocks = self.blocks(); block = blocks[-1]; fields = raw_columns(block)
        raw = raw_workbook()
        raw.active.cell(7, 2).value = "2026-10-03"
        block = self.blocks(raw=raw)[-1]
        rows = detail_values(block)
        self.assertEqual(sum(kind == "detail" for kind, _ in rows), 3)
        self.assertEqual(sum(kind == "subtotal" for kind, _ in rows), 2)
        self.assertEqual(rows[-1][1][fields["inspected"]], 300)
        self.assertEqual(rows[-1][1][fields["pass"]], 288)
        self.assertEqual(rows[-1][1][fields["defect"]], 12)

    def test_optional_source_text_and_missing_values_are_not_coerced_into_totals(self):
        source = raw_workbook(); raw = openpyxl.Workbook(); ws = raw.active
        headers = [c.value for c in source.active[3]]
        labels = headers[:8] + ["Order Qty", "Report No", "Working Hour"] + headers[8:]
        for col, value in enumerate(labels, 1): ws.cell(3, col, value)
        ws.merge_cells(start_row=1, start_column=12, end_row=1, end_column=46)
        ws.cell(1, 12, "A: Raw")
        for col, marker in enumerate(range(1, 36), 12): ws.cell(2, col, marker)
        for row in range(5, 8):
            values = [c.value for c in source.active[row]]
            for col, value in enumerate(values[:8] + ["1,000", None, 3.5] + values[8:], 1):
                ws.cell(row, col, value)
        source.close()
        blocks = self.blocks(raw=raw); block = blocks[-1]
        self.assertEqual(block.raw_rows[0][8:11], ["1,000", None, 3.5])
        self.assertIsNone(detail_values(block)[-1][1][8])
        wb = openpyxl.load_workbook(self.output(blocks))
        self.assertEqual(wb["100%"].cell(4, detail_spec(block).index(8) + 1).value, "1,000")
        self.assertIsNone(wb["100%"].cell(4, detail_spec(block).index(9) + 1).value)
        wb.close()

    def test_verification_rejects_detail_header_record_total_summary_or_extra_sheet(self):
        blocks = self.blocks()
        for change in ["header", "record", "total", "summary", "extra", "hidden", "formula", "unanchored", "boolean"]:
            with self.subTest(change=change):
                path = self.output(blocks); wb = openpyxl.load_workbook(path)
                ws = wb["100%"]
                if change == "header": ws.cell(3, 5, "Unknown")
                if change == "record": ws.cell(4, 4, 999)
                if change == "total": ws.cell(ws.max_row - 1, 4, 999)
                if change == "summary": wb["Summary"].cell(4, 8, 999)
                if change == "extra": wb.create_sheet("Extra").sheet_state = "hidden"
                if change == "hidden": ws.sheet_state = "hidden"
                if change == "formula": ws.cell(5, 1, "=1+1")
                if change == "unanchored": wb["Summary"].cell(wb["Summary"].max_row + 2, 1, "Unexpected block")
                if change == "boolean": ws.cell(4, 4, True)
                wb.save(path); wb.close()
                with self.assertRaises(OutputVerificationError): verify_report(path, blocks)

    def test_duplicate_defined_name_is_rejected_before_mapping_collapses_it(self):
        blocks = self.blocks(); path = self.output(blocks)
        with zipfile.ZipFile(path) as source: parts = {n: source.read(n) for n in source.namelist()}
        root = ET.fromstring(parts["xl/workbook.xml"])
        node = root.find("{http://schemas.openxmlformats.org/spreadsheetml/2006/main}definedNames")
        node.append(deepcopy(node[0])); parts["xl/workbook.xml"] = ET.tostring(root)
        with zipfile.ZipFile(path, "w") as out:
            for name, data in parts.items(): out.writestr(name, data)
        with self.assertRaises(OutputVerificationError): verify_report(path, blocks)

    def test_empty_block_has_no_unsupported_zero_or_personnel(self):
        blocks = self.blocks(["Empty"], empty=["Empty"])
        wb = openpyxl.load_workbook(self.output(blocks)); ws = wb["Summary"]
        next_row = ws[list(wb.defined_names["InspectionBlock_001"].destinations)[0][1]].row
        values = [c.value for row in ws.iter_rows(max_row=next_row - 1) for c in row]
        self.assertIsNone(ws.cell(4, 5).value)
        self.assertNotIn("Personnel / Inspector(s)", values)
        self.assertIn("Total: 00-Audit", values)
        wb.close()
