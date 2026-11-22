"""
------------------------------
Celery task: full audit-extraction pipeline for one UploadBatch.

Pipeline
--------
1. Load the BuyerFactoryPair from the batch.
2. Get the correct extractor via FORMAT_REGISTRY.
3. Discover Excel files in the temp upload folder.
4. For each file: resolve sheet → extract record (with injected inspection_date).
5. Run run_validation() on all records.
6. Save clean records to DB; collect blocked records for error log.
7. Update UploadBatch counters and status.
8. Push WebSocket progress events at each stage.
9. Clean up temp folder.

Key design decisions
--------------------
- date_of_issue is injected from batch.inspection_date, never extracted.
- format_type is derived from batch.pair.report_type, never user-selected.
- factory / client are set from pair registration after cross-check.
"""
import logging
import shutil
from pathlib import Path
from shared import _convert_xls_to_xlsx, _push_progress, _push_complete, _push_error
from final_summary.utils import _save_record
from celery import shared_task

from final_summary.models import UploadBatch

from final_summary.extraction.core import get_sheet_names
logger = logging.getLogger(__name__)

# Sheet name substrings checked in priority order (case-insensitive)
_PREFERRED_SHEET_KEYWORDS = ["audit report", "inspection report", "final audit"]


# ── Main task ─────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=0,
    soft_time_limit=1800,
    time_limit=2100,
    name="final_summary.process_audit_upload",
)
def process_audit_upload(
    self,
    batch_id: int,
    upload_folder: str,
) -> dict:
    """
    Parameters
    ----------
    batch_id      : UploadBatch PK
    upload_folder : absolute path to the temp dir containing uploaded files

    Note: format_type and inspection_date are both loaded from the batch
    record — they are not passed as task arguments.
    """
    from final_summary.extraction.formats import get_extractor
    from final_summary.extraction.validation import run_validation
    from utils.sheet_resolver import resolve_sheet_name

    try:
        batch = UploadBatch.objects.select_related(
            "pair", "pair__buyer", "pair__factory"
        ).get(pk=batch_id)
    except UploadBatch.DoesNotExist:
        logger.error("Batch #%s not found", batch_id)
        return {"error": "Batch not found"}

    pair            = batch.pair
    inspection_date = batch.inspection_date
    extractor       = get_extractor(pair)

    logger.info(
        "Batch #%s | pair=%s | format=%s | date=%s",
        batch_id, pair, pair.report_type, inspection_date,
    )

    batch.status = UploadBatch.Status.PROCESSING
    batch.save(update_fields=["status"])
    _push_progress(batch, stage="EXTRACTING")

    try:
        upload_path = Path(upload_folder)
        if not upload_path.exists():
            raise FileNotFoundError(f"Upload folder missing: {upload_folder}")

        excel_files = sorted(
            p for p in upload_path.rglob("*")
            if p.suffix.lower() in (".xlsx", ".xls")
            and not p.name.startswith("~$")
        )

        if not excel_files:
            raise ValueError("No Excel files found in upload folder.")

        batch.total_files = len(excel_files)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="EXTRACTING")

        # ── Stage 1: Extract ──────────────────────────────────────────────
        extracted        = []
        extract_failures = []

        # ── Resolve target sheets per inspection type from the pair ──────
        target_reports = batch.pair.available_reports or ["FINAL", "RE_FINAL", "INLINE"]
        if not target_reports:
            target_reports = ["FINAL", "RE_FINAL", "INLINE"]

        for excel_path in excel_files:
            logger.debug("Processing file: %s", excel_path.name)
            logger.debug("  Full path: %s", excel_path)

            # Convert .xls → .xlsx so the extractor always receives .xlsx
            actual_path = excel_path
            if excel_path.suffix.lower() == ".xls":
                try:
                    actual_path = _convert_xls_to_xlsx(excel_path)
                except Exception as exc:
                    msg = f"{excel_path.name}: failed to convert .xls to .xlsx: {exc}"
                    logger.exception("XLS conversion failed – %s", msg)
                    extract_failures.append(msg)
                    continue

            available_sheets = get_sheet_names(actual_path)  # your existing function
            if not available_sheets:
                extract_failures.append(f"{excel_path.name}: no sheets found")
                continue

            sheets_to_process = []
            for report_type in target_reports:
                match = next(
                    (s for s in available_sheets if s.lower() == report_type.lower()),
                    None,
                )
                if match:
                    sheets_to_process.append(match)

            if not sheets_to_process:
                logger.warning("  No matching sheets found for %s", excel_path.name)
                logger.warning("    Available sheets: %s", available_sheets)
                sheets_to_process = [available_sheets[0]]

            # ... rest of your existing sheet matching logic unchanged ...
            for sheet_name in sheets_to_process:
                try:
                    record = extractor.extract(
                        path=actual_path,          # always .xlsx at this point
                        sheet_name=sheet_name,
                        inspection_date=inspection_date,
                        pair=pair,
                    )
                    record.file_name = f"{excel_path.name} ({sheet_name})"  # original name
                    extracted.append(record)
                except Exception as exc:
                    msg = f"{excel_path.name} ({sheet_name}): {exc}"
                    logger.exception("Extraction failed – %s", msg)
                    extract_failures.append(msg)

        batch.total_files = len(extracted)
        batch.save(update_fields=["total_files"])
        _push_progress(batch, stage="VALIDATING")

        # ── Stage 2: Validate ─────────────────────────────────────────────
        validated = run_validation(extracted)
        clean     = [r for r in validated if not r.blocking_errors]
        blocked   = [r for r in validated if r.blocking_errors]

        _push_progress(batch, stage="SAVING")

        # ── Stage 3: Save ─────────────────────────────────────────────────
        saved = 0
        for record in clean:
            if _save_record(batch, record):
                saved += 1
                batch.processed_files += 1
            else:
                batch.failed_files += 1
            batch.save(update_fields=["processed_files", "failed_files"])
            _push_progress(batch, stage="SAVING")

        for record in blocked:
            _save_record(batch, record)

        batch.failed_files += len(blocked) + len(extract_failures)
        batch.save(update_fields=["failed_files"])

        # ── Finalise status ───────────────────────────────────────────────
        if batch.failed_files == 0:
            batch.status = UploadBatch.Status.COMPLETED
        elif saved == 0:
            batch.status = UploadBatch.Status.FAILED
        else:
            batch.status = UploadBatch.Status.PARTIAL

        error_lines = list(extract_failures) + [
            f"{r.file_name}: {'; '.join(r.blocking_errors)}"
            for r in blocked
        ]
        if error_lines:
            batch.error_log = "\n".join(error_lines)

        batch.save(update_fields=["status", "error_log"])
        _push_complete(batch)

        logger.info(
            "Batch #%s done | saved=%d blocked=%d extract_fail=%d",
            batch_id, saved, len(blocked), len(extract_failures),
        )
        return {
            "batch_id":       batch_id,
            "status":         batch.status,
            "saved":          saved,
            "blocked":        len(blocked),
            "failed_extract": len(extract_failures),
        }

    except Exception as exc:
        logger.exception("Batch #%s fatal error: %s", batch_id, exc)
        batch.status    = UploadBatch.Status.FAILED
        batch.error_log = str(exc)
        batch.save(update_fields=["status", "error_log"])
        _push_error(batch, str(exc))
        return {"error": str(exc)}

    finally:
        shutil.rmtree(upload_folder, ignore_errors=True)
        logger.info("Cleaned up temp folder: %s", upload_folder)