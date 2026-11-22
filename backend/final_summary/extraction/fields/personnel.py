"""
--------------------------------
Extracts personnel-related fields from an audit report sheet.

Fields handled:
  - inspector       (QC inspector name)
  - person          (responsible person / representative)
  - carton          (carton inspection number)
  - needle_detector (needle detector check result)
  - remarks         (general remarks)
  - audit_result    (PASS / FAIL)
  - do_set_col_size (D.O. set / colour / size breakdown note)

needle_detector and remarks intentionally scan DOWN — these values appear
below their labels in the sheet layout, not to the right.

audit_result scans RIGHT only — always in the same row as the label.

To add a new label → add to the relevant SYNONYMS list.
To change search direction for a field → edit the corresponding _DIRECTION constant.
"""

from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    resolve_value as _rslv,
    find_inline_value as _inlineval,
)
from final_summary.utils import base_extract

# ---------------------------------------------------------------------------
# Per-field synonym lists and directions
# ---------------------------------------------------------------------------

INSPECTOR_SYNONYMS: list[str] = [
    "inspector",
    "qc inspector",
    "auditor",
]
_INSPECTOR_DIR = DirectionRule.RIGHT

PERSON_SYNONYMS: list[str] = [
    "person",
    "responsible person",
    "rep",
    "person in charge",
]
_PERSON_DIR = DirectionRule.RIGHT

CARTON_SYNONYMS: list[str] = [
    "carton inspection",
    "inspection ctn",
    "inspection carton",
    "our inspection carton",
    "our inspection carton number",
    "carton no",
    "our inspection carton no",
    "inspection carton no",
]
_CARTON_DIR = DirectionRule.RIGHT

NEEDLE_DETECTOR_SYNONYMS: list[str] = [
    "needle detector",
    "needle detector check",
    "n d",
    "nd check",
]
# Intentionally DOWN — value is below the label in the sheet
_NEEDLE_DIR = DirectionRule.DOWN

REMARKS_SYNONYMS: list[str] = [
    "remarks",
    "remark",
    "note",
    "notes",
]
# Intentionally DOWN — multi-line remarks appear below the label
_REMARKS_DIR = DirectionRule.DOWN

AUDIT_RESULT_SYNONYMS: list[str] = [
    "audit result",
    "result",
    "inspection result",
    "overall result",
]
_AUDIT_RESULT_DIR = DirectionRule.RIGHT

DO_SET_COL_SIZE_SYNONYMS: list[str] = [
    "do set col size",
    "do set colour size",
    "d o set col size",
    "set col size",
]
# DOWN — breakdown table appears below the label
_DO_SET_COL_DIR = DirectionRule.DOWN
_labelp = CellGrid.find_label_positions

# ---------------------------------------------------------------------------
# Unified extract() — returns all personnel fields as a dict
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str]:
    
    return {
        "inspector":       base_extract(grid, path, _labelp, _inlineval, _rslv, INSPECTOR_SYNONYMS, _INSPECTOR_DIR),
        "person":          base_extract(grid, path, _labelp, _inlineval, _rslv, PERSON_SYNONYMS, _PERSON_DIR),
        "carton":          base_extract(grid, path, _labelp, _inlineval, _rslv, CARTON_SYNONYMS, _CARTON_DIR),
        "needle_detector": base_extract(grid, path, _labelp, _inlineval, _rslv, NEEDLE_DETECTOR_SYNONYMS, _NEEDLE_DIR),
        "remarks":         base_extract(grid, path, _labelp, _inlineval, _rslv, REMARKS_SYNONYMS, _REMARKS_DIR),
        "audit_result":    base_extract(grid, path, _labelp, _inlineval, _rslv, AUDIT_RESULT_SYNONYMS, _AUDIT_RESULT_DIR),
        "do_set_col_size": base_extract(grid, path, _labelp, _inlineval, _rslv, DO_SET_COL_SIZE_SYNONYMS, _DO_SET_COL_DIR),
    }