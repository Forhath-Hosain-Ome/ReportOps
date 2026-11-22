import hashlib
import json
from copy import copy
from pathlib import Path

import openpyxl

from inspection_summary import canonical as tpl
from inspection_summary.parser import parse_inspection_workbook
from inspection_summary.report_data import dashboard_scope, manpower, ranked_groups, style_key
from inspection_summary.template_writer import detail_spec
from .helpers import ordinary, raw_workbook
from .test_writer import WorkbookWriterFixture


class CanonicalTests(WorkbookWriterFixture):
    def test_dashboard_static_fidelity_and_all_original_artifacts(self):
        path = self.output(self.blocks())
        manifest = json.loads(tpl.MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(hashlib.sha256(tpl.ASSET.read_bytes()).hexdigest(), manifest["asset_sha256"])
        wb = openpyxl.load_workbook(path)
        self.assertEqual(json.loads(json.dumps(tpl.dashboard_profile(wb["QC Dashboard"]))), manifest["dashboard_profile"])
        self.assertEqual(len(wb["QC Dashboard"]._images), 37)
        self.assertEqual(len(wb["QC Dashboard"]._charts), 3)
        parts = tpl.read_package(path)
        for name, expected in manifest["dashboard_artifacts"].items():
            self.assertEqual(hashlib.sha256(parts[name]).hexdigest(), expected, name)
        for name, expected in manifest["dashboard_chart_styles"].items():
            self.assertEqual(tpl.chart_fingerprint(parts[name]), expected, name)
        wb.close()

    def test_asset_has_no_sample_records_or_cached_business_values(self):
        wb = openpyxl.load_workbook(tpl.ASSET)
        self.assertEqual(wb.sheetnames, tpl.SHEETS)
        self.assertIsNone(wb["QC Dashboard"]["G9"].value)
        self.assertIsNone(wb["Analysis"]["C44"].value)
        self.assertIsNone(wb["Summary"]["F7"].value)
        self.assertIsNone(wb["100%"]["E4"].value)
        wb.close()
        for name, data in tpl.read_package(tpl.ASSET).items():
            if "/charts/" in name and name.endswith(".xml") and "/_rels/" not in name:
                root = tpl.parse(data)
                self.assertEqual(root.findall(".//c:numCache/c:pt", tpl.NS), [], name)
                self.assertNotIn(b"#REF!", data)

    def test_analysis_and_summary_share_ranks_with_different_denominators(self):
        blocks = self.blocks(["Final", "Re-Final", "Random", "INLINE-SPL", "INLINE"])
        wb = openpyxl.load_workbook(self.output(blocks))
        for index, block in enumerate(blocks):
            anchors = [wb[s][list(wb.defined_names[p + f"{index:03d}"].destinations)[0][1]].row
                       for s, p in [("Analysis", "AnalysisBlock_"), ("Summary", "InspectionBlock_")]]
            starts = []
            for sheet, start in zip(("Analysis", "Summary"), anchors):
                row = next(r for r in range(start, start + 7) if wb[sheet].cell(r, 3).value == "Categories")
                starts.append(row + 1)
                expected = len(block.styles) if block.kind == "raw" else block.inspection_count
                suffix = "Style" if block.kind == "raw" else "Audit"
                self.assertEqual(wb[sheet].cell(start + 2, 1).value, f"Total: {expected:02d}-{suffix}")
                self.assertEqual(wb[sheet].cell(start + 1, 8).value, f"({block.inspection_days:02d} Days)")
            for i in range(len(ranked_groups(block))):
                a, s = starts[0] + i, starts[1] + i
                self.assertEqual([wb['Analysis'].cell(a, c).value for c in range(2, 6)],
                                 [wb['Summary'].cell(s, c).value for c in range(2, 6)])
                qty = wb['Summary'].cell(s, 5).value
                self.assertAlmostEqual(wb['Analysis'].cell(a, 6).value, qty / block.inspected_qty)
                self.assertAlmostEqual(wb['Summary'].cell(s, 6).value, qty / block.defect_qty)
        self.assertEqual(len(wb['Analysis']._charts), len(blocks))
        self.assertEqual(len(wb['Summary']._charts), len(blocks))
        wb.close()

    def test_dynamic_manifests_match_on_both_sheets(self):
        for names, empty in [(["Final"], ()), (["Final", "Re-Final", "Random"], ()),
                             (["INLINE-SPL", "INLINE"], ()), (["Re-Final"], ("Re-Final",))]:
            with self.subTest(names=names):
                blocks = self.blocks(names, empty)
                wb = openpyxl.load_workbook(self.output(blocks))
                expected = [b.report_name for b in blocks]
                for prefix in ["InspectionBlock_", "AnalysisBlock_"]:
                    self.assertEqual([wb.defined_names[n].comment for n in sorted(wb.defined_names) if n.startswith(prefix)], expected)
                if "Final" not in names:
                    self.assertNotIn('QC Dashboard', wb.sheetnames)
                wb.close()

    def matching_case(self, final_styles, raw_styles):
        wb = openpyxl.Workbook(); wb.remove(wb.active)
        ws = ordinary(wb, count=len(final_styles))
        for row, value in enumerate(final_styles, 4): ws.cell(row, 5, value)
        raw = raw_workbook()
        for row, value in enumerate(raw_styles, 5): raw.active.cell(row, 3, value)
        wb.save(self.root / "matching.xlsx"); raw.save(self.root / "raw.xlsx")
        wb.close(); raw.close()
        return parse_inspection_workbook(self.root / "matching.xlsx", self.root / "raw.xlsx")

    def test_exact_style_intersection_excludes_unmatched_records(self):
        blocks = self.matching_case(["A", "B", "C"], ["A", "B", "D"])
        matched, final, raw = dashboard_scope(blocks)
        self.assertEqual(matched, ["A", "B"])
        self.assertEqual((final.inspected_qty, final.defect_qty), (200, 6))
        self.assertEqual((raw.inspected_qty, raw.defect_qty), (200, 8))
        wb = openpyxl.load_workbook(self.output(blocks))
        self.assertEqual(wb['QC Dashboard']['G9'].value, 200)
        self.assertEqual(wb['QC Dashboard']['W9'].value, 200)
        wb.close()

    def test_suffix_case_numeric_and_whitespace_matching_contract(self):
        for a, b, expected in [("01277N111D", "01277N111D-BOTTOM-AFTER WASH", []),
                               (" A ", "A", ["A"]), ("A", "a", []),
                               (123, "123", []), ("001", "1", [])]:
            with self.subTest(final=a, raw=b):
                blocks = self.matching_case([a], [b, b, b])
                self.assertEqual(dashboard_scope(blocks)[0], expected)
        self.assertIsNone(style_key("   "))

    def test_duplicate_same_style_records_are_aggregated_not_deduplicated(self):
        blocks = self.matching_case(["A", "A", "B"], ["A", "A", "D"])
        matched, final, raw = dashboard_scope(blocks)
        self.assertEqual(matched, ["A"])
        self.assertEqual((final.inspection_count, final.inspected_qty), (2, 200))
        self.assertEqual((raw.inspection_count, raw.inspected_qty), (2, 200))

    def test_manpower_only_on_analysis_keeps_dates_conflicts_and_missing(self):
        raw = raw_workbook(); raw.active.cell(5, 8, 40); raw.active.cell(6, 8, 20)
        blocks = self.blocks(raw=raw); rows = manpower(blocks[-1])
        self.assertEqual(rows[0][1], ["40", "20"])
        self.assertEqual(rows[1][1], [None])
        wb = openpyxl.load_workbook(self.output(blocks))
        self.assertNotIn("MANPOWER", [c.value for row in wb['Summary'] for c in row])
        sheet = wb['Analysis']; r = next(c.row for row in sheet for c in row if c.value == 'MANPOWER')
        text = sheet.cell(r, 3).value
        self.assertIn('01 Oct - 40p / 20p', text)
        self.assertIn('02 Oct - not provided', text)
        self.assertIsNone(sheet.cell(r - 3, 10).value)  # aggregate persons deliberately blank
        wb.close()

    def test_canonical_block_styles_and_geometry_are_reused(self):
        blocks = self.blocks(["Final", "Re-Final", "Random", "INLINE-SPL", "INLINE"])
        output = openpyxl.load_workbook(self.output(blocks)); reference = openpyxl.load_workbook(tpl.ASSET)
        source_starts = [2, 13, 21, 29, 29, 40]
        for sheet, prefix in [('Analysis', 'AnalysisBlock_'), ('Summary', 'InspectionBlock_')]:
            self.assertEqual(dict(output[sheet].column_dimensions['D']), dict(reference[sheet].column_dimensions['D']))
            for index, old in enumerate(source_starts):
                row = output[sheet][list(output.defined_names[prefix + f'{index:03d}'].destinations)[0][1]].row
                for offset, col in [(0, 1), (1, 1), (1, 5), (2, 12), (2, 13)]:
                    actual, expected = output[sheet].cell(row+offset,col), reference[sheet].cell(old+offset,col)
                    self.assertEqual(copy(actual.font), copy(expected.font))
                    self.assertEqual(copy(actual.fill), copy(expected.fill))
                    self.assertEqual(copy(actual.border), copy(expected.border))
                    self.assertEqual(copy(actual.alignment), copy(expected.alignment))
                    self.assertEqual(actual.number_format, expected.number_format)
                self.assertIn(f'A{row}:M{row}', str(output[sheet].merged_cells))
        output.close(); reference.close()

    def test_detail_canonical_core_and_all_raw_fields_are_retained(self):
        blocks = self.blocks(); raw = blocks[-1]
        wb = openpyxl.load_workbook(self.output(blocks)); sheet = wb['100%']
        self.assertEqual(sheet['A3'].value, 'Inspection Date')
        self.assertEqual(sheet['B3'].value, 'Factory Name')
        self.assertEqual(sheet['C3'].value, 'Style No')
        self.assertEqual([sheet.cell(2,c).value for c in range(5,40)], list(range(1,36)))
        spec = detail_spec(raw)
        for i, source in enumerate(raw.raw_rows, 4):
            for j, index in enumerate(spec, 1):
                expected = source[index] if index is not None else None
                actual = sheet.cell(i,j).value
                if hasattr(actual, 'date'): actual = actual.date()
                self.assertEqual(actual, expected)
        self.assertEqual(len(sheet._charts), 2)
        self.assertEqual(sheet.page_setup.fitToWidth, 1)
        self.assertEqual(sheet.page_setup.fitToHeight, 1)
        self.assertNotEqual(sheet['A4'].number_format, 'ddd')
        self.assertGreater(sheet._charts[0].anchor._from.row, sheet.max_row - 1)
        self.assertFalse(sheet.column_dimensions['B'].hidden)
        self.assertFalse(sheet.column_dimensions['C'].hidden)
        wb.close()
