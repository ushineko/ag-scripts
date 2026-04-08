
import sys
import signal
import json
import os
import subprocess
import faulthandler
import shutil
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


from PyQt6.QtWidgets import (
    QApplication, QLabel, QWidget, QMenu, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QProgressBar, QPushButton
)
from PyQt6.QtCore import Qt, QTimer, QThread, pyqtSignal, QLockFile, QDir
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QCursor

import battery_reader
import structlog
import logging.config
import logging

__version__ = "1.5.5"

CONFIG_PATH = os.path.expanduser("~/.config/peripheral-battery-monitor.json")
CLAUDE_CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")

CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
CLAUDE_USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
CLAUDE_TOKEN_URL = "https://console.anthropic.com/api/oauth/token"
CLAUDE_USER_AGENT = "claude-code/2.1.42"
CLAUDE_BETA_HEADER = "oauth-2025-04-20"

# OAuth refresh backoff state (in-memory only, resets on app restart)
_oauth_backoff_until: float = 0.0   # monotonic timestamp; skip refresh if now < this
_oauth_fail_count: int = 0          # consecutive refresh failures
_oauth_creds_mtime: float = 0.0     # last-seen mtime of credentials file

# Usage API backoff state (in-memory only, resets on app restart)
_usage_backoff_until: float = 0.0   # monotonic timestamp; skip usage call if now < this
_usage_fail_count: int = 0          # consecutive usage API failures

# Usage API backoff constants (seconds)
_USAGE_BACKOFF_BASE = 60            # base delay for usage API errors
_USAGE_BACKOFF_CAP = 600            # max 10 minutes
_USAGE_429_DEFAULT_RETRY = 120      # default retry delay for 429 if no Retry-After header

# Backoff constants (seconds)
_BACKOFF_TRANSIENT_BASE = 30        # base delay for transient errors (timeout, network)
_BACKOFF_TRANSIENT_CAP = 300        # max 5 minutes
_BACKOFF_PERMANENT_BASE = 60        # base delay for permanent errors (401, 403)
_BACKOFF_PERMANENT_CAP = 1800       # max 30 minutes


def reset_oauth_backoff():
    """Reset OAuth backoff state, allowing the next refresh attempt immediately."""
    global _oauth_backoff_until, _oauth_fail_count
    _oauth_backoff_until = 0.0
    _oauth_fail_count = 0


def reset_usage_backoff():
    """Reset usage API backoff state, allowing the next call immediately."""
    global _usage_backoff_until, _usage_fail_count
    _usage_backoff_until = 0.0
    _usage_fail_count = 0


def is_claude_installed():
    """Check if Claude Code CLI is installed on the system."""
    return shutil.which('claude') is not None


