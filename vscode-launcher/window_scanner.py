"""KWin-backed enumeration of currently-open VSCode windows.

Loads a small KWin script via D-Bus that dumps the captions of every VSCode
window (`resourceClass == "code"`) to the compositor log, then reads the log
line back through journalctl and parses the JSON payload.

Mirrors the approach used by the sibling `vscode-gather` tool, which has
proven reliable on KDE Plasma 6 (Wayland). All failure modes return None
so callers can gracefully degrade (no running-state shown) when KWin or
journalctl are unavailable.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Iterable

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

SCRIPT_NAME = "vscode-launcher-scanner"
ACTION_SCRIPT_NAME = "vscode-launcher-action"
LOG_PREFIX = "VSCL_CAPTIONS:"
# Per-scan markers look like "VSCL_CAPTIONS_<nonce>:". A unique nonce per scan
# prevents the journal-race bug where a previous scan's log line is still in
# `journalctl --since "3 seconds ago"` output but the current scan's line
# hasn't flushed yet — without a nonce we'd accept the stale line.
SCAN_MARKER_PREFIX = "VSCL_CAPTIONS_"
ACTION_LOG_PREFIX = "VSCL_ACTION_OK:"


def _new_scan_nonce() -> str:
    return uuid.uuid4().hex[:12]


def build_enumerate_script(nonce: str) -> str:
    """Build the KWin JS enumeration script with `nonce` baked into the log
    marker so stale journal lines can be unambiguously rejected."""
    marker = SCAN_MARKER_PREFIX + nonce + ":"
    return (
        "(function() {"
        "  var windows = workspace.windowList();"
        "  var entries = [];"
        "  for (var i = 0; i < windows.length; i++) {"
        "    var w = windows[i];"
        '    if (w.resourceClass !== "code") continue;'
        "    if (w.skipTaskbar || w.specialWindow) continue;"
        "    entries.push({c: w.caption, p: w.pid});"
        "  }"
        '  console.log("%s" + JSON.stringify(entries));'
        "})();"
    ) % marker

ACTION_CLOSE = "close"
ACTION_ACTIVATE = "activate"

# Kept for test compatibility — legacy tests inject journal text using the
# bare `VSCL_CAPTIONS:` prefix (pre-nonce). Production scans always use
# `build_enumerate_script(nonce)` and the nonce-aware parser.
KWIN_ENUMERATE_SCRIPT = """
(function() {
    var windows = workspace.windowList();
    var entries = [];
    for (var i = 0; i < windows.length; i++) {
        var w = windows[i];
        if (w.resourceClass !== "code") continue;
        if (w.skipTaskbar || w.specialWindow) continue;
        entries.push({c: w.caption, p: w.pid});
    }
    console.log("%s" + JSON.stringify(entries));
})();
""" % LOG_PREFIX


def _build_action_script(label: str, action: str) -> str:
    """Return a KWin JS script that finds the first VSCode window whose caption
    contains `label` as a ` - `-separated token and performs the named action.

    `label` is JSON-encoded so embedded quotes, backslashes, and newlines are
    safe in the JS source.
    """
    label_literal = json.dumps(label)
    # Pick the action branch at generation time so the script doesn't need to
    # string-compare on each iteration.
    if action == ACTION_CLOSE:
        action_js = "w.closeWindow();"
    elif action == ACTION_ACTIVATE:
        action_js = "workspace.activeWindow = w;"
    else:
        raise ValueError(f"unsupported action: {action!r}")

    return (
        "(function() {"
        "  var target = %s;"
        "  var windows = workspace.windowList();"
        "  for (var i = 0; i < windows.length; i++) {"
        "    var w = windows[i];"
        '    if (w.resourceClass !== "code") continue;'
        "    if (w.skipTaskbar || w.specialWindow) continue;"
        '    var parts = w.caption.split(" - ");'
        "    var hit = false;"
        "    for (var j = 0; j < parts.length; j++) {"
        "      if (parts[j] === target) { hit = true; break; }"
        "    }"
        "    if (!hit) continue;"
        "    %s"
        '    console.log("%s" + w.caption);'
        "    break;"
        "  }"
        "})();"
    ) % (label_literal, action_js, ACTION_LOG_PREFIX)


def caption_matches_label(caption: str, label: str) -> bool:
    """Return True if `label` appears as a whole token in a VSCode window caption.

    VSCode captions look like `<file> - <label> - Visual Studio Code`. A direct
    substring check would produce false positives for labels that are prefixes
    of others (e.g. `aiq-ralph` inside `aiq-ralphbox`). Splitting on the
    well-known ` - ` delimiter and checking token equality avoids that.
    """
    if not label or not caption:
        return False
    return label in caption.split(" - ")


def running_labels(captions: Iterable[str], labels: Iterable[str]) -> set[str]:
    """Return the subset of `labels` that appear as a token in any caption."""
    cap_list = list(captions)
    return {label for label in labels if any(caption_matches_label(c, label) for c in cap_list)}


class WindowScanner(QObject):
    """Enumerate VSCode window captions via KWin scripting.

    Exposes two APIs for the same operation:

    * `start_async_scan()` — event-driven. Result delivered via the
      `scan_finished` signal. Uses QProcess, so no thread is spawned. This
      is what the background auto-refresh path uses — it can be invoked
      every N seconds without blocking the UI thread or tripping the PyQt
      QThread + QObject worker GC invariants.
    * `list_vscode_captions()` — synchronous, blocks on subprocess calls.
      Kept for rare sync callers (manual Refresh at startup, tests).

    The two implementations share the parsing helpers (`_build_action_script`,
    `parse_captions_from_journal`, etc.) but the subprocess/event-loop
    plumbing is separate because mixing synchronous `subprocess.run` with
    asynchronous `QProcess` in one function is a footgun.
    """

    # Payload: list of {"c": caption, "p": pid | None} dicts, or None on failure.
    scan_finished = pyqtSignal(object)

    def __init__(
        self,
        qdbus_cmd: str = "qdbus6",
        kwin_journal_unit: str = "plasma-kwin_wayland",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.qdbus_cmd = qdbus_cmd
        self.kwin_journal_unit = kwin_journal_unit
        # Async state machine — set during an in-flight scan.
        self._scan_in_progress = False
        self._script_path: str | None = None
        self._script_id: int | None = None
        self._scan_nonce: str | None = None
        self._load_proc: QProcess | None = None
        self._run_proc: QProcess | None = None
        self._log_proc: QProcess | None = None
        self._delay_timer: QTimer | None = None

    def available(self) -> bool:
        return bool(shutil.which(self.qdbus_cmd) and shutil.which("journalctl"))

    # ------------------------------------------------------------------
    # Async (event-driven) scan — preferred for the background auto-refresh.
    # ------------------------------------------------------------------

    def start_async_scan(self) -> None:
        """Start a non-blocking scan. Result arrives via `scan_finished`.

        If a scan is already in flight, the call is a silent no-op — callers
        don't need their own reentrance guards.
        """
        if self._scan_in_progress:
            return
        if not self.available():
            self.scan_finished.emit(None)
            return

        self._scan_in_progress = True
        self._scan_nonce = _new_scan_nonce()
        self._script_path = self._write_script(
            build_enumerate_script(self._scan_nonce)
        )
        if self._script_path is None:
            self._finish_async(None)
            return

        self._load_proc = QProcess(self)
        self._load_proc.finished.connect(self._on_load_finished)
        self._load_proc.errorOccurred.connect(self._on_async_error)
        self._load_proc.start(
            self.qdbus_cmd,
            [
                "org.kde.KWin",
                "/Scripting",
                "org.kde.kwin.Scripting.loadScript",
                self._script_path,
                SCRIPT_NAME,
            ],
        )

    def _on_load_finished(self, exit_code: int, _exit_status: object) -> None:
        if exit_code != 0 or self._load_proc is None:
            self._finish_async(None)
            return
        raw = bytes(self._load_proc.readAllStandardOutput()).decode(
            errors="replace"
        ).strip()
        try:
            self._script_id = int(raw)
        except ValueError:
            self._finish_async(None)
            return
        if self._script_id < 0:
            self._finish_async(None)
            return

        self._run_proc = QProcess(self)
        self._run_proc.finished.connect(self._on_run_finished)
        self._run_proc.errorOccurred.connect(self._on_async_error)
        self._run_proc.start(
            self.qdbus_cmd,
            [
                "org.kde.KWin",
                f"/Scripting/Script{self._script_id}",
                "org.kde.kwin.Script.run",
            ],
        )

    def _on_run_finished(self, *_args: object) -> None:
        # KWin's `console.log` is flushed to the journal asynchronously;
        # wait briefly before reading it back.
        self._delay_timer = QTimer(self)
        self._delay_timer.setSingleShot(True)
        self._delay_timer.timeout.connect(self._start_journal_read)
        self._delay_timer.start(300)

    def _start_journal_read(self) -> None:
        self._log_proc = QProcess(self)
        self._log_proc.finished.connect(self._on_log_finished)
        self._log_proc.errorOccurred.connect(self._on_async_error)
        self._log_proc.start(
            "journalctl",
            [
                "--user",
                "-u",
                self.kwin_journal_unit,
                "--since",
                "3 seconds ago",
                "--no-pager",
            ],
        )

    def _on_log_finished(self, *_args: object) -> None:
        if self._log_proc is None or self._scan_nonce is None:
            self._finish_async(None)
            return
        log_text = bytes(self._log_proc.readAllStandardOutput()).decode(
            errors="replace"
        )
        marker = SCAN_MARKER_PREFIX + self._scan_nonce + ":"
        self._finish_async(parse_scan_entries_from_journal(log_text, marker))

    def _on_async_error(self, *_args: object) -> None:
        self._finish_async(None)

    def _finish_async(self, result: list[dict] | None) -> None:
        """Emit the result, tear down any in-flight state, and fire an unload
        for the KWin script (fire-and-forget — we don't wait for its result).
        """
        # Fire-and-forget unload so KWin doesn't keep the named script around.
        if self._script_id is not None and self._script_id >= 0:
            unload = QProcess(self)
            unload.finished.connect(unload.deleteLater)
            unload.errorOccurred.connect(unload.deleteLater)
            unload.start(
                self.qdbus_cmd,
                [
                    "org.kde.KWin",
                    "/Scripting",
                    "org.kde.kwin.Scripting.unloadScript",
                    SCRIPT_NAME,
                ],
            )

        if self._script_path:
            try:
                os.unlink(self._script_path)
            except OSError:
                pass

        for proc in (self._load_proc, self._run_proc, self._log_proc):
            if proc is not None:
                proc.deleteLater()
        if self._delay_timer is not None:
            self._delay_timer.deleteLater()

        self._script_path = None
        self._script_id = None
        self._scan_nonce = None
        self._load_proc = None
        self._run_proc = None
        self._log_proc = None
        self._delay_timer = None
        self._scan_in_progress = False
        self.scan_finished.emit(result)

    @staticmethod
    def _write_script(body: str) -> str | None:
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", prefix=f"{SCRIPT_NAME}-", delete=False
            ) as f:
                f.write(body)
                return f.name
        except OSError:
            return None

    # ------------------------------------------------------------------
    # Synchronous scan — used by manual Refresh and tests.
    # ------------------------------------------------------------------

    def perform_window_action(self, label: str, action: str) -> bool:
        """Find the first VSCode window matching `label` and run `action` on it.

        Supported actions: `close` (via `w.closeWindow()`), `activate` (via
        `workspace.activeWindow = w`). Returns True if the journal shows the
        action was applied, False otherwise (no match, KWin error, tooling
        missing).
        """
        if action not in (ACTION_CLOSE, ACTION_ACTIVATE):
            raise ValueError(f"unsupported action: {action!r}")
        if not self.available():
            return False

        script_path: str | None = None
        try:
            script_body = _build_action_script(label, action)
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", prefix=f"{ACTION_SCRIPT_NAME}-", delete=False
            ) as f:
                f.write(script_body)
                script_path = f.name

            load = subprocess.run(
                [
                    self.qdbus_cmd,
                    "org.kde.KWin",
                    "/Scripting",
                    "org.kde.kwin.Scripting.loadScript",
                    script_path,
                    ACTION_SCRIPT_NAME,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if load.returncode != 0:
                return False
            try:
                script_id = int(load.stdout.strip())
            except ValueError:
                return False
            if script_id < 0:
                return False

            subprocess.run(
                [
                    self.qdbus_cmd,
                    "org.kde.KWin",
                    f"/Scripting/Script{script_id}",
                    "org.kde.kwin.Script.run",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )

            time.sleep(0.3)

            log = subprocess.run(
                [
                    "journalctl",
                    "--user",
                    "-u",
                    self.kwin_journal_unit,
                    "--since",
                    "3 seconds ago",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            return action_succeeded(log.stdout)
        except (subprocess.TimeoutExpired, OSError):
            return False
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
            try:
                subprocess.run(
                    [
                        self.qdbus_cmd,
                        "org.kde.KWin",
                        "/Scripting",
                        "org.kde.kwin.Scripting.unloadScript",
                        ACTION_SCRIPT_NAME,
                    ],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass

    def list_vscode_entries(self) -> list[dict] | None:
        """Return list of `{"c": caption, "p": pid | None}` dicts, or None if
        the scan failed. Pid may be None on KWin versions that don't expose
        it — callers should handle that gracefully.

        None signals "can't tell" — callers should treat this as "no running
        state is known" rather than "no VSCode windows are open".
        """
        if not self.available():
            return None

        script_path: str | None = None
        nonce = _new_scan_nonce()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", prefix=f"{SCRIPT_NAME}-", delete=False
            ) as f:
                f.write(build_enumerate_script(nonce))
                script_path = f.name

            load = subprocess.run(
                [
                    self.qdbus_cmd,
                    "org.kde.KWin",
                    "/Scripting",
                    "org.kde.kwin.Scripting.loadScript",
                    script_path,
                    SCRIPT_NAME,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if load.returncode != 0:
                return None
            script_id_str = load.stdout.strip()
            try:
                script_id = int(script_id_str)
            except ValueError:
                return None
            if script_id < 0:
                return None

            subprocess.run(
                [
                    self.qdbus_cmd,
                    "org.kde.KWin",
                    f"/Scripting/Script{script_id}",
                    "org.kde.kwin.Script.run",
                ],
                capture_output=True,
                timeout=5,
                check=False,
            )

            # KWin logs `console.log` output asynchronously; give it a moment.
            time.sleep(0.3)

            log = subprocess.run(
                [
                    "journalctl",
                    "--user",
                    "-u",
                    self.kwin_journal_unit,
                    "--since",
                    "3 seconds ago",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )

            marker = SCAN_MARKER_PREFIX + nonce + ":"
            return parse_scan_entries_from_journal(log.stdout, marker)
        except (subprocess.TimeoutExpired, OSError):
            return None
        finally:
            if script_path:
                try:
                    os.unlink(script_path)
                except OSError:
                    pass
            # Best-effort unload; ignore any errors
            try:
                subprocess.run(
                    [
                        self.qdbus_cmd,
                        "org.kde.KWin",
                        "/Scripting",
                        "org.kde.kwin.Scripting.unloadScript",
                        SCRIPT_NAME,
                    ],
                    capture_output=True,
                    timeout=5,
                    check=False,
                )
            except (subprocess.TimeoutExpired, OSError):
                pass

    def list_vscode_captions(self) -> list[str] | None:
        """Backward-compat wrapper over `list_vscode_entries` returning only
        caption strings. Preferred when the caller doesn't care about pids."""
        entries = self.list_vscode_entries()
        if entries is None:
            return None
        return [e["c"] for e in entries]


def action_succeeded(journal_text: str) -> bool:
    """Return True if any `VSCL_ACTION_OK:` marker appears in the recent log."""
    if not journal_text:
        return False
    for line in journal_text.splitlines():
        if ACTION_LOG_PREFIX in line:
            return True
    return False


def parse_scan_entries_from_journal(
    journal_text: str,
    marker: str = LOG_PREFIX,
) -> list[dict] | None:
    """Pull the most recent `<marker>[...]` payload from journalctl output.

    `marker` defaults to the legacy bare `VSCL_CAPTIONS:` prefix (accepted by
    legacy tests and the backward-compat code path). Production scans pass
    a per-scan `VSCL_CAPTIONS_<nonce>:` marker so stale journal lines from
    previous scans can't spoof the result when KWin's log flush is delayed.

    Returns the parsed entries list, or None if no matching line is found
    or the JSON payload is malformed.
    """
    if not journal_text:
        return None
    for line in reversed(journal_text.splitlines()):
        idx = line.find(marker)
        if idx < 0:
            continue
        payload = line[idx + len(marker):].strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, list):
            continue
        result: list[dict] = []
        for item in parsed:
            if isinstance(item, dict) and "c" in item:
                pid = item.get("p")
                result.append(
                    {"c": str(item["c"]), "p": int(pid) if isinstance(pid, int) else None}
                )
            elif isinstance(item, str):
                # Legacy format — caption without pid
                result.append({"c": item, "p": None})
        return result
    return None


