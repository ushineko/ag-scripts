"""Activate (raise + focus) and maximize a window on KDE Plasma 6 / Wayland.

Wayland forbids xdotool/wmctrl-style manipulation, so window control goes through
KWin's JavaScript scripting API over D-Bus (the mechanism vscode-gather uses):
load a temp script, run it, unload it. Success is confirmed by a post-condition
check (does the active window now own the target PID?) rather than journal
scraping, which is racy.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time

from herdr_api import _resolve_bin
from session_windows import active_window_pid

QDBUS_BIN = _resolve_bin("qdbus6", extra=("/usr/lib/qt6/bin/qdbus",))

# Plasma 6 KWin scripting: find the window owning target_pid, focus + maximize it.
_KWIN_SCRIPT = """\
(function() {
    var target = %(pid)d;
    var wins = workspace.windowList();
    for (var i = 0; i < wins.length; i++) {
        var w = wins[i];
        if (w.pid !== target) continue;
        if (w.skipTaskbar || w.specialWindow) continue;
        workspace.activeWindow = w;
        w.setMaximize(true, true);
        return;
    }
})();
"""


def _qdbus(*args: str, timeout: float = 5.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [QDBUS_BIN, "org.kde.KWin", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, ""
    return proc.returncode == 0, proc.stdout.strip()


def activate_and_maximize(terminal_pid: int, *, settle: float = 0.6) -> bool:
    """Raise, focus, and maximize the window owned by `terminal_pid`.

    Returns True if the active window owns that PID afterward.
    """
    script = _KWIN_SCRIPT % {"pid": terminal_pid}
    plugin = "herdr-switcher-activate"
    fd, path = tempfile.mkstemp(prefix="herdr-switcher-", suffix=".js")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(script)

        ok, out = _qdbus("/Scripting", "org.kde.kwin.Scripting.loadScript", path, plugin)
        if not ok:
            return False
        try:
            script_id = int(out)
        except ValueError:
            return False

        run_ok, _ = _qdbus(
            f"/Scripting/Script{script_id}", "org.kde.kwin.Script.run"
        )
        # Best-effort unload regardless of run result.
        _qdbus("/Scripting", "org.kde.kwin.Scripting.unloadScript", plugin)
        if not run_ok:
            return False
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass

    # Confirm by post-condition: active window now owns target_pid.
    deadline = time.monotonic() + settle
    while time.monotonic() < deadline:
        if active_window_pid() == terminal_pid:
            return True
        time.sleep(0.05)
    return active_window_pid() == terminal_pid
