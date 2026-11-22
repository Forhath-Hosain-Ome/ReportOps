"""
----------------------------
Extracts all time fields from an audit report sheet and derives duration totals.

Fields handled:
  - factory_in_time     (time factory staff arrived)
  - factory_out_time    (time factory staff left)
  - factory_total_hours (derived: factory_out − factory_in)
  - audit_start_time    (time audit began)
  - audit_end_time      (time audit ended)
  - audit_total_hours   (derived: audit_end − audit_start)

All raw values are normalised to "HH:MM" (24-hour) by to_hhmm().
Durations are computed by duration_hhmm() and also returned as "HH:MM".

To add a new label variant → add to the relevant SYNONYMS list.
To change time format      → edit to_hhmm() in extraction/core/normalise.py.
"""

from pathlib import Path
from typing import Optional
import logging
from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    to_hhmm as _tdtl,
    duration_hhmm,
    resolve_value as _dtbl,
)
logger = logging.getLogger(__name__)
from final_summary.utils import shipment_and_time
# ---------------------------------------------------------------------------
# Per-field synonym lists
# ---------------------------------------------------------------------------

FACTORY_IN_SYNONYMS: list[str] = [
    "factory in time",
    "factory in-time",
    "factory in",
    "in time",
    "factory intime",
]

FACTORY_OUT_SYNONYMS: list[str] = [
    "factory out time",
    "factory out-time",
    "factory out",
    "out time",
    "factory outtime",
]

AUDIT_START_SYNONYMS: list[str] = [
    "audit start time",
    "start time",
    "audit start",
    "inspection start",
    "inspection start time",
]

AUDIT_END_SYNONYMS: list[str] = [
    "audit end time",
    "end time",
    "audit end",
    "inspection end",
    "inspection end time",
]

_DIRECTION = DirectionRule.RIGHT

_labelp = CellGrid.find_label_positions

# ---------------------------------------------------------------------------
# Unified extract() — returns all time fields + derived durations
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
) -> dict[str, str]:
    """
    Extract all 4 raw time fields and derive the 2 duration totals.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    dict with keys:
      factory_in_time, factory_out_time, factory_total_hours,
      audit_start_time, audit_end_time, audit_total_hours
    All values are "HH:MM" strings or "" if not found / not computable.
    """
    factory_in  = shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, FACTORY_IN_SYNONYMS, _DIRECTION)
    factory_out = shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, FACTORY_OUT_SYNONYMS, _DIRECTION)
    audit_start = shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, AUDIT_START_SYNONYMS, _DIRECTION)
    audit_end   = shipment_and_time(grid, path, _labelp, _dtbl, _tdtl, AUDIT_END_SYNONYMS, _DIRECTION)

    return {
        "factory_in_time":     factory_in,
        "factory_out_time":    factory_out,
        "factory_total_hours": duration_hhmm(factory_in, factory_out),
        "audit_start_time":    audit_start,
        "audit_end_time":      audit_end,
        "audit_total_hours":   duration_hhmm(audit_start, audit_end),
    }