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
# Field configuration
# ---------------------------------------------------------------------------

syns: list[str] = [
    "department",
    "division",
]

dir = DirectionRule.DOWN
_labelp = CellGrid.find_label_positions

# ---------------------------------------------------------------------------
# Extractor
# ---------------------------------------------------------------------------


def extract_department(grid: CellGrid, path: Optional[Path] = None, frm: str = "", ) -> str:
    depertment = base_extract(grid, path, _labelp, _inlineval, _rslv, syns, dir, frm) or "UNKNOWN"
    return depertment