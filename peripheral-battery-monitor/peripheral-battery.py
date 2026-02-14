
import sys
import signal
import json
import os
import subprocess
import faulthandler
import shutil
from datetime import datetime, timezone, timedelta


from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QMenu, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QProgressBar, QDialog, QSpinBox, QComboBox, QPushButton, QFormLayout,
    QDialogButtonBox, QInputDialog
)
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal, QLockFile, QDir
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QCursor

import battery_reader
import structlog
import logging.config
import logging

__version__ = "1.3.4"

CONFIG_PATH = os.path.expanduser("~/.config/peripheral-battery-monitor.json")
CLAUDE_PROJECTS_PATH = os.path.expanduser("~/.claude/projects")


def is_claude_installed():
    """Check if Claude Code CLI is installed on the system."""
    return shutil.which('claude') is not None


def get_session_window(window_hours=4, reset_hour=2):
    """
    Calculate the current session window boundaries based on reset hour.
    Windows are aligned to the user's reset time (from Claude's /usage).

    For example, if reset_hour=2 and window_hours=4:
    - Windows are: 22:00-02:00, 02:00-06:00, 06:00-10:00, etc.

    Returns (window_start, window_end) as datetime objects in local timezone.
    """
    now = datetime.now().astimezone()
    current_hour = now.hour

    # Calculate all window boundary hours in a day (aligned to reset_hour)
    # E.g., reset_hour=2, window_hours=4 → boundaries at [2, 6, 10, 14, 18, 22]
    boundaries = [(reset_hour + i * window_hours) % 24 for i in range(24 // window_hours)]
    boundaries.sort()

    # Find which window we're in
    window_end_hour = None
    for i, boundary in enumerate(boundaries):
        if current_hour < boundary:
            window_end_hour = boundary
            break

    # If we didn't find one, we're past the last boundary → next window is first boundary tomorrow
    if window_end_hour is None:
        window_end_hour = boundaries[0]
        # Window ends tomorrow
        window_end = now.replace(hour=window_end_hour, minute=0, second=0, microsecond=0) + timedelta(days=1)
    else:
        window_end = now.replace(hour=window_end_hour, minute=0, second=0, microsecond=0)

    # Window start is window_hours before window end
    window_start = window_end - timedelta(hours=window_hours)

    return window_start, window_end


def get_time_until_reset(window_start, window_end):
    """Calculate time remaining until window resets, with window times displayed."""
    now = datetime.now().astimezone()
    delta = window_end - now

    # Format window times in 24H format
    start_time = window_start.strftime("%H:%M")
    end_time = window_end.strftime("%H:%M")
    window_str = f"{start_time}-{end_time}"

    if delta.total_seconds() <= 0:
        return f"{window_str} (resetting...)"

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    if hours > 0:
        return f"{window_str} ({hours}h {minutes}m)"
    else:
        return f"{window_str} ({minutes}m)"


def get_claude_stats(window_start=None, window_end=None):
    """
    Read and parse Claude Code usage from session files within the time window.
    If no window specified, uses all files modified today.
    """
    if not os.path.exists(CLAUDE_PROJECTS_PATH):
        return None

    try:
        total_input = 0
        total_output = 0
        total_cache_read = 0
        total_cache_create = 0
        api_calls = 0
        files_processed = 0

        # Convert window times to timestamps for comparison
        if window_start and window_end:
            window_start_ts = window_start.timestamp()
            window_end_ts = window_end.timestamp()
        else:
            # Fallback: use today (UTC)
            today = datetime.now(timezone.utc).date()
            window_start_ts = None
            window_end_ts = None

        for root, dirs, files in os.walk(CLAUDE_PROJECTS_PATH):
            for f in files:
                if f.endswith('.jsonl'):
                    path = os.path.join(root, f)
                    file_mtime = os.path.getmtime(path)

                    # Filter by window if specified
                    if window_start_ts and window_end_ts:
                        # Skip files not modified within window
                        if file_mtime < window_start_ts or file_mtime > window_end_ts:
                            continue
                    else:
                        # Fallback: only files modified today
                        mtime_date = datetime.fromtimestamp(file_mtime, tz=timezone.utc).date()
                        if mtime_date != today:
                            continue

                    files_processed += 1

                    # Parse this session file, filtering by timestamp if needed
                    with open(path, 'r') as fp:
                        for line in fp:
                            try:
                                data = json.loads(line)

                                # Check timestamp if window filtering
                                if window_start_ts and window_end_ts:
                                    # Try to get timestamp from the message
                                    msg_ts = data.get('timestamp')
                                    if msg_ts:
                                        # Parse ISO timestamp
                                        try:
                                            msg_time = datetime.fromisoformat(msg_ts.replace('Z', '+00:00'))
                                            msg_timestamp = msg_time.timestamp()
                                            if msg_timestamp < window_start_ts or msg_timestamp > window_end_ts:
                                                continue
                                        except (ValueError, AttributeError):
                                            pass

                                if 'message' in data and isinstance(data['message'], dict):
                                    usage = data['message'].get('usage', {})
                                    if usage:
                                        api_calls += 1
                                        total_input += usage.get('input_tokens', 0)
                                        total_output += usage.get('output_tokens', 0)
                                        total_cache_read += usage.get('cache_read_input_tokens', 0)
                                        total_cache_create += usage.get('cache_creation_input_tokens', 0)
                            except json.JSONDecodeError:
                                pass

        if files_processed == 0:
            return None

        return {
            'session_tokens': total_input + total_output,
            'input_tokens': total_input,
            'output_tokens': total_output,
            'cache_read': total_cache_read,
            'cache_create': total_cache_create,
            'api_calls': api_calls,
            'files_processed': files_processed,
            'window_start': window_start,
            'window_end': window_end
        }
    except Exception:
        return None


def setup_logging(debug_mode=False):
    log_file = os.path.expanduser("~/.local/state/peripheral-battery-monitor/peripheral_battery.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.processors.JSONRenderer(),
            },
            "console": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processor": structlog.dev.ConsoleRenderer(colors=True),
            },
        },
        "handlers": {
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": log_file,
                "maxBytes": 5 * 1024 * 1024, # 5MB
                "backupCount": 1,
                "formatter": "json",
                "level": "DEBUG",
            },
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "level": "DEBUG" if debug_mode else "INFO",
            },
        },
        "loggers": {
            "": {
                "handlers": ["file", "console"],
                "level": "DEBUG",
                "propagate": True,
            },
        }
    })

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

