"""Structural parsing and report values, independent of Django and old exporters."""
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

import openpyxl

from .workbook_security import WorkbookValidationError, bounded_sheet, validate_workbook


@dataclass(frozen=True)
class DefectColumn:
    column: int
    category: str | None
    label: str
    ordinal: int = 0
    occurrence: int = 1
    source_number: int | None = None


@dataclass(frozen=True)
class TopDefect:
    category: str | None
    label: str
    qty: int
    ratio: Decimal | None


@dataclass
class ReportBlock:
    source_sheet: str
    source_index: int
    report_name: str
    kind: str
    date_start: date | None = None
    date_end: date | None = None
    inspection_count: int | None = None
    shipment_qty: int | None = None
    inspected_qty: int | None = None
    defect_qty: int | None = None
    defect_ratio: Decimal | None = None
    items: list[str] = field(default_factory=list)
    personnel: list[str] = field(default_factory=list)
    top_defects: list[TopDefect] = field(default_factory=list)
    empty_state: bool = False
    factories: list[str] = field(default_factory=list)
    daily_rows: list[dict] = field(default_factory=list)
    defect_schema: list[DefectColumn] = field(default_factory=list)
    # Rendering projections; legacy extraction/ranking values remain unchanged.
    inspection_days: int | None = None
    defect_totals: list[int | None] = field(default_factory=list)
    pass_qty: int | None = None
    styles: list[str] = field(default_factory=list)
    raw_headers: list[str] = field(default_factory=list)
    raw_rows: list[list] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    format: str | None = None
    field_columns: dict[str, int] = field(default_factory=dict)
    blank_defects_are_zero: bool = False


def normalize_label(value):
    return "" if value is None else " ".join(str(value).strip().casefold().split())


def semantic(value):
    return re.sub(r"[\W_]+", "", normalize_label(value))


ALIASES = {
    "date": {"Inspection Date", "Date of issue", "Date"},
    "inspected": {"Inspection Qty", "Inspected Qty", "Checked Qty", "Audit Qty."},
    "defect": {"Defect Qty", "DefectQty."},
    "shipment": {"Shipping Qty", "Shipment Qty", "Ship Qty."},
    "pass": {"Pass Qty", "Passed Qty"},
    "item": {"Item Name"},
    "style": {"Style No", "Style NO."},
    "person": {"Person", "Personnel", "Inspectors"},
    "factory": {"Factory", "Factory Name"},
}
ALIASES = {key: {semantic(v) for v in values} for key, values in ALIASES.items()}
PREFIX_LABELS = {semantic(v) for v in (
    "Factory", "Factory Name", "Date of issue", "Inspection Date", "Inspection Type",
    "Factory In Time", "Factory Out Time", "Factory In-Out Time", "Working Hour", "Total Hours",
    "Audit Start Time", "Audit End Time", "Audit Result", "Report Number", "Report No",
    "Item Name", "Style No", "POーNO", "PO No", "DO No", "Country", "Order Qty",
    "PO Qty.(Pcs)", "PO Qty.(Set)", "PO Qty.(Pack)", "PO WH", "Shipping Qty", "Audit Qty.",
    "Inspection Qty", "Pass Qty", "Defect Qty.", "Acceptable Defect Qty", "Defect %",
    "Defect Ratio(%)", "Major Defect Qty", "Minor Defect Qty", "Person", "Inspectors",
)}


def fail(code, detail, ws=None, cell=None, input="inspection_summary"):
    raise WorkbookValidationError(code, detail, input=input,
                                  sheet=ws.title if ws is not None else None, cell=cell)


@contextmanager
def workbook_pair(path):
    formula = values = None
    with open(path, "rb") as stream:
        validate_workbook(stream)
    try:
        formula = openpyxl.load_workbook(path, data_only=False, read_only=False, keep_links=False)
        values = openpyxl.load_workbook(path, data_only=True, read_only=False, keep_links=False)
        yield formula, values
    finally:
        if formula is not None:
            formula.close()
        if values is not None:
            values.close()


