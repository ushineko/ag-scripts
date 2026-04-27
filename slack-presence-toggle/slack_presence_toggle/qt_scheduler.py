from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, QTimer


class QtScheduler(QObject):
    """Scheduler implementation backed by QTimer.singleShot.

    Each scheduled callback is owned by a QTimer kept in a dict keyed by
    handle id. We hold Python references to the timers because PyQt's QTimer
    objects can be garbage-collected if no Python ref exists, even when
    started — which silently drops the firing.
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._timers: dict[int, QTimer] = {}
        self._next_id = 0

    def schedule(self, delay_seconds: float, callback: Callable[[], None]) -> object:
        self._next_id += 1
        handle = self._next_id
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda h=handle, cb=callback: self._fire(h, cb))
        self._timers[handle] = timer
        timer.start(int(delay_seconds * 1000))
        return handle

    def _fire(self, handle: int, callback: Callable[[], None]) -> None:
        timer = self._timers.pop(handle, None)
        if timer is None:
            return  # cancelled in flight
        try:
            callback()
        finally:
            timer.deleteLater()

    def cancel(self, handle: object) -> None:
        timer = self._timers.pop(handle, None)  # type: ignore[arg-type]
        if timer is not None:
            timer.stop()
            timer.deleteLater()
