"""Subprocess wrapper around display-mirror-toggle.sh.

The shell script is the canonical implementation of the kscreen-doctor
call sequence; the tray just delegates. Keeping logic in one place
means the .sh tests still cover the engine.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("display_mirror_tray.engine")


def _default_script_path() -> Path:
    """Locate display-mirror-toggle.sh relative to this module.

    Layout: ag-scripts/display-mirror-toggle/{display-mirror-toggle.sh,
    display_mirror_tray/engine.py}. Walking one directory up lands on
    the script. Falls back to PATH lookup so an installed symlink
    works if the package is ever imported from elsewhere.
    """
    here = Path(__file__).resolve().parent.parent
    candidate = here / "display-mirror-toggle.sh"
    if candidate.exists():
        return candidate
    on_path = shutil.which("display-mirror-toggle")
    if on_path:
        return Path(on_path)
    return candidate  # let the caller's error surface


@dataclass(frozen=True)
class MirrorStatus:
    active: bool
    source_state: str       # "enabled" | "disabled" | "absent"
    replica_state: str      # "enabled" | "disabled" | "absent"
    replica_repl: str       # "0" or the source output's numeric id


class MirrorEngine:
    """Run display-mirror-toggle.sh and parse its output."""

    def __init__(self, source: str, replica: str,
                 script_path: Path | None = None) -> None:
        self.source = source
        self.replica = replica
        self.script_path = script_path or _default_script_path()

    def _run(self, *args: str, capture: bool = True
             ) -> subprocess.CompletedProcess[str]:
        cmd = [str(self.script_path),
               "--source", self.source,
               "--replica", self.replica,
               *args]
        env = dict(os.environ)
        # Avoid color escape codes leaking through when we parse output.
        env.setdefault("NO_COLOR", "1")
        return subprocess.run(
            cmd, check=False, capture_output=capture, text=True, env=env
        )

    def status(self) -> MirrorStatus:
        """Parse `--status` output. Falls back to inactive on error so
        the tray UI degrades gracefully instead of crashing the icon."""
        try:
            cp = self._run("--status")
        except FileNotFoundError as e:
            logger.error(f"Engine script not found: {e}")
            return MirrorStatus(False, "absent", "absent", "0")

        if cp.returncode != 0:
            logger.warning(
                f"display-mirror-toggle --status failed (rc={cp.returncode}): "
                f"{cp.stderr.strip()}"
            )
            return MirrorStatus(False, "absent", "absent", "0")

        active = False
        source_state = "absent"
        replica_state = "absent"
        replica_repl = "0"
        for raw in cp.stdout.splitlines():
            line = raw.strip()
            if line.startswith("Source:"):
                if "(enabled)" in line:
                    source_state = "enabled"
                elif "(disabled)" in line:
                    source_state = "disabled"
                elif "(absent)" in line:
                    source_state = "absent"
            elif line.startswith("Replica:"):
                if "(absent)" in line:
                    replica_state = "absent"
                elif "(enabled" in line:
                    replica_state = "enabled"
                elif "(disabled" in line:
                    replica_state = "disabled"
                if "mirroring output " in line:
                    try:
                        replica_repl = line.split("mirroring output ", 1)[1] \
                            .rstrip(")").strip()
                    except IndexError:
                        replica_repl = "0"
            elif line.startswith("State:"):
                active = "mirror active" in line
        return MirrorStatus(active, source_state, replica_state, replica_repl)

    def enable(self) -> tuple[bool, str]:
        cp = self._run("--enable", "--quiet")
        return cp.returncode == 0, (cp.stderr or cp.stdout).strip()

    def disable(self) -> tuple[bool, str]:
        cp = self._run("--disable", "--quiet")
        return cp.returncode == 0, (cp.stderr or cp.stdout).strip()

    def toggle(self) -> tuple[bool, str]:
        cp = self._run("--quiet")
        return cp.returncode == 0, (cp.stderr or cp.stdout).strip()
