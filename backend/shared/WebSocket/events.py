from .push import _push
from .groups import _group_name
from typing import Protocol


class BatchLike(Protocol):
    pk: int
    status: str
    progress_percent: int
    processed_files: int
    total_files: int
    failed_files: int

def _push_progress(batch: BatchLike, stage: str = "") -> None:
    _push(_group_name(batch.pk), {
        "type":             "audit.progress",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "stage":            stage,
        "progress_percent": batch.progress_percent,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
    })

def _push_complete(batch: BatchLike) -> None:
    _push(_group_name(batch.pk), {
        "type":             "audit.complete",
        "batch_id":         batch.pk,
        "status":           batch.status,
        "progress_percent": 100,
        "processed":        batch.processed_files,
        "total":            batch.total_files,
        "failed":           batch.failed_files,
        "report_count":     batch.reports.count(),
    })

def _push_error(batch: BatchLike, message: str) -> None:
    _push(_group_name(batch.pk), {
        "type":          "audit.error",
        "batch_id":      batch.pk,
        "status":        batch.Status.FAILED,
        "error_message": message,
    })