def get_time_until_reset(resets_at: str) -> str:
    """Calculate time remaining until reset from an ISO 8601 timestamp string."""
    now = datetime.now(timezone.utc)
    try:
        reset_time = datetime.fromisoformat(resets_at)
    except (ValueError, TypeError):
        return "Unknown"

    delta = reset_time - now
    if delta.total_seconds() <= 0:
        return "Resetting..."

    hours = int(delta.total_seconds() // 3600)
    minutes = int((delta.total_seconds() % 3600) // 60)

    if hours > 0:
        return f"Resets in {hours}h {minutes}m"
    return f"Resets in {minutes}m"


def _read_credentials() -> dict | None:
    """Read and return the Claude OAuth credentials, or None if unavailable."""
    try:
        with open(CLAUDE_CREDENTIALS_PATH, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError):
        return None


def _refresh_oauth_token(refresh_token: str) -> tuple[dict | None, bool]:
    """Refresh the OAuth access token.

    Returns:
        (token_data, is_permanent_error) — token_data is the parsed JSON on
        success or None on failure.  is_permanent_error is True for HTTP 401/403
        (token revoked / invalid), False for transient errors (network, timeout).
    """
    log = structlog.get_logger()
    body = json.dumps({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLAUDE_OAUTH_CLIENT_ID,
    }).encode()

    req = urllib.request.Request(
        CLAUDE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read()), False
    except urllib.error.HTTPError as e:
        is_permanent = e.code in (401, 403)
        if _oauth_fail_count == 0:
            log.warning("oauth_refresh_failed", error=str(e), status=e.code)
        else:
            log.debug("oauth_refresh_failed", error=str(e), status=e.code,
                       fail_count=_oauth_fail_count)
        return None, is_permanent
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError) as e:
        if _oauth_fail_count == 0:
            log.warning("oauth_refresh_failed", error=str(e))
        else:
            log.debug("oauth_refresh_failed", error=str(e),
                       fail_count=_oauth_fail_count)
        return None, False


def _save_credentials(creds: dict) -> None:
    """Write updated credentials back to disk."""
    try:
        with open(CLAUDE_CREDENTIALS_PATH, 'w') as f:
            json.dump(creds, f)
    except OSError:
        pass


def _check_creds_mtime():
    """Check if the credentials file has been modified since last seen. If so, reset backoff."""
    global _oauth_creds_mtime
    try:
        mtime = os.stat(CLAUDE_CREDENTIALS_PATH).st_mtime
    except OSError:
        return
    if mtime > _oauth_creds_mtime:
        if _oauth_creds_mtime > 0 and _oauth_fail_count > 0:
            log = structlog.get_logger()
            log.info("oauth_backoff_reset_creds_changed")
            reset_oauth_backoff()
        _oauth_creds_mtime = mtime


def _apply_backoff(is_permanent: bool):
    """Compute and set the next backoff deadline after a failed refresh."""
    global _oauth_backoff_until, _oauth_fail_count
    _oauth_fail_count += 1
    if is_permanent:
        delay = min(_BACKOFF_PERMANENT_BASE * (2 ** (_oauth_fail_count - 1)),
                     _BACKOFF_PERMANENT_CAP)
    else:
        delay = min(_BACKOFF_TRANSIENT_BASE * (2 ** (_oauth_fail_count - 1)),
                     _BACKOFF_TRANSIENT_CAP)
    _oauth_backoff_until = time.monotonic() + delay
    log = structlog.get_logger()
    log.warning("oauth_backoff_engaged", next_retry_secs=delay,
                fail_count=_oauth_fail_count,
                error_type="permanent" if is_permanent else "transient")


def fetch_claude_usage() -> dict | None:
    """Fetch Claude Code usage from the Anthropic OAuth API.

    Reads the OAuth token from ~/.claude/.credentials.json, refreshes if expired,
    and calls GET /api/oauth/usage. Returns the parsed JSON response or None on error.
    Applies exponential backoff on repeated refresh failures.
    """
    global _oauth_backoff_until, _oauth_fail_count, _usage_backoff_until, _usage_fail_count
    log = structlog.get_logger()

    # Check usage API backoff before doing any work
    if time.monotonic() < _usage_backoff_until:
        log.debug("usage_api_skipped_backoff", fail_count=_usage_fail_count)
        return {"error": "rate_limited"}

    _check_creds_mtime()

    creds = _read_credentials()
    if not creds:
        return None

    oauth = creds.get("claudeAiOauth")
    if not oauth:
        return None

    access_token = oauth.get("accessToken")
    refresh_token = oauth.get("refreshToken")
    expires_at = oauth.get("expiresAt", 0)

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    if now_ms >= expires_at:
        if not refresh_token:
            log.warning("claude_token_expired_no_refresh")
            return {"error": "auth_expired"}

        # Check backoff before attempting refresh
        if time.monotonic() < _oauth_backoff_until:
            log.debug("oauth_refresh_skipped_backoff", fail_count=_oauth_fail_count)
            return {"error": "auth_backoff"}

        new_token_data, is_permanent = _refresh_oauth_token(refresh_token)
        if not new_token_data or "access_token" not in new_token_data:
            _apply_backoff(is_permanent)
            return {"error": "auth_expired"}

        # Success — reset backoff
        _oauth_fail_count = 0
        _oauth_backoff_until = 0.0

        access_token = new_token_data["access_token"]
        oauth["accessToken"] = access_token
        if "refresh_token" in new_token_data:
            oauth["refreshToken"] = new_token_data["refresh_token"]
        if "expires_in" in new_token_data:
            oauth["expiresAt"] = now_ms + new_token_data["expires_in"] * 1000
        _save_credentials(creds)

    req = urllib.request.Request(
        CLAUDE_USAGE_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "User-Agent": CLAUDE_USER_AGENT,
            "anthropic-beta": CLAUDE_BETA_HEADER,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            # Success — reset usage backoff
            if _usage_fail_count > 0:
                reset_usage_backoff()
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        _usage_fail_count += 1
        if e.code == 429:
            # Exponential backoff: base * 2^(failures-1), floored at default, capped at max
            exp_delay = min(_USAGE_429_DEFAULT_RETRY * (2 ** (_usage_fail_count - 1)),
                            _USAGE_BACKOFF_CAP)
            # If server sends a Retry-After header, use whichever is larger
            retry_after = e.headers.get("Retry-After") if e.headers else None
            if retry_after:
                try:
                    delay = max(int(retry_after), exp_delay)
                except ValueError:
                    delay = exp_delay
            else:
                delay = exp_delay
            _usage_backoff_until = time.monotonic() + delay
            if _usage_fail_count == 1:
                log.warning("claude_usage_rate_limited", retry_after_secs=delay)
            else:
                log.debug("claude_usage_rate_limited", retry_after_secs=delay,
                           fail_count=_usage_fail_count)
            return {"error": "rate_limited"}
        else:
            # Other HTTP errors: apply exponential backoff
            delay = min(_USAGE_BACKOFF_BASE * (2 ** (_usage_fail_count - 1)),
                         _USAGE_BACKOFF_CAP)
            _usage_backoff_until = time.monotonic() + delay
            log.warning("claude_usage_api_error", status=e.code,
                         backoff_secs=delay, fail_count=_usage_fail_count)
            return {"error": "api_error"}
    except (urllib.error.URLError, TimeoutError) as e:
        log.warning("claude_usage_network_error", error=str(e))
        return {"error": "offline"}
    except json.JSONDecodeError:
        log.warning("claude_usage_invalid_json")
        return {"error": "invalid_response"}


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
        
        try:
            results['claude_usage'] = fetch_claude_usage()
        except Exception as e:
            log = structlog.get_logger()
            log.error("claude_usage_fetch_failed", error=str(e))

        self.data_ready.emit(results)


class PeripheralMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        self.worker = None
        self._last_good_usage: dict | None = None  # cached last successful API response
        self._last_good_usage_time: float = 0.0     # monotonic timestamp of last good fetch

        self.initUI()
        self.setup_timer()

        # Delay initial update so window shows up first
        QTimer.singleShot(100, self.update_status)

    def load_settings(self):
        default_settings = {
            "opacity": 0.95,
            "font_scale": 1.0,
            "claude_section_enabled": True,
            "claude_activity_interval": 2,  # minutes (1-5)
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

        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        icon_lbl = QLabel(self)
        icon = QIcon.fromTheme("dialog-scripts", QIcon.fromTheme("utilities-terminal"))
        icon_lbl.setPixmap(icon.pixmap(16, 16))
        header_row.addWidget(icon_lbl)

        title_lbl = QLabel("Claude Code", self)
        title_lbl.setObjectName("ClaudeTitle")
        header_row.addWidget(title_lbl)

        header_row.addStretch()

        self.claude_duration_lbl = QLabel("--", self)
        self.claude_duration_lbl.setObjectName("ClaudeReset")
        header_row.addWidget(self.claude_duration_lbl)

        self.claude_backoff_icon = QLabel("⚠", self)
        self.claude_backoff_icon.setObjectName("ClaudeBackoff")
        self.claude_backoff_icon.hide()
        header_row.addWidget(self.claude_backoff_icon)

        refresh_btn = QPushButton("↻", self)
        refresh_btn.setObjectName("ClaudeRefreshBtn")
        refresh_btn.setFixedSize(18, 18)
        refresh_btn.setToolTip("Refresh usage stats")
        refresh_btn.clicked.connect(self._manual_refresh)
        header_row.addWidget(refresh_btn)

        claude_layout.addLayout(header_row)

        self.claude_progress = QProgressBar(self)
        self.claude_progress.setObjectName("ClaudeProgress")
        self.claude_progress.setMinimum(0)
        self.claude_progress.setMaximum(100)
        self.claude_progress.setValue(0)
        self.claude_progress.setTextVisible(False)
        self.claude_progress.setFixedHeight(8)
        claude_layout.addWidget(self.claude_progress)

        stats_row = QHBoxLayout()

        self.claude_five_hour_lbl = QLabel("5h: --", self)
        self.claude_five_hour_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_five_hour_lbl)

        stats_row.addStretch()

        self.claude_seven_day_lbl = QLabel("7d: --", self)
        self.claude_seven_day_lbl.setObjectName("ClaudeStats")
        stats_row.addWidget(self.claude_seven_day_lbl)

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
            QLabel#ClaudeBackoff {{
                font-size: {int(8 * scale)}px;
                color: #ff9800;
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
            QPushButton#ClaudeRefreshBtn {{
                background-color: transparent;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 4px;
                color: #888888;
                font-size: {int(11 * scale)}px;
                padding: 0px;
            }}
            QPushButton#ClaudeRefreshBtn:hover {{
                background-color: rgba(255, 255, 255, 20);
                color: #cccccc;
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

        if is_claude_installed():
            contextMenu.addSeparator()
            claudeMenu = contextMenu.addMenu("Claude Code")

            toggleAction = QAction("Show Usage Stats", self, checkable=True)
            toggleAction.setChecked(self.settings.get('claude_section_enabled', True))
            toggleAction.triggered.connect(self.toggle_claude_section)
            claudeMenu.addAction(toggleAction)

            activityMenu = claudeMenu.addMenu("Activity Check Interval")
            activity_group = QActionGroup(self)
            current_interval = self.settings.get("claude_activity_interval", 2)
            for minutes in (1, 2, 3, 5):
                action = QAction(f"{minutes} min", self, checkable=True)
                action.setData(minutes)
                action.triggered.connect(lambda checked, m=minutes: self._set_activity_interval(m))
                if current_interval == minutes:
                    action.setChecked(True)
                activity_group.addAction(action)
                activityMenu.addAction(action)

        contextMenu.addSeparator()

        refreshAct = QAction("Refresh Now", self)
        refreshAct.triggered.connect(self._manual_refresh)
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

    def _set_activity_interval(self, minutes):
        """Change the Claude activity check interval."""
        self.settings["claude_activity_interval"] = minutes
        self.save_settings()
        self.activity_timer.setInterval(minutes * 60000)

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

    def setup_timer(self):
        # Full refresh every 10 minutes
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(600000)

        # Staleness label update every 60 seconds (updates "Xm ago" while in backoff)
        self.staleness_timer = QTimer(self)
        self.staleness_timer.timeout.connect(self._tick_staleness)
        self.staleness_timer.start(60000)

        # Activity check — triggers refresh when Claude session files change
        self._claude_last_activity_mtime: float = 0.0
        interval_min = max(1, min(5, self.settings.get("claude_activity_interval", 2)))
        self.activity_timer = QTimer(self)
        self.activity_timer.timeout.connect(self._check_claude_activity)
        self.activity_timer.start(interval_min * 60000)

    def _tick_staleness(self):
        """Update the staleness label and backoff indicator if we're showing cached data."""
        if self._last_good_usage and self._last_good_usage_time > 0:
            # Only update if data is stale (more than 60s since last good fetch)
            elapsed = time.monotonic() - self._last_good_usage_time
            if elapsed > 60:
                self._update_staleness_label()
        self._update_backoff_indicator()

    def _check_claude_activity(self):
        """Check if Claude session files have been modified; trigger refresh on new activity."""
        latest = self._get_claude_latest_mtime()
        if latest <= self._claude_last_activity_mtime:
            return  # No new activity
        self._claude_last_activity_mtime = latest
        log = structlog.get_logger()
        log.debug("claude_activity_detected")
        self.update_status()

    @staticmethod
    def _get_claude_latest_mtime() -> float:
        """Return the newest mtime of any .jsonl file in Claude's projects directory."""
        projects_dir = os.path.expanduser("~/.claude/projects")
        latest = 0.0
        try:
            for subdir in os.scandir(projects_dir):
                if not subdir.is_dir():
                    continue
                for entry in os.scandir(subdir.path):
                    if entry.name.endswith(".jsonl") and entry.is_file():
                        try:
                            mt = entry.stat().st_mtime
                            if mt > latest:
                                latest = mt
                        except OSError:
                            continue
        except (OSError, PermissionError):
            pass
        return latest

    def _manual_refresh(self):
        """Handle 'Refresh Now' from context menu or button — resets all backoff and triggers update."""
        reset_oauth_backoff()
        reset_usage_backoff()
        self.update_status()

    def update_status(self):
        # Prevent overlap
        if self.worker is not None:
            return

        # Start worker thread
        self.worker = UpdateThread()
        self.worker.data_ready.connect(self.on_data_ready)
        self.worker.finished.connect(self._cleanup_worker)
        self.worker.start()

    def _cleanup_worker(self):
        """Clean up the finished worker thread safely.

        Captures the reference in a local variable before clearing self.worker,
        so the Python wrapper stays alive until deleteLater() is scheduled.
        This avoids a race where Python GC destroys the wrapper before Qt
        processes the deferred delete, which causes qFatal() -> abort().
        """
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()

    def update_claude_section(self, usage_data: dict | None = None):
        """Update the Claude Code usage stats display from API data."""
        if not self.settings.get('claude_section_enabled', True) or self.claude_frame is None:
            return

        if not self.claude_section_visible:
            self.claude_frame.show()
            self.claude_section_visible = True

        if usage_data is None:
            if self._last_good_usage:
                self._render_usage_data(self._last_good_usage)
                self._update_staleness_label()
                self._update_backoff_indicator()
                return
            self.claude_progress.setValue(0)
            self.claude_five_hour_lbl.setText("5h: --")
            self.claude_seven_day_lbl.setText("7d: --")
            self.claude_duration_lbl.setText("No data")
            return

        error = usage_data.get("error")
        if error:
            # Show cached data if available during any error
            if self._last_good_usage:
                self._render_usage_data(self._last_good_usage)
                self._update_staleness_label()
                self._update_backoff_indicator()
                return
            # No cached data — show error state
            self.claude_progress.setValue(0)
            labels = {
                "auth_expired": "Auth expired",
                "auth_backoff": "Auth retry...",
                "offline": "Offline",
                "api_error": "API error",
                "rate_limited": "Rate limited",
                "invalid_response": "No data",
            }
            self.claude_five_hour_lbl.setText(labels.get(error, "Error"))
            self.claude_seven_day_lbl.setText("")
            self.claude_duration_lbl.setText("")
            return

        # Success — cache and render
        self._last_good_usage = usage_data
        self._last_good_usage_time = time.monotonic()
        self._render_usage_data(usage_data)
        self._update_backoff_indicator()

    def _update_backoff_indicator(self):
        """Show/hide the backoff warning icon based on current backoff state."""
        if not hasattr(self, 'claude_backoff_icon'):
            return
        now = time.monotonic()
        if _usage_backoff_until > now or _oauth_backoff_until > now:
            remaining = max(_usage_backoff_until, _oauth_backoff_until) - now
            mins = int(remaining // 60) + 1
            self.claude_backoff_icon.setToolTip(
                f"Backoff ~{mins}m — increase activity interval")
            self.claude_backoff_icon.show()
        else:
            self.claude_backoff_icon.hide()
            self.claude_backoff_icon.setToolTip("")

    def _update_staleness_label(self):
        """Show how long ago the last successful refresh was, plus cached reset time."""
        if self._last_good_usage_time <= 0:
            self.claude_duration_lbl.setText("")
            return
        elapsed = time.monotonic() - self._last_good_usage_time
        minutes = int(elapsed // 60)
        if minutes < 1:
            ago = "(<1m ago)"
        elif minutes < 60:
            ago = f"({minutes}m ago)"
        else:
            hours = minutes // 60
            mins = minutes % 60
            ago = f"({hours}h{mins}m ago)"

        # Include last-known reset countdown alongside staleness
        reset_text = ""
        if self._last_good_usage:
            resets_at = self._last_good_usage.get("five_hour", {}).get("resets_at", "")
            if resets_at:
                reset_text = get_time_until_reset(resets_at)

        if reset_text:
            self.claude_duration_lbl.setText(f"{ago} {reset_text}")
        else:
            self.claude_duration_lbl.setText(ago)

    def _render_usage_data(self, usage_data: dict):
        """Render usage data to the Claude section widgets."""
        five_hour = usage_data.get("five_hour", {})
        seven_day = usage_data.get("seven_day", {})

        five_pct = five_hour.get("utilization", 0)
        seven_pct = seven_day.get("utilization", 0)
        resets_at = five_hour.get("resets_at", "")

        progress = min(100, int(five_pct))
        self.claude_progress.setValue(progress)

        if progress >= 80:
            color = "#f44336"
        elif progress >= 50:
            color = "#ff9800"
        else:
            color = "#4caf50"

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

        self.claude_five_hour_lbl.setText(f"5h: {five_pct:.0f}%")

        right_parts = [f"7d: {seven_pct:.0f}%"]
        for key in ("seven_day_opus", "seven_day_sonnet"):
            bucket = usage_data.get(key)
            if bucket and bucket.get("utilization", 0) > 0:
                label = key.replace("seven_day_", "").capitalize()
                right_parts.append(f"{label}: {bucket['utilization']:.0f}%")
        self.claude_seven_day_lbl.setText(" | ".join(right_parts))

        self.claude_duration_lbl.setText(get_time_until_reset(resets_at) if resets_at else "")

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
        self.update_claude_section(results.get('claude_usage'))

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
        except Exception:
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