def read_cell(formula, values, row, column, *, input="inspection_summary"):
    source = formula.cell(row, column)
    cached = values.cell(row, column)
    value = cached.value if source.data_type == "f" else source.value
    if source.data_type == "f" and value is None:
        fail("FORMULA_VALUE_UNAVAILABLE", "A consumed formula has no cached result.",
             formula, source.coordinate, input)
    if cached.data_type == "e" or (isinstance(value, str) and value.startswith(("#REF!", "#DIV/0!", "#VALUE!", "#NAME?", "#N/A", "#NUM!", "#NULL!"))):
        fail("FORMULA_VALUE_UNAVAILABLE", "A consumed cell contains an Excel error.",
             formula, source.coordinate, input)
    return value


def optional_integer(value, *, ws, cell, input="inspection_summary", required=False):
    if value in (None, ""):
        if required:
            fail("REQUIRED_VALUE_MISSING", "A required quantity is missing.", ws, cell, input)
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        fail("INVALID_QUANTITY", "Quantities must be nonnegative whole numbers.", ws, cell, input)
    try:
        result = int(value)
    except (ValueError, OverflowError):
        fail("INVALID_QUANTITY", "Quantities must be finite whole numbers.", ws, cell, input)
    if value != result:
        fail("INVALID_QUANTITY", "Quantities must be whole numbers.", ws, cell, input)
    return result


def inspection_day(value, *, ws, cell, input="inspection_summary"):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            pass
    fail("INVALID_INSPECTION_DATE", "Use an Excel date or an unambiguous YYYY-MM-DD date.", ws, cell, input)


def detect_header(ws, required, *, input="inspection_summary"):
    bounded_sheet(ws)
    candidates = []
    for row in ws.iter_rows(max_row=min(40, ws.max_row)):
        fields = {}
        for cell in row:
            label = semantic(cell.value)
            for key, names in ALIASES.items():
                if label and label in names:
                    if key in fields:
                        fail("AMBIGUOUS_HEADER", "A semantic header occurs more than once.", ws, cell.coordinate, input)
                    fields[key] = cell.column
        if required.issubset(fields):
            candidates.append((row[0].row, fields))
    if len(candidates) != 1:
        fail("RAW_DEFECT_SCHEMA_INVALID" if input == "raw" else "UNRECOGNIZED_VISIBLE_SHEET",
             "Expected exactly one supported detail-table header band.", ws, input=input)
    return candidates[0]


def defect_columns(ws, header, *, input="inspection_summary"):
    bounded_sheet(ws)
    prefix = [c.column for c in ws[header] if semantic(c.value) in PREFIX_LABELS]
    if not prefix:
        fail("UNRECOGNIZED_VISIBLE_SHEET", "No supported quantity/identity headers.", ws, input=input)
    start = max(prefix) + 1
    columns = []
    for column in range(start, ws.max_column + 1):
        label = ws.cell(header, column).value
        if label in (None, ""):
            if any(ws.cell(header, c).value not in (None, "") for c in range(column + 1, ws.max_column + 1)):
                fail("AMBIGUOUS_DEFECT_SCHEMA", "The defect header band has a gap.", ws, ws.cell(header, column).coordinate, input)
            break
        category = None
        for merged in ws.merged_cells.ranges:
            if merged.min_col <= column <= merged.max_col and merged.max_row < header:
                value = ws.cell(merged.min_row, merged.min_col).value
                if value is not None and re.match(r"^[A-Z]\s*[:.]", str(value).strip()):
                    category = str(value).strip()
        columns.append(DefectColumn(column, category, str(label).strip()))
    if not columns:
        fail("UNRECOGNIZED_VISIBLE_SHEET", "No sheet-specific defect columns found.", ws, input=input)
    identities = [(normalize_label(c.category), normalize_label(c.label)) for c in columns]
    if len(set(identities)) != len(identities):
        fail("AMBIGUOUS_DEFECT_SCHEMA", "Duplicate defect headers within the same category.", ws, input=input)
    return columns


def total(values):
    return None if any(value is None for value in values) else sum(values)


def ratio(qty, inspected):
    return Decimal(qty) / Decimal(inspected) if qty is not None and inspected else None


def top_defects(schema, counts, inspected):
    ranked = [(i, count) for i, count in enumerate(counts) if count is not None and count > 0]
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return [TopDefect(schema[i].category, schema[i].label, qty, ratio(qty, inspected)) for i, qty in ranked[:5]]


