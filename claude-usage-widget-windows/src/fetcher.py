"""Asynchronous Claude usage fetch via QProcess (event loop, no threads).

Spawns a short-lived child process that fetches usage and prints it as JSON on
stdout, then parses the result on the Qt event loop when the process finishes.

This mirrors the QProcess + event-loop pattern used elsewhere in the repo
(``vscode-launcher``, ``vpn-toggle``) and deliberately avoids QThread: a
QThread destroyed before it fully terminates makes Qt call ``qFatal()`` /
``abort()`` (SIGABRT), which crashed the widget after a few update cycles.
"""

from __future__ import annotations

import json
import sys

from PySide6.QtCore import QObject, QProcess, Signal

import structlog

log = structlog.get_logger(__name__)


def fetch_command() -> tuple[str, list[str]]:
    """Return ``(program, args)`` that runs the JSON usage fetch as a child.

    Frozen (PyInstaller .app): the app's own executable is the entry point, so
    re-invoke it with ``--fetch-json``. From source (``python -m src.main``):
    re-invoke the module through the same interpreter.
    """
    if getattr(sys, "frozen", False):
        return sys.executable, ["--fetch-json"]
    return sys.executable, ["-m", "src.main", "--fetch-json"]


class UsageFetcher(QObject):
    """Run one usage fetch in a child process and emit the parsed result.

    One instance == one fetch. ``result_ready`` fires exactly once with the
    parsed payload (a ``dict``, an ``{"error": ...}`` dict, or ``None`` on
    failure). The QProcess is parented to this object; the caller should
    ``deleteLater()`` the fetcher after handling the signal — safe to do from
    the slot, since the process has already finished by then.
    """

    result_ready = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._proc: QProcess | None = None
        self._emitted = False

    def start(self) -> None:
        program, args = fetch_command()
        self._proc = QProcess(self)
        # JSON is on stdout, logs on stderr — keep the channels separate.
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        log.debug("usage_fetch_start", program=program, args=args)
        self._proc.start(program, args)

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        data = None
        if self._proc is not None:
            raw = bytes(self._proc.readAllStandardOutput().data()).decode("utf-8", "replace").strip()
            data = self._parse(raw)
            if exit_code != 0 and data is None:
                err = bytes(self._proc.readAllStandardError().data()).decode("utf-8", "replace").strip()
                log.warning("usage_fetch_nonzero_exit", exit_code=exit_code, stderr=err[-200:])
        self._emit(data)

    def _on_error(self, _error) -> None:
        msg = self._proc.errorString() if self._proc is not None else "unknown"
        log.warning("usage_fetch_process_error", error=msg)
        self._emit(None)

    @staticmethod
    def _parse(raw: str):
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("usage_fetch_bad_json", raw=raw[:200])
            return None

    def _emit(self, data) -> None:
        # finished and errorOccurred can both fire; emit the result only once.
        if self._emitted:
            return
        self._emitted = True
        self.result_ready.emit(data)
