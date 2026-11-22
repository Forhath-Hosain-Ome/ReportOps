import threading
from unittest.mock import patch

from celery.contrib.testing.worker import TestWorkController
from django.test import SimpleTestCase

from .runtime_cleanup import DatabaseClosingWorker


class WorkerCleanupTests(SimpleTestCase):
    def run_worker(self, failure=None):
        worker = object.__new__(DatabaseClosingWorker)
        observed = []
        def close():
            observed.append(threading.current_thread())
        def run():
            try:
                worker.start()
            except RuntimeError as exc:
                observed.append(str(exc))
        with patch.object(TestWorkController, 'start', side_effect=failure), \
                patch('inspection_summary.tests.runtime_cleanup.connections.close_all', side_effect=close):
            thread = threading.Thread(target=run)
            thread.start(); thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertIs(worker.worker_thread, thread)
        self.assertTrue(worker.database_closed)
        self.assertEqual(observed[0], thread)
        self.assertIsNot(observed[0], threading.current_thread())
        return observed

    def test_connections_close_inside_worker_thread_after_normal_shutdown(self):
        self.assertEqual(len(self.run_worker()), 1)

    def test_connections_close_inside_worker_thread_when_start_raises(self):
        self.assertEqual(self.run_worker(RuntimeError('startup failed'))[1], 'startup failed')
