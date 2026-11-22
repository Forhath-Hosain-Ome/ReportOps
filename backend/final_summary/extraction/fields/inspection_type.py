"""
--------------------------------------
Extracts and resolves the inspection type from an audit report.

Two-stage strategy:
  1. SHEET LABEL — scan the grid for an "Inspection Type" / "Audit Type" label
     and read the value next to it.
  2. FILE NAME FALLBACK — if the sheet has no label (common in some formats),
     infer the type from keywords in the Excel file name.

The file-name resolver also computes the audit percentage (e.g. "FINAL 75%")
from audit_qty / ship_qty when those are already known.  For that reason,
extract_from_filename() accepts optional qty strings as extra arguments.

To add new label text    → edit SYNONYMS
To add new type keywords → edit AUDIT_TYPE_PATTERNS in extraction/core/label_map.py
"""

import logging
import re
from pathlib import Path
from typing import Optional
from utils.normalize_filename import normalize_filename
from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    AUDIT_TYPE_PATTERNS,
    resolve_value,
    find_inline_value,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "inspection type",
    "audit type",
    "type of inspection",
    "inspection type:",
]

DIRECTION = DirectionRule.RIGHT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_pct(audit_qty: str, ship_qty: str) -> str:
    """Return "NN.NN" string or "" if either quantity is invalid."""
    try:
        pct = round(int(audit_qty) / int(ship_qty) * 100, 2)
        return str(pct)
    except (ValueError, TypeError, ZeroDivisionError):
        return ""


# ---------------------------------------------------------------------------
# File-name resolver (stage 2)
# ---------------------------------------------------------------------------

def extract_from_filename(
    filename: str,
    audit_qty: str = "",
    ship_qty: str = "",
) -> str:
    """
    Infer the inspection type from keywords in *filename*.

    Decision tree (evaluated top-to-bottom):
      1. RE-FINAL  (e.g. "2nd-time-RE-FINAL-50pct")
      2. FINAL     (e.g. "FACTORY_FINAL_AUDIT")
      3. INLINE / SAMPLE / CMF  (keyword match)
      4. ""        (no keyword matched — caller decides what to do)

    Parameters
    ----------
    filename  : Excel file name (stem or full name)
    audit_qty : optional — used to compute "NN.NN%" suffix
    ship_qty  : optional — used to compute "NN.NN%" suffix

    Returns
    -------
    Resolved inspection type string, or "" if unrecognised.
    """
    logging.warning("filename=%s", filename)
    if not filename:
        return ""
    name = normalize_filename(filename)
    name = filename.lower().strip()
    name = re.sub(r"\s+", " ", name.strip())
    name = name.upper()
    name = name.replace(" - ", "-").replace(" ", "-")

    # ── RE-FINAL ──────────────────────────────────────────────────────────
    if re.search(AUDIT_TYPE_PATTERNS["RE-FINAL"], name) or re.search(AUDIT_TYPE_PATTERNS["RE-AUDIT"], name):
        pct       = _safe_pct(audit_qty, ship_qty)
        nth_match = re.search(r"\b(\d+(?:st|nd|rd|th))\s*time\b", name)
        if nth_match:
            nth = nth_match.group(1).upper()
            return f"{nth} RE-FINAL {pct}%" if pct else f"{nth} RE-FINAL"
        return f"RE-FINAL {pct}%" if pct else "RE-FINAL"

    # ── FINAL ────────────────────────────────────────────────────────────
    if re.search(AUDIT_TYPE_PATTERNS["FINAL"], name):
        pct = _safe_pct(audit_qty, ship_qty)
        return f"FINAL {pct}%" if pct else "FINAL"

    # ── Other known types ─────────────────────────────────────────────────
    for audit_type in ("INLINE", "SAMPLE", "CMF", "RANDOM"):
        if re.search(AUDIT_TYPE_PATTERNS[audit_type], name):
            return audit_type
    logging.warning("normalized=%s", name)
    logging.warning("pattern=%s", AUDIT_TYPE_PATTERNS["FINAL"])
    logging.warning(
        "match=%s",
        bool(re.search(AUDIT_TYPE_PATTERNS["FINAL"], name, re.I))
    )
    logging.debug(f"inspection_type: no keyword match in '{filename}'")
    return ""


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None, format_type: str = "") -> str:
    """
    Stage 1: scan the grid for the inspection type label.
    Stage 2: fall back to file-name inference if stage 1 yields nothing.

    Note: percentage suffix (e.g. "FINAL 75%") is computed in
    extract_from_filename() only when called with qty values from the task.
    This function does not compute percentages — it just returns the raw
    label value found on the sheet (e.g. "FINAL AUDIT", "RE-FINAL 2ND").

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : Excel file Path — used for stage-2 file-name fallback

    Returns
    -------
    Inspection type string, or "" if not found on the sheet.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, cell_text in positions:
        for syn in SYNONYMS:
            value = find_inline_value(syn, cell_text)
            if value:
                return value.upper()

        value = resolve_value(grid, (row, col), DIRECTION)
        if value:
            return value.upper()

    # Stage 2: file-name fallback
    if path:
        return extract_from_filename(path.stem)

    return ""