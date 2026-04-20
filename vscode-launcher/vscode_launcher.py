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
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction

from window_scanner import WindowScanner, running_labels
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

__version__ = "1.3"

CONFIG_DIR = Path.home() / ".config" / "vscode-launcher"
CONFIG_FILE = CONFIG_DIR / "workspaces.json"
CONFIG_VERSION = 2

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    "tmux_mappings": {},
    "hidden_paths": [],
    "window_geometry": {"x": 100, "y": 100, "w": 700, "h": 500},
}

GATHER_DELAY_MS = 1500

VSCODE_DB_PATH = (
    Path.home() / ".config" / "Code" / "User" / "globalStorage" / "state.vscdb"
)
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

    def __init__(self, db_path: Path = VSCODE_DB_PATH) -> None:
        self.db_path = db_path

    def read_recents(self) -> list[Workspace]:
        if not self.db_path.exists():
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


class WorkspaceListWidget(QListWidget):
    """Read-only list of workspaces sourced from VSCode recents."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def add_workspace_row(self, workspace: Workspace) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, workspace.path)
        self.addItem(item)
        widget = self._build_row_widget(workspace)
        item.setSizeHint(widget.sizeHint())
        self.setItemWidget(item, widget)

    def _build_row_widget(self, workspace: Workspace) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(6, 4, 6, 4)

        checkbox = QCheckBox()
        checkbox.setObjectName("select_checkbox")
        layout.addWidget(checkbox)

        tmux_display = workspace.tmux_session or "—"
        running_badge = (
            " <span style='color:#4caf50'>● running</span>"
            if workspace.is_running
            else ""
        )
        label = QLabel(
            f"<b>{workspace.label}</b>{running_badge}"
            f"<br><small>{workspace.path}</small>"
            f"<br><small>tmux: {tmux_display}</small>"
        )
        label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(label, stretch=1)

        return widget

    def checked_workspace_paths(self) -> list[str]:
        paths: list[str] = []
        for i in range(self.count()):
            item = self.item(i)
            w = self.itemWidget(item)
            if w is None:
                continue
            cb = w.findChild(QCheckBox, "select_checkbox")
            if cb is not None and cb.isChecked():
                paths.append(item.data(Qt.ItemDataRole.UserRole))
        return paths

    def all_workspace_paths(self) -> list[str]:
        return [
            self.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.count())
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

        self.list_widget = WorkspaceListWidget()
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._show_context_menu)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.list_widget)

    def _refresh(self) -> None:
        """Re-read VSCode recents and rebuild the list."""
        self.workspaces = self._build_workspace_list()
        self._reload_list()

    def _build_workspace_list(self) -> list[Workspace]:
        recents = self.recents_reader.read_recents()
        visible: list[Workspace] = []
        for ws in recents:
            if ws.path in self.hidden_paths:
                continue
            ws.tmux_session = self.tmux_mappings.get(ws.path, "")
            visible.append(ws)

        # Mark which workspaces are currently open and sort running-first.
        # VSCode's recents are returned in MRU order (most-recent-first); a
        # stable sort by `is_running` groups running workspaces to the top
        # while preserving MRU order within each group.
        # The scanner returns None when KWin/journalctl aren't available;
        # in that case we silently skip the running-state pass.
        if self.window_scanner is not None:
            captions = self.window_scanner.list_vscode_captions()
            if captions is not None:
                running = running_labels(captions, (w.label for w in visible))
                for ws in visible:
                    ws.is_running = ws.label in running
                visible.sort(key=lambda w: 0 if w.is_running else 1)

        return visible

    def _reload_list(self) -> None:
        self.list_widget.clear()
        for w in self.workspaces:
            self.list_widget.add_workspace_row(w)

        if self.workspaces:
            self.empty_label.setVisible(False)
            self.list_widget.setVisible(True)
        else:
            self.list_widget.setVisible(False)
            if not self.recents_reader.db_path.exists():
                self.empty_label.setText(
                    "VSCode state database not found at\n"
                    f"{self.recents_reader.db_path}\n\n"
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
        item = self.list_widget.currentItem()
        if item is None:
            return None
        path = item.data(Qt.ItemDataRole.UserRole)
        for w in self.workspaces:
            if w.path == path:
                return w
        return None

    def _on_item_double_clicked(self, _item: Any) -> None:
        self._set_tmux_for_current()

    def _show_context_menu(self, pos: Any) -> None:
        item = self.list_widget.itemAt(pos)
        if item is None:
            return
        self.list_widget.setCurrentItem(item)
        menu = QMenu(self)
        menu.addAction("Launch", self._launch_current)
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

    def _launch_current(self) -> None:
        ws = self._current_workspace()
        if ws is None:
            return
        self._launch_paths([ws.path])

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

    def _launch_paths(self, paths: list[str]) -> None:
        if not shutil.which("code"):
            QMessageBox.critical(
                self,
                "VSCode not found",
                "The `code` command is not on PATH. Install VSCode or its CLI shim.",
            )
            return

        by_path = {w.path: w for w in self.workspaces}
        targets = [by_path[p] for p in paths if p in by_path]
        already_running = [w for w in targets if w.is_running]

        if already_running:
            names = "\n".join(f"  • {w.label}" for w in already_running)
            box = QMessageBox(self)
            box.setWindowTitle("Already running")
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(
                f"{len(already_running)} of the selected workspaces "
                f"appear to be open already:\n\n{names}\n\n"
                "Launch anyway (opens duplicate windows), skip them, or cancel?"
            )
            launch_anyway = box.addButton(
                "Launch Anyway", QMessageBox.ButtonRole.AcceptRole
            )
            skip = box.addButton("Skip Running", QMessageBox.ButtonRole.DestructiveRole)
            cancel = box.addButton(QMessageBox.StandardButton.Cancel)
            box.setDefaultButton(skip)
            box.exec()
            clicked = box.clickedButton()
            if clicked is cancel:
                return
            if clicked is skip:
                running_labels_set = {w.label for w in already_running}
                targets = [w for w in targets if w.label not in running_labels_set]

        launched = 0
        for ws in targets:
            proc = self.launcher.launch_workspace(ws)
            if proc is not None:
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
        self._save()
        super().closeEvent(event)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("vscode-launcher")
    app.setDesktopFileName("vscode-launcher")
    config = ConfigManager()
    launcher = Launcher()
    recents = VSCodeRecentsReader()
    scanner = WindowScanner()
    window = MainWindow(config, launcher, recents, window_scanner=scanner)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
