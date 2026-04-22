"""Window enumeration + window actions for vscode-launcher.

v2.0: scanning switched from KWin-scripting-via-journalctl to VSCode's own
internal IPC protocol (see `vscode_ipc.py`). The new path is ~170× faster
(~3 ms vs ~500 ms), returns accurate per-window renderer PIDs and real
folder URIs, and works on any platform where VSCode itself runs. The
entire v1.6/v1.7/v1.8.1 machinery — QProcess state machine, per-scan
nonces, journalctl-race workaround — is no longer needed and has been
removed.

Actions (Close / Activate) still use KWin scripting. Porting them to IPC
(`launch.start` for activate via `--reuse-window`, unknown for close)
is a separate investigation.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from typing import Iterable

from vscode_ipc import list_vscode_windows
# Re-exported so existing callers keep working after the move to
# platform_support.py. New code should import directly from platform_support.
from platform_support import process_start_time as get_process_start_time

ACTION_SCRIPT_NAME = "vscode-launcher-action"
ACTION_LOG_PREFIX = "VSCL_ACTION_OK:"

ACTION_CLOSE = "close"
ACTION_ACTIVATE = "activate"


def _build_action_script(label: str, action: str) -> str:
    """Build the KWin JS script that closes or activates the first VSCode
    window whose caption contains `label` as a ` - `-separated token.

    `label` is JSON-encoded to safely handle quotes / newlines / backslashes.
    """
    label_literal = json.dumps(label)
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
    """Return True if `label` appears as a whole ` - `-separated token in a
    VSCode window caption. Token-split instead of substring so that e.g.
    `aiq-ralph` doesn't spuriously match an `aiq-ralphbox` window's caption.
    """
    if not label or not caption:
        return False
    return label in caption.split(" - ")


def running_labels(captions: Iterable[str], labels: Iterable[str]) -> set[str]:
    """Return the subset of `labels` that appear as a token in any caption."""
    cap_list = list(captions)
    return {label for label in labels if any(caption_matches_label(c, label) for c in cap_list)}


def action_succeeded(journal_text: str) -> bool:
    """True if any `VSCL_ACTION_OK:` marker appears in the recent log."""
    if not journal_text:
        return False
    return any(ACTION_LOG_PREFIX in line for line in journal_text.splitlines())


def _ipc_entries_to_legacy_shape(entries: list[dict] | None) -> list[dict] | None:
    """Translate `vscode_ipc.WindowEntry` → the `{c: caption, p: pid}` shape
    MainWindow has always consumed. Keeps the backend swap invisible to the
    rest of the app."""
    if entries is None:
        return None
    out: list[dict] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        title = e.get("title")
        pid = e.get("pid")
        if isinstance(title, str):
            out.append(
                {
                    "c": title,
                    "p": int(pid) if isinstance(pid, int) else None,
                }
            )
    return out


class WindowScanner:
    """Enumerate VSCode windows (via IPC) and perform window actions (via KWin).

    Scanning is synchronous and fast enough (~3 ms) to invoke directly from
    the UI thread — no QThread, no QProcess, no signals required. Actions
    (Close / Activate) still use KWin scripting; see perform_window_action.
    """

    def __init__(
        self,
        qdbus_cmd: str = "qdbus6",
        kwin_journal_unit: str = "plasma-kwin_wayland",
    ) -> None:
        self.qdbus_cmd = qdbus_cmd
        self.kwin_journal_unit = kwin_journal_unit

    def available(self) -> bool:
        """Scanning is always available — the IPC path degrades to []
        when VSCode isn't running. (Actions need qdbus6, but callers
        don't need to check availability for reads.)"""
        return True

    # ------------------------------------------------------------------
    # Scanning (IPC)
    # ------------------------------------------------------------------

    def list_vscode_entries(self) -> list[dict] | None:
        """Return `[{c: caption, p: pid}, ...]` for every open VSCode window,
        or None on transient IPC failure. Returns [] when VSCode isn't
        running (no socket found)."""
        entries = list_vscode_windows()
        return _ipc_entries_to_legacy_shape(entries)

    def list_vscode_captions(self) -> list[str] | None:
        """Backward-compat wrapper returning only caption strings."""
        entries = self.list_vscode_entries()
        if entries is None:
            return None
        return [e["c"] for e in entries]

    # ------------------------------------------------------------------
    # Actions (KWin scripting)
    # ------------------------------------------------------------------

    def perform_window_action(self, label: str, action: str) -> bool:
        """Close or activate the first VSCode window whose caption contains
        `label` as a token. Returns True if the KWin script emitted the
        success marker, False otherwise (no match, tooling missing, error)."""
        if action not in (ACTION_CLOSE, ACTION_ACTIVATE):
            raise ValueError(f"unsupported action: {action!r}")
        if not self._kwin_available():
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

    def _kwin_available(self) -> bool:
        return bool(shutil.which(self.qdbus_cmd) and shutil.which("journalctl"))
