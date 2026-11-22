"""
------------------------------
Public registry of all per-field extractor functions.

Every field file exports one or more callables. They are collected here so
format extractors (extraction/formats/*.py) can import from a single place:

    from extraction.fields import FIELD_EXTRACTORS, extract_defects, extract_do_table

Adding a new field
------------------
1. Create extraction/fields/<field_name>.py with an extract() function.
2. Import and register it here — that is the only change needed.
3. Format extractors pick it up automatically via FIELD_EXTRACTORS.

FIELD_EXTRACTORS maps each AuditRecord field name (str) to the callable
that extracts it.  Fields that return multiple keys (times, quantities, dates,
personnel) use the dict-returning extract() and are handled specially by the
base format extractor.
"""

# ── Single-value extractors ────────────────────────────────────────────────
from .report_no       import extract as extract_report_no
from .item_name       import extract as extract_item_name
from .style_no        import extract as extract_style_no
from .po_no           import extract as extract_po_no
from .inspection_type import extract as extract_inspection_type
from .inspection_type import extract_from_filename as extract_type_from_filename

# ── Multi-value extractors (return dicts) ─────────────────────────────────
from .times      import extract as extract_times
from .dates      import extract as extract_dates
from .quantities import extract as extract_quantities
from .personnel  import extract as extract_personnel

# ── Special extractors (use openpyxl directly, not CellGrid) ─────────────
from .defects  import extract as extract_defects
from .do_table import extract as extract_do_table

from .country import get_country

# ---------------------------------------------------------------------------
# FIELD_EXTRACTORS registry
#
# Maps field name → callable(grid, path) → str
#
# Only SINGLE-value fields are listed here.
# Multi-value and special extractors are called separately by the base extractor.
# ---------------------------------------------------------------------------

FIELD_EXTRACTORS: dict = {
    "report_no":       extract_report_no,
    "item_name":       extract_item_name,
    "style_no":        extract_style_no,
    "po_no":           extract_po_no,
    "inspection_type": extract_inspection_type,
}

__all__ = [
    # Single-value
    "extract_report_no",
    "extract_item_name",
    "extract_style_no",
    "extract_po_no",
    "extract_inspection_type",
    "extract_type_from_filename",
    # Multi-value
    "extract_times",
    "extract_dates",
    "extract_quantities",
    "extract_personnel",
    # Special
    "extract_defects",
    "extract_do_table",
    # Registry
    "FIELD_EXTRACTORS",
]