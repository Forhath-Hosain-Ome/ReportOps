
from final_summary.models import UploadBatch, AuditReport, DefectEntry
import json
import logging
logger = logging.getLogger(__name__)


def _save_record(batch: UploadBatch, record) -> bool:
    """
    Persist one AuditRecord dataclass to the Django ORM.
    Returns True on success, False if skipped or failed.
    """
    from utils import _to_date
    # Skip exact duplicates within this batch
    if AuditReport.objects.filter(
        batch=batch, file_name=record.file_name
    ).exists():
        logger.info("Duplicate skipped: %s", record.file_name)
        return False

    try:
        report = AuditReport.objects.create(
            batch                 = batch,
            file_name             = record.file_name,
            factory               = record.factory or "",
            factory_extracted     = record.factory_extracted or "",
            client                = record.client or "",
            client_extracted      = record.client_extracted or "",
            cross_check_warnings  = "\n".join(record.cross_check_warnings or []),
            date_of_issue         = batch.inspection_date,
            inspection_type       = record.inspection_type or "",
            report_no             = record.report_no or "",
            item_name             = record.item_name or "",
            style_no              = record.style_no or "",
            po_no                 = record.po_no or "",
            country               = record.country or "",
            factory_in_time       = record.factory_in_time or "",
            factory_out_time      = record.factory_out_time or "",
            factory_total_hours   = record.factory_total_hours or "",
            audit_start_time      = record.audit_start_time or "",
            audit_end_time        = record.audit_end_time or "",
            audit_total_hours     = record.audit_total_hours or "",
            audit_result          = record.audit_result or "-",
            po_qty                = record.po_qty or "",
            po_qty_pcs            = int(record.po_qty_pcs or 0),
            po_qty_pack           = int(record.po_qty_pack or 0),
            po_qty_set            = int(record.po_qty_set or 0),
            do_qty                = int(record.do_qty or 0),
            ship_qty              = str(record.ship_qty or ""),
            audit_qty             = str(record.audit_qty or ""),
            exf                   = _to_date(record.exf),
            po_edt                = _to_date(record.po_edt),
            po_wh                 = _to_date(record.po_wh),
            plan_edt              = _to_date(record.plan_edt),
            plan_wh               = _to_date(record.plan_wh),
            defect_qty            = str(record.defect_qty or ""),
            acceptable_defect_qty = str(record.acceptable_defect_qty or "-"),
            defect_percentage     = str(record.defect_percentage or ""),
            person                = record.person or "",
            inspector             = record.inspector or "",
            carton                = record.carton or "",
            needle_detector       = record.needle_detector or "",
            remarks               = record.remarks or "",
            do_set_col_size       = record.do_set_col_size or "",
            do_note               = record.do_note or "",
            has_validation_errors = bool(record.validation_errors),
            validation_errors     = "\n".join(record.validation_errors or []),
            blocking_errors       = "\n".join(record.blocking_errors or []),
            do_orders_json        = json.dumps(record.do_orders or []),
        )

        # ── Bulk-create defect entries ─────────────────────────────────────
        # defect_rows come pre-enriched from defects.py with:
        #   item_no, category_code, category (label), item (canonical name)
        # We combine code + label into the single `category` field the
        # flat DefectEntry model expects: e.g. "A - Fabrics", "B - Sewing"
        defect_objects = []
        for d in (record.defect_rows or []):
            if not isinstance(d, dict):
                continue

            major   = int(d.get("major",   0) or 0)
            minor   = int(d.get("minor",   0) or 0)
            comment = str(d.get("comment") or "").strip()

            # Skip completely empty rows
            if not major and not minor and not comment:
                continue

            code  = str(d.get("category_code") or "").strip()
            label = str(d.get("category")      or "").strip()

            # Build combined category: "A - Fabrics", fall back gracefully
            if code and label:
                category = f"{code} - {label}"
            elif code:
                category = code
            else:
                category = label

            defect_objects.append(DefectEntry(
                report      = report,
                serial      = int(d.get("item_no", 0) or 0),
                category    = category,
                defect_name = str(d.get("item") or "").strip(),
                major       = major,
                minor       = minor,
                comment     = comment,
            ))

        if defect_objects:
            DefectEntry.objects.bulk_create(defect_objects)
            logger.debug(
                "Saved %d defect entries for report #%s (%s)",
                len(defect_objects), report.pk, record.file_name,
            )
        else:
            logger.debug(
                "No defect entries to save for report #%s (%s)",
                report.pk, record.file_name,
            )

        logger.info("Saved: %s → AuditReport #%s", record.file_name, report.pk)
        return True

    except Exception as exc:
        logger.exception("Failed to save %s: %s", record.file_name, exc)
        return False

