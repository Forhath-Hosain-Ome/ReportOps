"""Bound untrusted OOXML before openpyxl allocates workbook objects."""
import re
import stat
import struct
import zipfile
import zlib
from xml.etree import ElementTree

from .opc import Package, is_xml, TYPES_NS, RELS_NS, SHEET_NS

MAX_WORKBOOK_BYTES = 50 * 1024 * 1024
MAX_EXPANDED_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 10_000
MAX_COMPRESSION_RATIO = 100
MAX_DIRECTORY_BYTES = 4 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
MAX_SHEET_ROWS = 200_000
MAX_SHEET_COLUMNS = 512
MAX_WORKBOOK_CELLS = 2_000_000
# Resource ceilings, not business schema limits. Applied before openpyxl's
# object allocation, across hidden sheets too; aggregate budgets prevent many
# individually acceptable parts from amplifying memory/CPU.
MAX_XML_ELEMENTS = 1_000_000
MAX_WORKBOOK_XML_ELEMENTS = 3_000_000
MAX_XML_DEPTH = 64
MAX_WORKSHEETS = 128
MAX_CELLS_PER_SHEET = 500_000
MAX_SHARED_STRINGS = 200_000
MAX_STRING_LENGTH = 32_767
MAX_WORKBOOK_TEXT = 16_000_000
MAX_MERGED_RANGES = 10_000
MAX_XML_ATTRIBUTES = 64
MAX_METADATA_ENTRIES = 10_000  # Bound retained OPC maps, independently of XML node ceilings.


class WorkbookValidationError(ValueError):
    def __init__(self, code, detail, *, input=None, sheet=None, cell=None):
        self.code = code
        self.detail = {"input": input, "sheet": sheet, "cell": cell, "detail": detail}
        super().__init__(detail)


def coordinate(value):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]{0,6})", value)
    if not match:
        raise ValueError("coordinate")
    column = 0
    for char in match[1]:
        column = column * 26 + ord(char) - 64
    row = int(match[2])
    if column > MAX_SHEET_COLUMNS or row > MAX_SHEET_ROWS:
        raise ValueError("worksheet bounds")
    return row, column


