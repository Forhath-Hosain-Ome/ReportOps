import io
import uuid
import zipfile
from unittest.mock import patch

from django.test import SimpleTestCase

from inspection_summary import storage
from inspection_summary.workbook_security import WorkbookValidationError, validate_workbook
from .helpers import JobFixture, raw_workbook, workbook_bytes


class WorkbookSecurityTests(SimpleTestCase):
    def test_valid_workbook_and_repeated_validation_restore_position(self):
        stream = io.BytesIO(workbook_bytes(raw_workbook()))
        validate_workbook(stream); validate_workbook(stream)
        self.assertEqual(stream.tell(), 0)

    def test_malformed_zip_empty_and_non_ooxml_rejected(self):
        for payload in [b"", b"bad zip", b"PK"]:
            with self.subTest(payload=payload), self.assertRaises(WorkbookValidationError):
                validate_workbook(io.BytesIO(payload))
        payload = io.BytesIO()
        with zipfile.ZipFile(payload, "w") as z: z.writestr("a.txt", "text")
        with self.assertRaises(WorkbookValidationError): validate_workbook(payload)

    def test_traversal_and_xml_entities_rejected(self):
        for name, data in [("../escaped.xml", "x"), ("a.xml", '<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>')]:
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w") as z: z.writestr(name, data)
            with self.assertRaises(WorkbookValidationError): validate_workbook(stream)

    def test_compression_and_archive_entry_limits(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("bomb.xml", b"x" * 100_000)
        with self.assertRaises(WorkbookValidationError): validate_workbook(stream)
        valid = io.BytesIO(workbook_bytes(raw_workbook()))
        with patch("inspection_summary.workbook_security.MAX_ARCHIVE_ENTRIES", 2):
            with self.assertRaises(WorkbookValidationError): validate_workbook(valid)

    def test_size_limit_before_parsing(self):
        with patch("inspection_summary.workbook_security.MAX_WORKBOOK_BYTES", 3):
            with self.assertRaises(WorkbookValidationError): validate_workbook(io.BytesIO(b"abcd"))


class StorageSecurityTests(JobFixture):
    def test_paths_reject_absolute_traversal_drives_and_nul(self):
        for value in ["", "../outside", "/outside", "C:/outside", "x/../outside", "x\\outside", "x/aa:bb", "x/\x00"]:
            with self.subTest(value=value), self.assertRaises(ValueError): storage.resolve_stored_path(value)

    def test_client_filename_never_selects_storage_path(self):
        job = self.make_job()
        self.assertTrue(job.raw_path.startswith(f"inspection_summary/{job.pk}/input/"))
        with self.assertRaises(ValueError): storage.input_path(job.pk, "../outside")
        with self.assertRaises(ValueError): storage.job_root("../outside")

    def test_symlink_target_not_followed_or_deleted(self):
        outside = self.media.parent / "outside"; outside.mkdir()
        link = self.media / "inspection_summary"
        try: link.symlink_to(outside, target_is_directory=True)
        except OSError as exc: self.skipTest(str(exc))
        with self.assertRaises(ValueError): storage.job_root(uuid.uuid4())
        self.assertTrue(outside.exists())


class StreamingBudgetTests(SimpleTestCase):
    def package(self, replacements=None, extras=None):
        original = io.BytesIO(workbook_bytes(raw_workbook()))
        result = io.BytesIO()
        with zipfile.ZipFile(original) as source, zipfile.ZipFile(result, "w", zipfile.ZIP_STORED) as output:
            for entry in source.infolist():
                output.writestr(entry.filename, (replacements or {}).get(entry.filename, source.read(entry)))
            for name, data in (extras or {}).items(): output.writestr(name, data)
        result.seek(0)
        return result

    def reject(self, xml, **limits):
        from contextlib import ExitStack
        with ExitStack() as stack:
            for name, value in limits.items(): stack.enter_context(patch("inspection_summary.workbook_security." + name, value))
            with self.assertRaises(WorkbookValidationError):
                validate_workbook(self.package(extras={"budget.xml": xml}))

    def test_many_tiny_elements_bounded_without_element_trees(self):
        self.reject("<a>" + "<b/>" * 100_001 + "</a>", MAX_XML_ELEMENTS=100_000)

    def test_deep_nesting_rejected(self):
        self.reject("<a>" * 1000 + "</a>" * 1000)

    def test_excess_worksheet_parts_rejected(self):
        from .package_fixtures import parts, declare, archive, MIME, MAIN
        items = parts(); name = "anywhere/extra.bin"
        declare(items, name, MIME + "worksheet+xml")
        items[name] = ('<worksheet xmlns="' + MAIN + '"/>').encode()
        with patch("inspection_summary.workbook_security.MAX_WORKSHEETS", 1):
            with self.assertRaises(WorkbookValidationError): validate_workbook(archive(items))

    def sheet_reject(self, body, **limits):
        from contextlib import ExitStack
        xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">' + body + '</worksheet>'
        with ExitStack() as stack:
            for name, value in limits.items(): stack.enter_context(patch("inspection_summary.workbook_security." + name, value))
            with self.assertRaises(WorkbookValidationError):
                validate_workbook(self.package(replacements={"xl/worksheets/sheet1.xml": xml}))

    def test_excess_rows_rejected(self):
        self.sheet_reject('<sheetData><row r="200001"/></sheetData>')

    def test_excess_columns_rejected(self):
        self.sheet_reject('<sheetData><row r="1"><c r="SS1"/></row></sheetData>')

    def test_excess_cells_rejected(self):
        self.sheet_reject('<sheetData><row r="1">' + ''.join(f'<c r="A{i}"/>' for i in range(1, 8)) + '</row></sheetData>', MAX_CELLS_PER_SHEET=6)

    def test_excess_shared_string_count(self):
        from .package_fixtures import parts, add_strings, archive
        items = parts(); add_strings(items, "xl/data/strings.bin", count=4)
        with patch("inspection_summary.workbook_security.MAX_SHARED_STRINGS", 3):
            with self.assertRaises(WorkbookValidationError): validate_workbook(archive(items))

    def test_huge_individual_string_and_rich_string(self):
        self.reject('<a>' + 'x' * 32768 + '</a>')
        self.sheet_reject('<sheetData><row r="1"><c r="A1" t="inlineStr"><is><r><t>' + 'x' * 20000 + '</t></r><r><t>' + 'y' * 20000 + '</t></r></is></c></row></sheetData>')

    def test_dimension_metadata_and_merges_bounded(self):
        self.sheet_reject('<dimension ref="A1:XFD1048576"/>')
        self.sheet_reject('<mergeCells>' + '<mergeCell ref="A1:B2"/>' * 4 + '</mergeCells>', MAX_MERGED_RANGES=3)

    def test_aggregate_element_and_text_budgets(self):
        self.reject('<a>' + '<b/>' * 100 + '</a>', MAX_WORKBOOK_XML_ELEMENTS=100)
        self.reject('<a>' + 'x' * 100 + '</a>', MAX_WORKBOOK_TEXT=99)

    def test_split_dtd_entities_and_external_relationships_rejected(self):
        self.reject('<!DOCTYPE a [<!ENTITY x "boom">]><a>&x;</a>')
        with self.assertRaises(WorkbookValidationError):
            validate_workbook(self.package(extras={"bad.rels": '<Relationships><Relationship TargetMode="External" Type="evil"/></Relationships>'}))

    def test_normal_synthetic_workbook_accepted(self):
        validate_workbook(self.package())

    def test_parser_direct_dimensions_bounded(self):
        from inspection_summary.parser import detect_header
        from .helpers import summary_workbook
        wb = summary_workbook(); wb.active.cell(200001, 1, "out of bounds")
        with self.assertRaises(WorkbookValidationError): detect_header(wb.active, {"date"})
        wb.close()

    def test_unexpected_stream_oserror_is_not_user_validation(self):
        class Broken(io.BytesIO):
            def read(self, *args): raise OSError("private")
        with self.assertRaises(OSError): validate_workbook(Broken(b'not empty'))
