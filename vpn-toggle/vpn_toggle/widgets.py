"""
VPN card widget for displaying a single VPN connection
"""
import logging
import threading
from datetime import datetime
from typing import Optional

from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QDialog,
)
from PyQt6.QtGui import QFont, QPalette
from PyQt6.QtCore import Qt, QTimer, pyqtSignal

from .config import ConfigManager
from .vpn_manager import VPNManager
from .monitor import MonitorController
from .metrics import MetricsCollector

logger = logging.getLogger('vpn_toggle.widgets')


class VPNWidget(QFrame):
    """Widget representing a single VPN in the list"""

    move_requested = pyqtSignal(str, int)  # vpn_name, direction (-1=up, +1=down)

    def __init__(self, vpn_name: str, display_name: str, vpn_manager: VPNManager,
                 config_manager: ConfigManager, monitor_thread: Optional[MonitorController] = None,
                 metrics_collector: Optional[MetricsCollector] = None,
                 backend_type: str = "vpn"):
        super().__init__()
        self.vpn_name = vpn_name
        self.display_name = display_name
        self.vpn_manager = vpn_manager
        self.config_manager = config_manager
        self.monitor_thread = monitor_thread
        self.metrics_collector = metrics_collector
        self.backend_type = backend_type

        self._connected_since: Optional[datetime] = None
        # Last activeness result actually applied to the card. Survives a failed
        # probe so callers (e.g. the tray tooltip) don't see a phantom drop.
        self.is_active: bool = False

        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Raised)
        self.setup_ui()
        self.update_status()

    @staticmethod
    def _counter_font() -> QFont:
        """A genuinely fixed-pitch font sized in points, for the uptime counter.

        `setFixedPitch(True)` plus the Monospace style hint makes fontconfig pick
        a real monospace face; a stylesheet `font-family: monospace` leaves Qt
        reporting `fixedPitch: False` and can fall back to a proportional face.
        """
        font = QFont()
        font.setStyleHint(QFont.StyleHint.Monospace)
        font.setFamily("monospace")
        font.setFixedPitch(True)
        base = font.pointSizeF()
        # Slightly smaller than body text, but scale-aware unlike a px size.
        font.setPointSizeF(max(7.0, (base if base > 0 else 10.0) - 1.5))
        return font

    @staticmethod
    def _set_style(widget, sheet: str) -> None:
        """Apply a stylesheet only when it actually changes.

        setStyleSheet() forces a full style repolish and repaint of the widget.
        The 5s status sweep re-applied identical stylesheets on every pass, so
        every card was repolished 12 times a minute for no visual change. When
        one of those repolishes lands on the same frame as the 1s uptime
        counter's repaint, the counter renders coarse/aliased for that frame.
        """
        if widget.styleSheet() != sheet:
            widget.setStyleSheet(sheet)

    def setup_ui(self):
        """Setup the widget UI"""
        layout = QVBoxLayout()

        # Header with VPN name and status
        header_layout = QHBoxLayout()

        # Status indicator (colored dot)
        self.status_indicator = QLabel("●")
        self.status_indicator.setStyleSheet("color: gray; font-size: 16px;")
        header_layout.addWidget(self.status_indicator)

        # VPN name
        name_label = QLabel(self.display_name)
        name_font = QFont()
        name_font.setBold(True)
        name_label.setFont(name_font)
        header_layout.addWidget(name_label)

        # Backend type label
        backend_label_text = "NM" if self.backend_type != "openvpn3" else "OV3"
        backend_label = QLabel(backend_label_text)
        backend_label.setStyleSheet(
            "color: #888888; font-size: 9px; border: 1px solid #555555; "
            "border-radius: 3px; padding: 1px 4px;"
        )
        header_layout.addWidget(backend_label)

        header_layout.addStretch()

        # Status text
        self.status_label = QLabel("Disconnected")
        header_layout.addWidget(self.status_label)

        # Connection time counter (DD:HH:MM:SS).
        #
        # This is the only label in the card that repaints every second, so it is
        # the one that shows text-rendering artifacts. Three things keep its
        # repaint stable, which the original stylesheet did not give us:
        #
        #  - The font is a real QFont at a *point* size. A stylesheet
        #    "font-size: 10px" is a device-independent pixel size that rasterises
        #    badly under fractional display scaling (this host runs every output
        #    at 1.5x), which garbles glyphs on repaint.
        #  - An opaque background, so each repaint overwrites the previous
        #    second's glyphs instead of compositing over them.
        #  - A fixed width plus right alignment keeps the painted rect identical
        #    from tick to tick instead of depending on text metrics.
        self.connection_time_label = QLabel("")
        # An explicit opaque background, not autoFillBackground: Qt ignores
        # autoFillBackground once a stylesheet is set on the widget. Without an
        # opaque rect the label composites as a transparent overlay, and under
        # fractional scaling the damage region rounds to non-integer physical
        # pixels — leaving the previous frame's glyphs visible underneath the
        # new ones, so the counter renders doubled for a frame. The colour is
        # taken from the palette so it still follows the desktop theme.
        self.connection_time_label.setStyleSheet(
            f"color: #aaaaaa; background-color: "
            f"{self.palette().color(QPalette.ColorRole.Window).name()};"
        )
        self.connection_time_label.setFont(self._counter_font())
        self.connection_time_label.setTextFormat(Qt.TextFormat.PlainText)
        self.connection_time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Widest value the counter can render, plus a little slack.
        self.connection_time_label.setFixedWidth(
            self.connection_time_label.fontMetrics().horizontalAdvance("00:00:00:00") + 6
        )
        header_layout.addWidget(self.connection_time_label)

        layout.addLayout(header_layout)

        # Info row (asserts status, last check)
        info_layout = QHBoxLayout()
        self.info_label = QLabel("")
        self.info_label.setStyleSheet("color: gray; font-size: 10px;")
        info_layout.addWidget(self.info_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        # Stats row (avg latency, total failures, uptime)
        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("color: #888888; font-size: 10px;")
        layout.addWidget(self.stats_label)

        # Control buttons
        button_layout = QHBoxLayout()

        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.on_connect)
        button_layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self.on_disconnect)
        button_layout.addWidget(self.disconnect_btn)

        self.bounce_btn = QPushButton("Bounce")
        self.bounce_btn.clicked.connect(self.on_bounce)
        button_layout.addWidget(self.bounce_btn)

        self.details_btn = QPushButton("Details")
        self.details_btn.clicked.connect(self.on_details)
        self.details_btn.setEnabled(False)
        button_layout.addWidget(self.details_btn)

        self.configure_btn = QPushButton("Configure")
        self.configure_btn.clicked.connect(self.on_configure)
        button_layout.addWidget(self.configure_btn)

        button_layout.addStretch()

        # Ordering buttons
        self.move_up_btn = QPushButton("\u25B2")  # ▲
        self.move_up_btn.setMaximumWidth(30)
        self.move_up_btn.setToolTip("Move up")
        self.move_up_btn.clicked.connect(lambda: self.move_requested.emit(self.vpn_name, -1))
        button_layout.addWidget(self.move_up_btn)

        self.move_down_btn = QPushButton("\u25BC")  # ▼
        self.move_down_btn.setMaximumWidth(30)
        self.move_down_btn.setToolTip("Move down")
        self.move_down_btn.clicked.connect(lambda: self.move_requested.emit(self.vpn_name, 1))
        button_layout.addWidget(self.move_down_btn)

        layout.addLayout(button_layout)

        self.setLayout(layout)

    def update_status(self):
        """Probe the backend synchronously and update the display.

        Used by the user-initiated paths (button handlers, monitor signals).
        The periodic 5s sweep uses `apply_status()` with an async probe result
        so the GUI thread never blocks on nmcli/openvpn3.
        """
        self.apply_status(self.vpn_manager.is_vpn_active(self.vpn_name))

    def apply_status(self, is_active: bool, probe_ok: bool = True):
        """Render the card for an already-obtained activeness result.

        Args:
            is_active: whether the backend reports the VPN as connected.
            probe_ok: False when the backend probe itself failed (nmcli/openvpn3
                errored or timed out) rather than reporting a genuine
                disconnect. A failed probe must not be read as "disconnected":
                doing so blanks the card and discards `_connected_since`, which
                restarts the uptime counter from zero on the next good probe.
        """
        if not probe_ok:
            logger.debug(
                f"{self.vpn_name}: activeness probe failed, keeping last known state"
            )
            return

        self.is_active = is_active

        if is_active:
            self._set_style(self.status_indicator, "color: green; font-size: 16px;")
            self.status_label.setText("Connected")
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.bounce_btn.setEnabled(True)
            self.details_btn.setEnabled(True)

            # Track connection start time (fetch from the backend once, then cache)
            if self._connected_since is None:
                self._connected_since = (
                    self.vpn_manager.get_connection_timestamp(self.vpn_name)
                    or datetime.now()
                )
                # Track as active in restore list
                self.config_manager.add_restore_vpn(self.vpn_name)
                # Paint the counter immediately on the connect transition. In the
                # steady state the 1s timer is the sole writer: refreshing here
                # too would advance the display off-cadence on every 5s sweep,
                # making the seconds digit visibly stutter.
                self.update_connection_time()

            # Get assert status if monitor is running
            if self.monitor_thread:
                monitor_status = self.monitor_thread.get_vpn_status(self.vpn_name)
                failure_count = monitor_status['failure_count']
                last_check = monitor_status['last_check']

                if last_check:
                    time_ago = datetime.now() - last_check
                    minutes_ago = int(time_ago.total_seconds() / 60)
                    if minutes_ago == 0:
                        time_str = "just now"
                    else:
                        time_str = f"{minutes_ago}m ago"

                    if failure_count > 0:
                        self.info_label.setText(f"⚠ {failure_count} failures | Last check: {time_str}")
                        self._set_style(self.info_label, "color: orange; font-size: 10px;")
                    else:
                        self.info_label.setText(f"✓ All checks passing | Last check: {time_str}")
                        self._set_style(self.info_label, "color: green; font-size: 10px;")
                else:
                    self.info_label.setText("Monitoring active")
                    self._set_style(self.info_label, "color: gray; font-size: 10px;")

            # Update stats from metrics collector
            if self.metrics_collector:
                stats = self.metrics_collector.get_stats(self.vpn_name)
                if stats:
                    self.stats_label.setText(
                        f"Avg: {stats.avg_latency_ms:.0f}ms | "
                        f"Total failures: {stats.total_failures} | "
                        f"Uptime: {stats.uptime_pct:.1f}%"
                    )
                else:
                    self.stats_label.setText("No data")
            else:
                self.stats_label.setText("")
        else:
            recovering = self._recovery_status()
            self._set_style(
                self.status_indicator,
                "color: orange; font-size: 16px;" if recovering
                else "color: gray; font-size: 16px;"
            )
            self.status_label.setText("Reconnecting" if recovering else "Disconnected")
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.bounce_btn.setEnabled(False)
            self.details_btn.setEnabled(False)
            # Surface auto-recovery so a down VPN reads as "being worked on"
            # rather than silently idle.
            self.info_label.setText(recovering or "")
            self._set_style(self.info_label, "color: orange; font-size: 10px;")
            self.stats_label.setText("")
            self._connected_since = None
            self.connection_time_label.setText("")

    def _recovery_status(self) -> str:
        """Describe an in-progress auto-recovery, or '' when not recovering."""
        if not self.monitor_thread:
            return ""
        status = self.monitor_thread.get_vpn_status(self.vpn_name)
        if status.get('state') != 'recovering':
            return ""
        attempts = status.get('recovery_attempts', 0)
        if attempts:
            return f"↻ Auto-reconnecting (attempt {attempts + 1})"
        return "↻ Auto-reconnecting"

    def update_connection_time(self):
        """Update the connection time counter display (DD:HH:MM:SS)."""
        if self._connected_since is None:
            self.connection_time_label.setText("")
            return

        total_seconds = int((datetime.now() - self._connected_since).total_seconds())
        if total_seconds < 0:
            total_seconds = 0
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        self.connection_time_label.setText(
            f"{days:02d}:{hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    def _set_buttons_busy(self, busy: bool):
        """Disable/enable buttons during async operations."""
        self.connect_btn.setEnabled(not busy)
        self.disconnect_btn.setEnabled(not busy)
        self.bounce_btn.setEnabled(not busy)
        if busy:
            self.status_label.setText("Awaiting authentication...")

    def _run_in_thread(self, func, callback):
        """Run func in a background thread, call callback(result) on the GUI thread."""
        def worker():
            result = func()
            # Schedule callback on the main thread via a single-shot timer
            QTimer.singleShot(0, lambda: callback(result))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def on_connect(self):
        """Handle connect button click"""
        logger.info(f"Connecting to {self.vpn_name}")
        self._set_buttons_busy(True)

        def do_connect():
            return self.vpn_manager.connect_vpn(self.vpn_name)

        def on_done(result):
            success, message = result
            if success:
                if self.monitor_thread:
                    self.monitor_thread.reset_vpn_state(self.vpn_name)
                self.config_manager.add_restore_vpn(self.vpn_name)
            self.update_status()

        self._run_in_thread(do_connect, on_done)

    def on_disconnect(self):
        """Handle disconnect button click"""
        logger.info(f"Disconnecting from {self.vpn_name}")
        # Tell the monitor this is deliberate before the VPN actually goes down,
        # so auto-recovery does not race the user and bring it straight back up.
        if self.monitor_thread:
            self.monitor_thread.notify_user_disconnected(self.vpn_name)
        self.vpn_manager.disconnect_vpn(self.vpn_name)
        self.config_manager.remove_restore_vpn(self.vpn_name)
        self.update_status()

    def on_bounce(self):
        """Handle bounce button click"""
        logger.info(f"Bouncing {self.vpn_name}")
        self._set_buttons_busy(True)

        def do_bounce():
            return self.vpn_manager.bounce_vpn(self.vpn_name)

        def on_done(result):
            success, message = result
            if success and self.monitor_thread:
                self.monitor_thread.reset_vpn_state(self.vpn_name)
            self.update_status()

        self._run_in_thread(do_bounce, on_done)

    def on_details(self):
        """Handle details button click — show VPN interface/routes."""
        from .dialogs import VPNDetailsDialog

        details = self.vpn_manager.get_vpn_details(self.vpn_name)
        dialog = VPNDetailsDialog(self.display_name, details, self)
        dialog.exec()

    def on_configure(self):
        """Handle configure button click"""
        from .dialogs import VPNConfigDialog

        dialog = VPNConfigDialog(self.vpn_name, self.display_name, self.config_manager, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            vpn_config = dialog.get_config()
            self.config_manager.update_vpn_config(self.vpn_name, vpn_config)
            logger.info(f"Updated configuration for {self.vpn_name}")

            # Notify monitor of config change
            if self.monitor_thread and self.monitor_thread.isRunning():
                self.monitor_thread.notify_config_changed()

            self.update_status()
