from typing import Any, Dict, List
from dataclasses import dataclass, field, asdict
# ---------------------------------------------------------------------------
# AuditRecord dataclass — the extraction result
# ---------------------------------------------------------------------------

@dataclass
class AuditRecord:
    """
    All data extracted from one Excel audit file.
    Populated by BaseExtractor.extract() and persisted by the task layer.
    """

    # Source
    file_name:  str
    sheet_name: str = ""

    # Identity / header
    factory:         str = ""
    client:          str = ""
    date_of_issue:   str = ""   
    inspection_type: str = ""
    audit_report:    str = ""   
    item_name:       str = ""
    style_no:        str = ""
    po_no:           str = ""
    country:         str = ""

    # Time fields
    factory_in_time:     str = ""
    factory_out_time:    str = ""
    factory_total_hours: str = ""
    audit_start_time:    str = ""
    audit_end_time:      str = ""
    audit_total_hours:   str = ""

    # Audit outcome
    audit_result: str = "-"

    # Quantity fields
    po_qty:      str = ""
    po_qty_pcs:  int = 0
    po_qty_pack: int = 0
    po_qty_set:  int = 0
    do_qty:      int = 0
    ship_qty:    str = ""
    audit_qty:   str = ""

    # Shipment dates
    exf:      str = ""
    po_edt:   str = ""
    po_wh:    str = ""
    plan_edt: str = ""
    plan_wh:  str = ""

    # Defect summary
    defect_qty:            str = ""
    acceptable_defect_qty: str = "-"
    defect_percentage:     str = ""

    # Personnel
    person:    str = ""
    inspector: str = ""

    # Additional checks
    carton:          str = ""
    needle_detector: str = ""
    remarks:         str = ""
    do_set_col_size: str = ""

    # Extracted names (for cross-check against pair registration)
    factory_extracted: str = ""
    client_extracted:  str = ""

    # Structured data
    defect_rows: List[Dict[str, Any]] = field(default_factory=list)
    do_orders:   List[Dict[str, Any]] = field(default_factory=list)
    do_totals:   Dict[str, Any]       = field(default_factory=dict)
    do_note:     str                  = ""

    # Validation
    validation_errors:    List[str] = field(default_factory=list)
    blocking_errors:      List[str] = field(default_factory=list)
    cross_check_warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

