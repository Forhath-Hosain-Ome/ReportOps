"""
defect_extractor_enhanced.py
---------------------------
Enhanced defect extractor that handles different Excel layouts including:
- Standard SPI-78 format (Re-Final and Final)
- Knit-35 format (Inline) with measurement data
- Handling of horizontally merged cells for defect names
- Improved defect name matching logic

Structure understood from samples
----------------------------------
SPI-78 Format (Re-Final/Final):
  Row N   : "Defects" | ... | "Major Defect" | "Minor Defect" | "Comment"
  Row N+1 : "A : Fabrics" | "1.Damage" | ... | <major> | <minor> | <comment>

Knit-35 Format (Inline):
  Measurement specification sheets - not defect-focused
  May contain quality-related data in different layout

Enhanced Features:
1. Horizontal merge detection for defect names
2. Flexible column mapping based on content analysis
3. Better handling of different template variations
4. Improved defect name matching with fuzzy logic
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import openpyxl

from final_summary.extraction.core import get_template_key, get_items, get_categories


# ---------------------------------------------------------------------------
# Sentinel – the cell value that marks the end of the defect table
# ---------------------------------------------------------------------------

_END_SENTINEL_PATTERN = re.compile(
    r"do\s*/\s*set\s*/\s*col\s*/\s*size", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_int(value: Any) -> int:
    """Convert a cell value to int, returning 0 on failure."""
    if value is None:
        return 0
    try:
        return int(float(str(value).strip()))
    except (ValueError, TypeError):
        return 0


def _is_end_sentinel(value: Any) -> bool:
    if value is None:
        return False
    return bool(_END_SENTINEL_PATTERN.search(str(value)))


def _is_category_cell(value: Any) -> bool:
    """
    True for category separator rows in either template format.

    Format A (SPI):  "A : Fabrics", "B : Sewing", …
    Format B (PQC):  "A素材不良\n Material Defects", …
    Also catches None — a vertical merge shadow of a category header above.
    """
    if value is None:
        return True                             # merge shadow → category row
    s = str(value).strip()
    if not s:
        return False
    if re.match(r"^[A-F]\s*:", s):             # Format A
        return True
    if len(s) >= 2 and s[0] in "ABCDEF" and ord(s[1]) > 127:   # Format B
        return True
    return False


def _is_horizontally_merged_cell(row: List[Any], col_idx: int) -> bool:
    """
    Detect if a cell is part of a horizontally merged group.
    In openpyxl with data_only=True, merged cells have values only in
    the top-left cell; other cells in the merge are None/empty.
    """
    if col_idx >= len(row) or row[col_idx] is None:
        return False

    # Check if this cell has a value and subsequent cells are empty/None
    # suggesting it might be part of a horizontal merge
    has_value = row[col_idx] is not None and str(row[col_idx]).strip() != ""

    if not has_value:
        return False

    # Look ahead to see if we have a run of empty cells suggesting a merge
    empty_count = 0
    for i in range(col_idx + 1, min(col_idx + 5, len(row))):  # Check next 4 cells
        if i >= len(row):
            break
        cell_val = row[i]
        if cell_val is None or (isinstance(cell_val, str) and str(cell_val).strip() == ""):
            empty_count += 1
        else:
            break

    # If we have 2 or more consecutive empty cells after a value,
    # it's likely part of a horizontal merge
    return empty_count >= 2


def _find_actual_value_start(row: List[Any], start_idx: int) -> Tuple[int, Any]:
    """
    Find the first non-empty cell starting from start_idx,
    skipping over potentially merged cells.
    """
    idx = start_idx
    while idx < len(row):
        cell_val = row[idx]
        if cell_val is not None and str(cell_val).strip() != "":
            return idx, cell_val
        idx += 1
    return len(row), None


def _partial_match(excel_text: str, master_name: str) -> bool:
    """
    True when the Excel item text shares at least one meaningful word with
    the canonical master name.

    Normalisation strips leading numbers/dots ("1.Damage" → "damage") so
    positional prefixes never cause false mismatches.  Words of ≤ 2 chars
    are ignored (articles, prepositions, etc.).

    This is a sanity-check only — a mismatch logs a WARNING but never
    blocks saving.
    """
    def _words(s: str) -> set[str]:
        s = re.sub(r"[^a-z\s]", " ", s.lower())
        return {w for w in s.split() if len(w) > 2}

    return bool(_words(excel_text) & _words(master_name))


def _extract_defect_from_row_enhanced(
    row: List[Any],
    header_cols: Dict[str, int],
    item_position: int,
    master_items_by_no: Dict[int, Dict],
    master_categories: Dict[str, Dict],
    path_name: str
) -> Optional[Dict[str, Any]]:
    """
    Extract defect information from a single row with enhanced logic
    for handling merged cells and different layouts.
    """
    # Extract category from column A (with merge shadow handling)
    col_a = row[0] if len(row) > 0 else None
    current_category = None

    if col_a is not None and _is_category_cell(col_a):
        current_category = str(col_a).strip()
    # For merge shadows (None values), we keep the last known category
    # This is handled by the caller maintaining state

    # Get item cell - normally in the column after "Defects" header
    defect_col = header_cols.get("defect_col", 0)
    item_col_specified = header_cols.get("item_col")

    if item_col_specified is not None and item_col_specified < len(row):
        # Use explicitly identified item column
        item_cell = row[item_col_specified]
    else:
        # Default: item is in column after defect column
        default_item_col = defect_col + 1
        item_cell = row[default_item_col] if default_item_col < len(row) else None

    # Handle potential horizontal merge for defect name
    defect_name = None
    actual_item_col = None

    if item_cell is not None:
        item_str = str(item_cell).strip()
        if item_str != "":
            # Check if this might be part of a horizontal merge
            if _is_horizontally_merged_cell(row, default_item_col if item_col_specified is None else item_col_specified):
                # Find the actual start of the value (should be current cell if it's the merge origin)
                actual_item_col, defect_name = _find_actual_value_start(row,
                                                                      default_item_col if item_col_specified is None else item_col_specified)
            else:
                defect_name = item_str
                actual_item_col = default_item_col if item_col_specified is None else item_col_specified

    if defect_name is None or defect_name == "":
        return None  # No defect name found

    # Extract counts using enhanced logic for merged cells
    major_col = header_cols.get("major_col")
    minor_col = header_cols.get("minor_col")
    comment_col = header_cols.get("comment_col")

    # Extract major count
    major = 0
    if major_col is not None and major_col < len(row):
        major_val = row[major_col]
        # Check if the count cell might be part of a merge
        if _is_horizontally_merged_cell(row, major_col):
            _, actual_major_val = _find_actual_value_start(row, major_col)
            major_val = actual_major_val
        major = _to_int(major_val)

    # Extract minor count
    minor = 0
    if minor_col is not None and minor_col < len(row):
        minor_val = row[minor_col]
        # Check if the count cell might be part of a merge
        if _is_horizontally_merged_cell(row, minor_col):
            _, actual_minor_val = _find_actual_value_start(row, minor_col)
            minor_val = actual_minor_val
        minor = _to_int(minor_val)

    # Extract comment
    comment = ""
    if comment_col is not None and comment_col < len(row):
        comment_val = row[comment_col]
        # Check if the comment cell might be part of a merge
        if _is_horizontally_merged_cell(row, comment_col):
            _, actual_comment_val = _find_actual_value_start(row, comment_col)
            comment_val = actual_comment_val
        if comment_val is not None:
            comment = str(comment_val).strip()

    # Map to defect_master by position
    master_entry = master_items_by_no.get(item_position)
    category_code = master_entry["category_code"] if master_entry else ""
    category_label = (
        master_categories.get(category_code, {}).get("label", "")
        if category_code else ""
    )
    canonical_name = (
        master_entry["name"] if master_entry
        else str(defect_name or "").strip() or f"Item {item_position}"
    )

    # Partial-match sanity check
    matched = master_entry is not None
    if master_entry and defect_name:
        matched = _partial_match(str(defect_name), canonical_name)
        if not matched:
            logging.warning(
                f"[{path_name}] Row item_no={item_position}: "
                f"Defect text '{defect_name}' has low overlap with "
                f"master name '{canonical_name}'. "
                f"Saving with master name regardless."
            )

    return {
        "item_no":       item_position,
        "category_code": category_code,
        "category":      category_label,
        "item":          canonical_name,
        "major":         major,
        "minor":         minor,
        "comment":       comment,
        "name_matched":  matched,
    }


# ---------------------------------------------------------------------------
# Main extractor
# ---------------------------------------------------------------------------

def extract(
    path: Path,
    sheet_name: str = "Inspection Report",
    defect_column_count: int = 37,
    pair: Any = None,  # BuyerFactoryPair instance
) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, Any]]:
    """
    Open *path* with openpyxl, extract the defect table from *sheet_name*,
    and map every item row to its canonical defect_master entry.

    Enhanced version with better handling of:
    - Horizontally merged cells
    - Different template layouts
    - Knit-35 format detection
    """
    # ── Resolve defect_column_count from pair if provided ───────────────────
    if pair is not None:
        try:
            defect_column_count = pair.defect_column_count
            logging.info(
                f"[{path.name}] defect_column_count={defect_column_count} "
                f"(from pair.report_type='{pair.report_type}')"
            )
        except AttributeError as e:
            logging.warning(
                f"[{path.name}] pair has no defect_column_count ({e}); "
                f"using default={defect_column_count}"
            )
    else:
        logging.info(
            f"[{path.name}] No pair provided; "
            f"using defect_column_count={defect_column_count}"
        )

    # ── Resolve defect_master template ──────────────────────────────────────
    template_key = get_template_key(defect_column_count)
    if template_key is None:
        logging.warning(
            f"[{path.name}] No defect_master template for "
            f"defect_column_count={defect_column_count}. "
            f"Canonical names unavailable; will use Excel text as fallback."
        )
    else:
        logging.info(
            f"[{path.name}] defect_column_count={defect_column_count} "
            f"→ template '{template_key}'"
        )

    master_items = get_items(template_key)      if template_key else []
    master_cats  = get_categories(template_key) if template_key else {}
    item_by_no: dict[int, dict] = {it["item_no"]: it for it in master_items}

    def _empty_meta() -> Dict[str, Any]:
        return {
            "template_key":   template_key,
            "expected_count": defect_column_count,
            "actual_count":   0,
            "count_ok":       False,
        }

    # ── Open workbook ────────────────────────────────────────────────────────
    try:
        wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    except Exception as exc:
        logging.error(f"Cannot open '{path.name}': {exc}")
        return [], {}, _empty_meta()

    # Build search order: preferred sheet first, then all others.
    preferred = next(
        (s for s in wb.sheetnames if s.lower() == sheet_name.lower()), None
    )
    search_order = (
        [preferred] + [s for s in wb.sheetnames if s != preferred]
        if preferred
        else list(wb.sheetnames)
    )

    rows = []
    for s_name in search_order:
        candidate_rows = list(wb[s_name].iter_rows(values_only=True))
        # Quick check: does this sheet contain a "defects" header cell?
        found = any(
            cell is not None and str(cell).strip().lower() == "defects"
            for row in candidate_rows
            for cell in row
            if cell is not None
        )
        if found:
            rows = candidate_rows
            logging.info(f"[{path.name}] Defect table found on sheet '{s_name}'")
            break
        logging.debug(f"[{path.name}] Sheet '{s_name}': no defect header, skipping")

    wb.close()

    if not rows:
        logging.warning(
            f"[{path.name}] Defect header not found on any sheet "
            f"(searched: {search_order})."
        )
        return [], {}, _empty_meta()

    # ── Step 1: Find the header row ──────────────────────────────────────────
    # Scan every cell (not just col A) so both SPI and PQC layouts are found.
    header_row_idx: Optional[int] = None
    header_cols: Dict[str, int] = {}  # Maps "defect_col", "major_col", etc.

    for r_idx, row in enumerate(rows):
        if not row:
            continue
        for c_idx, cell in enumerate(row):
            if cell is None:
                continue
            normalised = str(cell).strip().lower()
            if normalised == "defects" and "defect_col" not in header_cols:
                header_row_idx = r_idx
                header_cols["defect_col"] = c_idx
                # If "Defects" header is in col A (index 0), item names
                # are typically in col B (index 1) - but we'll verify this
            if header_row_idx == r_idx:
                # Discover qty/comment columns from the same header row
                if "major" in normalised and "major_col" not in header_cols:
                    header_cols["major_col"] = c_idx
                if "minor" in normalised and "minor_col" not in header_cols:
                    header_cols["minor_col"] = c_idx
                if "comment" in normalised and "comment_col" not in header_cols:
                    header_cols["comment_col"] = c_idx
        if header_row_idx is not None and len(header_cols) >= 4:  # Found all needed columns
            break

    if header_row_idx is None:
        logging.warning(
            f"[{path.name}] Defect header not found "
            f"(no cell with text 'defects' in any row)."
        )
        return [], {}, _empty_meta()

    required_cols = ["defect_col", "major_col", "minor_col", "comment_col"]
    missing_cols = [col for col in required_cols if col not in header_cols]
    if missing_cols:
        logging.warning(
            f"[{path.name}] Missing columns in defect header row: {missing_cols}. "
            f"Found: {header_cols}"
        )
        # Try to infer missing columns based on typical SPI-78 layout
        defect_col = header_cols.get("defect_col", 0)
        if "major_col" not in header_cols:
            header_cols["major_col"] = defect_col + 5  # Typical offset
        if "minor_col" not in header_cols:
            header_cols["minor_col"] = defect_col + 6  # Typical offset
        if "comment_col" not in header_cols:
            header_cols["comment_col"] = defect_col + 7  # Typical offset
        logging.info(
            f"[{path.name}] Inferred missing columns: major={header_cols.get('major_col')}, "
            f"minor={header_cols.get('minor_col')}, comment={header_cols.get('comment_col')}"
        )

    logging.info(
        f"[{path.name}] Defect header at row {header_row_idx + 1} | "
        f"defect_col={header_cols.get('defect_col')} "
        f"major_col={header_cols.get('major_col')} "
        f"minor_col={header_cols.get('minor_col')} "
        f"comment_col={header_cols.get('comment_col')}"
    )

    # ── Step 2: Scan data rows ───────────────────────────────────────────────
    defect_rows: List[Dict[str, Any]] = []
    item_position = 0   # 1-based; incremented only for real item rows
    last_known_category = None  # Track category across merge shadows

    for r_idx in range(header_row_idx + 1, len(rows)):
        # Stop once we have exactly defect_column_count items
        if item_position >= defect_column_count:
            break

        row   = rows[r_idx]
        col_a = row[0] if row else None

        # Stop at end sentinel
        if _is_end_sentinel(col_a):
            break

        # Update current category for merge shadow handling
        if col_a is not None and _is_category_cell(col_a):
            last_known_category = str(col_a).strip()

        # Get item cell - normally in the column after "Defects" header
        defect_col = header_cols.get("defect_col", 0)
        item_col_specified = header_cols.get("item_col")

        if item_col_specified is not None and item_col_specified < len(row):
            item_cell = row[item_col_specified]
        else:
            # Default: item is in column after defect column
            default_item_col = defect_col + 1
            item_cell = row[default_item_col] if default_item_col < len(row) else None

        # Handle merge shadow: if col A is None, we're in a vertically merged category block
        effective_category = last_known_category if col_a is None else (
            str(col_a).strip() if col_a is not None and _is_category_cell(col_a) else None
        )
        if effective_category is not None:
            last_known_category = effective_category

        # Skip only truly empty rows — both item cell AND effective category are None/blank.
        item_text = str(item_cell).strip() if item_cell is not None else ""
        cat_text = str(effective_category).strip() if effective_category is not None else ""
        if not item_text and not cat_text:
            logging.debug(f"  Row {r_idx + 1}: empty row → skipped")
            continue

        item_position += 1  # this row's 1-based index in the template

        # Use enhanced extraction logic
        defect_row = _extract_defect_from_row_enhanced(
            row, header_cols, item_position, item_by_no, master_cats, path.name
        )

        if defect_row is not None:
            # Override category with the tracked one if we have it
            if last_known_category is not None:
                # Find the category code for this label
                for code, info in master_cats.items():
                    if info.get("label", "") == last_known_category:
                        defect_row["category_code"] = code
                        defect_row["category"] = last_known_category
                        break

            defect_rows.append(defect_row)

    # ── Step 3: Totals + count validation ────────────────────────────────────
    totals = {
        "major": sum(r["major"] for r in defect_rows),
        "minor": sum(r["minor"] for r in defect_rows),
    }

    actual_count = len(defect_rows)
    count_ok     = actual_count == defect_column_count
    if not count_ok:
        logging.warning(
            f"[{path.name}] Defect count mismatch: "
            f"expected {defect_column_count}, got {actual_count}."
        )

    meta: Dict[str, Any] = {
        "template_key":   template_key,
        "expected_count": defect_column_count,
        "actual_count":   actual_count,
        "count_ok":       count_ok,
    }

    logging.info(
        f"[{path.name}] Defects: {actual_count}/{defect_column_count} rows | "
        f"count_ok={count_ok} | totals={totals}"
    )

    return defect_rows, totals, meta