def parse_ordinary_sheet(ws, values, source_index):
    header, fields = detect_header(ws, {"date", "inspected", "defect", "item", "style"})
    schema = defect_columns(ws, header)
    records = []
    for row in range(header + 1, ws.max_row + 1):
        raw_date = ws.cell(row, fields["date"]).value
        # Ignore known totals and precomputed top-five panels, never detail dates.
        if raw_date in (None, ""):
            if any(str(c.value).strip().casefold() in {"合計", "total", "subtotal", "weekly subtotal"} for c in ws[row][:max(fields.values())]):
                continue
            if any(values.cell(row, fields[key]).value not in (None, "") for key in ("inspected", "defect")):
                fail("INVALID_INSPECTION_DATE", "A populated detail quantity has no inspection date.", ws, ws.cell(row, fields["date"]).coordinate)
            continue
        day = inspection_day(read_cell(ws, values, row, fields["date"]), ws=ws,
                             cell=ws.cell(row, fields["date"]).coordinate)
        record = {"date": day}
        for key in ("inspected", "defect", "shipment"):
            col = fields.get(key)
            record[key] = (optional_integer(read_cell(ws, values, row, col), ws=ws,
                                           cell=ws.cell(row, col).coordinate) if col else None)
        for key in ("item", "person", "factory"):
            col = fields.get(key)
            value = read_cell(ws, values, row, col) if col else None
            record[key] = None if value in (None, "") else str(value).strip()
        record["categories"] = [optional_integer(read_cell(ws, values, row, d.column), ws=ws,
                                                cell=ws.cell(row, d.column).coordinate) for d in schema]
        record["style"] = read_cell(ws, values, row, fields["style"])
        records.append(record)
    block = ReportBlock(ws.title, source_index, ws.title, "ordinary", inspection_count=len(records),
                        empty_state=not records, defect_schema=schema,
                        inspection_days=len({r["date"] for r in records}), records=records)
    if not records:
        return block
    block.date_start = min(r["date"] for r in records)
    block.date_end = max(r["date"] for r in records)
    block.inspected_qty = total([r["inspected"] for r in records])
    block.defect_qty = total([r["defect"] for r in records])
    block.shipment_qty = total([r["shipment"] for r in records])
    block.defect_ratio = ratio(block.defect_qty, block.inspected_qty)
    block.items = list(dict.fromkeys(r["item"] for r in records if r["item"]))
    block.personnel = list(dict.fromkeys(r["person"] for r in records if r["person"]))
    block.factories = list(dict.fromkeys(r["factory"] for r in records if r["factory"]))
    # Missing defect cells stay missing; observed positives may still be ranked.
    counts = [sum(known) if (known := [r["categories"][i] for r in records if r["categories"][i] is not None]) else None
              for i in range(len(schema))]
    block.top_defects = top_defects(schema, counts, block.inspected_qty)
    block.defect_totals = counts
    return block


def parse_inspection_workbook(path=None, raw_path=None, on_stage=None):
    from .raw_parser import parse_raw_workbook
    blocks = []
    hundred_position = None
    if path is not None:
        with workbook_pair(path) as (formula, values):
            visible = [formula[name] for name in formula.sheetnames if formula[name].sheet_state == "visible"]
            if not visible:
                fail("NO_VISIBLE_SHEETS", "The Inspection Summary workbook has no visible worksheets.")
            if on_stage:
                on_stage("PARSING_SHEETS")
            for index, ws in enumerate(visible):
                if not isinstance(ws, openpyxl.worksheet.worksheet.Worksheet):
                    fail("UNRECOGNIZED_VISIBLE_SHEET", "Visible chart sheets are not supported.", ws)
                if normalize_label(ws.title) == "100%":
                    if hundred_position is not None:
                        fail("DUPLICATE_100_PERCENT", "Only one visible 100% identity is allowed.", ws)
                    hundred_position = len(blocks)
                else:
                    blocks.append(parse_ordinary_sheet(ws, values[ws.title], index))
    if raw_path is not None:
        if on_stage:
            on_stage("PARSING_RAW")
        raw = parse_raw_workbook(raw_path)
        position = len(blocks) if hundred_position is None else hundred_position
        raw.source_index = position
        blocks.insert(position, raw)
    if not blocks:
        fail("NO_REPORT_BLOCKS", "At least one recognized Inspection Summary or 100% report block is required.")
    return blocks