class UpdateThread(QThread):
    data_ready = pyqtSignal(dict)

    def run(self):
        results = {}
        try:
            # Run the reader in a separate process to avoid resource leaks (DBus/asyncio)
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battery_reader.py")
            cmd = [sys.executable, script_path, "--json"]
            
            # Timeout to prevent hanging threads
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            
            if proc.returncode == 0:
                raw_data = json.loads(proc.stdout)
                
                # Reconstruct BatteryInfo objects
                for key, val in raw_data.items():
                    if val is not None:
                         # We need to handle the dict -> Object conversion
                         # BatteryInfo is a dataclass, so we can unpack
                         results[key] = battery_reader.BatteryInfo(**val)
            else:
                log = structlog.get_logger()
                log.error("reader_failed", returncode=proc.returncode, stderr=proc.stderr)

        except Exception as e:
            log = structlog.get_logger()
            log.error("update_failed", error=str(e))
        
        self.data_ready.emit(results)


class CalibrationDialog(QDialog):
    """Dialog for calibrating Claude usage display to match actual billing."""

    def __init__(self, parent, current_tokens, current_budget, current_percentage):
        super().__init__(parent)
        self.current_tokens = current_tokens
        self.current_budget = current_budget
        self.current_percentage = current_percentage
        self.result_budget = current_budget

        self.setWindowTitle("Calibrate Claude Usage")
        self.setModal(True)
        self.setup_ui()
        self.update_preview()

        # Ensure dialog fits on screen and is positioned properly
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

        # Center on screen (works better than centering on parent for small parent windows)
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = (screen.height() - self.height()) // 2
        self.move(x, y)

    def setup_ui(self):
        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Apply dark theme
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
            }
            QSpinBox, QComboBox {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px;
                min-width: 120px;
            }
            QPushButton {
                background-color: #3d3d3d;
                color: #e0e0e0;
                border: 1px solid #555;
                padding: 4px 12px;
                min-width: 60px;
            }
            QPushButton:hover {
                background-color: #4d4d4d;
            }
            QPushButton:pressed {
                background-color: #555;
            }
        """)

        def format_tokens(n):
            if n >= 1000000:
                return f"{n / 1000000:.1f}M"
            elif n >= 1000:
                return f"{n / 1000:.1f}k"
            return str(int(n))

        # Show current state inline
        current_lbl = QLabel(f"{format_tokens(self.current_tokens)} / {format_tokens(self.current_budget)} = {self.current_percentage}%")
        current_lbl.setStyleSheet("color: #888;")
        layout.addRow("Current:", current_lbl)

        # Target percentage input
        self.target_spin = QSpinBox()
        self.target_spin.setRange(1, 200)
        self.target_spin.setValue(self.current_percentage if self.current_percentage > 0 else 25)
        self.target_spin.setSuffix("%")
        self.target_spin.valueChanged.connect(self.update_preview)
        layout.addRow("Target %:", self.target_spin)

        # Adjustment mode
        self.adjust_combo = QComboBox()
        self.adjust_combo.addItems([
            "Adjust budget",
            "Adjust tokens"
        ])
        self.adjust_combo.currentIndexChanged.connect(self.update_preview)
        layout.addRow("Method:", self.adjust_combo)

        # Preview result
        self.preview_lbl = QLabel("--")
        self.preview_lbl.setStyleSheet("color: #4caf50; font-weight: bold;")
        layout.addRow("Result:", self.preview_lbl)

        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)

        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self.accept)
        apply_btn.setDefault(True)
        button_layout.addWidget(apply_btn)

        layout.addRow(button_layout)

    def update_preview(self):
        target_pct = self.target_spin.value()
        adjust_mode = self.adjust_combo.currentIndex()

        def format_tokens(n):
            if n >= 1000000:
                return f"{n / 1000000:.1f}M"
            elif n >= 1000:
                return f"{n / 1000:.1f}k"
            return str(int(n))

        if adjust_mode == 0:  # Adjust budget
            if target_pct > 0:
                new_budget = int(self.current_tokens / (target_pct / 100))
                self.result_budget = new_budget
                self.result_tokens = None
                self.preview_lbl.setText(f"Budget → {format_tokens(new_budget)}")
            else:
                self.preview_lbl.setText("Invalid percentage")
        else:  # Adjust token count (override)
            if self.current_budget > 0:
                new_tokens = int(self.current_budget * (target_pct / 100))
                self.result_budget = None
                self.result_tokens = new_tokens
                self.preview_lbl.setText(f"Tokens → {format_tokens(new_tokens)}")
            else:
                self.preview_lbl.setText("Unlimited budget - can't calibrate")

    def get_result(self):
        """Returns (new_budget, token_offset) or (None, None) if cancelled."""
        if self.adjust_combo.currentIndex() == 0:
            return (self.result_budget, None)
        else:
            # Token override: calculate offset from current counted tokens
            if hasattr(self, 'result_tokens') and self.result_tokens is not None:
                offset = self.result_tokens - self.current_tokens
                return (None, offset)
            return (None, None)


class PeripheralMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.worker = None

        self.initUI()
        self.setup_timer()

        # Update Claude section immediately with saved settings
        self.update_claude_section()

        # Delay initial update so window shows up first
        QTimer.singleShot(100, self.update_status)

    def load_settings(self):
        default_settings = {
            "opacity": 0.95,
            "font_scale": 1.0,
            "claude_section_enabled": True,
            "claude_session_budget": 500000,  # 500k tokens default
            "claude_window_hours": 4,  # 4-hour session window (Max plan)
            "claude_reset_hour": 2  # Reset hour from /usage (e.g., 2 = 2am)
        }
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    return {**default_settings, **json.load(f)}
            except Exception:
                pass
        return default_settings

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    def initUI(self):
        # Window flags: Frameless + StaysOnTop. Removed Tool to avoid Wayland coordinate bugs.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Set icon
        icon = QIcon.fromTheme("input-mouse")
        if icon.isNull():
             icon = QIcon.fromTheme("battery-full")
        self.setWindowIcon(icon)
        self.setWindowTitle("Battery Monitor")

        # Main Layout for the top-level widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container Frame - This is what we style and what the user sees
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        
        # Layout inside the container - Grid 2x2
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setContentsMargins(15, 12, 15, 12)
        self.grid_layout.setSpacing(15)

        # Create device widgets
        self.mouse_ui = self.create_device_cell("Mouse")
        self.kb_ui = self.create_device_cell("Keyboard")
        self.headset_ui = self.create_device_cell("Headset")
        self.airpods_ui = self.create_device_cell("AirPods")

        # Add to grid
        # (Row, Col)
        self.grid_layout.addLayout(self.mouse_ui['layout'], 0, 0)
        self.grid_layout.addLayout(self.kb_ui['layout'], 0, 1)
        self.grid_layout.addLayout(self.headset_ui['layout'], 1, 0)
        self.grid_layout.addLayout(self.airpods_ui['layout'], 1, 1)

        main_layout.addWidget(self.container)

        # Claude Code Section (conditionally shown)
        self.claude_section_visible = False
        self.claude_frame = None

        if is_claude_installed() and self.settings.get('claude_section_enabled', True):
            self.create_claude_section()
            main_layout.addWidget(self.claude_frame)
            self.claude_section_visible = True

        self.setMinimumWidth(260)  # Increased for 2x2 grid to avoid cutoff names on start
        self.update_style()
        self.adjustSize()

        # Default position
        self.move(100, 100)

    def create_device_cell(self, default_name):
        layout = QVBoxLayout()
        layout.setSpacing(2)
        
        name_lbl = QLabel(default_name, self)
        name_lbl.setObjectName("NameLabel")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        # Value Row with Icon
        h_layout = QHBoxLayout()
        h_layout.setContentsMargins(0, 0, 0, 0)
        h_layout.setSpacing(4)
        h_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        icon_lbl = QLabel(self)
        icon_lbl.setFixedSize(24, 24)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Initial Icon (Show 'missing' until first update)
        init_icon = QIcon.fromTheme("battery-missing")
        icon_lbl.setPixmap(init_icon.pixmap(24, 24))
        
        log = structlog.get_logger()
        log.debug("initial_icon_set", device=default_name)
        
        val_lbl = QLabel("--%", self)
        val_lbl.setObjectName("ValueLabel")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        h_layout.addWidget(icon_lbl)
        h_layout.addWidget(val_lbl)
        layout.addLayout(h_layout)
        
        stat_lbl = QLabel("Disconnected", self)
        stat_lbl.setObjectName("StatusLabel")
        stat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(stat_lbl)
        
        return {
            'layout': layout,
            'name_lbl': name_lbl,
            'val_lbl': val_lbl,
            'stat_lbl': stat_lbl,
            'icon_lbl': icon_lbl,
            'last_info': None,
            'default_name': default_name
        }

    def create_claude_section(self):
        """Create the Claude Code usage stats section."""
        self.claude_frame = QFrame(self)
        self.claude_frame.setObjectName("ClaudeSection")

        claude_layout = QVBoxLayout(self.claude_frame)
        claude_layout.setContentsMargins(15, 8, 15, 10)
        claude_layout.setSpacing(4)

        # Header row: title and session duration
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        # Icon
        icon_lbl = QLabel(self)
        icon = QIcon.fromTheme("dialog-scripts", QIcon.fromTheme("utilities-terminal"))
        icon_lbl.setPixmap(icon.pixmap(16, 16))
        header_row.addWidget(icon_lbl)

        # Title
        title_lbl = QLabel("Claude Code", self)
        title_lbl.setObjectName("ClaudeTitle")
        header_row.addWidget(title_lbl)

        header_row.addStretch()

        # Session duration
        self.claude_duration_lbl = QLabel("--", self)
        self.claude_duration_lbl.setObjectName("ClaudeReset")
        header_row.addWidget(self.claude_duration_lbl)

        claude_layout.addLayout(header_row)

        # Progress bar
        self.claude_progress = QProgressBar(self)
        self.claude_progress.setObjectName("ClaudeProgress")
        self.claude_progress.setMinimum(0)
        self.claude_progress.setMaximum(100)
        self.claude_progress.setValue(0)
        self.claude_progress.setTextVisible(False)
        self.claude_progress.setFixedHeight(8)
        claude_layout.addWidget(self.claude_progress)

        # Stats row: tokens and API calls
        stats_row = QHBoxLayout()

        self.claude_tokens_lbl = QLabel("-- tokens", self)
        self.claude_tokens_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_tokens_lbl)

        stats_row.addStretch()

        self.claude_calls_lbl = QLabel("0 calls", self)
        self.claude_calls_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_calls_lbl)

        claude_layout.addLayout(stats_row)

        return self.claude_frame

    def update_style(self):
        opacity = self.settings.get("opacity", 0.95)
        scale = self.settings.get("font_scale", 1.0)
        
        alpha = int(opacity * 255)
        
        # Base sizes
        val_size = int(22 * scale)
        name_size = int(11 * scale)
        stat_size = int(10 * scale)

        # We style the container specifically, not the global QWidget
        self.setStyleSheet(f"""
            QFrame#MainContainer {{
                background-color: rgba(43, 43, 43, {alpha});
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 12px;
            }}
            QLabel {{
                color: #e0e0e0;
                font-family: sans-serif;
                background: transparent;
            }}
            QLabel#ValueLabel {{
                font-size: {val_size}px;
                font-weight: bold;
                margin-bottom: 2px;
            }}
            QLabel#NameLabel {{
                font-size: {name_size}px;
                color: #aaaaaa;
                font-weight: bold;
            }}
            QLabel#StatusLabel {{
                font-size: {stat_size}px;
                color: #888888;
                font-style: italic;
            }}
            QFrame#ClaudeSection {{
                background-color: rgba(35, 35, 35, {alpha});
                border: 1px solid rgba(255, 255, 255, 15);
                border-radius: 8px;
                margin-top: 4px;
            }}
            QLabel#ClaudeTitle {{
                font-size: {name_size}px;
                color: #aaaaaa;
                font-weight: bold;
            }}
            QLabel#ClaudeReset {{
                font-size: {int(9 * scale)}px;
                color: #888888;
            }}
            QLabel#ClaudeStats {{
                font-size: {int(9 * scale)}px;
                color: #888888;
            }}
            QProgressBar#ClaudeProgress {{
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 4px;
            }}
            QProgressBar#ClaudeProgress::chunk {{
                background-color: #4caf50;
                border-radius: 4px;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.windowHandle():
                self.windowHandle().startSystemMove()

    def contextMenuEvent(self, event):
        contextMenu = QMenu(self)
        
        # Set dark theme for menu
        contextMenu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #444;
            }
            QMenu::item {
                padding: 4px 24px 4px 8px;
            }
            QMenu::item:selected {
                background-color: #3d3d3d;
            }
        """)

        # Opacity Submenu
        opacityMenu = contextMenu.addMenu("Opacity")
        opacity_group = QActionGroup(self)
        
        levels = [
            ("100%", 1.0),
            ("95%", 0.95),
            ("90%", 0.9),
            ("80%", 0.8),
            ("70%", 0.7),
        ]
        
        current_opacity = self.settings.get("opacity", 0.95)
        
        for label, val in levels:
            action = QAction(label, self, checkable=True)
            action.setData(val)
            action.triggered.connect(lambda checked, v=val: self.set_opacity(v))
            if abs(current_opacity - val) < 0.01:
                action.setChecked(True)
            opacity_group.addAction(action)
            opacityMenu.addAction(action)

        # Font Size Submenu
        fontMenu = contextMenu.addMenu("Font Size")
        font_group = QActionGroup(self)
        
        font_sizes = [
            ("Small", 0.8),
            ("Medium", 1.0),
            ("Large", 1.3),
        ]
        
        current_scale = self.settings.get("font_scale", 1.0)
        
        for label, val in font_sizes:
            action = QAction(label, self, checkable=True)
            action.setData(val)
            action.triggered.connect(lambda checked, v=val: self.set_font_scale(v))
            if abs(current_scale - val) < 0.01:
                action.setChecked(True)
            font_group.addAction(action)
            fontMenu.addAction(action)

        # Claude Section Menu (only if Claude is installed)
        if is_claude_installed():
            contextMenu.addSeparator()
            claudeMenu = contextMenu.addMenu("Claude Code")

            toggleAction = QAction("Show Session Stats", self, checkable=True)
            toggleAction.setChecked(self.settings.get('claude_section_enabled', True))
            toggleAction.triggered.connect(self.toggle_claude_section)
            claudeMenu.addAction(toggleAction)

            calibrateAction = QAction("Calibrate Usage...", self)
            calibrateAction.triggered.connect(self.show_calibration_dialog)
            claudeMenu.addAction(calibrateAction)

            claudeMenu.addSeparator()

            # Session Budget Submenu
            budgetMenu = claudeMenu.addMenu("Session Budget")
            budget_group = QActionGroup(self)

            budgets = [
                ("10k tokens", 10000),
                ("15k tokens", 15000),
                ("20k tokens", 20000),
                ("25k tokens", 25000),
                ("50k tokens", 50000),
                ("100k tokens", 100000),
                ("250k tokens", 250000),
                ("500k tokens", 500000),
                ("1M tokens", 1000000),
                ("Unlimited", 0),
            ]

            current_budget = self.settings.get("claude_session_budget", 500000)

            for label, val in budgets:
                action = QAction(label, self, checkable=True)
                action.setData(val)
                action.triggered.connect(lambda checked, v=val: self.set_claude_budget(v))
                if current_budget == val:
                    action.setChecked(True)
                budget_group.addAction(action)
                budgetMenu.addAction(action)

            budgetMenu.addSeparator()
            customBudgetAction = QAction("Custom...", self)
            customBudgetAction.triggered.connect(self.show_custom_budget_dialog)
            budgetMenu.addAction(customBudgetAction)

            # Window Duration Submenu
            windowMenu = claudeMenu.addMenu("Window Duration")
            window_group = QActionGroup(self)

            windows = [
                ("1 hour", 1),
                ("2 hours", 2),
                ("3 hours", 3),
                ("4 hours", 4),
                ("5 hours", 5),
                ("6 hours", 6),
                ("8 hours", 8),
                ("12 hours", 12),
            ]

            current_window = self.settings.get("claude_window_hours", 4)

            for label, val in windows:
                action = QAction(label, self, checkable=True)
                action.setData(val)
                action.triggered.connect(lambda checked, v=val: self.set_claude_window(v))
                if current_window == val:
                    action.setChecked(True)
                window_group.addAction(action)
                windowMenu.addAction(action)

            # Reset Hour Submenu (sync with /usage reset time)
            resetMenu = claudeMenu.addMenu("Reset Hour (from /usage)")
            reset_group = QActionGroup(self)

            # All 24 hours (window durations like 5h can have any reset hour)
            reset_hours = [
                ("12am (midnight)", 0),
                ("1am", 1),
                ("2am", 2),
                ("3am", 3),
                ("4am", 4),
                ("5am", 5),
                ("6am", 6),
                ("7am", 7),
                ("8am", 8),
                ("9am", 9),
                ("10am", 10),
                ("11am", 11),
                ("12pm (noon)", 12),
                ("1pm", 13),
                ("2pm", 14),
                ("3pm", 15),
                ("4pm", 16),
                ("5pm", 17),
                ("6pm", 18),
                ("7pm", 19),
                ("8pm", 20),
                ("9pm", 21),
                ("10pm", 22),
                ("11pm", 23),
            ]

            current_reset = self.settings.get("claude_reset_hour", 2)

            for label, val in reset_hours:
                action = QAction(label, self, checkable=True)
                action.setData(val)
                action.triggered.connect(lambda checked, v=val: self.set_claude_reset_hour(v))
                if current_reset == val:
                    action.setChecked(True)
                reset_group.addAction(action)
                resetMenu.addAction(action)

        contextMenu.addSeparator()

        refreshAct = QAction("Refresh Now", self)
        refreshAct.triggered.connect(self.update_status)
        contextMenu.addAction(refreshAct)

        quitAct = QAction("Quit", self)
        quitAct.triggered.connect(QApplication.instance().quit)
        contextMenu.addAction(quitAct)

        # Use popup() and global cursor position, verified to be the most reliable combo on Wayland.
        contextMenu.popup(QCursor.pos())

    def set_opacity(self, val):
        self.settings["opacity"] = val
        self.update_style()
        self.save_settings()

    def set_font_scale(self, val):
        self.settings["font_scale"] = val
        self.update_style()
        self.adjustSize()
        self.save_settings()

    def toggle_claude_section(self, checked):
        """Toggle Claude Code section visibility."""
        self.settings["claude_section_enabled"] = checked
        self.save_settings()

        if checked and is_claude_installed():
            if self.claude_frame is None:
                self.create_claude_section()
                self.layout().addWidget(self.claude_frame)
            self.claude_frame.show()
            self.claude_section_visible = True
            self.update_claude_section()
        elif self.claude_frame is not None:
            self.claude_frame.hide()
            self.claude_section_visible = False

        self.adjustSize()

    def set_claude_budget(self, val):
        """Set the session token budget for Claude Code."""
        self.settings["claude_session_budget"] = val
        self.save_settings()
        self.update_claude_section()

    def set_claude_window(self, val):
        """Set the session window duration in hours."""
        self.settings["claude_window_hours"] = val
        self.save_settings()
        self.update_claude_section()

    def set_claude_reset_hour(self, val):
        """Set the reset hour (from Claude's /usage display)."""
        self.settings["claude_reset_hour"] = val
        self.save_settings()
        self.update_claude_section()

    def show_calibration_dialog(self):
        """Show the calibration dialog to snap usage to a known percentage."""
        # Get current values
        window_hours = self.settings.get('claude_window_hours', 4)
        reset_hour = self.settings.get('claude_reset_hour', 2)
        window_start, window_end = get_session_window(window_hours, reset_hour)
        stats = get_claude_stats(window_start, window_end)

        current_tokens = stats['session_tokens'] if stats else 0
        current_budget = self.settings.get('claude_session_budget', 500000)

        if current_budget > 0:
            current_percentage = int((current_tokens / current_budget) * 100)
        else:
            current_percentage = 0

        # Add any existing token offset
        token_offset = self.settings.get('claude_token_offset', 0)
        current_tokens += token_offset

        dialog = CalibrationDialog(self, current_tokens, current_budget, current_percentage)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_budget, token_offset = dialog.get_result()

            if new_budget is not None:
                self.settings['claude_session_budget'] = new_budget
                # Clear any previous token offset when adjusting budget
                self.settings['claude_token_offset'] = 0
            elif token_offset is not None:
                # Store offset to apply to counted tokens
                existing_offset = self.settings.get('claude_token_offset', 0)
                self.settings['claude_token_offset'] = existing_offset + token_offset

            self.save_settings()
            self.update_claude_section()

    def show_custom_budget_dialog(self):
        """Show dialog to enter a custom budget value."""
        current_budget = self.settings.get('claude_session_budget', 500000)

        # Use QInputDialog for simple integer input
        value, ok = QInputDialog.getInt(
            self,
            "Custom Budget",
            "Enter token budget (0 for unlimited):",
            value=current_budget,
            min=0,
            max=10000000,
            step=10000
        )

        if ok:
            self.settings['claude_session_budget'] = value
            self.save_settings()
            self.update_claude_section()

    def setup_timer(self):
        # Update every 30 seconds
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(30000) 

    def update_status(self):
        # Prevent overlap
        if self.worker and self.worker.isRunning():
            return

    def update_status(self):
        # Prevent overlap
        if self.worker is not None:
             # Just in case it's lingering but finished? 
             # No, if it's not None it implies running or not cleaned up.
             # We rely on on_worker_finished to clean it up.
             return

        # Start worker thread
        self.worker = UpdateThread()
        self.worker.data_ready.connect(self.on_data_ready)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.start()
    
    def on_worker_finished(self):
        # Safely clear the reference
        self.worker = None

    def update_claude_section(self):
        """Update the Claude Code usage stats display."""
        # Check if section should be visible based on settings (not transient state)
        if not self.settings.get('claude_section_enabled', True) or self.claude_frame is None:
            return

        # Ensure section is visible if it should be
        if not self.claude_section_visible:
            self.claude_frame.show()
            self.claude_section_visible = True

        # Get window boundaries based on configured window hours and reset hour
        window_hours = self.settings.get('claude_window_hours', 4)
        reset_hour = self.settings.get('claude_reset_hour', 2)
        window_start, window_end = get_session_window(window_hours, reset_hour)

        # Get stats for current window
        stats = get_claude_stats(window_start, window_end)
        if stats is None:
            # Show "no data" state instead of hiding
            self.claude_progress.setValue(0)
            self.claude_tokens_lbl.setText("No activity")
            self.claude_calls_lbl.setText("0 calls")
            self.claude_duration_lbl.setText(get_time_until_reset(window_start, window_end))
            return

        # Format token counts (use k for thousands, M for millions)
        def format_tokens(n):
            if n >= 1000000:
                return f"{n / 1000000:.1f}M"
            elif n >= 1000:
                return f"{n / 1000:.1f}k"
            else:
                return str(int(n))

        session_tokens = stats['session_tokens']
        # Apply any calibration offset
        token_offset = self.settings.get('claude_token_offset', 0)
        session_tokens += token_offset
        session_tokens = max(0, session_tokens)  # Don't go negative

        api_calls = stats['api_calls']
        budget = self.settings.get('claude_session_budget', 500000)

        # Update progress bar
        if budget > 0:
            progress = min(100, int((session_tokens / budget) * 100))
            self.claude_progress.setValue(progress)

            # Color code: green < 50%, yellow 50-80%, red > 80%
            if progress >= 80:
                color = "#f44336"  # Red
            elif progress >= 50:
                color = "#ff9800"  # Orange/Yellow
            else:
                color = "#4caf50"  # Green

            self.claude_progress.setStyleSheet(f"""
                QProgressBar#ClaudeProgress {{
                    background-color: rgba(255, 255, 255, 0.1);
                    border: none;
                    border-radius: 4px;
                }}
                QProgressBar#ClaudeProgress::chunk {{
                    background-color: {color};
                    border-radius: 4px;
                }}
            """)

            self.claude_tokens_lbl.setText(f"{format_tokens(session_tokens)} / {format_tokens(budget)} ({progress}%)")
        else:
            # Unlimited - no progress bar
            self.claude_progress.setValue(0)
            self.claude_tokens_lbl.setText(f"{format_tokens(session_tokens)} tokens")

        self.claude_calls_lbl.setText(f"{api_calls} calls")
        self.claude_duration_lbl.setText(get_time_until_reset(window_start, window_end))

    def on_data_ready(self, results):
        # 1. Update Mouse - Now comes from results like everything else
        self.update_single_device(self.mouse_ui, lambda: results.get('mouse'), use_offline_cache=True)
        
        # 2. Update Keyboard
        self.update_single_device(self.kb_ui, lambda: results.get('kb'), use_offline_cache=True)

        # 3. Update Headset - User wants immediate "Disconnected" state, no offline cache
        self.update_single_device(self.headset_ui, lambda: results.get('headset'), use_offline_cache=False)

        # 4. Update AirPods - User wants "Disconnected", no offline cache
        self.update_single_device(self.airpods_ui, lambda: results.get('airpods'), use_offline_cache=False)

        # 5. Update Claude Code section
        self.update_claude_section()

        self.setToolTip(f"Last updated: {self.format_time()}")
        self.adjustSize()

        # NOTE: Cleanup is handled by finished signal now

    def update_single_device(self, ui_dict, func_to_call, use_offline_cache=True):
        try:
            current_info = func_to_call()
            last_known = ui_dict.get('last_info')

            # Detect status change (e.g., Charging -> Discharging).
            # When status changes, invalidate the cached level because the battery
            # situation has fundamentally changed and old levels may be stale.
            status_changed = False
            if current_info and last_known:
                current_status = current_info.status.lower() if current_info.status else ""
                last_status = last_known.status.lower() if last_known.status else ""

                # Check for meaningful status transitions
                charging_states = {"charging", "full", "recharging"}
                discharging_states = {"discharging", "slow discharging"}

                current_is_charging = any(s in current_status for s in charging_states)
                last_is_charging = any(s in last_status for s in charging_states)
                current_is_discharging = any(s in current_status for s in discharging_states)
                last_is_discharging = any(s in last_status for s in discharging_states)

                # Status changed if we went from charging to discharging or vice versa
                if (current_is_charging and last_is_discharging) or (current_is_discharging and last_is_charging):
                    status_changed = True
                    # Clear cached info on status transition to force fresh display
                    ui_dict['last_info'] = None
                    last_known = None

            # Smart Fallback Logic for "Connected" but "--%" (Level -1)
            # Only use merged level if status hasn't changed
            if current_info and current_info.level == -1 and current_info.status == "Connected":
                 if last_known and last_known.level >= 0 and not status_changed:
                     # Create a merged info object
                     merged = battery_reader.BatteryInfo(
                         level=last_known.level,
                         status=current_info.status,
                         voltage=last_known.voltage,
                         device_name=current_info.device_name,
                         details=last_known.details
                     )
                     current_info = merged

            # If we got info with valid level, update last known.
            if current_info and current_info.level >= 0:
                ui_dict['last_info'] = current_info

            # Decide what info to pass to display logic
            display_info = current_info
            last_valid = ui_dict.get('last_info')

            if use_offline_cache:
                display_info = current_info or last_valid

            self._update_label_block(
                ui_dict['name_lbl'],
                ui_dict['val_lbl'],
                ui_dict['stat_lbl'],
                ui_dict['icon_lbl'],
                display_info,
                last_valid if use_offline_cache else None,
                ui_dict['default_name']
            )
        except Exception as e:
            # print(f"Error updating {ui_dict['default_name']}: {e}")
            pass

    def _update_label_block(self, name_lbl, val_lbl, stat_lbl, icon_lbl, current_info, last_info, fallback_name):
        info = current_info or last_info
        
        is_offline = current_info is None and last_info is not None
        
        icon_name = "battery-missing"
        
        if info:
            level = info.level
            
            # Icon Logic
            if level >= 0:
                # Round to nearest 10
                rounded = int(level / 10) * 10
                icon_name = f"battery-level-{rounded}"
                
                # Check status for charging
                if "Charging" in info.status or "Full" in info.status:
                     # Some themes have battery-charging-XX, others just battery-charging
                     # We'll try generic charging or charging-XX if logic permitted, but strictly:
                     if level == 100:
                         icon_name = "battery-charging-100"
                     else:
                         icon_name = f"battery-charging-{rounded}"
                         # Fallback if that specific icon doesn't exist? QIcon.fromTheme handles fallbacks if provided.
                         # But safely, 'battery-charging' is standard.
                         # Let's try explicit levels first.
            
            # Update Icon
            icon = QIcon.fromTheme(icon_name, QIcon.fromTheme("battery-missing"))
            icon_lbl.setPixmap(icon.pixmap(24, 24))
            
            # Handle special "Unknown Level but Connected" state
            # Handle special "Unknown Level but Connected" state
            if level == -1:
                val_text = '<span style="color: #e0e0e0;">--%</span>' # Light gray/white for connected
            elif info.details and ('left' in info.details or 'right' in info.details or 'case' in info.details):
                # We have L/R OR Case details
                parts = []
                if 'left' in info.details: 
                    l = info.details['left']
                    c_l = "#4caf50" if l > 20 else "#f44336"
                    parts.append(f'<span style="color:{c_l}">L:{l}%</span>')
                if 'right' in info.details:
                    r = info.details['right']
                    c_r = "#4caf50" if r > 20 else "#f44336"
                    parts.append(f'<span style="color:{c_r}">R:{r}%</span>')
                if 'case' in info.details:
                    c = info.details['case']
                    c_c = "#4caf50" if c > 20 else "#f44336"
                    parts.append(f'<span style="color:{c_c}">C:{c}%</span>')
                
                # Use a smaller font size for the combined string
                joined = " ".join(parts)
                val_text = f'<span style="font-size: 13px;">{joined}</span>'
            else:
                color = "#4caf50" if not is_offline else "#558b2f"
                if level <= 20:
                    color = "#f44336" if not is_offline else "#c62828"
                elif level <= 50:
                    color = "#ff9800" if not is_offline else "#ef6c00"
                val_text = f'<span style="color: {color};">{level}%</span>'
            
            # Use device name if available, otherwise fallback
            disp_name = info.device_name if info.device_name else fallback_name
            # Truncate if too long?
            if len(disp_name) > 20: 
                disp_name = disp_name[:18] + ".."
            
            name_lbl.setText(disp_name)
            val_lbl.setText(val_text)
            
            status_text = info.status
            if "BatteryStatus." in status_text:
                status_text = status_text.replace("BatteryStatus.", "").capitalize()
            elif status_text == "Unknown":
                status_text = "Connected"
                
            if is_offline:
                status_text = "(Offline)"
                
            if status_text:
                if status_text == "Wired":
                    val_text = '<span style="color: #4caf50;">Wired</span>'
                    icon_name = "input-keyboard" # Or plug icon
                elif status_text == "Wireless":
                    val_text = '<span style="color: #4caf50;">Wireless</span>'
                    icon_name = "network-wireless"

            stat_lbl.setText(status_text)
            
            # If we overrode icon_name above, update it
            if status_text in ["Wired", "Wireless"]:
                 icon = QIcon.fromTheme(icon_name)
                 icon_lbl.setPixmap(icon.pixmap(24, 24))
        else:
            name_lbl.setText(fallback_name)
            val_lbl.setText('<span style="color: gray;">--%</span>')
            stat_lbl.setText("Disconnected")
            
            icon = QIcon.fromTheme("battery-missing")
            icon_lbl.setPixmap(icon.pixmap(24, 24))

    def format_time(self):
        from PyQt6.QtCore import QTime
        return QTime.currentTime().toString("HH:mm:ss")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Single Instance Lock
    lock = QLockFile(QDir.tempPath() + "/peripheral-battery-monitor.lock")
    if not lock.tryLock(100):
        print("Another instance is already running.")
        sys.exit(1)

    debug_mode = "--debug" in sys.argv
    setup_logging(debug_mode)

    # redirect stderr to file
    stderr_path = os.path.expanduser("~/.local/state/peripheral-battery-monitor/stderr.log")
    try:
        stderr_fd = os.open(stderr_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC)
        os.dup2(stderr_fd, 2)
        # We don't close stderr_fd because 2 is now a copy of it, 
        # but we can close the original descriptor if we want.
        # Keeping it open is fine.
    except Exception as e:
        pass
    
    # Fault Handler for hard crashes (SIGSEGV/SIGABRT)
    crash_log_path = os.path.expanduser("~/.local/state/peripheral-battery-monitor/crash.log")
    try:
        crash_fd = open(crash_log_path, 'a')
        faulthandler.enable(file=crash_fd, all_threads=True)
    except Exception as e:
        print(f"Failed to enable faulthandler: {e}", file=sys.stderr)

    log = structlog.get_logger()
    log.info("app_started", version=__version__, debug=debug_mode)

    app = QApplication(sys.argv)
    app.setApplicationName("peripheral-battery-monitor")
    app.setDesktopFileName("peripheral-battery-monitor")
    
    ex = PeripheralMonitor()
    ex.show()
    
    sys.exit(app.exec())
