
import sys
import signal
import json
import os
import subprocess
import faulthandler
import shutil
from datetime import datetime, timezone, timedelta


from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu, QVBoxLayout, QHBoxLayout, QGridLayout, QFrame, QProgressBar
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal, QLockFile, QDir
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QCursor

import battery_reader
import structlog
import logging.config
import logging

__version__ = "1.3.0"

CONFIG_PATH = os.path.expanduser("~/.config/peripheral-battery-monitor.json")
CLAUDE_STATS_PATH = os.path.expanduser("~/.claude/stats-cache.json")


def is_claude_installed():
    """Check if Claude Code CLI is installed on the system."""
    return shutil.which('claude') is not None


def get_claude_stats():
    """Read and parse Claude Code usage statistics from stats-cache.json."""
    if not os.path.exists(CLAUDE_STATS_PATH):
        return None

    try:
        with open(CLAUDE_STATS_PATH, 'r') as f:
            data = json.load(f)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Find today's token usage by summing all models
        today_tokens = 0
        for entry in data.get('dailyModelTokens', []):
            if entry.get('date') == today:
                for model, tokens in entry.get('tokensByModel', {}).items():
                    today_tokens += tokens
                break

        return {
            'today_tokens': today_tokens,
            'last_computed': data.get('lastComputedDate'),
            'total_sessions': data.get('totalSessions', 0),
            'total_messages': data.get('totalMessages', 0)
        }
    except Exception:
        return None


def get_time_until_reset():
    """Calculate time until daily quota resets at midnight UTC."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = tomorrow - now

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    return f"{hours}h {minutes}m"


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

class PeripheralMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.worker = None
        
        self.initUI()
        self.setup_timer()
        
        # Delay initial update so window shows up first
        QTimer.singleShot(100, self.update_status)

    def load_settings(self):
        default_settings = {
            "opacity": 0.95,
            "font_scale": 1.0,
            "claude_section_enabled": True,
            "claude_daily_limit": 500000
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

        # Header row: title and reset time
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

        # Reset time
        self.claude_reset_lbl = QLabel("--h --m", self)
        self.claude_reset_lbl.setObjectName("ClaudeReset")
        header_row.addWidget(self.claude_reset_lbl)

        claude_layout.addLayout(header_row)

        # Progress bar
        self.claude_progress = QProgressBar(self)
        self.claude_progress.setObjectName("ClaudeProgress")
        self.claude_progress.setMinimum(0)
        self.claude_progress.setMaximum(100)
        self.claude_progress.setValue(0)
        self.claude_progress.setTextVisible(True)
        self.claude_progress.setFormat("%p%")
        self.claude_progress.setFixedHeight(14)
        claude_layout.addWidget(self.claude_progress)

        # Stats row: tokens used / limit and remaining
        stats_row = QHBoxLayout()

        self.claude_tokens_lbl = QLabel("0 / 500k", self)
        self.claude_tokens_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_tokens_lbl)

        stats_row.addStretch()

        self.claude_remaining_lbl = QLabel("500k left", self)
        self.claude_remaining_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_remaining_lbl)

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
                background-color: #1a1a1a;
                border: 1px solid #444;
                border-radius: 4px;
                text-align: center;
                color: #e0e0e0;
                font-size: {int(9 * scale)}px;
            }}
            QProgressBar#ClaudeProgress::chunk {{
                background-color: #4caf50;
                border-radius: 3px;
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

            toggleAction = QAction("Show Usage Stats", self, checkable=True)
            toggleAction.setChecked(self.settings.get('claude_section_enabled', True))
            toggleAction.triggered.connect(self.toggle_claude_section)
            claudeMenu.addAction(toggleAction)

            # Daily Limit Submenu
            limitMenu = claudeMenu.addMenu("Daily Limit")
            limit_group = QActionGroup(self)

            limits = [
                ("100k tokens", 100000),
                ("250k tokens", 250000),
                ("500k tokens", 500000),
                ("1M tokens", 1000000),
                ("Unlimited", 0),
            ]

            current_limit = self.settings.get('claude_daily_limit', 500000)

            for label, val in limits:
                action = QAction(label, self, checkable=True)
                action.setData(val)
                action.triggered.connect(lambda checked, v=val: self.set_claude_limit(v))
                if current_limit == val:
                    action.setChecked(True)
                limit_group.addAction(action)
                limitMenu.addAction(action)

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

    def set_claude_limit(self, val):
        """Set the daily token limit for Claude Code usage tracking."""
        self.settings["claude_daily_limit"] = val
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
        if not self.claude_section_visible or self.claude_frame is None:
            return

        stats = get_claude_stats()
        if stats is None:
            # Hide section if stats unavailable
            self.claude_frame.hide()
            self.claude_section_visible = False
            self.adjustSize()
            return

        today_tokens = stats['today_tokens']
        daily_limit = self.settings.get('claude_daily_limit', 500000)

        # Calculate remaining and percentage
        if daily_limit > 0:
            remaining = max(0, daily_limit - today_tokens)
            percentage = min(100, (today_tokens / daily_limit) * 100)
        else:
            # Unlimited mode - show 0% used
            remaining = float('inf')
            percentage = 0

        # Update progress bar
        self.claude_progress.setValue(int(percentage))
        self._update_claude_progress_color(percentage)

        # Format token counts (use k for thousands)
        def format_tokens(n):
            if n == float('inf'):
                return "∞"
            elif n >= 1000:
                return f"{n / 1000:.1f}k"
            else:
                return str(int(n))

        used_str = format_tokens(today_tokens)
        limit_str = format_tokens(daily_limit) if daily_limit > 0 else "∞"
        remaining_str = format_tokens(remaining)

        self.claude_tokens_lbl.setText(f"{used_str} / {limit_str}")
        self.claude_remaining_lbl.setText(f"{remaining_str} left")
        self.claude_reset_lbl.setText(get_time_until_reset())

    def _update_claude_progress_color(self, percentage):
        """Update progress bar color based on usage percentage."""
        if percentage < 50:
            color = "#4caf50"  # Green
        elif percentage < 75:
            color = "#ff9800"  # Yellow/Orange
        else:
            color = "#f44336"  # Red

        self.claude_progress.setStyleSheet(f"""
            QProgressBar#ClaudeProgress::chunk {{
                background-color: {color};
                border-radius: 3px;
            }}
        """)

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
            
            # Smart Fallback Logic for "Connected" but "--%" (Level -1)
            if current_info and current_info.level == -1 and current_info.status == "Connected":
                 last_known = ui_dict.get('last_info')
                 if last_known and last_known.level >= 0:
                     # Create a merged info object
                     merged = battery_reader.BatteryInfo(
                         level=last_known.level,
                         status=current_info.status,
                         voltage=last_known.voltage,
                         device_name=current_info.device_name,
                         details=last_known.details
                     )
                     current_info = merged
            
            # If we got info, update last known.
            if current_info and current_info.level >= 0:
                ui_dict['last_info'] = current_info
            
            # Decide what info to pass to display logic
            display_info = current_info
            last_valid = ui_dict['last_info']
            
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
