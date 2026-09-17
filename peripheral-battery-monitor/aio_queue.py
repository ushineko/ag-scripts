"""Serialised liquidctl invocation (spec 021).

Every liquidctl call in this app — the spec 020 status poll, RGB writes, LCD
writes — opens the same `/dev/hidraw*` node on the same device. Running two at
once risks interleaved control transfers on one HID endpoint, and this machine
has a documented history of hidraw contention (logid, solaar and battery_reader
sharing a node produced 25 s stalls). So they go through one queue and exactly
one process runs at a time.

Priorities, highest first:

- `PRIORITY_WRITE` — a user just clicked something. Runs ahead of polling so the
  UI feels immediate.
- `PRIORITY_READ`  — the status poll. Cooling telemetry must not starve.
- `PRIORITY_IDLE`  — the LCD dashboard push. Dropped rather than queued when
  anything else is pending: a skipped frame on a decorative screen costs
  nothing, and not writing is the main mitigation for liquidctl#774.

Nothing here blocks the GUI thread; QProcess is asynchronous throughout.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QObject, QProcess, QTimer

_log = logging.getLogger(__name__)

PRIORITY_WRITE = 0
PRIORITY_READ = 1
PRIORITY_IDLE = 2

DEFAULT_TIMEOUT_MS = 15000
# Cap the backlog. A pathologically slow device must not accumulate work that
# would then all fire at once; dropping the oldest low-priority job is better.
MAX_PENDING = 8


class LiquidctlQueue(QObject):
    """Runs liquidctl commands one at a time, in priority order."""

    def __init__(self, parent=None, timeout_ms: int = DEFAULT_TIMEOUT_MS):
        super().__init__(parent)
        self._pending: list[dict] = []
        self._current: dict | None = None
        self._proc: QProcess | None = None
        self._killer: QTimer | None = None
        self._timeout_ms = timeout_ms

    # -- public -------------------------------------------------------------

    @property
    def busy(self) -> bool:
        return self._current is not None

    def pending_count(self) -> int:
        return len(self._pending)

    def submit(self, argv: list[str], priority: int, on_done=None,
               coalesce_key: str | None = None) -> bool:
        """Queue a command. Returns False when it was refused or dropped.

        `on_done(ok: bool, stdout: bytes, stderr: str)` is called on completion,
        always exactly once.

        `coalesce_key` replaces any queued-but-not-started job carrying the same
        key. The dashboard uses it so a burst of renders collapses to the newest
        frame instead of replaying stale ones.
        """
        if not argv:
            return False

        # An idle job is a luxury: never let it wait behind real work.
        if priority >= PRIORITY_IDLE and (self._current is not None or self._pending):
            _log.debug("liquidctl_idle_job_dropped busy=%s pending=%d",
                       self._current is not None, len(self._pending))
            return False

        if coalesce_key is not None:
            self._pending = [j for j in self._pending if j.get("key") != coalesce_key]

        if len(self._pending) >= MAX_PENDING:
            # Drop the lowest-priority queued job to make room, else refuse.
            victim = max(self._pending, key=lambda j: j["priority"])
            if victim["priority"] >= priority:
                self._pending.remove(victim)
                self._finish_job(victim, False, b"", "dropped: queue full")
            else:
                self._finish_job({"on_done": on_done}, False, b"", "refused: queue full")
                return False

        self._pending.append({
            "argv": list(argv),
            "priority": priority,
            "on_done": on_done,
            "key": coalesce_key,
        })
        # Stable within a priority: sorted() preserves insertion order for ties.
        self._pending.sort(key=lambda j: j["priority"])
        self._maybe_start()
        return True

    def clear_idle(self):
        """Drop queued idle work, e.g. when the dashboard is switched off."""
        keep, drop = [], []
        for job in self._pending:
            (drop if job["priority"] >= PRIORITY_IDLE else keep).append(job)
        self._pending = keep
        for job in drop:
            self._finish_job(job, False, b"", "cancelled")

    # -- internals ----------------------------------------------------------

    def _maybe_start(self):
        if self._current is not None or not self._pending:
            return
        job = self._pending.pop(0)
        self._current = job

        proc = QProcess(self)
        self._proc = proc
        proc.setProgram(job["argv"][0])
        proc.setArguments(job["argv"][1:])

        settled = {"done": False}

        def settle(ok: bool, err: str):
            if settled["done"]:
                return
            settled["done"] = True
            if self._killer is not None:
                self._killer.stop()
                self._killer = None
            out = b""
            stderr = err
            try:
                out = bytes(proc.readAllStandardOutput())
                if not stderr:
                    stderr = bytes(proc.readAllStandardError()).decode("utf-8", "replace")
            except Exception:
                pass
            proc.deleteLater()
            self._proc = None
            current, self._current = self._current, None
            self._finish_job(current, ok, out, stderr)
            # Drain the next job on the event loop, not recursively, so a long
            # queue cannot deepen the stack.
            QTimer.singleShot(0, self._maybe_start)

        proc.finished.connect(lambda code, _s: settle(code == 0, ""))
        proc.errorOccurred.connect(lambda e: settle(False, f"process error: {e}"))

        killer = QTimer(self)
        killer.setSingleShot(True)
        killer.setInterval(self._timeout_ms)
        killer.timeout.connect(lambda: (proc.kill(), settle(False, "timeout")))
        self._killer = killer
        killer.start()

        proc.start()

    @staticmethod
    def _finish_job(job: dict | None, ok: bool, out: bytes, err: str):
        if not job:
            return
        callback = job.get("on_done")
        if callback is None:
            return
        try:
            callback(ok, out, err)
        except Exception:
            # A misbehaving callback must not stall the queue.
            _log.warning("liquidctl_callback_failed", exc_info=True)
