"""
db_manager.py
-------------
All SQLite database operations for the audit extraction system.

Responsibilities
----------------
- Initialise the database (create tables from schema.sql)
- Upsert lookup rows (factories, clients, styles, purchase_orders)
- Insert / update audit_reports and all child tables
- Duplicate detection: block re-insertion of same file_name OR
  same (report_no + date_of_issue) combination
- Query helpers for the Writer script

Usage
-----
    from db.db_manager import DBManager

    db = DBManager("audit.db")
    db.init_db()
    db.save_record(audit_record)
    rows = db.query_records(factory="BABL Factory", client="BABL",
                            start_date="2026-01-01", end_date="2026-03-31")
    db.close()

All public methods wrap their work in a transaction. One bad record never
aborts the batch — errors are logged and re-raised to the caller.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .db_manager import AuditRecord


# ---------------------------------------------------------------------------
# Date normalisation for DB storage
# ---------------------------------------------------------------------------
# All dates are stored as YYYY-MM-DD so SQLite string comparison works
# correctly for range queries (>= / <=).
# The validator outputs MM/DD/YYYY; we convert here before INSERT.

def _to_iso_date(value: str) -> Optional[str]:
    """
    Convert any recognised date string to YYYY-MM-DD for DB storage.
    Returns None if blank or unparseable.

    Handles every format that Excel / the validator can produce:
      MM/DD/YYYY   01/05/2026  ← validator always outputs this
      YYYY-MM-DD   2026-01-05  ← already ISO
      YYYY/MM/DD   2026/01/05
      DD-MMM-YY    05-Jan-26
      DD-MMM-YYYY  05-Jan-2026
      MM-DD-YYYY   01-05-2026
      YYYY-MM-DD HH:MM:SS  (Excel datetime — time part stripped first)
    """
    if not value or not str(value).strip():
        return None

    from datetime import datetime as _dt

    s = str(value).strip()

    # Strip time component first: "2026-01-05 00:00:00" → "2026-01-05"
    # Handles space-separated and T-separated datetimes
    if len(s) > 10 and (s[10] in (" ", "T")):
        s = s[:10]

    # Try every known format in order of likelihood
    formats = [
        "%m/%d/%Y",   # 01/05/2026  ← validator always outputs this — FIRST
        "%Y-%m-%d",   # 2026-01-05  ← already ISO
        "%Y/%m/%d",   # 2026/01/05
        "%d-%b-%y",   # 05-Jan-26
        "%d-%b-%Y",   # 05-Jan-2026
        "%m-%d-%Y",   # 01-05-2026
        "%d/%m/%Y",   # 05/01/2026  ← LAST (ambiguous with MM/DD/YYYY)
    ]
    for fmt in formats:
        try:
            return _dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    return s   # store as-is if nothing matches; never block an insert


# Resolve schema.sql path whether running as a script or frozen exe
if getattr(sys, 'frozen', False):
    # Running inside PyInstaller bundle — schema.sql is in the 'db' subfolder
    _SCHEMA_PATH = Path(sys._MEIPASS) / "db" / "schema.sql"  # type: ignore[attr-defined]
else:
    # Running as plain script — schema.sql is in the same directory as this file
    _SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class DBManager:
    """SQLite wrapper for the audit extraction system."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._conn: Optional[sqlite3.Connection] = None

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open the database connection."""
        self._conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL;")
        self._conn.execute("PRAGMA foreign_keys = ON;")

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "DBManager":
        self.connect()
        return self

    def __exit__(self, *_) -> None:
        self.close()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_db(self) -> None:
        """
        Create all tables, indexes, triggers, and views from schema.sql.
        Safe to call on an already-initialised database (IF NOT EXISTS).
        Also runs migrate_dates() to normalise any existing non-ISO dates.
        """
        if not _SCHEMA_PATH.exists():
            raise FileNotFoundError(f"Schema file not found: {_SCHEMA_PATH}")

        sql = _SCHEMA_PATH.read_text(encoding="utf-8")
        with self.conn:
            self.conn.execute("PRAGMA foreign_keys = OFF")
            self.conn.executescript(sql)
            self.conn.execute("PRAGMA foreign_keys = ON")
        logging.info(f"Database initialised: {self.db_path}")

        # Load static defect master data if the file exists next to schema.sql
        _master_path = _SCHEMA_PATH.parent / "defect_master.sql"
        if _master_path.exists():
            master_sql = _master_path.read_text(encoding="utf-8")
            with self.conn:
                self.conn.executescript(master_sql)
            logging.info("Defect master data loaded from defect_master.sql")

        # Add any columns introduced after the DB was first created
        self.migrate_schema()
        # Always normalise dates — safe to run multiple times (idempotent)
        self.migrate_dates()
        # Migrate old defect_items rows into the new normalised tables
        self.migrate_defect_items()

    # ------------------------------------------------------------------
    # Schema migration  (idempotent ALTER TABLE for new columns)
    # ------------------------------------------------------------------

    def migrate_schema(self) -> None:
        """
        Idempotent ALTER TABLE migrations for columns added after the initial
        DB was first created.  Each entry checks whether the column already
        exists before issuing ALTER TABLE, so this is safe to call every startup.
        """
        _MIGRATIONS = [
            # (table, column, column_definition)
            (
                "audit_reports",
                "defect_template_id",
                "INTEGER REFERENCES defect_templates(id) ON DELETE SET NULL",
            ),
        ]

        existing: dict = {}
        for table, column, definition in _MIGRATIONS:
            if table not in existing:
                rows = self.conn.execute(
                    f"PRAGMA table_info({table})"
                ).fetchall()
                existing[table] = {row[1] for row in rows}
            if column not in existing[table]:
                self.conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                )
                self.conn.commit()
                existing[table].add(column)
                logging.info(
                    f"migrate_schema: added column '{column}' to '{table}'"
                )

    # ------------------------------------------------------------------
    # Defect template matching
    # ------------------------------------------------------------------

    _TEMPLATE_TOLERANCE = 4   # ±4 items counts as a match

    def match_defect_template(self, defect_count: int) -> Optional[int]:
        """
        Given the number of defect items extracted from an Excel file,
        return the matching defect_templates.id (or None if no match).

        Matches within ±TEMPLATE_TOLERANCE of any template's item_count.
        When two templates are equally close, the smaller item_count wins.
        """
        rows = self.conn.execute(
            "SELECT id, item_count FROM defect_templates ORDER BY item_count"
        ).fetchall()

        best_id:   Optional[int] = None
        best_diff: int = self._TEMPLATE_TOLERANCE + 1

        for row in rows:
            diff = abs(defect_count - row["item_count"])
            if diff <= self._TEMPLATE_TOLERANCE and diff < best_diff:
                best_id   = row["id"]
                best_diff = diff

        if best_id:
            logging.info(
                f"  Defect template matched: id={best_id} "
                f"(extracted={defect_count}, tolerance=±{self._TEMPLATE_TOLERANCE})"
            )
        else:
            logging.info(
                f"  No defect template matched for count={defect_count}"
            )
        return best_id
    
    def _ensure_defect_entries_table(self):
        """Ensure defect_entries table exists before trying to insert."""
        try:
            self.conn.execute("SELECT 1 FROM defect_entries LIMIT 1").fetchone()
        except sqlite3.OperationalError:
            # Table doesn't exist - create it
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS defect_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    audit_report_id INTEGER NOT NULL,
                    defect_type_id INTEGER NOT NULL,
                    major INTEGER DEFAULT 0,
                    minor INTEGER DEFAULT 0,
                    comment TEXT,
                    FOREIGN KEY (audit_report_id) REFERENCES audit_reports(id) ON DELETE CASCADE,
                    FOREIGN KEY (defect_type_id) REFERENCES defect_types(id) ON DELETE CASCADE,
                    UNIQUE(audit_report_id, defect_type_id)
                )
            """)
            self.conn.commit()

    def get_defect_item_def_id(
        self,
        template_id: int,
        category_name: str,
        item_name: str,
    ) -> Optional[int]:
        """
        Look up defect_items_def.id for a given template + category + item name.
        Matching is case-insensitive and ignores leading/trailing whitespace.
        Returns None if not found (item will be saved to defect_types/entries
        without a static definition link).
        """
        row = self.conn.execute(
            """
            SELECT did.id
            FROM   defect_items_def  did
            JOIN   defect_categories dc  ON dc.id  = did.category_id
            JOIN   defect_templates  dt  ON dt.id  = dc.template_id
            WHERE  dt.id = ?
              AND  UPPER(TRIM(did.name))        = UPPER(TRIM(?))
            LIMIT 1
            """,
            (template_id, item_name),
        ).fetchone()
        return row["id"] if row else None

    def migrate_dates(self) -> None:
        """
        Convert any date fields stored in non-ISO formats to YYYY-MM-DD.

        Safe to run multiple times — records already in YYYY-MM-DD are
        left unchanged. Covers audit_reports.date_of_issue and all five
        date columns in shipment_dates.
        """
        _DATE_COLS_AUDIT    = ["date_of_issue"]
        _DATE_COLS_SHIPMENT = ["exf", "po_edt", "po_wh", "plan_edt", "plan_wh"]

        fixed_total = 0

        # ── audit_reports ─────────────────────────────────────────────────────
        rows = self.conn.execute(
            "SELECT id, date_of_issue FROM audit_reports "
            "WHERE date_of_issue IS NOT NULL"
        ).fetchall()

        updates = []
        for row in rows:
            original = row["date_of_issue"]
            converted = _to_iso_date(original)
            # Only update if the value actually changed
            if converted and converted != original:
                updates.append((converted, row["id"]))

        if updates:
            with self.conn:
                self.conn.executemany(
                    "UPDATE audit_reports SET date_of_issue = ? WHERE id = ?",
                    updates,
                )
            fixed_total += len(updates)
            logging.info(f"migrate_dates: fixed {len(updates)} audit_reports.date_of_issue rows")

        # ── shipment_dates ────────────────────────────────────────────────────
        for col in _DATE_COLS_SHIPMENT:
            rows = self.conn.execute(
                f"SELECT audit_report_id, {col} FROM shipment_dates "
                f"WHERE {col} IS NOT NULL"
            ).fetchall()

            updates = []
            for row in rows:
                original  = row[col]
                converted = _to_iso_date(original)
                if converted and converted != original:
                    updates.append((converted, row["audit_report_id"]))

            if updates:
                with self.conn:
                    self.conn.executemany(
                        f"UPDATE shipment_dates SET {col} = ? "
                        f"WHERE audit_report_id = ?",
                        updates,
                    )
                fixed_total += len(updates)
                logging.info(
                    f"migrate_dates: fixed {len(updates)} shipment_dates.{col} rows"
                )

        if fixed_total:
            logging.info(f"migrate_dates: total {fixed_total} date value(s) normalised to ISO")
        else:
            logging.debug("migrate_dates: all dates already in ISO format — nothing to do")

    def migrate_defect_items(self) -> None:
        """
        One-time migration: move data from the old defect_items table (if it
        exists and has rows) into the new defect_types + defect_entries tables.

        Safe to run multiple times — already-migrated rows are skipped via
        INSERT OR IGNORE on the UNIQUE constraint of defect_entries.
        Drops defect_items table after all rows are migrated.
        """
        # Check if the old table still exists
        old_exists = self.conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='defect_items'"
        ).fetchone()
        if not old_exists:
            return

        rows = self.conn.execute(
            "SELECT audit_report_id, category, item, major_count, minor_count, comment "
            "FROM defect_items"
        ).fetchall()

        if not rows:
            # Nothing to migrate — drop the empty table
            with self.conn:
                self.conn.execute("DROP TABLE IF EXISTS defect_items")
            return

        migrated = 0
        with self.conn:
            for row in rows:
                cat     = (row["category"] or "").strip()
                item    = (row["item"] or "").strip()
                major   = int(row["major_count"] or 0)
                minor   = int(row["minor_count"] or 0)
                comment = row["comment"]
                report_id = row["audit_report_id"]

                if not cat or not item:
                    continue

                # Get-or-create defect_type
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_types (category, item_name, sort_order) "
                    "VALUES (?, ?, 0)",
                    (cat, item),
                )
                type_row = self.conn.execute(
                    "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
                    (cat, item),
                ).fetchone()
                if not type_row:
                    continue
                type_id = type_row["id"]

                # Insert entry (skip if already migrated)
                self.conn.execute(
                    "INSERT OR IGNORE INTO defect_entries "
                    "(audit_report_id, defect_type_id, major, minor, comment) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (report_id, type_id, major, minor, comment),
                )
                migrated += 1

        logging.info(f"migrate_defect_items: migrated {migrated} row(s) into defect_entries")

        # Drop the old table once migration is complete
        with self.conn:
            self.conn.execute("DROP TABLE IF EXISTS defect_items")
        logging.info("migrate_defect_items: defect_items table removed")
    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def is_duplicate(self, file_name: str, report_no: str, date_of_issue: str) -> bool:
        """
        Return True if this audit record already exists in the DB.

        Duplicate criteria (checked separately, either is sufficient):
          1. Same file_name
          2. Same (report_no + date_of_issue) — catches re-named files
        """
        cur = self.conn.cursor()

        # Check 1: file_name
        cur.execute(
            "SELECT 1 FROM audit_reports WHERE file_name = ? LIMIT 1",
            (file_name,),
        )
        if cur.fetchone():
            logging.info(f"Duplicate (file_name): {file_name}")
            return True

        # Check 2: report_no + date_of_issue (normalise to ISO before comparing)
        if report_no and date_of_issue:
            iso = _to_iso_date(date_of_issue) or date_of_issue
            cur.execute(
                "SELECT 1 FROM audit_reports "
                "WHERE report_no = ? AND date_of_issue = ? LIMIT 1",
                (report_no, iso),
            )
            if cur.fetchone():
                logging.info(
                    f"Duplicate (report_no+date): {report_no} / {date_of_issue}"
                )
                return True

        return False

    # ------------------------------------------------------------------
    # Lookup upserts (get-or-create)
    # ------------------------------------------------------------------

    def _upsert_factory(self, name: str) -> int:
        """Return the factory.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO factories(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM factories WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_client(self, name: str) -> int:
        """Return the client.id for *name*, inserting if necessary."""
        name = (name or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO clients(name) VALUES (?)", (name,)
            )
        row = self.conn.execute(
            "SELECT id FROM clients WHERE name = ?", (name,)
        ).fetchone()
        return row["id"]

    def _upsert_style(
        self,
        client_id: int,
        style_no: str,
        item_name: str,
        country: str,
    ) -> int:
        """Return style.id, inserting or updating item_name/country."""
        style_no = (style_no or "UNKNOWN").strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO styles(client_id, style_no, item_name, country)
                VALUES(?, ?, ?, ?)
                ON CONFLICT(style_no) DO UPDATE SET
                    item_name = COALESCE(excluded.item_name, item_name),
                    country   = COALESCE(excluded.country,   country)
                """,
                (client_id, style_no, item_name or None, country or None),
            )
        row = self.conn.execute(
            "SELECT id FROM styles WHERE style_no = ?", (style_no,)
        ).fetchone()
        return row["id"]

    def _upsert_purchase_order(
        self,
        style_id: int,
        po_no: str,
        po_qty_raw: str,
        po_qty_pcs: int,
        po_qty_pack: int,
        po_qty_set: int,
    ) -> Optional[int]:
        """Return po.id, inserting or updating qty fields. Returns None if no po_no."""
        if not po_no or not po_no.strip():
            return None
        po_no = po_no.strip()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO purchase_orders
                    (style_id, po_no, po_qty_raw, po_qty_pcs, po_qty_pack, po_qty_set)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(po_no) DO UPDATE SET
                    po_qty_raw  = COALESCE(excluded.po_qty_raw,  po_qty_raw),
                    po_qty_pcs  = COALESCE(excluded.po_qty_pcs,  po_qty_pcs),
                    po_qty_pack = COALESCE(excluded.po_qty_pack, po_qty_pack),
                    po_qty_set  = COALESCE(excluded.po_qty_set,  po_qty_set)
                """,
                (style_id, po_no, po_qty_raw or None,
                 po_qty_pcs or None, po_qty_pack or None, po_qty_set or None),
            )
        row = self.conn.execute(
            "SELECT id FROM purchase_orders WHERE po_no = ?", (po_no,)
        ).fetchone()
        return row["id"]

    def _upsert_defect_type(self, category: str, item_name: str) -> int:
        """
        Return defect_types.id for the given (category, item_name) pair,
        inserting a new row if one does not already exist.

        sort_order is set to max+1 on first insert so new defect types
        always appear after the pre-seeded master list.
        """
        category  = (category  or "").strip()
        item_name = (item_name or "").strip()

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        if row:
            return row["id"]

        max_row = self.conn.execute(
            "SELECT COALESCE(MAX(sort_order), 0) FROM defect_types"
        ).fetchone()
        next_sort = (max_row[0] or 0) + 1

        self.conn.execute(
            """
            INSERT OR IGNORE INTO defect_types (category, item_name, sort_order)
            VALUES (?, ?, ?)
            """,
            (category, item_name, next_sort),
        )

        row = self.conn.execute(
            "SELECT id FROM defect_types WHERE category = ? AND item_name = ?",
            (category, item_name),
        ).fetchone()
        return row["id"]

    # ------------------------------------------------------------------
    # Main record save
    # ------------------------------------------------------------------

    def save_record(self, record: AuditRecord) -> Optional[int]:
        """
        Persist a single AuditRecord to the database.

        Returns the new audit_reports.id, or None if:
          - record has blocking_errors  (user must fix via error JSON)
          - record is a duplicate

        Steps:
          1. Blocking check — return None with reason logged
          2. Duplicate check — return None if already present
          3. Upsert lookup rows (factory, client, style, PO)
          4. Detect defect template (28 / 35 / 78)
          5. Insert audit_reports row
          6. Insert audit_times, shipment_dates
          7. Insert defect_entries (linked to static defect_items_def if available)
          8. Insert delivery_orders
          9. Insert validation_errors (soft warnings)
        """
        # 1. Blocking check
        if record.blocking_errors:
            logging.info(
                f"SKIP (blocking errors) [{record.file_name}]: "
                + " | ".join(record.blocking_errors)
            )
            return None

        # 2. Duplicate check
        if self.is_duplicate(record.file_name, record.report_no, record.date_of_issue):
            return None

        # 2. Upsert lookups
        factory_id = self._upsert_factory(record.factory)
        client_id  = self._upsert_client(record.client)
        style_id   = self._upsert_style(
            client_id, record.style_no, record.item_name, record.country
        )
        po_id = self._upsert_purchase_order(
            style_id,
            record.po_no,
            record.po_qty,
            record.po_qty_pcs,
            record.po_qty_pack,
            record.po_qty_set,
        )

        # 4. Detect defect template from defect row count
        defect_count = len([
            d for d in record.defect_rows
            if isinstance(d, dict) and (
                int(d.get("major", 0) or 0) > 0 or
                int(d.get("minor", 0) or 0) > 0
            )
        ])
        # Use total rows (including zero-count) for template matching — the
        # template is determined by the Excel file's column structure, not
        # just the rows that happen to have defects.
        total_defect_rows = len([d for d in record.defect_rows if isinstance(d, dict)])
        template_id = self.match_defect_template(total_defect_rows) if total_defect_rows else None

        # Helper: convert "" to None for DB storage
        def _v(val: Any) -> Any:
            if val == "" or val == "-":
                return None
            return val

        # Helper: parse defect_percentage ("3.71%" → 3.71)
        def _pct(val: str) -> Optional[float]:
            if not val:
                return None
            try:
                return float(str(val).replace("%", "").strip())
            except (ValueError, TypeError):
                return None

        # Helper: safe int
        def _int(val: Any) -> Optional[int]:
            if val is None or val == "":
                return None
            try:
                return int(float(str(val).strip()))
            except (ValueError, TypeError):
                return None

        try:
            with self.conn:
                # 3. Insert audit_reports
                cur = self.conn.execute(
                    """
                    INSERT INTO audit_reports (
                        factory_id, client_id, style_id, po_id,
                        file_name, report_no,
                        inspection_type, audit_result, date_of_issue,
                        do_qty, ship_qty, audit_qty,
                        defect_qty, acceptable_defect_qty, defect_percentage,
                        inspector, person,
                        carton, needle_detector, remarks, do_set_col_size, do_note,
                        has_validation_errors, defect_template_id
                    ) VALUES (
                        ?, ?, ?, ?,
                        ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?
                    )
                    """,
                    (
                        factory_id, client_id, style_id, po_id,
                        record.file_name,
                        _v(record.report_no),
                        _v(record.inspection_type),
                        _v(record.audit_result) or "-",
                        _to_iso_date(record.date_of_issue),
                        _int(record.do_qty),
                        _int(record.ship_qty),
                        _int(record.audit_qty),
                        _int(record.defect_qty),
                        _v(record.acceptable_defect_qty),
                        _pct(record.defect_percentage),
                        _v(record.inspector),
                        _v(record.person),
                        _v(record.carton),
                        _v(record.needle_detector),
                        _v(record.remarks),
                        _v(record.do_set_col_size),
                        _v(record.do_note),
                        1 if record.validation_errors else 0,
                        template_id,
                    ),
                )
                report_id = cur.lastrowid

                # 4. audit_times
                self.conn.execute(
                    """
                    INSERT INTO audit_times
                        (audit_report_id, factory_in, factory_out, factory_total_hours,
                         audit_start, audit_end, audit_total_hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _v(record.factory_in_time),
                        _v(record.factory_out_time),
                        _v(record.factory_total_hours),
                        _v(record.audit_start_time),
                        _v(record.audit_end_time),
                        _v(record.audit_total_hours),
                    ),
                )

                # shipment_dates
                self.conn.execute(
                    """
                    INSERT INTO shipment_dates
                        (audit_report_id, exf, po_edt, po_wh, plan_edt, plan_wh)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        report_id,
                        _to_iso_date(record.exf),
                        _to_iso_date(record.po_edt),
                        _to_iso_date(record.po_wh),
                        _to_iso_date(record.plan_edt),
                        _to_iso_date(record.plan_wh),
                    ),
                )

                # 5. defect_entries (via defect_types lookup/upsert)

                self._ensure_defect_entries_table()
                
                for d in record.defect_rows:
                    if not isinstance(d, dict):
                        continue
                    cat  = (d.get("category") or "").strip()
                    item = (d.get("item") or "").strip()
                    if not cat or not item:
                        continue

                    major   = int(d.get("major", 0) or 0)
                    minor   = int(d.get("minor", 0) or 0)
                    comment = d.get("comment") or None

                    # Skip rows with no data at all
                    if major == 0 and minor == 0 and not comment:
                        continue

                    # Get-or-create the defect_type master row
                    type_id = self._upsert_defect_type(cat, item)

                    # Insert the per-audit entry
                    self.conn.execute(
                        """
                        INSERT OR REPLACE INTO defect_entries
                            (audit_report_id, defect_type_id, major, minor, comment)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (report_id, type_id, major, minor, comment),
                    )

                # 6. delivery_orders
                for idx, do_row in enumerate(record.do_orders):
                    if not isinstance(do_row, dict):
                        continue
                    self.conn.execute(
                        """
                        INSERT INTO delivery_orders (
                            audit_report_id, do_date, po_qty, do_no, do_qty,
                            ship_qty, audit_qty, do_balance_and_extra, po_balance,
                            remarks, special_note, row_order
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            report_id,
                            do_row.get("date"),
                            do_row.get("po_qty"),
                            do_row.get("do_no"),
                            do_row.get("do_qty"),
                            do_row.get("ship_qty"),
                            do_row.get("audit_qty"),
                            do_row.get("do_balance_and_extra"),
                            do_row.get("po_balance"),
                            do_row.get("remarks"),
                            do_row.get("special_note"),
                            idx,
                        ),
                    )

                # 7. validation_errors
                for err in record.validation_errors:
                    self.conn.execute(
                        "INSERT INTO validation_errors (audit_report_id, error_message) "
                        "VALUES (?, ?)",
                        (report_id, err),
                    )

            logging.info(f"Saved record id={report_id}: {record.file_name}")
            return report_id

        except sqlite3.IntegrityError as exc:
            logging.warning(f"IntegrityError saving {record.file_name}: {exc}")
            return None
        except Exception as exc:
            logging.exception(f"Error saving {record.file_name}: {exc}")
            raise

    # ------------------------------------------------------------------
    # Query helpers (used by Writer script)
    # ------------------------------------------------------------------

    def query_records(
        self,
        factory: str = "",
        client: str = "",
        style: str = "",
        po: str = "",
        start_date: str = "",
        end_date: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Return audit rows matching the given filters as a list of dicts.

        All parameters are optional; omitting them returns all records.
        Dates should be in 'MM/DD/YYYY' or 'YYYY-MM-DD' format.
        """
        conditions = []
        params: List[Any] = []

        if factory:
            conditions.append("LOWER(factory) LIKE LOWER(?)")
            params.append(f"%{factory}%")

        if client:
            conditions.append("LOWER(client) LIKE LOWER(?)")
            params.append(f"%{client}%")

        if style:
            conditions.append("LOWER(style_no) LIKE LOWER(?)")
            params.append(f"%{style}%")

        if po:
            conditions.append("LOWER(po_no) LIKE LOWER(?)")
            params.append(f"%{po}%")

        if start_date:
            conditions.append("date_of_issue >= ?")
            params.append(start_date)

        if end_date:
            conditions.append("date_of_issue <= ?")
            params.append(end_date)

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        sql = f"SELECT * FROM v_audit_full {where} ORDER BY date_of_issue, report_id"

        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items(self, report_id: int) -> List[Dict[str, Any]]:
        """Return all defect items for a given audit_reports.id.

        Queries defect_entries + defect_types (current schema) and returns
        legacy-compatible column names used by summary_writer.py:
            audit_report_id, category, item, major_count, minor_count, comment
        """
        rows = self.conn.execute(
            """
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id = ?
            ORDER BY dt.sort_order, dt.category, dt.item_name
            """,
            (report_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_defect_items_for_reports(
        self, report_ids: List[int]
    ) -> Dict[int, List[Dict[str, Any]]]:
        """
        Batch-fetch defect items for multiple report IDs.
        Returns {report_id: [defect_item_dict, ...]}
        """
        if not report_ids:
            return {}
        placeholders = ",".join("?" * len(report_ids))
        rows = self.conn.execute(
            f"""
            SELECT
                de.audit_report_id,
                dt.category,
                dt.item_name        AS item,
                de.major            AS major_count,
                de.minor            AS minor_count,
                de.comment
            FROM defect_entries de
            JOIN defect_types   dt ON dt.id = de.defect_type_id
            WHERE de.audit_report_id IN ({placeholders})
            ORDER BY de.audit_report_id, dt.sort_order, dt.category, dt.item_name
            """,
            report_ids,
        ).fetchall()
        result: Dict[int, List[Dict[str, Any]]] = {}
        for r in rows:
            d = dict(r)
            result.setdefault(d["audit_report_id"], []).append(d)
        return result

    def get_all_factories(self) -> List[str]:
        """Return sorted list of all factory names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM factories ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_all_clients(self) -> List[str]:
        """Return sorted list of all client names in the DB."""
        rows = self.conn.execute(
            "SELECT name FROM clients ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_date_range(self) -> tuple:
        """
        Return (min_date, max_date) of date_of_issue across all records,
        both as YYYY-MM-DD strings. Returns ('', '') if no records exist.
        """
        row = self.conn.execute(
            "SELECT MIN(date_of_issue), MAX(date_of_issue) FROM audit_reports"
        ).fetchone()
        if row and row[0]:
            return row[0], row[1]
        return "", ""