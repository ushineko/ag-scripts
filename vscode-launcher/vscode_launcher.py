#!/usr/bin/env python3
"""
VSCode Launcher - bulk-launch VSCode workspaces from VSCode's own Recent list
with automatic window placement and tmux session switching.

Targets CachyOS / KDE Plasma 6 (Wayland). Delegates window placement to
`vscode-gather`. Tmux switching is performed by a zsh shell hook installed
into ~/.zshrc; the hook looks up the session by PWD via `vscl-tmux-lookup`,
so it works whether or not VSCode was already running when the workspace
was launched.

The workspace list is read live from VSCode's state.vscdb (SQLite). Per-path
tmux-session mappings and hide flags are persisted in this tool's own config.
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

from platform_support import (
    launcher_config_dir,
    process_start_time,
    vscode_state_db_path,
)
from window_scanner import (
    ACTION_ACTIVATE,
    ACTION_CLOSE,
    WindowScanner,
    running_labels,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

__version__ = "2.0"

CONFIG_DIR = launcher_config_dir()
CONFIG_FILE = CONFIG_DIR / "workspaces.json"
CONFIG_VERSION = 2

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "tmux_mappings": {},
    "hidden_paths": [],
    "window_geometry": {"x": 100, "y": 100, "w": 700, "h": 500},
}

GATHER_DELAY_MS = 1500
AUTO_REFRESH_INTERVAL_MS = 5000

# Enable with `VSCODE_LAUNCHER_DEBUG=1 vscode-launcher` for diagnostic logging
# of the auto-refresh cycle (timer ticks, scan launches, result processing).
_DEBUG = os.environ.get("VSCODE_LAUNCHER_DEBUG", "").lower() in ("1", "true", "yes")


def _dlog(msg: str) -> None:
    if _DEBUG:
        print(f"[vscl] {msg}", flush=True)

VSCODE_DB_PATH = vscode_state_db_path()  # None on unknown platforms
VSCODE_RECENTS_KEY = "history.recentlyOpenedPathsList"


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


@dataclass
class Workspace:
    label: str
    path: str
    tmux_session: str = ""
    is_workspace_file: bool = False
    is_running: bool = False
    # Unix timestamp (seconds since epoch) when the VSCode window backing this
    # workspace was launched. Populated from `platform_support.process_start_time`
    # when the scan reports this workspace as running. None for non-running rows
    # or when pid lookup fails.
    launched_at: float | None = None


def _normalize_scan_result(result: list) -> list[dict]:
    """Accept either v1.8 entries `[{c, p}, ...]` or legacy captions
    `["caption", ...]`. Always returns the entries shape."""
    out: list[dict] = []
    for item in result:
        if isinstance(item, dict) and "c" in item:
            out.append(item)
        elif isinstance(item, str):
            out.append({"c": item, "p": None})
    return out


def format_relative_time(ts: float | None, now: float | None = None) -> str:
    """Short relative time string like '5m ago', '2h ago', '3d ago'.
    Returns an em-dash for None inputs (non-running rows)."""
    if ts is None:
        return "—"
    reference = now if now is not None else time.time()
    delta = reference - ts
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta // 60)}m ago"
    if delta < 86400:
        return f"{int(delta // 3600)}h ago"
    return f"{int(delta // 86400)}d ago"


# ---------------------------------------------------------------------------
# VSCode recents reader
# ---------------------------------------------------------------------------


def uri_to_path(uri: str) -> str:
    """Convert a file:// URI to a local path. Returns '' for non-file schemes."""
    if not uri:
        return ""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        return ""
    return unquote(parsed.path)


def label_for_path(path: str, is_workspace_file: bool) -> str:
    p = Path(path)
    if is_workspace_file:
        return f"{p.stem} (Workspace)"
    return p.name or path