def parse_captions_from_journal(journal_text: str) -> list[str] | None:
    """Backward-compatible wrapper returning just the caption strings."""
    entries = parse_scan_entries_from_journal(journal_text)
    if entries is None:
        return None
    return [e["c"] for e in entries]


def get_process_start_time(pid: int) -> float | None:
    """Return the Unix timestamp when the process `pid` was started, or None
    on any failure (bad pid, race, permission, exotic system). Reads
    `/proc/<pid>/stat` field 22 (starttime in clock ticks since boot) and
    combines with `/proc/stat` `btime` (seconds since epoch at boot).
    """
    try:
        with open(f"/proc/{pid}/stat", "rb") as f:
            data = f.read()
    except OSError:
        return None
    try:
        # comm may contain spaces and parens; rsplit on last ")" is the safe cut.
        close_paren = data.rindex(b")")
    except ValueError:
        return None
    after_comm = data[close_paren + 2:].split()
    try:
        # After skipping pid and (comm), field 22 (starttime) is at index 19.
        starttime_ticks = int(after_comm[19])
    except (IndexError, ValueError):
        return None
    try:
        hz = os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError):
        return None
    try:
        with open("/proc/stat", "r") as f:
            btime: int | None = None
            for line in f:
                if line.startswith("btime "):
                    try:
                        btime = int(line.split()[1])
                    except (IndexError, ValueError):
                        return None
                    break
    except OSError:
        return None
    if btime is None:
        return None
    return btime + starttime_ticks / hz