class XMLBudget:
    """XMLParser event target: no Element/tree is ever constructed or retained.

    Only depth counters and package counters survive a callback. Character data
    arrives incrementally and is budgeted before openpyxl reads the package.
    """
    def __init__(self, name, budget, kind):
        self.name, self.budget, self.kind = name, budget, kind
        self.metadata = dict(defaults=[], overrides=[], relationships=[], sheets=[])
        self.tags = []
        self.stack = []
        self.string_lengths = []
        self.elements = self.cells = self.rows = self.merges = 0
        self.last_row = self.last_column = 0
        self.root = None
        self.worksheet = kind == "worksheet"

    def doctype(self, *args):
        raise ValueError("DTD forbidden")

    def start(self, tag, attrs):
        self.elements += 1
        self.budget["elements"] += 1
        if (self.elements > MAX_XML_ELEMENTS or self.budget["elements"] > MAX_WORKBOOK_XML_ELEMENTS
                or len(self.stack) >= MAX_XML_DEPTH or len(attrs) > MAX_XML_ATTRIBUTES):
            raise ValueError("XML resource budget")
        if any(len(k) > MAX_STRING_LENGTH or len(v) > MAX_STRING_LENGTH for k, v in attrs.items()):
            raise ValueError("XML attribute budget")
        self.stack.append(0)
        self.tags.append(tag)
        local = tag.rsplit("}", 1)[-1]
        if local in {"si", "is"}:
            self.string_lengths.append(0)
        if self.root is None:
            self.root = tag
        collection = None
        if self.kind == "types" and len(self.stack) == 2:
            collection = {"{" + TYPES_NS + "}Default": "defaults",
                          "{" + TYPES_NS + "}Override": "overrides"}.get(tag)
            if not collection:
                raise ValueError("Unsupported content-type metadata")
        elif self.kind == "relationships" and len(self.stack) == 2:
            if tag != "{" + RELS_NS + "}Relationship":
                raise ValueError("Unsupported relationship metadata")
            collection = "relationships"
        elif (self.kind == "workbook" and tag == "{" + SHEET_NS + "}sheet"
              and len(self.tags) >= 2 and self.tags[-2] == "{" + SHEET_NS + "}sheets"):
            collection = "sheets"
            self.budget["sheets"] += 1
            if self.budget["sheets"] > MAX_WORKSHEETS:
                raise ValueError("worksheet count")
        if collection:
            self.budget["metadata"] += 1
            if self.budget["metadata"] > MAX_METADATA_ENTRIES:
                raise ValueError("OPC metadata budget")
            self.metadata[collection].append(dict(attrs))
        if self.kind == "strings" and local == "si":
            self.budget["strings"] += 1
            if self.budget["strings"] > MAX_SHARED_STRINGS:
                raise ValueError("shared string count")
        if self.worksheet:
            if local == "row":
                self.rows += 1
                if self.rows > MAX_SHEET_ROWS or not 0 < int(attrs.get("r", "0")) <= MAX_SHEET_ROWS:
                    raise ValueError("row budget")
            if local == "c":
                self.cells += 1
                self.budget["cells"] += 1
                row, column = coordinate(attrs.get("r", ""))
                self.last_row = max(self.last_row, row)
                self.last_column = max(self.last_column, column)
                if self.cells > MAX_CELLS_PER_SHEET or self.budget["cells"] > MAX_WORKBOOK_CELLS:
                    raise ValueError("cell budget")
            if local in {"dimension", "mergeCell"}:
                ref = attrs.get("ref", "")
                ends = ref.split(":")
                if len(ends) not in (1, 2):
                    raise ValueError("range")
                for end in ends:
                    row, column = coordinate(end)
                    self.last_row = max(self.last_row, row)
                    self.last_column = max(self.last_column, column)
                if local == "mergeCell":
                    self.merges += 1
                    if self.merges > MAX_MERGED_RANGES:
                        raise ValueError("merged range budget")
            if self.last_row * self.last_column > MAX_WORKBOOK_CELLS:
                raise ValueError("worksheet extent budget")

    def data(self, data):
        if not self.stack:
            return
        self.string_lengths = [n + len(data) for n in self.string_lengths]
        if any(n > MAX_STRING_LENGTH for n in self.string_lengths):
            raise ValueError("rich string budget")
        self.stack[-1] += len(data)
        self.budget["text"] += len(data)
        if self.stack[-1] > MAX_STRING_LENGTH or self.budget["text"] > MAX_WORKBOOK_TEXT:
            raise ValueError("string budget")

    def end(self, tag):
        self.stack.pop()
        self.tags.pop()
        if tag.rsplit("}", 1)[-1] in {"si", "is"}:
            self.string_lengths.pop()

    def close(self):
        expected = {"types": "{" + TYPES_NS + "}Types", "relationships": "{" + RELS_NS + "}Relationships",
                    "workbook": "{" + SHEET_NS + "}workbook", "worksheet": "{" + SHEET_NS + "}worksheet",
                    "strings": "{" + SHEET_NS + "}sst", "chartsheet": "{" + SHEET_NS + "}chartsheet"}
        if self.kind in expected and self.root != expected[self.kind]:
            raise ValueError("Unsupported OPC/XML root")
        if self.worksheet:
            self.budget["extent"] += self.last_row * self.last_column
            if self.budget["extent"] > MAX_WORKBOOK_CELLS:
                raise ValueError("aggregate worksheet extent budget")


