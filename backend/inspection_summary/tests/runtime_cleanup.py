"""Owned integration-worker cleanup only; never used by production workers."""
import threading

from celery.contrib.testing.worker import TestWorkController
from django.db import close_old_connections, connection, connections


class DatabaseClosingWorker(TestWorkController):
    def start(self):
        self.worker_thread = threading.current_thread()
        self.database_closed = False
        try:
            return super().start()
        finally:
            # Django connections are thread-local. Parent-thread cleanup cannot
            # close the solo worker's connection after its thread has exited.
            connections.close_all()
            self.database_closed = True


def assert_no_worker_sessions(test):
    """Observe the exact disposable DB; never terminate sessions or hide leaks."""
    close_old_connections()
    connections.close_all()
    database = connection.settings_dict['NAME']
    test.assertEqual(database, 'test_inspection_summary_r75')
    # A maintenance connection avoids counting a new parent test-DB session.
    with connection._nodb_cursor() as cursor:
        cursor.execute(
            'SELECT pid, application_name, state FROM pg_stat_activity '
            'WHERE datname = %s AND pid <> pg_backend_pid()', [database])
        sessions = cursor.fetchall()
    test.assertEqual(sessions, [], f'Disposable database sessions survived worker shutdown: {sessions}')
    print(f'Worker cleanup verified: {database} has zero remaining sessions', flush=True)
