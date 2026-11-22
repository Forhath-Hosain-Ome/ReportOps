"""
defect_extractor.py
-------------------
Auto-discovers and extracts the structured defect table from an Excel sheet,
then maps every row to its canonical entry in defect_master.py so the DB
always receives consistent category + item names regardless of how the
factory typed them in the Excel.

Structure understood from samples
----------------------------------
The defect table always follows this layout:

  Row N   : "Defects" | ... | "Major Defect" | "Minor Defect" | "Comment"
  Row N+1 : "A : Fabrics" | "1.Damage" | ...
  ...
  Row M   : "F : Others" | ... | "3.Others" | ...   ← last data row

Detection strategy
------------------
1. Find the header row — scan ALL cells in each row for a cell whose text
   == "defects" (case-insensitive). Works for both SPI (col A) and PQC
   (non-col-A) layouts.
2. Major / Minor / Comment column indices are discovered from that same
   header row — NO hardcoded columns.
3. Scan downward; category separator rows (e.g. "A : Fabrics") are skipped
   and do NOT consume an item_no slot.
4. Every non-category row gets a 1-based item_no (sequential position).
5. item_no is looked up in defect_master.py for the given report_format to
   get the canonical category label and item name.
6. A partial-match check logs a WARNING if the Excel cell text diverges
   significantly from the master name — data is still saved using the
   canonical master name regardless.
7. Stop after reading exactly defect_column_count item rows OR when the
   end sentinel ("DO/Set/Col/Size") is hit — whichever comes first.
8. Count validation: actual item rows vs defect_column_count is logged.

defect_master mapping
---------------------
  report_format   defect_column_count   template_key
  ─────────────   ───────────────────   ────────────
  KNIT_35         35                    TEMPLATE_31  (31 actual items)
  WOVEN_37        37                    TEMPLATE_37
  SWEATER_37      37                    TEMPLATE_37
  WOVEN_78        78                    TEMPLATE_78

Output
------
(defect_rows, totals, meta)

  defect_rows : list of dicts
    {
        "item_no":       int,   # 1-based position = index into template
        "category_code": str,   # e.g. "A"          — from defect_master
        "category":      str,   # canonical label   — from defect_master
        "item":          str,   # canonical name    — from defect_master
        "major":         int,
        "minor":         int,
        "comment":       str,
        "name_matched":  bool,  # False → Excel text diverged; warning logged
    }

  totals : {"major": int, "minor": int}

  meta : {
      "template_key":   str | None,
      "expected_count": int,         # = defect_column_count
      "actual_count":   int,         # rows actually collected
      "count_ok":       bool,
  }

SCALABILITY NOTE
----------------
Adding a new template requires only two steps:
  1. Add the template dict to defect_master.py (items + categories).
  2. Add its count → key mapping to TEMPLATE_FOR_COUNT in defect_master.py.
No changes needed here.
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

    Parameters
    ----------
    path                : Path to the Excel file.
    sheet_name          : Preferred sheet name; falls back to first sheet.
    defect_column_count : From BuyerFactoryPair.defect_column_count.
                          Determines which defect_master template to use
                          and how many item rows to read.

    Returns
    -------
    (defect_rows, totals, meta)  — see module docstring for field details.
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
    # The header scan below will try each sheet in turn and stop at the
    # first one where the defect header row is found.
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
    item_col:    Optional[int] = None   # column containing defect item names
    major_col:   Optional[int] = None
    minor_col:   Optional[int] = None
    comment_col: Optional[int] = None

    for r_idx, row in enumerate(rows):
        if not row:
            continue
        for c_idx, cell in enumerate(row):
            if cell is None:
                continue
            normalised = str(cell).strip().lower()
            if normalised == "defects" and item_col is None:
                header_row_idx = r_idx
                # If "Defects" header is in col A (index 0), item names
                # are in col B (index 1) — col A holds the repeated
                # category label on every data row in this layout.
                item_col = c_idx + 1 if c_idx == 0 else c_idx
            if header_row_idx == r_idx:
                # Discover qty/comment columns from the same header row
                if "major" in normalised and major_col is None:
                    major_col = c_idx
                if "minor" in normalised and minor_col is None:
                    minor_col = c_idx
                if "comment" in normalised and comment_col is None:
                    comment_col = c_idx
        if header_row_idx is not None:
            break

    if header_row_idx is None:
        logging.warning(
            f"[{path.name}] Defect header not found "
            f"(no cell with text 'defects' in any row)."
        )
        return [], {}, _empty_meta()

    if major_col is None:
        logging.warning(
            f"[{path.name}] 'Major' column not found in defect header row."
        )
        return [], {}, _empty_meta()

    logging.info(
        f"[{path.name}] Defect header at row {header_row_idx + 1} | "
        f"item_col={item_col} major_col={major_col} "
        f"minor_col={minor_col} comment_col={comment_col}"
    )

    # ── Step 2: Scan data rows ───────────────────────────────────────────────
    defect_rows: List[Dict[str, Any]] = []
    item_position = 0   # 1-based; incremented only for real item rows

    for r_idx in range(header_row_idx + 1, len(rows)):
        # Stop once we have exactly defect_column_count items
        if item_position >= defect_column_count:
            break

        row   = rows[r_idx]
        col_a = row[0] if row else None

        # Stop at end sentinel
        if _is_end_sentinel(col_a):
            break

        # item_cell: col B (item_col) always holds the defect item name.
        # col A holds the category label — either the real value on the
        # first row of a merged block, or None (merge shadow) on the rest.
        # We track the category from col A but NEVER use it to skip rows.
        item_cell = (
            row[item_col]
            if item_col is not None and item_col < len(row)
            else None
        )

        # Update current category whenever col A has a category label.
        # (merge shadow rows have col A = None → keep previous category)
        if col_a is not None and _is_category_cell(col_a):
            _current_category_from_col_a = str(col_a).strip()

        # Skip only truly empty rows — both item cell AND col A are None/blank.
        item_text = str(item_cell).strip() if item_cell is not None else ""
        col_a_text = str(col_a).strip() if col_a is not None else ""
        if not item_text and not col_a_text:
            logging.debug(f"  Row {r_idx + 1}: empty row → skipped")
            continue

        item_position += 1  # this row's 1-based index in the template

        # ── Map to defect_master by position ────────────────────────────────
        master_entry   = item_by_no.get(item_position)
        category_code  = master_entry["category_code"] if master_entry else ""
        category_label = (
            master_cats.get(category_code, {}).get("label", "")
            if category_code else ""
        )
        canonical_name = (
            master_entry["name"] if master_entry
            else str(item_cell or "").strip() or f"Item {item_position}"
        )

        # ── Partial-match sanity check ───────────────────────────────────────
        excel_item_text = str(item_cell or "").strip()
        if master_entry and excel_item_text:
            matched = _partial_match(excel_item_text, canonical_name)
            if not matched:
                logging.warning(
                    f"[{path.name}] Row {r_idx + 1} item_no={item_position}: "
                    f"Excel text '{excel_item_text}' has low overlap with "
                    f"master name '{canonical_name}'. "
                    f"Saving with master name regardless."
                )
        else:
            matched = master_entry is not None

        # ── Extract quantities ───────────────────────────────────────────────
        major   = _to_int(row[major_col]   if major_col   < len(row) else None)
        minor   = _to_int(
            row[minor_col] if minor_col is not None and minor_col < len(row) else None
        )
        comment = (
            str(row[comment_col]).strip()
            if comment_col is not None
            and comment_col < len(row)
            and row[comment_col] is not None
            else ""
        )

        defect_rows.append({
            "item_no":       item_position,
            "category_code": category_code,
            "category":      category_label,
            "item":          canonical_name,
            "major":         major,
            "minor":         minor,
            "comment":       comment,
            "name_matched":  matched,
        })

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

