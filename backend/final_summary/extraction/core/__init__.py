"""
----------------------------
Public exports for the extraction core package.

Import from here instead of the individual modules to avoid coupling callers
to internal file layout:

    from extraction.core import CellGrid, normalize_text
    from extraction.core import read_sheet, read_all_sheets
    from extraction.core import resolve_value, resolve_po_or_report_number
    from extraction.core import FieldName, DirectionRule, DOFieldName
    from extraction.core import to_display_date, to_iso_date, to_hhmm
"""

# ── Grid & sheet utilities ────────────────────────────────────────────────────
from .cell_grid import CellGrid, normalize_text
from .sheet_reader import read_sheet, read_first_sheet, read_all_sheets, get_sheet_names

# ── Proximity engine ──────────────────────────────────────────────────────────
from .proximity import (
    resolve_value,
    date_table,
    resolve_po_or_report_number,
    find_inline_value,
    is_int,
    is_valid_po_no,
    is_valid_report_no,
)

# ── Normalisation ─────────────────────────────────────────────────────────────
from .normalise import (
    # Date
    strip_time_from_date,
    to_display_date,
    to_iso_date,
    is_valid_display_date,
    # Time
    to_hhmm,
    to_display_time,
    duration_hhmm,
    # Numeric
    to_int,
    to_float,
    to_percentage,
    extract_first_number,
    calc_defect_percentage,
)

# ── Enums & maps ──────────────────────────────────────────────────────────────
from .label_map import (
    FieldName,
    DirectionRule,
    DOFieldName,
    AUDIT_TYPE_PATTERNS,
    NUMERIC_FIELD_NAMES,
    DO_FILL_DOWN_FIELDS,
)

from .defect_master import get_template_key, get_items, get_categories

__all__ = [
    # Grid & sheets
    "CellGrid", "normalize_text",
    "read_sheet", "read_first_sheet", "read_all_sheets", "get_sheet_names",
    # Proximity
    "resolve_value", "resolve_po_or_report_number",
    "find_inline_value", "is_int", "is_valid_po_no", "is_valid_report_no",
    # Normalise
    "strip_time_from_date", "to_display_date", "to_iso_date", "is_valid_display_date",
    "to_hhmm", "to_display_time", "duration_hhmm",
    "to_int", "to_float", "to_percentage", "extract_first_number",
    "calc_defect_percentage",
    # Enums & maps
    "FieldName", "DirectionRule", "DOFieldName",
    "AUDIT_TYPE_PATTERNS",
    "NUMERIC_FIELD_NAMES", "DO_FILL_DOWN_FIELDS",
]