class VSCodeRecentsReader:
    """Reads VSCode's recently-opened workspaces from its SQLite state DB.

    The DB may be in use by a running VSCode process; we open it read-only
    (uri=True, mode=ro) to avoid locking issues.
    """

    def __init__(self, db_path: Path | None = VSCODE_DB_PATH) -> None:
        self.db_path = db_path

    def read_recents(self) -> list[Workspace]:
        if self.db_path is None or not self.db_path.exists():
            return []
        try:
            uri = f"file:{self.db_path}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            try:
                cur = conn.cursor()
                cur.execute(
                    "SELECT value FROM ItemTable WHERE key = ?",
                    (VSCODE_RECENTS_KEY,),
                )
                row = cur.fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return []
        if not row or not row[0]:
            return []
        try:
            payload = json.loads(row[0])
        except json.JSONDecodeError:
            return []
        entries = payload.get("entries", []) or []
        return [w for w in (self._normalize_entry(e) for e in entries) if w is not None]

    @staticmethod
    def _normalize_entry(entry: dict[str, Any]) -> Workspace | None:
        if not isinstance(entry, dict):
            return None
        if "folderUri" in entry:
            path = uri_to_path(entry["folderUri"])
            if not path:
                return None
            return Workspace(
                label=label_for_path(path, is_workspace_file=False),
                path=path,
                is_workspace_file=False,
            )
        if "workspace" in entry and isinstance(entry["workspace"], dict):
            config_path = uri_to_path(entry["workspace"].get("configPath", ""))
            if not config_path:
                return None
            return Workspace(
                label=label_for_path(config_path, is_workspace_file=True),
                path=config_path,
                is_workspace_file=True,
            )
        return None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class ConfigManager:
    """Load/save the v2 config file. Migrates v1 -> v2 on first load."""

    def __init__(self, config_file: Path = CONFIG_FILE) -> None:
        self.config_file = config_file
        self._raw: dict[str, Any] = {}

    def load(self) -> dict[str, Any]:
        if not self.config_file.exists():
            self._raw = self._default()
            return self._raw
        try:
            with self.config_file.open("r", encoding="utf-8") as f:
                self._raw = json.load(f)
        except (json.JSONDecodeError, OSError):
            self._raw = self._default()
            return self._raw

        version = self._raw.get("version")
        if version == 1:
            self._raw = self._migrate_v1_to_v2(self._raw)
        elif version != CONFIG_VERSION:
            # Unknown / future version: treat as default but keep raw for round-trip
            self._raw.setdefault("tmux_mappings", {})
            self._raw.setdefault("hidden_paths", [])
            self._raw.setdefault(
                "window_geometry", dict(DEFAULT_CONFIG["window_geometry"])
            )
        else:
            self._raw.setdefault("tmux_mappings", {})
            self._raw.setdefault("hidden_paths", [])
            self._raw.setdefault(
                "window_geometry", dict(DEFAULT_CONFIG["window_geometry"])
            )
        return self._raw

    def save(
        self,
        tmux_mappings: dict[str, str],
        hidden_paths: list[str],
        window_geometry: dict[str, int],
    ) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(self._raw) if self._raw else {}
        payload["version"] = CONFIG_VERSION
        payload["tmux_mappings"] = dict(tmux_mappings)
        payload["hidden_paths"] = list(hidden_paths)
        payload["window_geometry"] = dict(window_geometry)
        # Drop v1-only key if present
        payload.pop("workspaces", None)
        tmp = self.config_file.with_suffix(".json.tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        tmp.replace(self.config_file)

    @staticmethod
    def _default() -> dict[str, Any]:
        d = dict(DEFAULT_CONFIG)
        d["tmux_mappings"] = {}
        d["hidden_paths"] = []
        d["window_geometry"] = dict(DEFAULT_CONFIG["window_geometry"])
        return d

    @staticmethod
    def _migrate_v1_to_v2(raw: dict[str, Any]) -> dict[str, Any]:
        """v1 stored a list of workspaces; extract path -> tmux_session mappings."""
        mappings: dict[str, str] = {}
        for entry in raw.get("workspaces", []) or []:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path", "").strip()
            session = entry.get("tmux_session", "").strip()
            if path and session:
                mappings[path] = session
        migrated = dict(raw)
        migrated["version"] = CONFIG_VERSION
        migrated["tmux_mappings"] = mappings
        migrated.setdefault("hidden_paths", [])
        migrated.setdefault(
            "window_geometry", dict(DEFAULT_CONFIG["window_geometry"])
        )
        migrated.pop("workspaces", None)
        return migrated


# ---------------------------------------------------------------------------
# Tmux
# ---------------------------------------------------------------------------


class TmuxClient:
    """Read-only wrapper around `tmux list-sessions`. Never creates or kills sessions."""

    @staticmethod
    def list_sessions() -> list[str]:
        if not shutil.which("tmux"):
            return []
        try:
            result = subprocess.run(
                ["tmux", "list-sessions", "-F", "#S"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Launcher
# ---------------------------------------------------------------------------


def build_code_command(workspace_path: str) -> list[str]:
    return ["code", "--new-window", workspace_path]


class Launcher:
    def __init__(self, gather_cmd: str = "vscode-gather") -> None:
        self.gather_cmd = gather_cmd

    def launch_workspace(self, workspace: Workspace) -> subprocess.Popen[bytes] | None:
        if not shutil.which("code"):
            return None
        cmd = build_code_command(workspace.path)
        return subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    def run_gather(self) -> bool:
        if not shutil.which(self.gather_cmd):
            return False
        try:
            subprocess.run(
                [self.gather_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
            return True
        except (OSError, subprocess.TimeoutExpired):
            return False


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class TmuxSessionDialog(QDialog):
    """Dialog for selecting a tmux session name for a workspace path."""

    def __init__(
        self,
        parent: QWidget | None = None,
        current_session: str = "",
        workspace_label: str = "",
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set Tmux Session")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        if workspace_label:
            layout.addWidget(QLabel(f"<b>{workspace_label}</b>"))

        layout.addWidget(QLabel("Tmux session:"))
        row = QHBoxLayout()
        self.combo = QComboBox()
        self.combo.setEditable(True)
        self._refresh_sessions()
        if current_session:
            idx = self.combo.findText(current_session)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
            else:
                self.combo.setEditText(current_session)
        row.addWidget(self.combo)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_sessions)
        row.addWidget(refresh_btn)
        layout.addLayout(row)

        hint = QLabel(
            "Leave blank to clear the mapping. Session names are free-form — "
            "the launcher never creates or kills tmux sessions."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("QLabel { color: gray; }")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _refresh_sessions(self) -> None:
        current = self.combo.currentText() if self.combo.count() else ""
        self.combo.clear()
        sessions = TmuxClient.list_sessions()
        if sessions:
            self.combo.addItems(sessions)
        if current:
            idx = self.combo.findText(current)
            if idx >= 0:
                self.combo.setCurrentIndex(idx)
            else:
                self.combo.setEditText(current)

    def selected_session(self) -> str:
        return self.combo.currentText().strip()


class WorkspaceTableWidget(QTableWidget):
    """Grid of workspaces sourced from VSCode recents.

    Columns (no header row — personal tool, column purposes are obvious):
      0: Checkbox (disabled for running rows — running workspaces can't be
         bulk-re-launched; user uses [Activate] / [Stop] buttons instead)
      1: Workspace — label (bold) + path (small, 2nd line)
      2: Status — "● running" (green) or blank
      3: Launched — relative time since the VSCode window started (e.g.
         "5m ago"), em-dash for non-running rows
      4: Tmux session name (or em-dash)
      5: Actions — [Activate][Stop] for running, [Start] for non-running
    """

    COL_CHECK = 0
    COL_WORKSPACE = 1
    COL_STATUS = 2
    COL_LAUNCHED = 3
    COL_TMUX = 4
    COL_ACTIONS = 5

    # Emitted with the workspace path when a per-row button is clicked.
    start_requested = pyqtSignal(str)
    stop_requested = pyqtSignal(str)
    activate_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 6, parent)
        self.horizontalHeader().setVisible(False)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        # Only take focus when the user clicks a row — otherwise Qt draws a
        # "current item" indicator on the first row on startup.
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)

        header = self.horizontalHeader()
        header.setSectionResizeMode(self.COL_CHECK, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_CHECK, 40)
        header.setSectionResizeMode(self.COL_WORKSPACE, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(self.COL_STATUS, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_STATUS, 90)
        header.setSectionResizeMode(self.COL_LAUNCHED, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_LAUNCHED, 100)
        header.setSectionResizeMode(self.COL_TMUX, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_TMUX, 160)
        header.setSectionResizeMode(self.COL_ACTIONS, QHeaderView.ResizeMode.Fixed)
        self.setColumnWidth(self.COL_ACTIONS, 180)

        self._path_by_row: dict[int, str] = {}

    # --- population ---

    def clear_workspaces(self) -> None:
        self.setRowCount(0)
        self._path_by_row.clear()

    def add_workspace_row(self, workspace: Workspace) -> None:
        row = self.rowCount()
        self.insertRow(row)
        self.setRowHeight(row, 54)
        self._path_by_row[row] = workspace.path

        self.setCellWidget(row, self.COL_CHECK, self._build_checkbox_cell(workspace))
        self.setCellWidget(
            row, self.COL_WORKSPACE, self._build_workspace_cell(workspace)
        )
        self.setCellWidget(row, self.COL_STATUS, self._build_status_cell(workspace))
        self.setCellWidget(
            row, self.COL_LAUNCHED, self._build_launched_cell(workspace)
        )
        self.setCellWidget(row, self.COL_TMUX, self._build_tmux_cell(workspace))
        self.setCellWidget(row, self.COL_ACTIONS, self._build_actions_cell(workspace))

    @staticmethod
    def _build_checkbox_cell(workspace: Workspace) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        checkbox = QCheckBox()
        checkbox.setObjectName("select_checkbox")
        # Running workspaces can't be bulk-launched — checkbox disabled.
        # (Advanced: users who genuinely want to duplicate a window can use
        # the right-click "Launch" context-menu item.)
        if workspace.is_running:
            checkbox.setEnabled(False)
        layout.addWidget(checkbox)
        return container

    @staticmethod
    def _build_workspace_cell(workspace: Workspace) -> QWidget:
        label = QLabel(
            f"<b>{workspace.label}</b>"
            f"<br><small style='color:gray'>{workspace.path}</small>"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setContentsMargins(8, 0, 8, 0)
        return label

    @staticmethod
    def _build_status_cell(workspace: Workspace) -> QWidget:
        text = (
            "<span style='color:#4caf50'>● running</span>"
            if workspace.is_running
            else ""
        )
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    @staticmethod
    def _build_launched_cell(workspace: Workspace) -> QWidget:
        label = QLabel(
            format_relative_time(workspace.launched_at if workspace.is_running else None)
        )
        label.setContentsMargins(8, 0, 8, 0)
        label.setStyleSheet("QLabel { color: gray; }")
        return label

    def refresh_launched_cells(
        self, workspaces_by_path: dict[str, "Workspace"]
    ) -> None:
        """Rewrite only the Launched column for every row. Called on each
        auto-refresh tick so relative times ('5m ago' → '6m ago') stay
        current without rebuilding the whole table.

        `workspaces_by_path` must contain the current Workspace objects with
        up-to-date `launched_at` values."""
        for row in range(self.rowCount()):
            path = self._path_by_row.get(row)
            if path is None:
                continue
            ws = workspaces_by_path.get(path)
            if ws is None:
                continue
            self.setCellWidget(row, self.COL_LAUNCHED, self._build_launched_cell(ws))

    @staticmethod
    def _build_tmux_cell(workspace: Workspace) -> QWidget:
        label = QLabel(workspace.tmux_session or "—")
        label.setContentsMargins(8, 0, 8, 0)
        return label

    def _build_actions_cell(self, workspace: Workspace) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(4)

        path = workspace.path
        if workspace.is_running:
            btn_activate = QPushButton("Activate")
            btn_activate.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_activate.clicked.connect(
                lambda _=False, p=path: self.activate_requested.emit(p)
            )
            layout.addWidget(btn_activate)

            btn_stop = QPushButton("Stop")
            btn_stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_stop.clicked.connect(
                lambda _=False, p=path: self.stop_requested.emit(p)
            )
            layout.addWidget(btn_stop)
        else:
            btn_start = QPushButton("Start")
            btn_start.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            btn_start.clicked.connect(
                lambda _=False, p=path: self.start_requested.emit(p)
            )
            layout.addWidget(btn_start)

        return container

    # --- query helpers ---

    def path_at_row(self, row: int) -> str | None:
        return self._path_by_row.get(row)

    def checked_workspace_paths(self) -> list[str]:
        paths: list[str] = []
        for row in range(self.rowCount()):
            container = self.cellWidget(row, self.COL_CHECK)
            if container is None:
                continue
            cb = container.findChild(QCheckBox, "select_checkbox")
            if cb is not None and cb.isChecked():
                p = self._path_by_row.get(row)
                if p:
                    paths.append(p)
        return paths

    def all_workspace_paths(self) -> list[str]:
        return [
            self._path_by_row[row]
            for row in range(self.rowCount())
            if row in self._path_by_row
        ]


class MainWindow(QMainWindow):
    def __init__(
        self,
        config_manager: ConfigManager,
        launcher: Launcher,
        recents_reader: VSCodeRecentsReader,
        window_scanner: WindowScanner | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"VSCode Launcher v{__version__}")
        self.config_manager = config_manager
        self.launcher = launcher
        self.recents_reader = recents_reader
        self.window_scanner = window_scanner
        # v2.0 scanner is IPC-backed and sync (~3 ms). We just call
        # list_vscode_entries() directly every poll — no QProcess state
        # machine, no background thread, no signal wiring.
        self._auto_refresh_timer: QTimer | None = None
        # Per-path launch timestamps we record ourselves when the launcher
        # spawns `code --new-window`. Preferred source for the Launched
        # column — IPC gives us the real renderer PID, but /proc's starttime
        # on that PID can lag slightly behind the actual window open
        # (renderer is forked after the `code --new-window` IPC roundtrip).
        # Our own timestamp is closest to "moment the user clicked Start".
        self._launched_at_by_path: dict[str, float] = {}

        raw = self.config_manager.load()
        self.tmux_mappings: dict[str, str] = dict(raw.get("tmux_mappings", {}) or {})
        self.hidden_paths: set[str] = set(raw.get("hidden_paths", []) or [])
        geom = raw.get("window_geometry") or DEFAULT_CONFIG["window_geometry"]
        self.setGeometry(
            int(geom.get("x", 100)),
            int(geom.get("y", 100)),
            int(geom.get("w", 700)),
            int(geom.get("h", 500)),
        )

        self.workspaces: list[Workspace] = []
        self._build_ui()
        self._refresh()
        self._start_auto_refresh()

    def _start_auto_refresh(self) -> None:
        """Poll the window scanner on an interval so the running-state column
        updates without user interaction. No-ops if no scanner is configured."""
        if self.window_scanner is None:
            _dlog("auto-refresh disabled: no window_scanner configured")
            return
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self._trigger_background_scan)
        self._auto_refresh_timer.start(AUTO_REFRESH_INTERVAL_MS)
        _dlog(f"auto-refresh timer started at {AUTO_REFRESH_INTERVAL_MS} ms")

    def _trigger_background_scan(self) -> None:
        """Poll the IPC scanner synchronously (3 ms round-trip — no need
        for threads or async machinery). If any row's running state
        changed, re-read VSCode recents and rebuild the list so the
        running group re-sorts with fresh MRU. Otherwise refresh only the
        Launched column so its relative times tick forward."""
        if self.window_scanner is None:
            return
        if not self.isVisible():
            _dlog("tick: skipping, window not visible")
            return

        result = self.window_scanner.list_vscode_entries()
        if result is None:
            _dlog("tick: scan returned None (transient IPC failure)")
            return

        entries = _normalize_scan_result(result)
        captions = [e["c"] for e in entries]
        running = running_labels(captions, (w.label for w in self.workspaces))
        flips = sum(
            1 for ws in self.workspaces if ws.is_running != (ws.label in running)
        )
        if flips > 0:
            visible = self._load_visible_workspaces()
            self._apply_running_and_sort(visible, entries)
            self.workspaces = visible
            self._reload_list()
        else:
            # No-flip ticks: just refresh the Launched column so relative
            # times ('5m ago' → '6m ago') tick forward. launched_at is
            # already correct from the last flip (process start times don't
            # change while the process is alive).
            self.list_widget.refresh_launched_cells(
                {w.path: w for w in self.workspaces}
            )
        _dlog(
            f"tick: {len(entries)} entry(ies), running={sorted(running)}, "
            f"{flips} flip(s)"
            + (
                " (recents re-read + resorted)"
                if flips > 0
                else " (launched column refreshed)"
            )
        )

    def _build_ui(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)
        self.setCentralWidget(central)

        toolbar = QToolBar("Actions")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        act_launch_selected = QAction("Launch Selected", self)
        act_launch_selected.triggered.connect(self._launch_selected)
        toolbar.addAction(act_launch_selected)

        act_launch_all = QAction("Launch All", self)
        act_launch_all.triggered.connect(self._launch_all)
        toolbar.addAction(act_launch_all)

        toolbar.addSeparator()

        act_refresh = QAction("Refresh", self)
        act_refresh.triggered.connect(self._refresh)
        toolbar.addAction(act_refresh)

        act_set_tmux = QAction("Set Tmux Session…", self)
        act_set_tmux.triggered.connect(self._set_tmux_for_current)
        toolbar.addAction(act_set_tmux)

        toolbar.addSeparator()

        act_hide = QAction("Hide", self)
        act_hide.triggered.connect(self._hide_current)
        toolbar.addAction(act_hide)

        act_unhide_all = QAction("Unhide All", self)
        act_unhide_all.triggered.connect(self._unhide_all)
        toolbar.addAction(act_unhide_all)

        self.empty_label = QLabel()
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        self.empty_label.setStyleSheet("QLabel { color: gray; padding: 40px; }")
        layout.addWidget(self.empty_label)

        self.list_widget = WorkspaceTableWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.cellDoubleClicked.connect(self._on_cell_double_clicked)
        self.list_widget.start_requested.connect(self._on_start_requested)
        self.list_widget.stop_requested.connect(self._on_stop_requested)
        self.list_widget.activate_requested.connect(self._on_activate_requested)
        layout.addWidget(self.list_widget)

    def _refresh(self) -> None:
        """Re-read VSCode recents and rebuild the list."""
        self.workspaces = self._build_workspace_list()
        self._reload_list()

    def _load_visible_workspaces(self) -> list[Workspace]:
        """Read recents, apply hidden-path filter and tmux mappings. Running
        state is *not* marked here — callers layer that on via
        `_apply_running_and_sort` using either sync or async scan data."""
        recents = self.recents_reader.read_recents()
        visible: list[Workspace] = []
        for ws in recents:
            if ws.path in self.hidden_paths:
                continue
            ws.tmux_session = self.tmux_mappings.get(ws.path, "")
            visible.append(ws)
        return visible

    @staticmethod
    def _pid_by_label(
        workspaces: list[Workspace], entries: list[dict]
    ) -> dict[str, int | None]:
        """For each workspace label, find the pid of the first scan entry
        whose caption contains that label as a ` - `-split token."""
        result: dict[str, int | None] = {}
        for entry in entries:
            parts = entry["c"].split(" - ")
            for ws in workspaces:
                if ws.label not in result and ws.label in parts:
                    result[ws.label] = entry.get("p")
                    break
        return result

    def _apply_running_and_sort(
        self, workspaces: list[Workspace], entries: list[dict]
    ) -> None:
        """Mark each workspace's is_running + launched_at based on scan
        `entries` (list of {"c": caption, "p": pid}) and sort running-first.
        Stable sort → MRU order preserved within each group, which —
        combined with a fresh read of VSCode recents — makes a just-launched
        workspace bubble to the top of the running group.

        `launched_at` precedence:
          1. An in-memory timestamp we recorded when the launcher itself
             spawned `code --new-window` (exact, recorded at click time)
          2. `/proc`-derived start time for the window's renderer PID
             (accurate per window since the IPC scanner now surfaces real
             per-window renderer PIDs, not just the main Electron PID)
          3. None (em-dash in the UI) if neither is available
        """
        captions = [e["c"] for e in entries]
        pid_by_label = self._pid_by_label(workspaces, entries)
        running = running_labels(captions, (w.label for w in workspaces))
        for ws in workspaces:
            ws.is_running = ws.label in running
            if ws.is_running:
                tracked = self._launched_at_by_path.get(ws.path)
                if tracked is not None:
                    ws.launched_at = tracked
                else:
                    pid = pid_by_label.get(ws.label)
                    ws.launched_at = (
                        process_start_time(pid)
                        if isinstance(pid, int)
                        else None
                    )
            else:
                ws.launched_at = None
                # A workspace that's no longer running invalidates our tracked
                # timestamp — if it gets relaunched later, we'll record afresh.
                self._launched_at_by_path.pop(ws.path, None)
        workspaces.sort(key=lambda w: 0 if w.is_running else 1)

    def _build_workspace_list(self) -> list[Workspace]:
        """Called by manual Refresh and by __init__. Uses the sync scan path
        so the initial populate is deterministic (no event loop dance)."""
        visible = self._load_visible_workspaces()
        if self.window_scanner is not None and hasattr(
            self.window_scanner, "list_vscode_entries"
        ):
            entries = self.window_scanner.list_vscode_entries()
            if entries is not None:
                self._apply_running_and_sort(visible, entries)
        elif self.window_scanner is not None:
            # Test fakes that only implement the legacy captions-only API
            captions = self.window_scanner.list_vscode_captions()
            if captions is not None:
                self._apply_running_and_sort(
                    visible, [{"c": c, "p": None} for c in captions]
                )
        return visible

    def _reload_list(self) -> None:
        self.list_widget.clear_workspaces()
        for w in self.workspaces:
            self.list_widget.add_workspace_row(w)
        # Start with no current/selected row so Qt doesn't show the (subtle)
        # "current item" indicator on the first row by default. A row only
        # becomes highlighted when the user actively clicks one.
        self.list_widget.setCurrentCell(-1, -1)
        self.list_widget.clearSelection()

        if self.workspaces:
            self.empty_label.setVisible(False)
            self.list_widget.setVisible(True)
        else:
            self.list_widget.setVisible(False)
            db = self.recents_reader.db_path
            if db is None or not db.exists():
                where = str(db) if db is not None else "(path unknown for this platform)"
                self.empty_label.setText(
                    "VSCode state database not found at\n"
                    f"{where}\n\n"
                    "Install VSCode and open a workspace to populate this list."
                )
            elif self.hidden_paths:
                self.empty_label.setText(
                    "All VSCode recents are hidden.\n\n"
                    "Click \"Unhide All\" to show them."
                )
            else:
                self.empty_label.setText(
                    "No recent workspaces found in VSCode.\n\n"
                    "Open a folder or .code-workspace file in VSCode, "
                    "then click \"Refresh\"."
                )
            self.empty_label.setVisible(True)

    def _current_workspace(self) -> Workspace | None:
        row = self.list_widget.currentRow()
        if row < 0:
            return None
        path = self.list_widget.path_at_row(row)
        if path is None:
            return None
        return self._find_workspace_by_path(path)

    def _on_cell_double_clicked(self, _row: int, _col: int) -> None:
        self._set_tmux_for_current()

    def _show_context_menu(self, pos: Any) -> None:
        row = self.list_widget.rowAt(pos.y())
        if row < 0:
            return
        self.list_widget.selectRow(row)
        menu = QMenu(self)
        # Context-menu Launch is the power-user escape hatch: it forces a
        # launch even for running workspaces, producing a duplicate window.
        menu.addAction("Launch", lambda: self._launch_current(allow_running=True))
        menu.addAction("Set Tmux Session…", self._set_tmux_for_current)
        menu.addSeparator()
        menu.addAction("Hide", self._hide_current)
        menu.exec(self.list_widget.mapToGlobal(pos))

    def _set_tmux_for_current(self) -> None:
        ws = self._current_workspace()
        if ws is None:
            return
        dialog = TmuxSessionDialog(
            self, current_session=ws.tmux_session, workspace_label=ws.label
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_session = dialog.selected_session()
            if new_session:
                self.tmux_mappings[ws.path] = new_session
            else:
                self.tmux_mappings.pop(ws.path, None)
            self._save()
            self._refresh()

    def _hide_current(self) -> None:
        ws = self._current_workspace()
        if ws is None:
            return
        self.hidden_paths.add(ws.path)
        self._save()
        self._refresh()

    def _unhide_all(self) -> None:
        if not self.hidden_paths:
            return
        self.hidden_paths.clear()
        self._save()
        self._refresh()

    def _launch_current(self, allow_running: bool = True) -> None:
        ws = self._current_workspace()
        if ws is None:
            return
        self._launch_paths([ws.path], allow_running=allow_running)

    def _on_start_requested(self, path: str) -> None:
        # Per-row Start button only appears on non-running rows, so skipping
        # running would be a no-op. Pass allow_running=True to be explicit
        # that this intentional single-row start should always proceed.
        self._launch_paths([path], allow_running=True)

    def _on_stop_requested(self, path: str) -> None:
        ws = self._find_workspace_by_path(path)
        if ws is None or self.window_scanner is None:
            return
        # VSCode's own "unsaved changes?" dialog runs inside KWin's async action;
        # we don't auto-refresh because the close may not complete immediately.
        self.window_scanner.perform_window_action(ws.label, ACTION_CLOSE)

    def _on_activate_requested(self, path: str) -> None:
        ws = self._find_workspace_by_path(path)
        if ws is None or self.window_scanner is None:
            return
        self.window_scanner.perform_window_action(ws.label, ACTION_ACTIVATE)

    def _find_workspace_by_path(self, path: str) -> Workspace | None:
        for w in self.workspaces:
            if w.path == path:
                return w
        return None

    def _launch_selected(self) -> None:
        paths = self.list_widget.checked_workspace_paths()
        if not paths:
            QMessageBox.information(
                self,
                "No selection",
                "Tick the checkboxes next to the workspaces you want to launch.",
            )
            return
        self._launch_paths(paths)

    def _launch_all(self) -> None:
        paths = self.list_widget.all_workspace_paths()
        if not paths:
            return
        self._launch_paths(paths)

    def _launch_paths(self, paths: list[str], allow_running: bool = False) -> None:
        if not shutil.which("code"):
            QMessageBox.critical(
                self,
                "VSCode not found",
                "The `code` command is not on PATH. Install VSCode or its CLI shim.",
            )
            return

        by_path = {w.path: w for w in self.workspaces}
        targets = [by_path[p] for p in paths if p in by_path]
        if not allow_running:
            # Bulk launch paths (Launch Selected / Launch All) silently skip
            # running workspaces — they can't be re-launched into duplicate
            # windows without the user explicitly using the context-menu
            # "Launch" action. The checkbox is disabled on running rows as
            # the primary signal, so this branch normally filters nothing.
            targets = [w for w in targets if not w.is_running]

        launched = 0
        for ws in targets:
            proc = self.launcher.launch_workspace(ws)
            if proc is not None:
                # Record our own launch timestamp for this path — the auto-
                # refresh uses this in preference to /proc (which can only
                # give us "when VSCode itself started", not per-window).
                self._launched_at_by_path[ws.path] = time.time()
                launched += 1
        if launched > 0:
            QTimer.singleShot(GATHER_DELAY_MS, self._run_gather)

    def _run_gather(self) -> None:
        ok = self.launcher.run_gather()
        if not ok:
            QMessageBox.warning(
                self,
                "vscode-gather not available",
                "Could not run `vscode-gather`. New VSCode windows will not be "
                "auto-placed on the primary monitor. Install the sibling "
                "vscode-gather tool to enable this.",
            )

    def _save(self) -> None:
        geom = self.geometry()
        self.config_manager.save(
            tmux_mappings=self.tmux_mappings,
            hidden_paths=sorted(self.hidden_paths),
            window_geometry={
                "x": geom.x(),
                "y": geom.y(),
                "w": geom.width(),
                "h": geom.height(),
            },
        )

    def closeEvent(self, event: Any) -> None:
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()
        # No thread to wait on — any in-flight QProcess will be cleaned up
        # by the scanner's parent-child tree when the app exits.
        self._save()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _resolve_app_icon() -> QIcon:
    """Prefer the installed theme icon; fall back to the bundled SVG next to
    this file so the app shows the right icon even when run from the source
    checkout before install.sh has copied it into hicolor."""
    themed = QIcon.fromTheme("vscode-launcher")
    if not themed.isNull():
        return themed
    bundled = Path(__file__).resolve().parent / "vscode-launcher.svg"
    if bundled.is_file():
        return QIcon(str(bundled))
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("vscode-launcher")
    app.setDesktopFileName("vscode-launcher")
    app.setWindowIcon(_resolve_app_icon())
    config = ConfigManager()
    launcher = Launcher()
    recents = VSCodeRecentsReader()
    scanner = WindowScanner()
    window = MainWindow(config, launcher, recents, window_scanner=scanner)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
