"""Tests for the MirrorEngine subprocess wrapper.

These don't run kscreen-doctor — they substitute a fake `script_path`
that prints canned output, so the tests work on any host.
"""

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from display_mirror_tray.engine import MirrorEngine


def _write_fake_engine(path: Path, *, stdout: str = "", rc: int = 0) -> Path:
    """Write a bash stub that mimics display-mirror-toggle.sh's stdout
    for whichever flag the engine invokes."""
    script = f"""#!/usr/bin/env bash
cat <<'EOF'
{stdout}
EOF
exit {rc}
"""
    path.write_text(script)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return path


def test_status_parses_active(tmp_path: Path) -> None:
    fake = _write_fake_engine(
        tmp_path / "engine.sh",
        stdout=(
            "Display Mirror Toggle v1.0.0\n"
            "Source:  HDMI-A-1 (enabled)\n"
            "Replica: DP-3 (mirroring output 5)\n"
            "State:   mirror active"
        ),
    )
    engine = MirrorEngine("HDMI-A-1", "DP-3", script_path=fake)
    status = engine.status()
    assert status.active is True
    assert status.source_state == "enabled"
    assert status.replica_repl == "5"


def test_status_parses_inactive(tmp_path: Path) -> None:
    fake = _write_fake_engine(
        tmp_path / "engine.sh",
        stdout=(
            "Display Mirror Toggle v1.0.0\n"
            "Source:  HDMI-A-1 (disabled)\n"
            "Replica: DP-3 (enabled, no mirror)\n"
            "State:   mirror off"
        ),
    )
    engine = MirrorEngine("HDMI-A-1", "DP-3", script_path=fake)
    status = engine.status()
    assert status.active is False
    assert status.source_state == "disabled"
    assert status.replica_repl == "0"


def test_status_handles_absent(tmp_path: Path) -> None:
    fake = _write_fake_engine(
        tmp_path / "engine.sh",
        stdout=(
            "Display Mirror Toggle v1.0.0\n"
            "Source:  HDMI-A-99 (absent)\n"
            "Replica: DP-99 (absent)\n"
            "State:   mirror off"
        ),
    )
    engine = MirrorEngine("HDMI-A-99", "DP-99", script_path=fake)
    status = engine.status()
    assert status.active is False
    assert status.source_state == "absent"
    assert status.replica_state == "absent"


def test_status_failure_returns_inactive(tmp_path: Path) -> None:
    fake = _write_fake_engine(tmp_path / "engine.sh", stdout="boom", rc=1)
    engine = MirrorEngine("HDMI-A-1", "DP-3", script_path=fake)
    status = engine.status()
    assert status.active is False


def test_missing_script_returns_inactive(tmp_path: Path) -> None:
    engine = MirrorEngine(
        "HDMI-A-1", "DP-3", script_path=tmp_path / "does-not-exist.sh"
    )
    status = engine.status()
    assert status.active is False


def test_toggle_passes_source_and_replica(tmp_path: Path) -> None:
    """The engine must forward the configured connectors to the script."""
    log_file = tmp_path / "args.log"
    fake = tmp_path / "engine.sh"
    fake.write_text(
        f"#!/usr/bin/env bash\necho \"$@\" > {log_file}\nexit 0\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    engine = MirrorEngine("HDMI-A-2", "DP-1", script_path=fake)
    ok, _ = engine.toggle()
    assert ok is True
    args = log_file.read_text()
    assert "--source HDMI-A-2" in args
    assert "--replica DP-1" in args
