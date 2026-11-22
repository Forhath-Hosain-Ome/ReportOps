"""
----------------------------
Extracts all date fields from an audit report sheet.

Fields handled:
  - date_of_issue  (NOT extracted from sheet — injected from batch.inspection_date)
  - exf            (Ex-Factory date)
  - po_edt         (PO Estimated Delivery)
  - po_wh          (PO Warehouse / ship date — may be split across 3 cells)
  - plan_edt       (Plan Estimated Delivery)
  - plan_wh        (Plan Warehouse date)

Important: date_of_issue is always set by the upload batch (user-selected
inspection date) and is never extracted from the sheet.  This file provides
extract() as a stub that always returns "" for it, but provides individual
extract functions for the 5 shipment dates.

All extracted values are normalised to MM/DD/YYYY by to_display_date().

To add a new date label → add to the relevant SYNONYMS list below.
To change normalisation → edit to_display_date() in extraction/core/normalise.py.
"""

from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    to_display_date as _tdtl,
    date_table as _dtbl,
)
from final_summary.utils import shipment_and_time
# ---------------------------------------------------------------------------
# Per-field synonym lists
# ---------------------------------------------------------------------------

EXF_SYNONYMS: list[str] = [
    "exf",
]

PO_EDT_SYNONYMS: list[str] = [
    "po etd",
    "po. etd",
]

PO_WH_SYNONYMS: list[str] = [
    "po wh",
    "powh",
    "po w/h",
    "po. wh",
]

PLAN_EDT_SYNONYMS: list[str] = [
    "plan etd",
    "plan edt",
    "plan  etd",
]

PLAN_WH_SYNONYMS: list[str] = [
    "plan wh",
    "plan w/h",
]

# All dates scan right (value is in the next cell / cells)
_DIRECTION = DirectionRule.RIGHT

_labelp = CellGrid.find_label_positions

# ---------------------------------------------------------------------------
# Unified extract() — returns all 5 date fields as a dict
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """
    Extract all 5 shipment date fields in one pass.

    date_of_issue is NOT extracted here — it is always injected from
    batch.inspection_date in the task layer.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    dict with keys: exf, po_edt, po_wh, plan_edt, plan_wh
    All values are MM/DD/YYYY strings or "" if not found.
    """
    return {
        "exf":      shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, EXF_SYNONYMS),
        "po_edt":   shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, PO_EDT_SYNONYMS),
        "po_wh":    shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, PO_WH_SYNONYMS),
        "plan_edt": shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, PLAN_EDT_SYNONYMS),
        "plan_wh":  shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, PLAN_WH_SYNONYMS),
    }