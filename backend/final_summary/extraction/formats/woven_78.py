"""
-------------------------------
Extractor for SPI Woven garment reports with 78 defect columns.

The PQC format files (like BEACON KNIT WEAR) use this layout.
Key differences handled here:
  - Sheet name is "Audit Report" (not the active sheet)
  - Times are inline in cells: "FACTORY IN TIME: 08.00 AM"
  - Category cells use Japanese + English: "A素材不良\n Material Defects"
  - Report No may be a sequential number like "01"

The inline time and category differences are already handled generically
by the shared field extractors. This class documents the format differences
and provides a post_process() hook for any remaining corrections.
"""

from pathlib import Path
import re
from .base import BaseExtractor, AuditRecord
from final_summary.extraction.core import CellGrid


class Woven78Extractor(BaseExtractor):
    """SPI Woven garment audit report — 78 defect columns (PQC format)."""

    REPORT_TYPE = "WOVEN_78"

    def post_process(
        self,
        record: AuditRecord,
        grid: CellGrid,
        path: Path,
    ) -> AuditRecord:
        """
        PQC-specific corrections applied after base extraction.

        1. report_no: bare sequential numbers like "01" are valid — do not
           replace them with "" even if they fail the standard pattern.
           (The validator treats this as a soft warning, not a block.)

        2. audit_result: PQC sheets may not have an explicit result cell.
           If still empty after extraction, leave as "-" (the default).
        """
        # Ensure report_no is kept as-is even if it's just "01"
        if not record.carton and not record.do_note:
            m = re.search(
                r"our inspection carton\s+no[:\s]+(.+)",
                record.do_note, re.IGNORECASE
            )
            if m:
                record.carton = m.group(1).strip()
        if record.report_no and not record.report_no.strip():
            record.report_no = ""
        if not record.audit_qty:
            record.audit_qty = int(record.do_orders[0].get("audit_qty") or "")
        if not record.po_qty:
            record.po_qty      = int(record.do_orders[0].get("po_qty") or "")
        if not record.po_qty_pcs and not record.po_qty_pack and not record.po_qty_set:
            record.po_qty_pcs  = int(record.do_orders[0].get("po_qty") or "")
            record.po_qty_pack = ""
            record.po_qty_set  = ""

        return super().post_process(record, grid, path)