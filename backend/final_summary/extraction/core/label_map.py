"""
-----------------------------
Shared enums and constants used across the entire extraction pipeline.

Design decision (agreed in Step 2):
  - FieldName     : kept as an enum — safe autocomplete, typo-proof field keys
  - DirectionRule : kept as an enum — shared constants used by proximity engine
  - LabelSynonym  : DROPPED — each field file in extraction/fields/ owns its
                    own synonym list as plain Python strings. No central registry.

Adding a new field
------------------
1. Add a value to FieldName below.
2. Create extraction/fields/<field_name>.py with SYNONYMS list + extract() fn.
3. Import and register it in extraction/fields/__init__.py.
4. That's it — no changes needed here.

Changing direction for a field
-------------------------------
Change the direction in the field's own .py file, not here.
DirectionRule values are imported from here into the field file.
"""

from enum import Enum


# =============================================================================
# FIELD NAMES — canonical internal names for all extracted fields
# =============================================================================

class FieldName(str, Enum):
    """
    All fields that can be extracted from any Excel audit report.
    The .value is the Python attribute name used on AuditRecord.

    Fields are grouped by category for readability.
    """

    # ── Identity / header ─────────────────────────────────────────────────
    FACTORY         = "factory"
    CLIENT          = "client"
    REPORT_NO       = "report_no"
    ITEM_NAME       = "item_name"
    STYLE_NO        = "style_no"
    PO_NO           = "po_no"
    INSPECTION_TYPE = "inspection_type"
    DATE_OF_ISSUE   = "date_of_issue"

    # ── Quantities ─────────────────────────────────────────────────────────
    PO_QTY          = "po_qty"
    DO_QTY          = "do_qty"
    SHIP_QTY        = "ship_qty"
    AUDIT_QTY       = "audit_qty"
    DEFECT_QTY      = "defect_qty"

    # ── Shipment dates ─────────────────────────────────────────────────────
    EXF             = "exf"
    PO_EDT          = "po_edt"
    PO_WH           = "po_wh"
    PLAN_EDT        = "plan_edt"
    PLAN_WH         = "plan_wh"

    # ── Times ──────────────────────────────────────────────────────────────
    FACTORY_IN_TIME  = "factory_in_time"
    FACTORY_OUT_TIME = "factory_out_time"
    AUDIT_START_TIME = "audit_start_time"
    AUDIT_END_TIME   = "audit_end_time"

    # ── Audit outcome ──────────────────────────────────────────────────────
    AUDIT_RESULT    = "audit_result"

    # ── Personnel ──────────────────────────────────────────────────────────
    INSPECTOR       = "inspector"
    PERSON          = "person"

    # ── Additional checks ─────────────────────────────────────────────────
    CARTON          = "carton"
    NEEDLE_DETECTOR = "needle_detector"
    REMARKS         = "remarks"
    DO_SET_COL_SIZE = "do_set_col_size"


# =============================================================================
# DIRECTION RULES — how the proximity engine reads the value after finding a label
# =============================================================================

class DirectionRule(str, Enum):
    """
    Controls which cell(s) the proximity resolver scans for the field value
    after the label cell is located.

    Rules can be combined in a list:
        direction = [DirectionRule.DOWN_IF_INT, DirectionRule.RIGHT]
    means: try DOWN (integers only) first; fall back to RIGHT.
    """

    # Scan right across the same row (most common — "Label | Value")
    RIGHT         = "right"

    # Scan down the same column ("Label\\nValue")
    DOWN          = "down"

    # Scan down but only accept integer values; stop on first non-integer
    DOWN_IF_INT   = "down_if_int"

    # Try right first, then down (used when value position varies)
    RIGHT_THEN_DOWN = "right_then_down"

    # Try down first, then right
    DOWN_THEN_RIGHT = "down_then_right"


# =============================================================================
# DO TABLE FIELD NAMES — internal names for D.O. plan table columns
# =============================================================================

class DOFieldName(str, Enum):
    """Canonical field names for columns in the Delivery Order plan table."""

    DATE       = "date"
    PO_QTY     = "po_qty"
    DO_NO      = "do_no"
    DO_QTY     = "do_qty"
    SHIP_QTY   = "ship_qty"
    AUDIT_QTY  = "audit_qty"
    DO_BALANCE = "do_balance"
    PO_EXTRA   = "po_extra"
    REMARKS    = "remarks"
    PO_BALANCE = "po_balance"




# =============================================================================
# AUDIT TYPE PATTERNS
# =============================================================================
# Regex patterns used to infer the inspection type from a file name.
# Update here when new naming conventions appear.

AUDIT_TYPE_PATTERNS: dict = {
    "RE-FINAL": r"re[-\s]?final",
    "RE-AUDIT": r"re[-\s]?audit",
    "FINAL":    r"\bfinal\b",
    "INLINE":   r"in[-\s]?line",
    "SAMPLE":   r"sample",
    "CMF":      r"cmf",
    "RANDOM":   r"random",
}


# =============================================================================
# NUMERIC FIELDS
# =============================================================================
# Fields that must hold a pure integer after extraction.
# The post-processor strips non-numeric text from these automatically.

NUMERIC_FIELD_NAMES: set = {
    FieldName.PO_QTY,
    FieldName.DO_QTY,
    FieldName.SHIP_QTY,
    FieldName.AUDIT_QTY,
}


# =============================================================================
# DO TABLE FILL-DOWN FIELDS
# =============================================================================
# D.O. table columns whose values carry forward across merged/empty rows.

DO_FILL_DOWN_FIELDS: set = {
    DOFieldName.DATE,
    DOFieldName.PO_QTY,
    DOFieldName.PO_EXTRA,
}