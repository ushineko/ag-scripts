#!/usr/bin/env python3
"""
Foghorn Leghorn - Always-on-top countdown timer with system tray integration.

A desktop timer application for KDE Plasma that keeps countdown reminders
visible and fires notifications with attention-grabbing sounds when timers expire.
"""

import json
import subprocess
import sys
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path

from PyQt6.QtCore import (
    QTimer,
    Qt,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QFont, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSlider,
    QSpinBox,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

__version__ = "1.0.0"

SCRIPT_DIR = Path(__file__).resolve().parent
SOUNDS_DIR = SCRIPT_DIR / "sounds"
CONFIG_DIR = Path.home() / ".config" / "foghorn-leghorn"
CONFIG_FILE = CONFIG_DIR / "config.json"

DEFAULT_CONFIG = {
    "window_x": 100,
    "window_y": 100,
    "window_width": 520,
    "window_height": 400,
    "font_size": 48,
    "sound_enabled": True,
    "timers": [],
}

BUILTIN_SOUNDS = {
    "Foghorn": SOUNDS_DIR / "foghorn.wav",
    "Wilhelm Scream": SOUNDS_DIR / "wilhelm_scream.wav",
    "Air Horn": SOUNDS_DIR / "air_horn.wav",
}


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

@dataclass
class TimerData:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    name: str = "Timer"
    duration_seconds: int = 300
    remaining_seconds: int = 300
    sound_key: str = "Foghorn"
    custom_sound_path: str = ""
    is_running: bool = False
    is_paused: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TimerData":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in data.items() if k in known})


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class ConfigManager:
    """Load/save JSON configuration."""

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self._data: dict = {}
        self.load()

    def load(self):
        if self.config_path.exists():
            try:
                self._data = json.loads(self.config_path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = dict(DEFAULT_CONFIG)
        else:
            self._data = dict(DEFAULT_CONFIG)

    def save(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(self._data, indent=2))

    def get(self, key: str, default=None):
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def save_timers(self, timers: list[TimerData]):
        self._data["timers"] = [t.to_dict() for t in timers]
        self.save()

    def load_timers(self) -> list[TimerData]:
        raw = self._data.get("timers", [])
        timers: list[TimerData] = []
        for entry in raw:
            try:
                timers.append(TimerData.from_dict(entry))
            except (TypeError, KeyError, AttributeError):
                continue
        return timers


# ---------------------------------------------------------------------------
# Sound player
# ---------------------------------------------------------------------------

class SoundPlayer:
    """Play alarm sounds via paplay (PipeWire/PulseAudio) or aplay (ALSA)."""

    def play(self, sound_path: str | Path):
        path = Path(sound_path)
        if not path.exists():
            return
        try:
            subprocess.Popen(
                ["paplay", str(path)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            try:
                subprocess.Popen(
                    ["aplay", str(path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except FileNotFoundError:
                pass


# ---------------------------------------------------------------------------
# Timer engine
# ---------------------------------------------------------------------------

class TimerEngine(QTimer):
    """1-second tick engine managing all timers."""

    timer_tick = pyqtSignal()
    timer_expired = pyqtSignal(str)  # timer id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.timers: list[TimerData] = []
        self.setInterval(1000)
        self.timeout.connect(self._tick)

    def _tick(self):
        for t in self.timers:
            if t.is_running and not t.is_paused and t.remaining_seconds > 0:
                t.remaining_seconds -= 1
                if t.remaining_seconds <= 0:
                    t.is_running = False
                    self.timer_expired.emit(t.id)
        self.timer_tick.emit()

    def ensure_running(self):
        has_active = any(t.is_running and not t.is_paused for t in self.timers)
        if has_active and not self.isActive():
            self.start()
        elif not has_active and self.isActive():
            self.stop()

    def add_timer(self, timer_data: TimerData):
        self.timers.append(timer_data)
        self.ensure_running()

    def remove_timer(self, timer_id: str):
        self.timers = [t for t in self.timers if t.id != timer_id]
        self.ensure_running()

    def get_timer(self, timer_id: str) -> TimerData | None:
        for t in self.timers:
            if t.id == timer_id:
                return t
        return None


# ---------------------------------------------------------------------------
# Add / Edit timer dialog
# ---------------------------------------------------------------------------

class TimerDialog(QDialog):
    """Dialog for creating or editing a timer."""

    def __init__(self, parent=None, timer_data: TimerData | None = None):
        super().__init__(parent)
        self.setWindowTitle("Edit Timer" if timer_data else "Add Timer")
        self._custom_path = ""
        self._build_ui(timer_data)

    def _build_ui(self, td: TimerData | None):
        layout = QVBoxLayout(self)

        # Name
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit(td.name if td else "Timer")
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        # Duration
        dur_row = QHBoxLayout()
        dur_row.addWidget(QLabel("Duration:"))
        total = td.duration_seconds if td else 300
        h, remainder = divmod(total, 3600)
        m, s = divmod(remainder, 60)

        self.hours_spin = QSpinBox()
        self.hours_spin.setRange(0, 99)
        self.hours_spin.setValue(h)
        self.hours_spin.setSuffix("h")
        dur_row.addWidget(self.hours_spin)

        self.mins_spin = QSpinBox()
        self.mins_spin.setRange(0, 59)
        self.mins_spin.setValue(m)
        self.mins_spin.setSuffix("m")
        dur_row.addWidget(self.mins_spin)

        self.secs_spin = QSpinBox()
        self.secs_spin.setRange(0, 59)
        self.secs_spin.setValue(s)
        self.secs_spin.setSuffix("s")
        dur_row.addWidget(self.secs_spin)

        layout.addLayout(dur_row)

        # Sound
        sound_row = QHBoxLayout()
        sound_row.addWidget(QLabel("Sound:"))
        self.sound_combo = QComboBox()
        self.sound_combo.addItems(list(BUILTIN_SOUNDS.keys()) + ["Custom..."])
        sound_row.addWidget(self.sound_combo)

        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setEnabled(False)
        self.browse_btn.clicked.connect(self._browse_sound)
        sound_row.addWidget(self.browse_btn)
        layout.addLayout(sound_row)

        self.custom_label = QLabel("")
        layout.addWidget(self.custom_label)

        self.sound_combo.currentTextChanged.connect(self._on_sound_changed)

        if td and td.custom_sound_path:
            self.sound_combo.setCurrentText("Custom...")
            self._custom_path = td.custom_sound_path
            self.custom_label.setText(Path(td.custom_sound_path).name)
        elif td and td.sound_key in BUILTIN_SOUNDS:
            self.sound_combo.setCurrentText(td.sound_key)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_sound_changed(self, text: str):
        self.browse_btn.setEnabled(text == "Custom...")

    def _browse_sound(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Sound File", "", "Audio Files (*.wav *.ogg *.mp3 *.flac);;All Files (*)"
        )
        if path:
            self._custom_path = path
            self.custom_label.setText(Path(path).name)

    def get_duration_seconds(self) -> int:
        return (
            self.hours_spin.value() * 3600
            + self.mins_spin.value() * 60
            + self.secs_spin.value()
        )

    def get_sound_key(self) -> str:
        text = self.sound_combo.currentText()
        if text == "Custom...":
            return "Custom"
        return text

    def get_custom_sound_path(self) -> str:
        if self.sound_combo.currentText() == "Custom...":
            return self._custom_path
        return ""

    def get_name(self) -> str:
        return self.name_edit.text().strip() or "Timer"


# ---------------------------------------------------------------------------
# Timer row widget
# ---------------------------------------------------------------------------

class TimerRowWidget(QWidget):
    """Single timer row displayed in the list."""

    request_edit = pyqtSignal(str)
    request_delete = pyqtSignal(str)
    request_toggle_pause = pyqtSignal(str)
    request_reset = pyqtSignal(str)
    request_move_up = pyqtSignal(str)
    request_move_down = pyqtSignal(str)

    def __init__(self, timer_data: TimerData, font_size: int, parent=None):
        super().__init__(parent)
        self.timer_id = timer_data.id
        self._font_size = font_size
        self._build_ui(timer_data)

    def _build_ui(self, td: TimerData):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)

        # Reorder buttons
        self.up_btn = QPushButton("\u25b2")
        self.up_btn.setFixedWidth(28)
        self.up_btn.setToolTip("Move up")
        self.up_btn.clicked.connect(lambda: self.request_move_up.emit(self.timer_id))
        layout.addWidget(self.up_btn)

        self.down_btn = QPushButton("\u25bc")
        self.down_btn.setFixedWidth(28)
        self.down_btn.setToolTip("Move down")
        self.down_btn.clicked.connect(lambda: self.request_move_down.emit(self.timer_id))
        layout.addWidget(self.down_btn)

        # Name label
        self.name_label = QLabel(td.name)
        self.name_label.setMinimumWidth(80)
        layout.addWidget(self.name_label)

        # Countdown display
        self.time_label = QLabel(format_seconds(td.remaining_seconds))
        font = QFont("monospace", self._font_size)
        font.setBold(True)
        self.time_label.setFont(font)
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.time_label, stretch=1)

        # Action buttons
        self.pause_btn = QPushButton("Pause")
        self.pause_btn.setFixedWidth(70)
        self.pause_btn.clicked.connect(lambda: self.request_toggle_pause.emit(self.timer_id))
        layout.addWidget(self.pause_btn)

        self.reset_btn = QPushButton("Reset")
        self.reset_btn.setFixedWidth(60)
        self.reset_btn.clicked.connect(lambda: self.request_reset.emit(self.timer_id))
        layout.addWidget(self.reset_btn)

        self.edit_btn = QPushButton("Edit")
        self.edit_btn.setFixedWidth(50)
        self.edit_btn.clicked.connect(lambda: self.request_edit.emit(self.timer_id))
        layout.addWidget(self.edit_btn)

        self.del_btn = QPushButton("Del")
        self.del_btn.setFixedWidth(42)
        self.del_btn.clicked.connect(lambda: self.request_delete.emit(self.timer_id))
        layout.addWidget(self.del_btn)

    def update_display(self, td: TimerData, font_size: int):
        self.name_label.setText(td.name)
        self.time_label.setText(format_seconds(td.remaining_seconds))

        if font_size != self._font_size:
            self._font_size = font_size
            font = QFont("monospace", font_size)
            font.setBold(True)
            self.time_label.setFont(font)

        if td.remaining_seconds <= 0:
            self.pause_btn.setText("Done")
            self.pause_btn.setEnabled(False)
        elif td.is_paused:
            self.pause_btn.setText("Resume")
            self.pause_btn.setEnabled(True)
        elif td.is_running:
            self.pause_btn.setText("Pause")
            self.pause_btn.setEnabled(True)
        else:
            self.pause_btn.setText("Start")
            self.pause_btn.setEnabled(True)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    """Primary application window."""

    def __init__(self, config: ConfigManager, engine: TimerEngine, sound_player: SoundPlayer):
        super().__init__()
        self.config = config
        self.engine = engine
        self.sound_player = sound_player
        self._row_widgets: dict[str, TimerRowWidget] = {}
        self._tray: QSystemTrayIcon | None = None
        self._quitting = False

        self.setWindowTitle(f"Foghorn Leghorn v{__version__}")
        self.setWindowIcon(QIcon.fromTheme("chronometer"))
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint
        )

        self._build_ui()
        self._build_tray()
        self._restore_geometry()
        self._load_timers()

        self.engine.timer_tick.connect(self._on_tick)
        self.engine.timer_expired.connect(self._on_timer_expired)

    # -- UI --

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)

        # Top bar: Add button + font slider + sound toggle
        top_bar = QHBoxLayout()

        add_btn = QPushButton("+ Add Timer")
        add_btn.clicked.connect(self._add_timer)
        top_bar.addWidget(add_btn)

        top_bar.addStretch()

        top_bar.addWidget(QLabel("Font:"))
        self.font_slider = QSlider(Qt.Orientation.Horizontal)
        self.font_slider.setRange(16, 72)
        self.font_slider.setValue(self.config.get("font_size", 48))
        self.font_slider.setFixedWidth(120)
        self.font_slider.valueChanged.connect(self._on_font_changed)
        top_bar.addWidget(self.font_slider)

        self.font_size_label = QLabel(str(self.font_slider.value()))
        self.font_size_label.setFixedWidth(24)
        top_bar.addWidget(self.font_size_label)

        self.sound_check = QCheckBox("Sound")
        self.sound_check.setChecked(self.config.get("sound_enabled", True))
        self.sound_check.toggled.connect(self._on_sound_toggled)
        top_bar.addWidget(self.sound_check)

        main_layout.addLayout(top_bar)

        # Timer list
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        main_layout.addWidget(self.list_widget)

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(QIcon.fromTheme("chronometer"))
        self._tray.setToolTip("Foghorn Leghorn - 0 active timers")

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        hide_action = QAction("Hide", self)
        hide_action.triggered.connect(self.hide)
        menu.addAction(hide_action)

        menu.addSeparator()

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    def _show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def _quit(self):
        self._quitting = True
        self._save_state()
        QApplication.instance().quit()

    # -- Geometry persistence --

    def _restore_geometry(self):
        x = self.config.get("window_x", 100)
        y = self.config.get("window_y", 100)
        w = self.config.get("window_width", 520)
        h = self.config.get("window_height", 400)
        self.setGeometry(x, y, w, h)

    def _save_geometry(self):
        geo = self.geometry()
        self.config.set("window_x", geo.x())
        self.config.set("window_y", geo.y())
        self.config.set("window_width", geo.width())
        self.config.set("window_height", geo.height())

    # -- Timer loading --

    def _load_timers(self):
        for td in self.config.load_timers():
            self.engine.add_timer(td)
            self._add_row(td)
        self.engine.ensure_running()

    # -- Timer actions --

    def _add_timer(self):
        dlg = TimerDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        duration = dlg.get_duration_seconds()
        if duration <= 0:
            return
        td = TimerData(
            name=dlg.get_name(),
            duration_seconds=duration,
            remaining_seconds=duration,
            sound_key=dlg.get_sound_key(),
            custom_sound_path=dlg.get_custom_sound_path(),
            is_running=True,
        )
        self.engine.add_timer(td)
        self._add_row(td)
        self._save_state()

    def _add_row(self, td: TimerData):
        row = TimerRowWidget(td, self.font_slider.value())
        row.request_edit.connect(self._edit_timer)
        row.request_delete.connect(self._delete_timer)
        row.request_toggle_pause.connect(self._toggle_pause)
        row.request_reset.connect(self._reset_timer)
        row.request_move_up.connect(self._move_up)
        row.request_move_down.connect(self._move_down)

        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, td.id)
        item.setSizeHint(row.sizeHint())
        self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, row)
        self._row_widgets[td.id] = row

    def _edit_timer(self, timer_id: str):
        td = self.engine.get_timer(timer_id)
        if not td:
            return
        dlg = TimerDialog(self, timer_data=td)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        td.name = dlg.get_name()
        td.duration_seconds = dlg.get_duration_seconds()
        td.sound_key = dlg.get_sound_key()
        td.custom_sound_path = dlg.get_custom_sound_path()
        if not td.is_running:
            td.remaining_seconds = td.duration_seconds
        self._refresh_row(td)
        self._save_state()

    def _delete_timer(self, timer_id: str):
        td = self.engine.get_timer(timer_id)
        if not td:
            return
        reply = QMessageBox.question(
            self,
            "Delete Timer",
            f'Delete timer "{td.name}"?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.engine.remove_timer(timer_id)
        self._remove_row(timer_id)
        self._save_state()

    def _toggle_pause(self, timer_id: str):
        td = self.engine.get_timer(timer_id)
        if not td or td.remaining_seconds <= 0:
            return
        if not td.is_running:
            td.is_running = True
            td.is_paused = False
        elif td.is_paused:
            td.is_paused = False
        else:
            td.is_paused = True
        self.engine.ensure_running()
        self._refresh_row(td)
        self._save_state()

    def _reset_timer(self, timer_id: str):
        td = self.engine.get_timer(timer_id)
        if not td:
            return
        td.remaining_seconds = td.duration_seconds
        td.is_running = False
        td.is_paused = False
        self.engine.ensure_running()
        self._refresh_row(td)
        self._save_state()

    def _move_up(self, timer_id: str):
        idx = self._find_row_index(timer_id)
        if idx <= 0:
            return
        self._swap_rows(idx, idx - 1)

    def _move_down(self, timer_id: str):
        idx = self._find_row_index(timer_id)
        if idx < 0 or idx >= self.list_widget.count() - 1:
            return
        self._swap_rows(idx, idx + 1)

    # -- Row helpers --

    def _find_row_index(self, timer_id: str) -> int:
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == timer_id:
                return i
        return -1

    def _swap_rows(self, idx_a: int, idx_b: int):
        # Swap in engine list
        self.engine.timers[idx_a], self.engine.timers[idx_b] = (
            self.engine.timers[idx_b],
            self.engine.timers[idx_a],
        )
        # Rebuild list widget
        self._rebuild_list()
        self._save_state()

    def _rebuild_list(self):
        self.list_widget.clear()
        self._row_widgets.clear()
        for td in self.engine.timers:
            self._add_row(td)

    def _refresh_row(self, td: TimerData):
        row = self._row_widgets.get(td.id)
        if row:
            row.update_display(td, self.font_slider.value())
            # Resize list item to match
            idx = self._find_row_index(td.id)
            if idx >= 0:
                item = self.list_widget.item(idx)
                if item:
                    item.setSizeHint(row.sizeHint())

    def _remove_row(self, timer_id: str):
        idx = self._find_row_index(timer_id)
        if idx >= 0:
            self.list_widget.takeItem(idx)
        self._row_widgets.pop(timer_id, None)

    # -- Tick / expiry --

    def _on_tick(self):
        for td in self.engine.timers:
            self._refresh_row(td)
        self._update_tray_tooltip()

    def _on_timer_expired(self, timer_id: str):
        td = self.engine.get_timer(timer_id)
        if not td:
            return
        self._notify(td)
        self._play_sound(td)
        self._refresh_row(td)

    def _notify(self, td: TimerData):
        title = "Timer Expired"
        body = f'"{td.name}" has finished!'
        # Try tray notification first
        if self._tray and self._tray.isVisible():
            self._tray.showMessage(title, body, QSystemTrayIcon.MessageIcon.Warning, 10000)
        # Also send via notify-send for richer KDE integration
        try:
            subprocess.Popen(
                ["notify-send", "--urgency=critical", "--app-name=Foghorn Leghorn", title, body],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except FileNotFoundError:
            pass

    def _play_sound(self, td: TimerData):
        if not self.sound_check.isChecked():
            return
        if td.custom_sound_path and Path(td.custom_sound_path).exists():
            self.sound_player.play(td.custom_sound_path)
        elif td.sound_key in BUILTIN_SOUNDS:
            self.sound_player.play(BUILTIN_SOUNDS[td.sound_key])

    # -- Settings callbacks --

    def _on_font_changed(self, value: int):
        self.font_size_label.setText(str(value))
        for td in self.engine.timers:
            self._refresh_row(td)
        self.config.set("font_size", value)

    def _on_sound_toggled(self, checked: bool):
        self.config.set("sound_enabled", checked)

    # -- Tray --

    def _update_tray_tooltip(self):
        if not self._tray:
            return
        active = sum(1 for t in self.engine.timers if t.is_running and not t.is_paused)
        self._tray.setToolTip(f"Foghorn Leghorn - {active} active timer{'s' if active != 1 else ''}")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._show_window()

    # -- State --

    def _save_state(self):
        self._save_geometry()
        self.config.set("font_size", self.font_slider.value())
        self.config.set("sound_enabled", self.sound_check.isChecked())
        self.config.save_timers(self.engine.timers)

    # -- Events --

    def closeEvent(self, event):
        if self._quitting:
            self._save_state()
            event.accept()
            return
        if self._tray and self._tray.isVisible():
            self._save_state()
            self.hide()
            event.ignore()
        else:
            self._save_state()
            event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Update size hints for list items after resize
        for td in self.engine.timers:
            row = self._row_widgets.get(td.id)
            if row:
                idx = self._find_row_index(td.id)
                if idx >= 0:
                    item = self.list_widget.item(idx)
                    if item:
                        item.setSizeHint(row.sizeHint())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def format_seconds(total: int) -> str:
    if total < 0:
        total = 0
    h, remainder = divmod(total, 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Foghorn Leghorn")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("foghorn-leghorn")
    app.setWindowIcon(QIcon.fromTheme("chronometer"))
    app.setQuitOnLastWindowClosed(False)

    config = ConfigManager()
    engine = TimerEngine()
    sound_player = SoundPlayer()
    window = MainWindow(config, engine, sound_player)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
