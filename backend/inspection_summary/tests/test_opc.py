import io
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from inspection_summary.parser import parse_inspection_workbook
from inspection_summary.workbook_security import WorkbookValidationError, validate_workbook
from .helpers import JobFixture, summary_workbook, upload
from .package_fixtures import (CT, DOCREL, MAIN, MIME, REL, add_strings, aliases,
                               archive, corrupt, declare, parts, relocate)


class OPCSecurityTests(SimpleTestCase):
    def reject(self, items, **ceilings):
        from contextlib import ExitStack
        with ExitStack() as context:
            for name, value in ceilings.items():
                context.enter_context(patch("inspection_summary.workbook_security." + name, value))
            with self.assertRaises(WorkbookValidationError): validate_workbook(archive(items))

    def test_nonstandard_worksheet_names_still_charge_rows(self):
        for name in ["xl/customSheet.xml", "other/data.bin", "other/data.XML"]:
            with self.subTest(name=name):
                items = parts(); relocate(items, "xl/worksheets/sheet1.xml", name)
                items[name] = ('<worksheet xmlns="' + MAIN + '"><sheetData><row r="200001">'
                               '<c r="A200001"><v>1</v></c></row></sheetData></worksheet>').encode()
                self.reject(items)

    def test_valid_relocated_worksheet_and_workbook_are_supported(self):
        items = parts(); relocate(items, "xl/worksheets/sheet1.xml", "other/sheet.bin")
        relocate(items, "xl/workbook.xml", "book/main.bin")
        stream = archive(items); validate_workbook(stream)
        wb = openpyxl.load_workbook(stream, keep_links=False)
        self.assertEqual(wb.active["A3"].value, "Factory Name"); wb.close()

    def test_relocated_shared_strings_use_real_authority_budget(self):
        for name in ["xl/data/strings.bin", "other/strings.XML"]:
            items = parts(); add_strings(items, name, count=4)
            self.reject(items, MAX_SHARED_STRINGS=3)
            validate_workbook(archive(items))

    def test_aliases_rejected_before_openpyxl(self):
        for count in [2, 128]:
            items = parts(); aliases(items, count)
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "summary.xlsx"; path.write_bytes(archive(items).getvalue())
                with patch("inspection_summary.parser.openpyxl.load_workbook") as load:
                    with self.assertRaises(WorkbookValidationError): parse_inspection_workbook(path, path)
                load.assert_not_called()

    def test_normalized_alias_targets_are_rejected(self):
        items = parts(); aliases(items)
        sheets = ET.fromstring(items["xl/workbook.xml"])
        sheets.find("{" + MAIN + "}sheets")[1].set("{" + DOCREL + "}id", "alias-rid")
        items["xl/workbook.xml"] = ET.tostring(sheets)
        rels = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
        ET.SubElement(rels, "{" + REL + "}Relationship", Id="alias-rid", Type=DOCREL + "/worksheet",
                      Target="worksheets/./sheet1.xml")
        items["xl/_rels/workbook.xml.rels"] = ET.tostring(rels)
        self.reject(items)

    def test_root_traversal_missing_external_and_wrong_type_targets(self):
        for target, mode in [("../../escape.xml", "Internal"), ("missing.xml", "Internal"),
                             ("https://invalid.example/sheet", "External"),
                             ("/xl/styles.xml", "Internal"), ("%2e%2e/escape.xml", "Internal")]:
            items = parts(); rels = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
            for rel in rels:
                if rel.get("Type").endswith("/worksheet"):
                    rel.set("Target", target); rel.set("TargetMode", mode)
            items["xl/_rels/workbook.xml.rels"] = ET.tostring(rels)
            self.reject(items)

    def test_consumed_relationship_part_types_must_match(self):
        for part in ["xl/_rels/workbook.xml.rels", "xl/styles.xml"]:
            items = parts(); declare(items, part, "image/png")
            if part == "xl/styles.xml":
                # Replace the existing override, rather than failing on duplicate metadata.
                tree = ET.fromstring(items["[Content_Types].xml"])
                original = [n for n in tree if n.get("PartName") == "/" + part]
                tree.remove(original[0]); items["[Content_Types].xml"] = ET.tostring(tree)
            self.reject(items)

    def test_noncanonical_manifest_authority_is_rejected_explicitly(self):
        items = parts(); tree = ET.fromstring(items["[Content_Types].xml"])
        for node in tree:
            if node.get("PartName") == "/xl/workbook.xml": node.set("PartName", "/xl/../xl/workbook.xml")
        items["[Content_Types].xml"] = ET.tostring(tree); self.reject(items)

    def test_legitimate_relative_navigation_normalizes_within_package(self):
        items = parts(); rels = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
        for rel in rels:
            if rel.get("Type").endswith("/worksheet"): rel.set("Target", "../xl/worksheets/sheet1.xml")
        items["xl/_rels/workbook.xml.rels"] = ET.tostring(rels)
        validate_workbook(archive(items))

    def test_duplicate_shared_string_authorities_rejected(self):
        items = parts(); add_strings(items)
        name = "other/strings.bin"; declare(items, name, MIME + "sharedStrings+xml")
        items[name] = items["xl/sharedStrings.xml"]; self.reject(items)
        items = parts(); add_strings(items)
        rels = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
        ET.SubElement(rels, "{" + REL + "}Relationship", Id="second-string-rel",
                      Type=DOCREL + "/sharedStrings", Target="/xl/sharedStrings.xml")
        items["xl/_rels/workbook.xml.rels"] = ET.tostring(rels); self.reject(items)

    def test_external_shared_string_authority_rejected(self):
        items = parts(); add_strings(items)
        rels = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
        for rel in rels:
            if rel.get("Type").endswith("/sharedStrings"): rel.set("TargetMode", "External")
        items["xl/_rels/workbook.xml.rels"] = ET.tostring(rels); self.reject(items)

    def test_duplicate_content_types_relationship_ids_and_zip_parts_rejected(self):
        items = parts(); tree = ET.fromstring(items["[Content_Types].xml"])
        tree.append(ET.fromstring(ET.tostring(tree[-1])))
        items["[Content_Types].xml"] = ET.tostring(tree); self.reject(items)
        items = parts(); tree = ET.fromstring(items["xl/_rels/workbook.xml.rels"])
        tree.append(ET.fromstring(ET.tostring(tree[0])))
        items["xl/_rels/workbook.xml.rels"] = ET.tostring(tree); self.reject(items)
        stream = archive(parts())
        with zipfile.ZipFile(stream, "a") as output: output.writestr("xl/workbook.xml", b"duplicate")
        with self.assertRaises(WorkbookValidationError): validate_workbook(stream)

    def test_relocated_sheet_all_resource_budgets_apply(self):
        for body, ceiling in [
            ('<sheetData><row r="1"><c r="SS1"/></row></sheetData>', {}),
            ('<dimension ref="A1:XFD1048576"/>', {}),
            ('<sheetData><row r="1"><c r="A1"/><c r="B1"/></row></sheetData>', {"MAX_CELLS_PER_SHEET": 1}),
            ('<mergeCells><mergeCell ref="A1:B2"/><mergeCell ref="C1:D2"/></mergeCells>', {"MAX_MERGED_RANGES": 1}),
            ('<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>' + 'x' * 32768 + '</t></is></c></row></sheetData>', {}),
        ]:
            items = parts(); name = "elsewhere/sheet.bin"; relocate(items, "xl/worksheets/sheet1.xml", name)
            items[name] = ('<worksheet xmlns="' + MAIN + '">' + body + '</worksheet>').encode()
            self.reject(items, **ceiling)

    def test_unreferenced_typed_worksheets_count_against_aggregate(self):
        items = parts(); name = "orphan.bin"; declare(items, name, MIME + "worksheet+xml")
        items[name] = ('<worksheet xmlns="' + MAIN + '"><sheetData><row r="100000">'
                       '<c r="Z100000"/></row></sheetData></worksheet>').encode()
        self.reject(items)

    def test_malformed_compression_and_xml_are_business_errors(self):
        for kind in ["deflate", "truncated", "crc", "xml"]:
            with self.subTest(kind=kind), self.assertRaises(WorkbookValidationError):
                validate_workbook(io.BytesIO(corrupt(kind)))


class MalformedUploadTests(JobFixture):
    def test_malformed_input_is_structured_400_without_dispatch(self):
        for kind in ["deflate", "truncated", "crc", "xml"]:
            with self.subTest(kind=kind), patch("inspection_summary.services.publish_inspection_summary_job") as send:
                response = self.client.post("/inspection-summary/jobs/", {
                    "inspection_summary": upload(summary_workbook()),
                    "raw": SimpleUploadedFile("bad.xlsx", corrupt(kind))}, format="multipart")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertIn("INVALID_WORKBOOK", str(response.data))
                self.assertNotIn("Traceback", str(response.data))
                self.assertNotIn("decompressing", str(response.data))
                send.assert_not_called()
