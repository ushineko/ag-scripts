#!/usr/bin/env python3
"""WhoaPipe - GUI launcher manager for waypipe SSH remote Wayland applications."""

__version__ = "1.0"

import base64
import configparser
import json
import re
import shutil
import signal
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtCore import (
    QProcess,
    QSortFilterProxyModel,
    QSize,
    Qt,
)
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListView,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

CONFIG_DIR = Path.home() / ".config" / "whoapipe"
PROFILES_FILE = CONFIG_DIR / "profiles.json"


# ---------------------------------------------------------------------------
# Profile data
# ---------------------------------------------------------------------------

def load_config() -> dict:
    """Load config (profiles + settings) from JSON config file."""
    if not PROFILES_FILE.exists():
        return {"profiles": [], "settings": {}}
    try:
        with open(PROFILES_FILE) as f:
            data = json.load(f)
        # Migrate from old format (bare list) to new format (dict with profiles + settings)
        if isinstance(data, list):
            return {"profiles": data, "settings": {}}
        if isinstance(data, dict):
            data.setdefault("profiles", [])
            data.setdefault("settings", {})
            return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[whoapipe] Error loading config: {e}", file=sys.stderr)
    return {"profiles": [], "settings": {}}


def save_config(config: dict) -> None:
    """Save config (profiles + settings) to JSON config file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        with open(PROFILES_FILE, "w") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        print(f"[whoapipe] Error saving config: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Remote app browser
# ---------------------------------------------------------------------------

def parse_desktop_entries(raw_text: str) -> list[dict]:
    """Parse concatenated .desktop file contents into a list of app entries.

    Expects input in the format produced by the remote SSH command:
    each file separated by a marker line.
    """
    apps = []
    # Split on file markers
    chunks = re.split(r"^###WHOAPIPE_FILE###.*$", raw_text, flags=re.MULTILINE)
    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue
        parser = configparser.ConfigParser(interpolation=None)
        parser.optionxform = str  # preserve case
        try:
            parser.read_string(chunk)
        except configparser.Error:
            continue
        if "Desktop Entry" not in parser:
            continue
        entry = parser["Desktop Entry"]
        entry_type = entry.get("Type", "")
        if entry_type != "Application":
            continue
        # Skip entries marked as hidden or not meant to show
        if entry.get("NoDisplay", "false").lower() == "true":
            continue
        if entry.get("Hidden", "false").lower() == "true":
            continue
        name = entry.get("Name", "").strip()
        exec_line = entry.get("Exec", "").strip()
        comment = entry.get("Comment", "").strip()
        categories = entry.get("Categories", "").strip()
        if not name or not exec_line:
            continue
        # Clean up Exec field — remove %f, %F, %u, %U, etc.
        exec_clean = re.sub(r"\s*%[a-zA-Z]", "", exec_line).strip()
        icon_name = entry.get("Icon", "").strip()
        apps.append({
            "name": name,
            "exec": exec_clean,
            "comment": comment,
            "categories": categories,
            "icon": icon_name,
        })
    # Sort by name
    apps.sort(key=lambda a: a["name"].lower())
    return apps


class RemoteAppBrowser(QDialog):
    """Dialog that fetches and displays .desktop entries from a remote host."""

    def __init__(self, parent=None, host: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"Browse Remote Apps — {host}")
        self.resize(550, 500)
        self.host = host
        self.selected_app: dict | None = None

        layout = QVBoxLayout(self)

        # Search bar
        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Type to filter apps...")
        self.search_edit.setClearButtonEnabled(True)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        # App list
        self.model = QStandardItemModel()
        self.proxy = QSortFilterProxyModel()
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.proxy.setFilterRole(Qt.ItemDataRole.UserRole + 1)  # filter on search text

        self.list_view = QListView()
        self.list_view.setModel(self.proxy)
        self.list_view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.list_view.setViewMode(QListView.ViewMode.IconMode)
        self.list_view.setIconSize(QSize(48, 48))
        self.list_view.setGridSize(QSize(140, 90))
        self.list_view.setWordWrap(True)
        self.list_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.list_view.setUniformItemSizes(True)
        self.list_view.setFont(QFont("sans-serif", 8))
        self.list_view.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self.list_view)

        self.search_edit.textChanged.connect(self.proxy.setFilterFixedString)

        # Status label
        self.status_label = QLabel("Fetching apps from remote host...")
        layout.addWidget(self.status_label)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        # Start fetching
        self._fetch_apps()

    def _fetch_apps(self):
        self._proc = QProcess(self)
        self._proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._proc.finished.connect(self._on_fetch_finished)

        # Read all .desktop files from standard locations on the remote host
        remote_cmd = (
            'for f in /usr/share/applications/*.desktop '
            '$HOME/.local/share/applications/*.desktop; do '
            '[ -f "$f" ] && echo "###WHOAPIPE_FILE###$f" && cat "$f"; '
            'done'
        )
        self._proc.start("ssh", [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            self.host,
            remote_cmd,
        ])

    def _on_fetch_finished(self, exit_code, exit_status):
        output = bytes(self._proc.readAll()).decode(errors="replace")
        if exit_code != 0:
            self.status_label.setText(f"Failed to fetch apps (exit code {exit_code})")
            return

        apps = parse_desktop_entries(output)
        if not apps:
            self.status_label.setText("No applications found on remote host.")
            return

        cache_dir = CONFIG_DIR / "icon-cache" / self.host
        cache_dir.mkdir(parents=True, exist_ok=True)
        fallback_icon = QIcon.fromTheme("applications-other")
        unresolved = {}  # icon_name -> list of model row indices

        for app in apps:
            item = QStandardItem(app["name"])
            tooltip = app["name"]
            if app.get("comment"):
                tooltip += f"\n{app['comment']}"
            item.setToolTip(tooltip)
            icon_name = app.get("icon", "")
            icon = None

            if icon_name:
                # Check local cache first
                for ext in ("png", "svg"):
                    cached = cache_dir / f"{Path(icon_name).stem}.{ext}"
                    if cached.exists():
                        icon = QIcon(str(cached))
                        if icon.isNull():
                            icon = None
                        break

                # Try local theme (skip absolute paths)
                if icon is None and not icon_name.startswith("/"):
                    theme_icon = QIcon.fromTheme(icon_name)
                    if not theme_icon.isNull():
                        icon = theme_icon

                # Mark as unresolved for remote fetch
                if icon is None:
                    row_idx = self.model.rowCount()
                    unresolved.setdefault(icon_name, []).append(row_idx)

            item.setIcon(icon or fallback_icon)
            item.setData(app, Qt.ItemDataRole.UserRole)
            search_text = f"{app['name']} {app['comment']} {app['exec']} {app['categories']}"
            item.setData(search_text, Qt.ItemDataRole.UserRole + 1)
            self.model.appendRow(item)

        self.status_label.setText(f"{len(apps)} apps found. Double-click or select and press OK.")

        # Fetch unresolved icons from remote
        if unresolved:
            self._fetch_remote_icons(unresolved, cache_dir)

    def _fetch_remote_icons(self, unresolved: dict, cache_dir: Path):
        """Fetch missing icons from the remote host in a single SSH call."""
        self._unresolved = unresolved
        self._icon_cache_dir = cache_dir

        # Build a remote script that finds and base64-encodes each icon
        icon_names = list(unresolved.keys())
        find_cmds = []
        for name in icon_names:
            if name.startswith("/"):
                # Absolute path — just cat it directly
                find_cmds.append(
                    f'if [ -f "{name}" ]; then '
                    f'echo "###ICON###{name}"; base64 "{name}"; '
                    f'echo "###ICON_END###"; fi'
                )
            else:
                # Search all icon theme dirs and pixmaps via find
                find_cmds.append(
                    f'p=$(find /usr/share/icons /usr/share/pixmaps $HOME/.local/share/icons '
                    f'-name "{name}.png" -o -name "{name}.svg" '
                    f'2>/dev/null | head -1); '
                    f'if [ -n "$p" ]; then '
                    f'echo "###ICON###{name}"; base64 "$p"; '
                    f'echo "###ICON_END###"; fi'
                )

        remote_script = "; ".join(find_cmds)
        self._icon_proc = QProcess(self)
        self._icon_proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        self._icon_proc.finished.connect(self._on_icons_fetched)
        self._icon_proc.start("ssh", [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=10",
            self.host,
            remote_script,
        ])

    def _on_icons_fetched(self, exit_code, exit_status):
        output = bytes(self._icon_proc.readAll()).decode(errors="replace")
        cache_dir = self._icon_cache_dir

        # Parse icon data blocks
        for match in re.finditer(
            r"###ICON###(.+?)\n(.*?)###ICON_END###", output, re.DOTALL
        ):
            icon_key = match.group(1).strip()
            b64_data = match.group(2).strip()
            if not b64_data:
                continue
            try:
                raw = base64.b64decode(b64_data)
            except Exception:
                continue

            # Determine extension from magic bytes
            ext = "png"
            if raw[:4] == b"<?xm" or raw[:5] == b"<svg " or raw[:5] == b"<?xml":
                ext = "svg"
            elif raw[:4] == b"\x89PNG":
                ext = "png"

            cache_name = Path(icon_key).stem
            cached_path = cache_dir / f"{cache_name}.{ext}"
            cached_path.write_bytes(raw)

            # Update model items that need this icon
            rows = self._unresolved.get(icon_key, [])
            icon = QIcon(str(cached_path))
            if not icon.isNull():
                for row_idx in rows:
                    item = self.model.item(row_idx)
                    if item:
                        item.setIcon(icon)

    def _on_double_click(self, index):
        source_index = self.proxy.mapToSource(index)
        self.selected_app = self.model.itemFromIndex(source_index).data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_accept(self):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if indexes:
            source_index = self.proxy.mapToSource(indexes[0])
            self.selected_app = self.model.itemFromIndex(source_index).data(Qt.ItemDataRole.UserRole)
        self.accept()


# ---------------------------------------------------------------------------
# Entry editor dialog
# ---------------------------------------------------------------------------

class EntryDialog(QDialog):
    """Dialog for adding/editing a launcher entry."""

    COMPRESS_OPTIONS = ["none", "lz4", "zstd"]
    VIDEO_OPTIONS = ["none", "h264", "vp9", "av1"]

    def __init__(self, parent=None, entry: dict | None = None, default_host: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Edit Launcher" if entry else "Add Launcher")
        self._icon_name = ""
        self.setMinimumWidth(460)

        layout = QFormLayout(self)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Remote Firefox")
        layout.addRow("Name:", self.name_edit)

        self.host_edit = QLineEdit()
        self.host_edit.setPlaceholderText("e.g. cachyos or user@192.168.1.50")
        if not entry and default_host:
            self.host_edit.setText(default_host)
        layout.addRow("Host:", self.host_edit)

        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText("e.g. firefox or /usr/bin/mpv ~/video.mp4")
        command_row = QHBoxLayout()
        command_row.addWidget(self.command_edit)
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.setToolTip("Browse installed apps on the remote host")
        self.browse_btn.clicked.connect(self._browse_remote_apps)
        command_row.addWidget(self.browse_btn)
        layout.addRow("Command:", command_row)

        # Run in terminal (wraps command in foot for TUI apps)
        self.run_in_terminal_cb = QCheckBox(
            "Run in terminal  (wrap in foot -e for TUI/CLI apps)"
        )
        layout.addRow(self.run_in_terminal_cb)

        # Force dark theme on remote app
        self.dark_theme_cb = QCheckBox(
            "Force dark theme  (set GTK/libadwaita dark mode env vars)"
        )
        layout.addRow(self.dark_theme_cb)

        # -- Waypipe flags as checkboxes / dropdowns -------------------------
        flags_group = QGroupBox("Waypipe Options")
        flags_layout = QVBoxLayout(flags_group)

        # --no-gpu
        self.no_gpu_cb = QCheckBox("--no-gpu  (block GPU/DMABUF transfers)")
        flags_layout.addWidget(self.no_gpu_cb)

        # --debug
        self.debug_cb = QCheckBox("--debug  (print debug messages)")
        flags_layout.addWidget(self.debug_cb)

        # --oneshot
        self.oneshot_cb = QCheckBox("--oneshot  (only permit one connected application)")
        flags_layout.addWidget(self.oneshot_cb)

        # --xwls
        self.xwls_cb = QCheckBox("--xwls  (run xwayland-satellite for X11 clients)")
        flags_layout.addWidget(self.xwls_cb)

        # --compress
        compress_row = QHBoxLayout()
        compress_label = QLabel("Compression:")
        self.compress_combo = QComboBox()
        self.compress_combo.addItems(self.COMPRESS_OPTIONS)
        self.compress_combo.setCurrentText("lz4")
        compress_row.addWidget(compress_label)
        compress_row.addWidget(self.compress_combo)
        compress_row.addStretch()
        flags_layout.addLayout(compress_row)

        # --video
        video_row = QHBoxLayout()
        video_label = QLabel("Video encode:")
        self.video_combo = QComboBox()
        self.video_combo.addItems(self.VIDEO_OPTIONS)
        self.video_combo.setCurrentText("none")
        video_row.addWidget(video_label)
        video_row.addWidget(self.video_combo)
        video_row.addStretch()
        flags_layout.addLayout(video_row)

        # Extra flags (free text for anything not covered)
        extra_row = QHBoxLayout()
        extra_label = QLabel("Extra flags:")
        self.extra_flags_edit = QLineEdit()
        self.extra_flags_edit.setPlaceholderText("any additional flags")
        extra_row.addWidget(extra_label)
        extra_row.addWidget(self.extra_flags_edit)
        flags_layout.addLayout(extra_row)

        layout.addRow(flags_group)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        if entry:
            self._load_entry(entry)

    def _load_entry(self, entry: dict):
        self.name_edit.setText(entry.get("name", ""))
        self.host_edit.setText(entry.get("host", ""))
        self.command_edit.setText(entry.get("command", ""))

        self.run_in_terminal_cb.setChecked(entry.get("run_in_terminal", False))
        self.dark_theme_cb.setChecked(entry.get("dark_theme", False))
        self._icon_name = entry.get("icon", "")

        flags = entry.get("flags", "")
        self.no_gpu_cb.setChecked(entry.get("no_gpu", "--no-gpu" in flags))
        self.debug_cb.setChecked(entry.get("debug", "--debug" in flags))
        self.oneshot_cb.setChecked(entry.get("oneshot", "--oneshot" in flags))
        self.xwls_cb.setChecked(entry.get("xwls", "--xwls" in flags))
        self.compress_combo.setCurrentText(entry.get("compress", "lz4"))
        self.video_combo.setCurrentText(entry.get("video", "none"))
        self.extra_flags_edit.setText(entry.get("extra_flags", ""))

    def _browse_remote_apps(self):
        host = self.host_edit.text().strip()
        if not host:
            QMessageBox.warning(self, "Host Required", "Enter a host before browsing remote apps.")
            return
        dlg = RemoteAppBrowser(self, host=host)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_app:
            app = dlg.selected_app
            self.command_edit.setText(app["exec"])
            if not self.name_edit.text().strip():
                self.name_edit.setText(app["name"])
            self._icon_name = app.get("icon", "")

    def _validate_and_accept(self):
        if not self.name_edit.text().strip() and self.command_edit.text().strip():
            self.name_edit.setText(self.command_edit.text().strip())
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if not self.host_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Host is required.")
            return
        if not self.command_edit.text().strip():
            QMessageBox.warning(self, "Validation", "Command is required.")
            return
        self.accept()

    def build_flags(self) -> str:
        """Build the waypipe flags string from checkbox/combo state."""
        parts = []
        if self.no_gpu_cb.isChecked():
            parts.append("--no-gpu")
        if self.debug_cb.isChecked():
            parts.append("--debug")
        if self.oneshot_cb.isChecked():
            parts.append("--oneshot")
        if self.xwls_cb.isChecked():
            parts.append("--xwls")
        compress = self.compress_combo.currentText()
        if compress != "lz4":  # lz4 is the default, no need to specify
            parts.append(f"--compress {compress}")
        video = self.video_combo.currentText()
        if video != "none":
            parts.append(f"--video {video}")
        extra = self.extra_flags_edit.text().strip()
        if extra:
            parts.append(extra)
        return " ".join(parts)

    def get_entry(self) -> dict:
        return {
            "name": self.name_edit.text().strip(),
            "host": self.host_edit.text().strip(),
            "command": self.command_edit.text().strip(),
            "run_in_terminal": self.run_in_terminal_cb.isChecked(),
            "dark_theme": self.dark_theme_cb.isChecked(),
            "no_gpu": self.no_gpu_cb.isChecked(),
            "debug": self.debug_cb.isChecked(),
            "oneshot": self.oneshot_cb.isChecked(),
            "xwls": self.xwls_cb.isChecked(),
            "compress": self.compress_combo.currentText(),
            "video": self.video_combo.currentText(),
            "extra_flags": self.extra_flags_edit.text().strip(),
            "flags": self.build_flags(),
            "icon": self._icon_name,
        }


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Main WhoaPipe window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"WhoaPipe v{__version__}")
        self.resize(800, 600)

        self._config = load_config()
        self.profiles: list[dict] = self._config["profiles"]
        self.settings: dict = self._config["settings"]
        # Map row index -> list of (QProcess, process_id) for running instances
        self._running: dict[int, list[tuple[QProcess, str]]] = {}
        self._process_counter = 0
        # Per-process output buffer and launch time for error reporting
        self._process_output: dict[str, list[str]] = {}
        self._process_launch_time: dict[str, float] = {}
        # Rapid exit threshold in seconds — if process dies this fast, likely a failure
        self._rapid_exit_threshold = 5.0

        self._build_ui()
        self._populate_table()
        self._check_waypipe()

    # -- UI construction -----------------------------------------------------

    def _build_ui(self):
        # Toolbar
        toolbar = QToolBar("Actions")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        add_action = QAction("Add", self)
        add_action.setToolTip("Add a new launcher entry")
        add_action.triggered.connect(self._add_entry)
        toolbar.addAction(add_action)

        edit_action = QAction("Edit", self)
        edit_action.setToolTip("Edit the selected entry")
        edit_action.triggered.connect(self._edit_entry)
        toolbar.addAction(edit_action)

        remove_action = QAction("Remove", self)
        remove_action.setToolTip("Remove the selected entry")
        remove_action.triggered.connect(self._remove_entry)
        toolbar.addAction(remove_action)

        toolbar.addSeparator()

        launch_action = QAction("Launch", self)
        launch_action.setToolTip("Launch the selected entry")
        launch_action.triggered.connect(self._launch_selected)
        toolbar.addAction(launch_action)

        stop_action = QAction("Stop", self)
        stop_action.setToolTip("Stop all running instances of the selected entry")
        stop_action.triggered.connect(self._stop_selected)
        toolbar.addAction(stop_action)

        toolbar.addSeparator()

        test_action = QAction("Test Connection", self)
        test_action.setToolTip("Test SSH connectivity to the selected host")
        test_action.triggered.connect(self._test_connection_selected)
        toolbar.addAction(test_action)

        test_all_action = QAction("Test All", self)
        test_all_action.setToolTip("Test SSH connectivity to all hosts")
        test_all_action.triggered.connect(self._test_all_connections)
        toolbar.addAction(test_all_action)

        toolbar.addSeparator()

        clear_log_action = QAction("Clear Log", self)
        clear_log_action.setToolTip("Clear the log panel")
        clear_log_action.triggered.connect(self._clear_log)
        toolbar.addAction(clear_log_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        about_action = QAction("About", self)
        about_action.setToolTip("Help & About")
        about_action.triggered.connect(self._show_about)
        toolbar.addAction(about_action)

        # Splitter: table on top, log on bottom
        splitter = QSplitter(Qt.Orientation.Vertical)
        self.setCentralWidget(splitter)

        # Launcher table
        self.table = QTableWidget()
        self.table.setIconSize(QSize(24, 24))
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Name", "Host", "Command", "Flags", "Status"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Interactive
        )
        self.table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(self._launch_selected)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        splitter.addWidget(self.table)

        # Log panel
        log_group = QGroupBox("Log Output")
        log_layout = QVBoxLayout(log_group)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("monospace", 9))
        self.log_view.setMaximumBlockCount(5000)
        log_layout.addWidget(self.log_view)
        splitter.addWidget(log_group)

        splitter.setSizes([350, 250])

        # Status bar
        self.statusBar().showMessage("Ready")

    def _context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("Launch", self._launch_selected)
        menu.addAction("Stop", self._stop_selected)
        menu.addSeparator()
        menu.addAction("Edit", self._edit_entry)
        menu.addAction("Remove", self._remove_entry)
        menu.addSeparator()
        menu.addAction("Test Connection", self._test_connection_selected)
        menu.exec(self.table.viewport().mapToGlobal(pos))

    # -- Table management ----------------------------------------------------

    def _populate_table(self):
        self.table.setRowCount(len(self.profiles))
        for row, profile in enumerate(self.profiles):
            name_item = QTableWidgetItem(profile.get("name", ""))
            icon_name = profile.get("icon", "")
            if icon_name and not icon_name.startswith("/"):
                icon = QIcon.fromTheme(icon_name)
                if not icon.isNull():
                    name_item.setIcon(icon)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, QTableWidgetItem(profile.get("host", "")))
            self.table.setItem(row, 2, QTableWidgetItem(profile.get("command", "")))
            flags_display = profile.get("flags", "")
            if not flags_display:
                # Build from structured fields for backwards compat
                parts = []
                if profile.get("no_gpu"):
                    parts.append("--no-gpu")
                if profile.get("debug"):
                    parts.append("--debug")
                compress = profile.get("compress", "lz4")
                if compress != "lz4":
                    parts.append(f"-c {compress}")
                video = profile.get("video", "none")
                if video != "none":
                    parts.append(f"--video {video}")
                if profile.get("oneshot"):
                    parts.append("--oneshot")
                if profile.get("xwls"):
                    parts.append("--xwls")
                flags_display = " ".join(parts)
            self.table.setItem(row, 3, QTableWidgetItem(flags_display))
            self._update_status_cell(row)

    def _update_status_cell(self, row: int):
        running = self._running.get(row, [])
        active = [p for p, pid in running if p.state() != QProcess.ProcessState.NotRunning]
        if active:
            item = QTableWidgetItem(f"Running ({len(active)})")
            item.setForeground(QColor("#27ae60"))
        else:
            item = QTableWidgetItem("Stopped")
            item.setForeground(QColor("#95a5a6"))
        self.table.setItem(row, 4, item)

    def _selected_row(self) -> int | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return rows[0].row()

    # -- Config persistence --------------------------------------------------

    def _save(self):
        self._config["profiles"] = self.profiles
        self._config["settings"] = self.settings
        save_config(self._config)

    # -- CRUD operations -----------------------------------------------------

    def _add_entry(self):
        default_host = self.settings.get("default_host", "")
        dlg = EntryDialog(self, default_host=default_host)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            entry = dlg.get_entry()
            # Remember the host as the new default
            self.settings["default_host"] = entry["host"]
            self.profiles.append(entry)
            self._save()
            self._populate_table()
            self._log(f"Added entry: {entry['name']}")

    def _edit_entry(self):
        row = self._selected_row()
        if row is None:
            self.statusBar().showMessage("Select an entry to edit")
            return
        dlg = EntryDialog(self, entry=self.profiles[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.profiles[row] = dlg.get_entry()
            self.settings["default_host"] = self.profiles[row]["host"]
            self._save()
            self._populate_table()
            self._log(f"Updated entry: {self.profiles[row]['name']}")

    def _remove_entry(self):
        row = self._selected_row()
        if row is None:
            self.statusBar().showMessage("Select an entry to remove")
            return
        name = self.profiles[row]["name"]
        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            f"Remove launcher '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            # Stop any running processes for this entry
            self._stop_processes_for_row(row)
            self.profiles.pop(row)
            # Reindex running processes
            new_running = {}
            for r, procs in self._running.items():
                if r < row:
                    new_running[r] = procs
                elif r > row:
                    new_running[r - 1] = procs
            self._running = new_running
            self._save()
            self._populate_table()
            self._log(f"Removed entry: {name}")

    # -- Launching -----------------------------------------------------------

    def _launch_selected(self):
        row = self._selected_row()
        if row is None:
            self.statusBar().showMessage("Select an entry to launch")
            return
        self._launch_entry(row)

    def _launch_entry(self, row: int):
        profile = self.profiles[row]
        host = profile["host"]
        command = profile["command"]
        flags = profile.get("flags", "").strip()
        name = profile["name"]

        self._log(f"--- Launching: {name} ({host}: {command}) ---")
        self.statusBar().showMessage(f"Checking SSH to {host}...")

        # SSH connectivity check first
        ssh_check = QProcess(self)
        ssh_check.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        def on_ssh_check_finished(exit_code, exit_status):
            if exit_code != 0:
                output = bytes(ssh_check.readAll()).decode(errors="replace").strip()
                self._log(f"SSH check FAILED for {host}: {output}")
                QMessageBox.warning(
                    self,
                    "SSH Connection Failed",
                    f"Cannot connect to '{host}'.\n\n{output}",
                )
                self.statusBar().showMessage(f"SSH check failed for {host}")
                return
            self._log(f"SSH check OK for {host}")
            self._do_launch(row)

        ssh_check.finished.connect(on_ssh_check_finished)
        ssh_check.start("ssh", [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            host, "true",
        ])

    def _do_launch(self, row: int):
        profile = self.profiles[row]
        host = profile["host"]
        command = profile["command"]
        flags = profile.get("flags", "").strip()
        name = profile["name"]

        self._process_counter += 1
        pid = f"{name}#{self._process_counter}"

        args = []
        if flags:
            args.extend(flags.split())
        args.extend(["ssh", host])

        # Build the remote command with optional env vars and terminal wrapper
        remote_cmd = command
        if profile.get("dark_theme", False):
            dark_vars = (
                "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus "
                "QT_QPA_PLATFORMTHEME=xdgdesktopportal "
                "GTK_THEME=Adwaita:dark "
                "ADW_DEBUG_COLOR_SCHEME=prefer-dark"
            )
            remote_cmd = f"env {dark_vars} {remote_cmd}"
        if profile.get("run_in_terminal", False):
            remote_cmd = f"foot -e {remote_cmd}"
        args.extend(remote_cmd.split())

        self._log(f"[{pid}] waypipe {' '.join(args)}")
        self._process_output[pid] = []
        self._process_launch_time[pid] = datetime.now().timestamp()

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        proc.readyReadStandardOutput.connect(
            lambda p=proc, pid_=pid: self._on_process_output(p, pid_)
        )
        proc.finished.connect(
            lambda code, status, r=row, pid_=pid, n=name: self._on_process_finished(
                r, pid_, code, n
            )
        )

        proc.start("waypipe", args)

        if row not in self._running:
            self._running[row] = []
        self._running[row].append((proc, pid))
        self._update_status_cell(row)
        self.statusBar().showMessage(f"Launched: {name}")

    def _on_process_output(self, proc: QProcess, pid: str):
        data = bytes(proc.readAll()).decode(errors="replace").strip()
        if data:
            for line in data.splitlines():
                self._log(f"[{pid}] {line}")
                if pid in self._process_output:
                    self._process_output[pid].append(line)

    def _on_process_finished(self, row: int, pid: str, exit_code: int, name: str):
        self._log(f"[{pid}] Process exited with code {exit_code}")
        output_lines = self._process_output.pop(pid, [])
        launch_time = self._process_launch_time.pop(pid, 0)
        elapsed = datetime.now().timestamp() - launch_time if launch_time else 0

        # Detect failure: explicit non-zero exit, OR rapid exit (likely didn't launch)
        is_explicit_failure = exit_code != 0
        is_rapid_exit = elapsed < self._rapid_exit_threshold
        has_error_output = self._output_looks_like_error(output_lines)

        if is_explicit_failure:
            self._set_status_failed(row)
            self._show_launch_failure(name, exit_code, output_lines, elapsed)
        elif is_rapid_exit and (has_error_output or output_lines):
            # Rapid exit with any output — app likely didn't launch successfully
            self._set_status_failed(row)
            self._show_launch_failure(name, exit_code, output_lines, elapsed)
        elif is_rapid_exit:
            # Rapid exit, no output at all — still suspicious
            self._log(
                f"[{pid}] WARNING: Exited after {elapsed:.1f}s with no output."
            )
            self._set_status_failed(row)
        else:
            self._update_status_cell(row)

    @staticmethod
    def _strip_ansi(text: str) -> str:
        """Remove ANSI escape sequences from text."""
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)

    @classmethod
    def _output_looks_like_error(cls, output_lines: list[str]) -> bool:
        """Check if process output contains error-like patterns."""
        if not output_lines:
            return False
        full = cls._strip_ansi("\n".join(output_lines)).lower()
        error_keywords = (
            "error", "failed", "fatal", "cannot", "unable",
            "not found", "no such", "permission denied", "segfault",
            "segmentation fault", "abort", "panic", "refused",
            "resource temporarily unavailable",
        )
        return any(kw in full for kw in error_keywords)

    def _set_status_failed(self, row: int):
        item = QTableWidgetItem("Failed")
        item.setForeground(QColor("#e74c3c"))
        self.table.setItem(row, 4, item)

    def _show_launch_failure(
        self, name: str, exit_code: int, output_lines: list[str], elapsed: float = 0
    ):
        # Show last 20 lines of output — most relevant for diagnosing failure
        tail = output_lines[-20:] if output_lines else []
        output_text = "\n".join(tail) if tail else "(no output captured)"

        # Build hints based on common failure patterns
        hints = self._diagnose_failure(exit_code, output_lines)
        hint_text = ""
        if hints:
            hint_text = "\n\nPossible causes:\n" + "\n".join(f"  - {h}" for h in hints)

        timing = ""
        if elapsed < self._rapid_exit_threshold:
            timing = f" (exited after {elapsed:.1f}s)"

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(f"Launch Failed: {name}")
        msg.setText(
            f"'{name}' exited with code {exit_code}{timing}.{hint_text}"
        )
        msg.setDetailedText(output_text)
        msg.exec()

    @classmethod
    def _diagnose_failure(cls, exit_code: int, output_lines: list[str]) -> list[str]:
        """Produce human-readable hints from waypipe/app failure output."""
        hints = []
        full_output = cls._strip_ansi("\n".join(output_lines)).lower()

        # DMABUF / GPU failures
        if any(kw in full_output for kw in ("dmabuf", "drm", "egl", "vulkan", "gpu")):
            hints.append(
                "GPU/DMABUF error detected. Try enabling '--no-gpu' in Waypipe Options."
            )

        # Wayland display issues
        if "wayland" in full_output and ("display" in full_output or "socket" in full_output):
            hints.append(
                "Wayland display not available on remote host. "
                "Ensure the remote is running a Wayland compositor or waypipe can create one."
            )

        # Electron app defaulting to X11 (ozone platform)
        if "ozone_platform_x11" in full_output or "missing x server" in full_output:
            hints.append(
                "This looks like an Electron app defaulting to X11. "
                "Try adding '--ozone-platform=wayland' to the command, e.g.:\n"
                "    marktext --ozone-platform=wayland\n"
                "Or enable '--xwls' to provide X11 via xwayland-satellite."
            )
        # Other X11 apps without xwayland
        elif any(kw in full_output for kw in ("cannot open display", "xwayland", "x11")):
            hints.append(
                "This may be an X11-only app. Try enabling '--xwls' to run "
                "xwayland-satellite on the remote."
            )

        # Command not found
        if "command not found" in full_output or "no such file" in full_output:
            hints.append(
                "The command was not found on the remote host. "
                "Check that the application is installed remotely."
            )

        # Permission denied
        if "permission denied" in full_output:
            hints.append("Permission denied on the remote host. Check file permissions.")

        # Segfault / crash
        if "segfault" in full_output or "segmentation fault" in full_output:
            hints.append(
                "The application crashed (segfault). This may be a compatibility issue "
                "with waypipe forwarding. Try '--no-gpu' or a different video codec."
            )

        # Connection issues
        if "connection refused" in full_output or "connection reset" in full_output:
            hints.append("Network connection issue between local and remote host.")

        # Already running (single-instance apps like MarkText, Electron apps)
        if "already running" in full_output:
            hints.append(
                "Another instance of this app is already running on the remote host. "
                "Close it first or use a different profile."
            )

        # Locale / UTF-8 issues (btop, etc.)
        if "utf-8" in full_output or "locale" in full_output:
            hints.append(
                "The app requires a UTF-8 locale on the remote host. "
                "This is also a terminal/TUI app — only GUI apps work through waypipe."
            )

        # TUI / non-GUI app
        if "resource temporarily unavailable" in full_output:
            hints.append(
                "This may be a terminal/TUI app that cannot run through waypipe. "
                "Only Wayland GUI applications are supported."
            )

        # waypipe itself not found on remote
        if "waypipe" in full_output and "not found" in full_output:
            hints.append(
                "waypipe is not installed on the remote host. "
                "Install it: pacman -S waypipe / apt install waypipe"
            )

        # Generic hint if nothing matched
        if not hints:
            hints.append(
                "Check the log panel for detailed output. "
                "Enable '--debug' in Waypipe Options for more information."
            )

        return hints

    # -- Stop ----------------------------------------------------------------

    def _stop_selected(self):
        row = self._selected_row()
        if row is None:
            self.statusBar().showMessage("Select an entry to stop")
            return
        self._stop_processes_for_row(row)

    def _stop_processes_for_row(self, row: int):
        procs = self._running.get(row, [])
        for proc, pid in procs:
            if proc.state() != QProcess.ProcessState.NotRunning:
                self._log(f"[{pid}] Stopping...")
                proc.terminate()
                if not proc.waitForFinished(3000):
                    proc.kill()
                    self._log(f"[{pid}] Force killed")
        self._update_status_cell(row)

    # -- SSH test ------------------------------------------------------------

    def _test_connection_selected(self):
        row = self._selected_row()
        if row is None:
            self.statusBar().showMessage("Select an entry to test")
            return
        self._test_connection(row)

    def _test_all_connections(self):
        for row in range(len(self.profiles)):
            self._test_connection(row)

    def _test_connection(self, row: int):
        profile = self.profiles[row]
        host = profile["host"]
        name = profile["name"]

        self._log(f"Testing SSH to {host} ({name})...")
        self.statusBar().showMessage(f"Testing SSH to {host}...")

        proc = QProcess(self)
        proc.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)

        def on_finished(exit_code, exit_status):
            output = bytes(proc.readAll()).decode(errors="replace").strip()
            if exit_code == 0:
                self._log(f"SSH test PASSED: {host} ({name})")
                self.statusBar().showMessage(f"SSH OK: {host}")
            else:
                self._log(f"SSH test FAILED: {host} ({name}): {output}")
                self.statusBar().showMessage(f"SSH FAILED: {host}")

        proc.finished.connect(on_finished)
        proc.start("ssh", [
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=5",
            host, "true",
        ])

    # -- Logging -------------------------------------------------------------

    def _log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.appendPlainText(f"[{ts}] {message}")

    def _clear_log(self):
        self.log_view.clear()

    # -- About dialog ---------------------------------------------------------

    def _show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Help & About")
        dlg.resize(620, 520)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self._get_about_text())
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        dlg.exec()

    @staticmethod
    def _get_about_text() -> str:
        return f"""
        <div align="center">
            <h1>WhoaPipe</h1>
            <p><b>Version {__version__}</b></p>
            <p>A GUI launcher manager for waypipe SSH remote Wayland applications.</p>
            <p>Copyright (c) 2026 ushineko</p>
        </div>
        <hr>

        <h3>What is WhoaPipe?</h3>
        <p>WhoaPipe manages <b>waypipe</b> SSH connections for launching remote
        Wayland applications on your local desktop. Define per-app profiles
        (host + command + flags), verify SSH connectivity, and launch remote
        apps with a double-click. All waypipe output is captured and displayed
        for troubleshooting.</p>

        <h3>Quick Start</h3>
        <ol>
            <li><b>Add a profile:</b> Click <i>Add</i> in the toolbar</li>
            <li><b>Set host:</b> Enter the SSH hostname or alias</li>
            <li><b>Pick a command:</b> Type it or click <i>Browse...</i> to
                discover installed apps on the remote host</li>
            <li><b>Launch:</b> Double-click the entry or select it and
                click <i>Launch</i></li>
        </ol>

        <h3>Waypipe Options</h3>
        <ul>
            <li><b>--no-gpu:</b> Required for GPU-accelerated apps (mpv,
                browsers with WebGL) to prevent dmabuf/Vulkan init crashes</li>
            <li><b>--compress:</b> Reduces bandwidth &mdash; lz4 (fast) or
                zstd (smaller)</li>
            <li><b>--video:</b> Hardware video encoding for high-bandwidth
                apps &mdash; h264, vp9, or av1</li>
            <li><b>--debug:</b> Verbose waypipe logging in the log panel</li>
            <li><b>--oneshot:</b> Exit waypipe when the app closes</li>
        </ul>

        <h3>Run in Terminal</h3>
        <p>For TUI/CLI apps (btop, yazi, etc.), check <i>"Run in terminal"</i>
        in the profile editor. This wraps the command in <code>foot -e</code>
        so it runs inside a foot terminal window forwarded via waypipe.</p>

        <h3>Failure Detection</h3>
        <p>WhoaPipe detects failed launches (rapid exits, error output) and
        shows a diagnostic dialog with hints:</p>
        <ul>
            <li><b>GPU/DMABUF errors:</b> Enable --no-gpu</li>
            <li><b>Electron/X11 apps:</b> Add --ozone-platform=wayland</li>
            <li><b>TUI apps failing:</b> Enable "Run in terminal"</li>
            <li><b>Command not found:</b> Check the remote command path</li>
        </ul>

        <h3>Changelog</h3>
        <p><b>v{__version__}</b> &mdash; Initial release</p>
        <ul>
            <li>Profile management with auto-save/load</li>
            <li>Remote .desktop file browser with searchable icon grid</li>
            <li>Remote icon caching via SSH</li>
            <li>SSH connectivity testing (single and batch)</li>
            <li>Waypipe flag checkboxes (--no-gpu, --compress, --video, etc.)</li>
            <li>Real-time log capture with timestamps</li>
            <li>Failure detection with diagnostic hints</li>
            <li>Run-in-terminal support (foot -e wrapper)</li>
            <li>Force dark theme (GTK/libadwaita/Qt)</li>
            <li>Default host setting</li>
        </ul>
        """

    # -- Waypipe check -------------------------------------------------------

    def _check_waypipe(self):
        if not shutil.which("waypipe"):
            self._log("ERROR: 'waypipe' binary not found in PATH")
            QMessageBox.critical(
                self,
                "waypipe Not Found",
                "'waypipe' is not installed or not in PATH.\n\n"
                "Install it with your package manager:\n"
                "  pacman -S waypipe\n"
                "  apt install waypipe",
            )
        else:
            self._log("waypipe found in PATH")

    # -- Cleanup on close ----------------------------------------------------

    def closeEvent(self, event):
        # Terminate all running processes
        for row, procs in self._running.items():
            for proc, pid in procs:
                if proc.state() != QProcess.ProcessState.NotRunning:
                    proc.terminate()
                    proc.waitForFinished(2000)
                    if proc.state() != QProcess.ProcessState.NotRunning:
                        proc.kill()
        event.accept()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setApplicationName("WhoaPipe")
    app.setDesktopFileName("whoapipe")

    icon_path = Path(__file__).parent / "whoapipe.png"
    if icon_path.exists():
        icon = QIcon(str(icon_path))
    else:
        icon = QIcon.fromTheme("krdc")
    app.setWindowIcon(icon)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
