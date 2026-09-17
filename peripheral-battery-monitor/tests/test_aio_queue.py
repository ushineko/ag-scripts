"""Spec 021 AC5/AC6: liquidctl invocations are serialised.

Every liquidctl call in this app opens the same hidraw node. These tests use
real short-lived processes (`true`, `sleep`, `false`) rather than mocks, because
the property under test is that two OS processes never overlap — a mocked
QProcess would not demonstrate that.
"""

import os
import sys
import unittest

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
sys.path.insert(0, PROJECT_DIR)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEventLoop, QTimer  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

import aio_queue  # noqa: E402

_app = QApplication.instance() or QApplication([])


def pump(ms: int = 1500, until=None):
    """Run the event loop until `until()` or the deadline."""
    loop = QEventLoop()
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    deadline.start(ms)
    if until is not None:
        poll = QTimer()
        poll.timeout.connect(lambda: loop.quit() if until() else None)
        poll.start(10)
    loop.exec()


class TestSerialisation(unittest.TestCase):
    def test_only_one_process_runs_at_a_time(self):
        """The core guarantee: overlapping hidraw access must be impossible."""
        q = aio_queue.LiquidctlQueue()
        live = {"now": 0, "max": 0}
        done = []

        def make(i):
            def cb(ok, out, err):
                live["now"] -= 1
                done.append(i)
            return cb

        # Each job sleeps, so an unserialised queue would overlap them.
        for i in range(4):
            started = q.submit(["sh", "-c", "sleep 0.15"],
                               aio_queue.PRIORITY_READ, on_done=make(i))
            self.assertTrue(started)

        def watch():
            if q.busy:
                live["now"] = 1
                live["max"] = max(live["max"], live["now"])
            return len(done) == 4

        pump(4000, watch)
        self.assertEqual(len(done), 4, "all jobs should finish")
        self.assertLessEqual(live["max"], 1, "never more than one in flight")

    def test_writes_run_before_reads(self):
        q = aio_queue.LiquidctlQueue()
        order = []
        q.submit(["true"], aio_queue.PRIORITY_READ,
                 on_done=lambda *a: order.append("read1"))
        q.submit(["true"], aio_queue.PRIORITY_READ,
                 on_done=lambda *a: order.append("read2"))
        q.submit(["true"], aio_queue.PRIORITY_WRITE,
                 on_done=lambda *a: order.append("write"))
        pump(3000, lambda: len(order) == 3)
        self.assertEqual(len(order), 3)
        # read1 is already running; the write must precede the queued read2.
        self.assertLess(order.index("write"), order.index("read2"))

    def test_idle_job_is_dropped_when_busy(self):
        """A dashboard push is a luxury: skip it rather than queue it."""
        q = aio_queue.LiquidctlQueue()
        q.submit(["sh", "-c", "sleep 0.2"], aio_queue.PRIORITY_READ)
        accepted = q.submit(["true"], aio_queue.PRIORITY_IDLE)
        self.assertFalse(accepted)
        pump(2000, lambda: not q.busy)

    def test_idle_job_runs_when_queue_is_empty(self):
        q = aio_queue.LiquidctlQueue()
        got = []
        self.assertTrue(q.submit(["true"], aio_queue.PRIORITY_IDLE,
                                 on_done=lambda ok, *a: got.append(ok)))
        pump(2000, lambda: bool(got))
        self.assertEqual(got, [True])

    def test_failure_is_reported_not_raised(self):
        q = aio_queue.LiquidctlQueue()
        got = []
        q.submit(["false"], aio_queue.PRIORITY_WRITE,
                 on_done=lambda ok, *a: got.append(ok))
        pump(2000, lambda: bool(got))
        self.assertEqual(got, [False])

    def test_missing_binary_reports_failure(self):
        q = aio_queue.LiquidctlQueue()
        got = []
        q.submit(["definitely-not-a-real-binary-xyz"], aio_queue.PRIORITY_WRITE,
                 on_done=lambda ok, *a: got.append(ok))
        pump(2000, lambda: bool(got))
        self.assertEqual(got, [False])

    def test_timeout_kills_and_reports(self):
        q = aio_queue.LiquidctlQueue(timeout_ms=150)
        got = []
        q.submit(["sh", "-c", "sleep 5"], aio_queue.PRIORITY_WRITE,
                 on_done=lambda ok, *a: got.append(ok))
        pump(3000, lambda: bool(got))
        self.assertEqual(got, [False], "a hung device must not wedge the queue")

    def test_queue_survives_a_raising_callback(self):
        q = aio_queue.LiquidctlQueue()
        second = []

        def boom(*_a):
            raise RuntimeError("callback blew up")

        q.submit(["true"], aio_queue.PRIORITY_WRITE, on_done=boom)
        q.submit(["true"], aio_queue.PRIORITY_WRITE,
                 on_done=lambda *a: second.append(True))
        pump(3000, lambda: bool(second))
        self.assertEqual(second, [True], "a bad callback must not stall the queue")

    def test_stdout_is_delivered(self):
        q = aio_queue.LiquidctlQueue()
        got = []
        q.submit(["sh", "-c", "echo hello"], aio_queue.PRIORITY_READ,
                 on_done=lambda ok, out, err: got.append((ok, bytes(out))))
        pump(2000, lambda: bool(got))
        self.assertTrue(got[0][0])
        self.assertIn(b"hello", got[0][1])

    def test_coalesce_replaces_queued_job(self):
        q = aio_queue.LiquidctlQueue()
        results = []
        q.submit(["sh", "-c", "sleep 0.2"], aio_queue.PRIORITY_READ)   # occupies
        q.submit(["true"], aio_queue.PRIORITY_READ,
                 on_done=lambda *a: results.append("stale"), coalesce_key="k")
        q.submit(["true"], aio_queue.PRIORITY_READ,
                 on_done=lambda *a: results.append("fresh"), coalesce_key="k")
        pump(3000, lambda: "fresh" in results)
        self.assertIn("fresh", results)
        self.assertNotIn("stale", results, "superseded job should not run")

    def test_empty_argv_refused(self):
        self.assertFalse(aio_queue.LiquidctlQueue().submit([], aio_queue.PRIORITY_WRITE))

    def test_clear_idle_cancels_pending_dashboard_work(self):
        q = aio_queue.LiquidctlQueue()
        cancelled = []
        q.submit(["sh", "-c", "sleep 0.2"], aio_queue.PRIORITY_READ)
        q._pending.append({"argv": ["true"], "priority": aio_queue.PRIORITY_IDLE,
                           "on_done": lambda ok, *a: cancelled.append(ok),
                           "key": None})
        q.clear_idle()
        self.assertEqual(cancelled, [False])
        pump(2000, lambda: not q.busy)


if __name__ == "__main__":
    unittest.main()
