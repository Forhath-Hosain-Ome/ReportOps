"""One execution lock for workers, retry/recovery and retention maintenance."""
from contextlib import contextmanager
from threading import Lock

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction

_test_locks = {}
_registry_lock = Lock()


@contextmanager
def batch_lock(batch_id):
    # Session locks deliberately outlive the short authority transactions. Never
    # keep a row transaction open during image processing or filesystem deletion.
    if connection.vendor == "postgresql":
        held = getattr(connection, "_image_batch_locks", {})
        if batch_id in held:
            yield False
            return
        connection._image_batch_locks = held
        key = (0x494D47 << 32) + int(batch_id)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [key])
            acquired = cursor.fetchone()[0]
        if acquired:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                held[batch_id] = cursor.fetchone()[0]
        try:
            yield acquired
        finally:
            if acquired:
                held.pop(batch_id, None)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_unlock(%s)", [key])
    elif getattr(settings, "IMAGE_PROCESSOR_TEST_LOCKS", False):
        with _registry_lock:
            lock = _test_locks.setdefault(batch_id, Lock())
        acquired = lock.acquire(blocking=False)
        try:
            yield acquired
        finally:
            if acquired:
                lock.release()
    else:
        raise ImproperlyConfigured("Image processing requires PostgreSQL coordination.")


class StaleExecution(RuntimeError):
    pass


@contextmanager
def execution_write(batch_id, generation, dispatch_token, run_token, attempt_id=None):
    """Fence *every* execution-owned write, inside the write transaction."""
    from image_processor.models import FolderBatch, ProcessingAttempt
    with transaction.atomic():
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                pid = cursor.fetchone()[0]
            if getattr(connection, "_image_batch_locks", {}).get(batch_id) != pid:
                raise StaleExecution("Execution coordination session was lost.")
        batch = FolderBatch.objects.select_for_update().get(pk=batch_id)
        if (not run_token or not dispatch_token or not batch.active_run_token
                or batch.dispatch_generation != generation
                or str(batch.dispatch_token) != str(dispatch_token)
                or str(batch.active_run_token) != str(run_token)
                or batch.status != "PROCESSING"
                or batch.maintenance_token):
            raise StaleExecution("Execution no longer owns this batch.")
        attempt = None
        if attempt_id is not None:
            attempt = ProcessingAttempt.objects.select_for_update().filter(
                pk=attempt_id, report__batch_id=batch_id, generation=generation,
                dispatch_token=dispatch_token, run_token=run_token, status="PROCESSING",
                report_id__in=batch.intended_reports, report__status="PROCESSING",
            ).first()
            if attempt is None:
                raise StaleExecution("Attempt no longer belongs to this execution.")
        yield batch, attempt
