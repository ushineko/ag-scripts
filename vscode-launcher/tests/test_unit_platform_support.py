"""Unit tests for platform_support path/API resolution.

These exercise the platform-branching helpers by monkeypatching the
module-level IS_LINUX / IS_MACOS / IS_WINDOWS flags (the functions read
them as globals at call time) and the HOME env (Path.home() honors $HOME
on POSIX). They assert the *shape* of the resolved paths rather than
asserting against the host's real platform, so the suite is meaningful no
matter where CI runs it.
"""

import os
import sys

import pytest

import platform_support as ps


@pytest.fixture
def as_macos(monkeypatch):
    monkeypatch.setattr(ps, "IS_LINUX", False)
    monkeypatch.setattr(ps, "IS_MACOS", True)
    monkeypatch.setattr(ps, "IS_WINDOWS", False)


@pytest.fixture
def as_linux(monkeypatch):
    monkeypatch.setattr(ps, "IS_LINUX", True)
    monkeypatch.setattr(ps, "IS_MACOS", False)
    monkeypatch.setattr(ps, "IS_WINDOWS", False)


@pytest.fixture
def as_windows(monkeypatch):
    monkeypatch.setattr(ps, "IS_LINUX", False)
    monkeypatch.setattr(ps, "IS_MACOS", False)
    monkeypatch.setattr(ps, "IS_WINDOWS", True)


@pytest.fixture
def fake_home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    return tmp_path


# ---------------------------------------------------------------------------
# vscode_state_db_paths
# ---------------------------------------------------------------------------


def test_state_db_paths_macos(as_macos, fake_home):
    paths = ps.vscode_state_db_paths()
    # Shared application storage first, then per-profile globalStorage under
    # ~/Library/Application Support/Code.
    assert paths[0] == fake_home / ".vscode-shared/sharedStorage/state.vscdb"
    assert (
        paths[1]
        == fake_home
        / "Library/Application Support/Code/User/globalStorage/state.vscdb"
    )
    # No Linux ~/.config/Code path leaks into the macOS list.
    assert not any(".config/Code" in str(p) for p in paths)


def test_state_db_paths_linux(as_linux, fake_home):
    paths = ps.vscode_state_db_paths()
    assert paths[0] == fake_home / ".vscode-shared/sharedStorage/state.vscdb"
    assert (
        paths[1]
        == fake_home / ".config/Code/User/globalStorage/state.vscdb"
    )
    assert not any("Application Support" in str(p) for p in paths)


def test_state_db_paths_windows(as_windows, fake_home, monkeypatch):
    monkeypatch.setenv("APPDATA", str(fake_home / "AppData/Roaming"))
    paths = ps.vscode_state_db_paths()
    assert paths[0] == fake_home / ".vscode-shared/sharedStorage/state.vscdb"
    assert any("Roaming" in str(p) and "Code" in str(p) for p in paths)


# ---------------------------------------------------------------------------
# vscode_ipc_socket_candidates (macOS)
# ---------------------------------------------------------------------------


def test_ipc_sockets_macos_sorted_by_mtime(as_macos, fake_home):
    code_dir = fake_home / "Library/Application Support/Code"
    code_dir.mkdir(parents=True)
    older = code_dir / "1.11-main.sock"
    newer = code_dir / "1.12-main.sock"
    decoy = code_dir / "vscode-git-abc.sock"  # not a *-main.sock
    for f in (older, newer, decoy):
        f.touch()
    # Make `newer` genuinely newer so the mtime sort is deterministic.
    os.utime(older, (1_000_000, 1_000_000))
    os.utime(newer, (2_000_000, 2_000_000))

    candidates = ps.vscode_ipc_socket_candidates()

    assert decoy not in candidates
    assert candidates == [newer, older]


def test_ipc_sockets_macos_missing_dir(as_macos, fake_home):
    # No "Application Support/Code" directory at all -> empty, not a crash.
    assert ps.vscode_ipc_socket_candidates() == []


# ---------------------------------------------------------------------------
# process_start_time (macOS / psutil)
# ---------------------------------------------------------------------------


def test_process_start_time_macos_current_process(as_macos):
    pytest.importorskip("psutil")
    ts = ps.process_start_time(os.getpid())
    assert ts is not None
    assert ts > 0


def test_process_start_time_macos_bad_pid(as_macos):
    pytest.importorskip("psutil")
    # A pid that cannot exist -> None, never an exception.
    assert ps.process_start_time(2**31 - 1) is None


def test_process_start_time_macos_psutil_absent(as_macos, monkeypatch):
    # Simulate psutil not being installed: a None entry in sys.modules makes
    # `import psutil` raise ImportError. The helper must degrade to None.
    monkeypatch.setitem(sys.modules, "psutil", None)
    assert ps.process_start_time(os.getpid()) is None


# ---------------------------------------------------------------------------
# launcher_config_dir
# ---------------------------------------------------------------------------


def test_launcher_config_dir_macos_uses_xdg(as_macos, fake_home):
    # macOS shares the XDG-style path with Linux (stable, no branch needed).
    assert ps.launcher_config_dir() == fake_home / ".config/vscode-launcher"
