"""
--------------------------------
Extracts the item / product name from an audit report sheet.

To change label text  → edit SYNONYMS
To change search dir  → edit DIRECTION
"""

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
    "product description",
    "product name",
    "item name",
    "description",
    "item",
]

DIRECTION = DirectionRule.DOWN


# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------

def extract(grid: CellGrid, path: Optional[Path] = None, format_type: str = "") -> str:
    """
    Find the item name label and return the value to its right.

    Parameters
    ----------
    grid : CellGrid for the sheet being processed
    path : unused

    Returns
    -------
    Item name string, or "" if not found.
    """
    positions = grid.find_label_positions(SYNONYMS)

    for row, col, cell_text in positions:
        for syn in SYNONYMS:
            value = find_inline_value(syn, cell_text)
            if value:
                return value
        value = resolve_value(grid, (row, col), DIRECTION)
        if value:
            return value

    return ""