def validate_workbook(stream, *, input=None):
    """Stream each ZIP member once; never extract or materialize XML trees."""
    try:
        stream.seek(0, 2)
        size = stream.tell()
        if not 0 < size <= MAX_WORKBOOK_BYTES:
            raise ValueError("size")
        stream.seek(max(0, size - 65557))
        tail = stream.read(65557)
        end = tail.rfind(b"PK\x05\x06")
        if end < 0 or len(tail) - end < 22:
            raise ValueError("directory")
        disk, start, count_disk, count, length, offset, comment = struct.unpack_from("<4H2LH", tail, end + 4)
        if (disk or start or count != count_disk or not 0 < count <= MAX_ARCHIVE_ENTRIES
                or length > MAX_DIRECTORY_BYTES or offset + length != size - len(tail) + end
                or end + 22 + comment != len(tail)):
            raise ValueError("directory budget")
        stream.seek(0)
        with zipfile.ZipFile(stream) as archive:
            entries = {}
            expanded = 0
            for info in archive.infolist():
                name = info.orig_filename
                parts = name.rstrip("/").split("/")
                mode = stat.S_IFMT(info.external_attr >> 16)
                if (name != info.filename or name in entries or not name or len(name) > 1024
                        or "\\" in name or ":" in name or "%" in name or name.startswith("/")
                        or any(part in ("", ".", "..") for part in parts)
                        or any(ord(c) < 32 for c in name) or info.flag_bits & 1
                        or mode not in (0, stat.S_IFREG, stat.S_IFDIR)
                        or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                        or info.file_size > max(1, info.compress_size) * MAX_COMPRESSION_RATIO):
                    raise ValueError("member")
                entries[name] = info
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise ValueError("expanded budget")
            if not {"[Content_Types].xml", "_rels/.rels"}.issubset(entries):
                raise ValueError("OPC package metadata missing")
            budget = dict(elements=0, cells=0, sheets=0, strings=0, text=0, extent=0,
                          metadata=0, worksheet_parts=0)
            consumed = {}

            def read_part(name, kind):
                if name in consumed:
                    return consumed[name]
                info = entries[name]
                target = XMLBudget(name, budget, kind) if kind != "binary" else None
                parser = ElementTree.XMLParser(target=target) if target else None
                if target and target.worksheet:
                    budget["worksheet_parts"] += 1
                    if budget["worksheet_parts"] > MAX_WORKSHEETS:
                        raise ValueError("worksheet count")
                with archive.open(info) as member:
                    total = 0
                    while chunk := member.read(16 * 1024):
                        total += len(chunk)
                        if total > info.file_size or (target and total > MAX_XML_BYTES):
                            raise ValueError("member budget")
                        if parser is not None:
                            parser.feed(chunk)
                    if total != info.file_size:
                        raise ValueError("member size")
                if parser is not None:
                    parser.close()
                consumed[name] = target.metadata if target else {}
                return consumed[name]

            package = Package(entries, read_part)
            # Charge all physical typed worksheets, referenced or not. Every sheet
            # identity has a unique target, so loading cannot multiply this budget.
            for name, content_type in package.types.items():
                kind = package.kind(name)
                xml = is_xml(content_type) or name.endswith((".xml", ".rels"))
                read_part(name, kind if xml else "binary")
            if not budget["worksheet_parts"]:
                raise ValueError("No worksheet parts")
    except WorkbookValidationError:
        raise
    except (ValueError, ElementTree.ParseError, zipfile.BadZipFile, zipfile.LargeZipFile, zlib.error, struct.error, EOFError, UnicodeError) as exc:
        raise WorkbookValidationError("INVALID_WORKBOOK", "Invalid, unsupported or oversized XLSX workbook.", input=input) from exc
    finally:
        stream.seek(0)


def bounded_sheet(ws):
    """Defense in depth for direct parser calls and untrusted dimension metadata."""
    if (ws.max_row > MAX_SHEET_ROWS or ws.max_column > MAX_SHEET_COLUMNS
            or ws.max_row * ws.max_column > MAX_WORKBOOK_CELLS):
        raise WorkbookValidationError("INVALID_WORKBOOK", "Worksheet dimensions exceed resource ceilings.", sheet=ws.title)
    return ws.max_row, ws.max_column
