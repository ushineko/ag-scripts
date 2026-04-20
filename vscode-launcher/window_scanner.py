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
from typing import Iterable

SCRIPT_NAME = "vscode-launcher-scanner"
ACTION_SCRIPT_NAME = "vscode-launcher-action"
LOG_PREFIX = "VSCL_CAPTIONS:"
ACTION_LOG_PREFIX = "VSCL_ACTION_OK:"

ACTION_CLOSE = "close"
ACTION_ACTIVATE = "activate"

KWIN_ENUMERATE_SCRIPT = """
(function() {
    var windows = workspace.windowList();
    var captions = [];
    for (var i = 0; i < windows.length; i++) {
        var w = windows[i];
        if (w.resourceClass !== "code") continue;
        if (w.skipTaskbar || w.specialWindow) continue;
        captions.push(w.caption);
    }
    console.log("%s" + JSON.stringify(captions));
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


class WindowScanner:
    """Enumerate VSCode window captions via KWin scripting."""

    def __init__(
        self,
        qdbus_cmd: str = "qdbus6",
        kwin_journal_unit: str = "plasma-kwin_wayland",
    ) -> None:
        self.qdbus_cmd = qdbus_cmd
        self.kwin_journal_unit = kwin_journal_unit

    def available(self) -> bool:
        return bool(shutil.which(self.qdbus_cmd) and shutil.which("journalctl"))

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

    def list_vscode_captions(self) -> list[str] | None:
        """Return list of VSCode window captions, or None if the scan failed.

        None signals "can't tell" — callers should treat this as "no running
        state is known" rather than "no VSCode windows are open".
        """
        if not self.available():
            return None

        script_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".js", prefix=f"{SCRIPT_NAME}-", delete=False
            ) as f:
                f.write(KWIN_ENUMERATE_SCRIPT)
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

            return parse_captions_from_journal(log.stdout)
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


def action_succeeded(journal_text: str) -> bool:
    """Return True if any `VSCL_ACTION_OK:` marker appears in the recent log."""
    if not journal_text:
        return False
    for line in journal_text.splitlines():
        if ACTION_LOG_PREFIX in line:
            return True
    return False


def parse_captions_from_journal(journal_text: str) -> list[str] | None:
    """Pull the most recent `VSCL_CAPTIONS:[...]` payload from journalctl output.

    Returns None if no line matches or if the JSON payload is malformed.
    """
    if not journal_text:
        return None
    # Scan from the end so we pick up the most recent run.
    for line in reversed(journal_text.splitlines()):
        idx = line.find(LOG_PREFIX)
        if idx < 0:
            continue
        payload = line[idx + len(LOG_PREFIX):].strip()
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, list):
            return [str(c) for c in parsed]
    return None
