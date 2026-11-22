r"""
extraction/fields/report_no.py
--------------------------------
Extracts the Report Number from an audit report sheet.

Three-stage strategy
--------------------
1. LABEL SEARCH — scan for known report number labels; accept any non-empty
   value to the right (pattern validation is a soft check, not a gate).
   This handles:
      - Standard format: "EU26-02CIPL-001"  → passes pattern
      - PQC format:      "01"               → fails pattern but is still valid

2. PATTERN SEARCH — scan the entire grid for any cell matching the standard
   Report Number pattern ([A-Z]{2}\\d{2}-\\d{2}[A-Z0-9]+-\\d+).

3. FIXED CELL FALLBACK — for formats where the report number is always at a
   known position (e.g. PQC: row 61, col 7).
   Define FORMAT_FIXED_CELLS keyed by format_type from BuyerFactoryPair.

To add a new label      → add to SYNONYMS
To add a new fixed cell → add to FORMAT_FIXED_CELLS
"""

import re
from pathlib import Path
from typing import Optional

from final_summary.extraction.core import (
    CellGrid,
    DirectionRule,
    resolve_value,
    find_inline_value,
)

# ---------------------------------------------------------------------------
# Field configuration
# ---------------------------------------------------------------------------

SYNONYMS: list[str] = [
    "report no",
    "report number",
    "inspection report no",
    "audit report no",
]

DIRECTION = DirectionRule.RIGHT

# Standard Report Number pattern
_REPORT_NO_RE = re.compile(r"^[A-Z]{2}\d{2}-\d{2}[A-Z0-9]+-\d+$")
_PO_NO_RE     = re.compile(r"^P\d{0,4}[-\s]?\d{6}-\d{3}(?:-\d+)*$")

# Fixed cell fallback per format_type: {format_type: (row_0based, col_0based)}
# These are checked only when label + pattern search both fail.
FORMAT_FIXED_CELLS: dict[str, tuple[int, int]] = {
    "WOVEN_78": (60, 6),   # PQC format: R61 C7 (0-based: R60 C6)
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_valid_report_no(value: str) -> bool:
    if not value:
        return False
    return bool(_REPORT_NO_RE.match(value.strip().rstrip(".,;:")))

def _is_po_no(value: str) -> bool:
    """True if value looks like a PO number — must not be returned as report_no."""
    return bool(_PO_NO_RE.search(value.strip()))

def _pattern_scan(grid: CellGrid) -> str:
    """Scan every cell for a value matching the standard report number pattern."""
    for row, col, value in grid.iter_cells():
        cleaned = value.strip().rstrip(".,;:")
        if _is_valid_report_no(cleaned):
            return cleaned
    return ""


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(
    grid: CellGrid,
    path: Optional[Path] = None,
    format_type: str = "",
) -> str:
    """
    Extract the report number using a three-stage strategy.

    Stage 1: Label search → any non-empty value (raw fallback accepted).
    Stage 2: Pattern scan of entire grid.
    Stage 3: Fixed cell lookup by format_type.

    Parameters
    ----------
    grid        : CellGrid for the sheet being processed
    path        : unused
    format_type : BuyerFactoryPair.report_type — used for fixed-cell fallback

    Returns
    -------
    Report number string (e.g. "EU26-02CIPL-001" or "01"), or "" if not found.
    """
    # ── Stage 1: Label search ─────────────────────────────────────────────
    positions = grid.find_label_positions(SYNONYMS)
    for row, col, cell_text in positions:
        # Try inline first: "Label: Value" packed into same cell
        for syn in SYNONYMS:
            inline_value = find_inline_value(syn, cell_text)
            if inline_value and not _is_po_no(inline_value):
                return inline_value.strip()
        
        # Scan right up to 10 cells
        for c in range(col + 1, min(col + 10, grid.ncols)):
            value = grid.get(row, c)
            if not value:
                continue
            # Clean and return — valid pattern preferred, but raw accepted
            cleaned = value.strip().rstrip(".,;:")
            if not cleaned:
                continue
            if _is_po_no(cleaned):
                # This cell holds a PO number, not a report number — skip
                continue
            
            return cleaned

    # ── Stage 2: Pattern scan ─────────────────────────────────────────────
    found = _pattern_scan(grid)
    if found:
        return found

    # ── Stage 3: Fixed cell fallback ──────────────────────────────────────
    if format_type and format_type in FORMAT_FIXED_CELLS:
        r, c = FORMAT_FIXED_CELLS[format_type]
        value = grid.get(r, c)
        if value and value.strip():
            return value.strip()

    return ""