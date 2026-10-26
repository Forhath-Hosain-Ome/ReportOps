def progress_payload(batch):
    terminal = batch.status in {"COMPLETED", "PARTIAL", "FAILED"}
    return {
        "event": "complete" if terminal else "progress", "batch_id": batch.pk,
        "status": batch.status, "dispatch_state": batch.dispatch_state,
        "progress_percent": batch.progress_percent, "processed": batch.processed_folders,
        "partial": batch.partial_reports, "failed": batch.failed_folders,
        "total": batch.total_folders, "submitted_images": batch.submitted_images,
        "successful_images": batch.successful_images, "failed_images": batch.failed_images,
        "success_rate": batch.success_rate, "last_error_code": batch.last_error_code,
        "report_count": batch.reports.count(), "excel_available": False,
    }
