"""
Event-driven VPN monitor (MonitorController).

Replaces the earlier MonitorThread(QThread) architecture with a main-thread
controller driven by QTimer + QProcess/QDnsLookup/QNetworkAccessManager. All
checks, asserts, and bounce operations run on the Qt event loop; no blocking
subprocess / socket / HTTP calls on the main thread. See specs/009 for the
rationale and acceptance criteria.
"""
import logging
import time
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .asserts import AssertResult, create_async_assert
from .config import ConfigManager
from .vpn_manager import VPNManager

logger = logging.getLogger('vpn_toggle.monitor')


class MonitorState(Enum):
    """States for the per-VPN monitor state machine."""
    IDLE = "idle"
    MONITORING = "monitoring"
    GRACE_PERIOD = "grace_period"
    RECONNECTING = "reconnecting"
    DISABLED = "disabled"


class MonitorController(QObject):
    """
    Event-driven VPN monitor.

    Runs a single periodic QTimer on the main thread; each tick walks the
    configured VPNs and, for each one, launches a VPNCheckSession that owns
    a small state machine of async operations.

    Emits the same signals as the previous MonitorThread so gui.py wiring is
    unchanged.
    """

    status_changed = pyqtSignal(str, str)  # vpn_name, status_text
    assert_result = pyqtSignal(str, bool, str)  # vpn_name, success, message
    log_message = pyqtSignal(str)  # log message
    vpn_disabled = pyqtSignal(str, str)  # vpn_name, reason
    check_completed = pyqtSignal(str, dict)  # vpn_name, data_point dict

    def __init__(self, config_manager: ConfigManager, vpn_manager: VPNManager,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.vpn_manager = vpn_manager

        self.monitoring_enabled = False

        # Per-VPN state tracking
        self.failure_counts: Dict[str, int] = {}
        self.last_check_times: Dict[str, datetime] = {}
        self.connection_times: Dict[str, datetime] = {}
        self.vpn_states: Dict[str, MonitorState] = {}

        # Active check sessions and bounce operations, keyed by vpn_name.
        # Strong references keep Qt objects alive; cleared in completion slots.
        self._active_sessions: Dict[str, "VPNCheckSession"] = {}
        self._active_bounces: Dict[str, QObject] = {}
        self._active_is_active_ops: Dict[str, QObject] = {}

        self._timer = QTimer(self)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._tick)

    # -- Lifecycle --

    def start_monitoring(self) -> None:
        """Enable monitoring and start the periodic timer."""
        logger.info("Monitor thread started")
        self.log_message.emit("Monitor thread started")
        self._apply_interval()
        self._timer.start()

    def stop(self) -> None:
        """Stop monitoring and cancel any in-flight async operations."""
        logger.info("Stopping monitor...")
        self._timer.stop()
        self.monitoring_enabled = False
        for session in list(self._active_sessions.values()):
            session.cancel()
        self._active_sessions.clear()
        for bounce in list(self._active_bounces.values()):
            bounce.deleteLater()
        self._active_bounces.clear()
        for op in list(self._active_is_active_ops.values()):
            op.deleteLater()
        self._active_is_active_ops.clear()
        logger.info("Monitor thread stopped")
        self.log_message.emit("Monitor thread stopped")

    # Back-compat aliases so gui.py can call either name.
    def start(self) -> None:
        self.start_monitoring()

    def enable_monitoring(self) -> None:
        logger.info("Monitoring enabled")
        self.log_message.emit("Monitoring enabled")
        self.monitoring_enabled = True
        self.config_manager.update_monitor_settings(enabled=True)

    def disable_monitoring(self) -> None:
        logger.info("Monitoring disabled")
        self.log_message.emit("Monitoring disabled")
        self.monitoring_enabled = False
        self.config_manager.update_monitor_settings(enabled=False)

    def notify_config_changed(self) -> None:
        """Reload monitor settings (e.g. interval) immediately on config change."""
        logger.debug("Configuration changed, refreshing monitor timer")
        self._apply_interval()

    def reset_vpn_state(self, vpn_name: str) -> None:
        """Reset state for a VPN (e.g., after user manually reconnects)."""
        logger.info(f"Resetting state for {vpn_name}")
        self.failure_counts[vpn_name] = 0
        self.connection_times[vpn_name] = datetime.now()
        self.vpn_states[vpn_name] = MonitorState.GRACE_PERIOD

    def get_vpn_status(self, vpn_name: str) -> Dict:
        """Get current status for a VPN (shape matches the old MonitorThread)."""
        return {
            'state': self.vpn_states.get(vpn_name, MonitorState.IDLE).value,
            'failure_count': self.failure_counts.get(vpn_name, 0),
            'last_check': self.last_check_times.get(vpn_name),
            'connection_time': self.connection_times.get(vpn_name),
        }

    # -- Compatibility with the old QThread-based API --

    def isRunning(self) -> bool:  # noqa: N802 — mirrors QThread.isRunning()
        return self._timer.isActive()

    def wait(self, _msec: int = 0) -> bool:
        """No-op: nothing to wait on in the event-driven design."""
        return True

    # -- Internal --

    def _apply_interval(self) -> None:
        settings = self.config_manager.get_monitor_settings()
        interval = max(1, int(settings.get('check_interval_seconds', 120)))
        self._timer.setInterval(interval * 1000)

    def _tick(self) -> None:
        if not self.monitoring_enabled:
            return
        monitor_settings = self.config_manager.get_monitor_settings()
        vpns = self.config_manager.get_all_vpns()
        if vpns:
            logger.debug(f"Starting check cycle for {len(vpns)} VPN(s)")
        for vpn_config in vpns:
            if not vpn_config.get('enabled', True):
                continue
            vpn_name = vpn_config['name']
            # Avoid overlapping operations for the same VPN.
            if vpn_name in self._active_sessions:
                logger.debug(f"{vpn_name}: previous check still running, skipping")
                continue
            if vpn_name in self._active_bounces:
                logger.debug(f"{vpn_name}: bounce in progress, skipping check")
                continue
            if vpn_name in self._active_is_active_ops:
                logger.debug(f"{vpn_name}: is-active probe still in flight, skipping")
                continue
            self._kick_off_check(vpn_config, monitor_settings)

    def _kick_off_check(self, vpn_config: Dict, monitor_settings: Dict) -> None:
        vpn_name = vpn_config['name']
        # First, ask whether the VPN is currently active.
        op = self.vpn_manager.is_vpn_active_async(vpn_name, parent=self)
        self._active_is_active_ops[vpn_name] = op
        op.finished.connect(
            lambda active, _vn=vpn_name, _vc=vpn_config, _ms=monitor_settings:
            self._on_is_active(_vn, active, _vc, _ms)
        )
        op.start()

    def _on_is_active(self, vpn_name: str, is_connected: bool,
                      vpn_config: Dict, monitor_settings: Dict) -> None:
        op = self._active_is_active_ops.pop(vpn_name, None)
        if op is not None:
            op.deleteLater()

        # Guard: stop() may have landed between start() and finished.
        if not self.monitoring_enabled:
            return

        if not is_connected:
            self.vpn_states[vpn_name] = MonitorState.IDLE
            return

        if vpn_name not in self.connection_times:
            self.connection_times[vpn_name] = datetime.now()

        grace_period = monitor_settings.get('grace_period_seconds', 15)
        time_since_connect = (
            datetime.now() - self.connection_times[vpn_name]
        ).total_seconds()
        if time_since_connect < grace_period:
            self.vpn_states[vpn_name] = MonitorState.GRACE_PERIOD
            remaining = grace_period - time_since_connect
            logger.debug(
                f"{vpn_name}: In grace period "
                f"({time_since_connect:.1f}s / {grace_period}s, {remaining:.0f}s remaining)"
            )
            self.log_message.emit(
                f"{vpn_name}: In grace period, checks will start in {remaining:.0f}s"
            )
            return

        self.vpn_states[vpn_name] = MonitorState.MONITORING
        asserts_config = vpn_config.get('asserts', [])
        if not asserts_config:
            logger.debug(f"{vpn_name}: No asserts configured, skipping")
            return

        logger.info(f"{vpn_name}: Running {len(asserts_config)} assert(s)")
        self.log_message.emit(
            f"{vpn_name}: Checking {len(asserts_config)} assert(s)...")
        session = VPNCheckSession(
            vpn_name=vpn_name,
            asserts_config=asserts_config,
            parent=self,
        )
        session.assert_completed.connect(
            lambda ok, msg, _vn=vpn_name: self.assert_result.emit(_vn, ok, msg)
        )
        session.log_message.connect(self.log_message.emit)
        session.finished.connect(
            lambda passed, details, elapsed_ms, _vn=vpn_name, _ms=monitor_settings:
            self._on_session_done(_vn, passed, details, elapsed_ms, _ms)
        )
        self._active_sessions[vpn_name] = session
        session.start()

    def _on_session_done(self, vpn_name: str, all_passed: bool,
                         assert_details: List[Dict], cycle_elapsed_ms: float,
                         monitor_settings: Dict) -> None:
        session = self._active_sessions.pop(vpn_name, None)
        if session is not None:
            session.deleteLater()

        self.last_check_times[vpn_name] = datetime.now()

        bounce_triggered = False
        if all_passed:
            prev_count = self.failure_counts.get(vpn_name, 0)
            if prev_count > 0:
                logger.info(
                    f"{vpn_name}: All asserts passing, reset failure count "
                    f"(was {prev_count})")
                self.log_message.emit(f"{vpn_name}: All asserts passing")
            self.failure_counts[vpn_name] = 0
        else:
            self.failure_counts[vpn_name] = self.failure_counts.get(vpn_name, 0) + 1
            failure_count = self.failure_counts[vpn_name]
            failure_threshold = monitor_settings.get('failure_threshold', 3)

            logger.warning(
                f"{vpn_name}: Assert failed ({failure_count}/{failure_threshold})")
            self.log_message.emit(
                f"{vpn_name}: Assert failed ({failure_count}/{failure_threshold})")

            if failure_count < failure_threshold:
                bounce_triggered = True
                self._start_bounce(vpn_name)
            else:
                logger.error(f"{vpn_name}: Failure threshold exceeded, disabling VPN")
                self.log_message.emit(
                    f"{vpn_name}: Failure threshold exceeded, disabling VPN")
                self.vpn_states[vpn_name] = MonitorState.DISABLED
                self._disconnect_and_disable(vpn_name, failure_count)

        self._emit_data_point(vpn_name, cycle_elapsed_ms, all_passed,
                              bounce_triggered, assert_details)

    def _start_bounce(self, vpn_name: str) -> None:
        if vpn_name in self._active_bounces:
            return
        logger.info(
            f"{vpn_name}: Attempting auto-reconnect "
            f"(attempt {self.failure_counts[vpn_name]})")
        self.log_message.emit(f"{vpn_name}: Attempting auto-reconnect...")
        self.vpn_states[vpn_name] = MonitorState.RECONNECTING
        bounce = self.vpn_manager.bounce_vpn_async(vpn_name, parent=self)
        self._active_bounces[vpn_name] = bounce
        bounce.finished.connect(
            lambda success, message, _vn=vpn_name:
            self._on_bounce_done(_vn, success, message)
        )
        bounce.start()

    def _on_bounce_done(self, vpn_name: str, success: bool, message: str) -> None:
        bounce = self._active_bounces.pop(vpn_name, None)
        if bounce is not None:
            bounce.deleteLater()

        if success:
            logger.info(f"{vpn_name}: Reconnect successful")
            self.log_message.emit(f"{vpn_name}: Reconnected successfully")
            self.connection_times[vpn_name] = datetime.now()
        else:
            logger.error(f"{vpn_name}: Reconnect failed: {message}")
            self.log_message.emit(f"{vpn_name}: Reconnect failed: {message}")

    def _disconnect_and_disable(self, vpn_name: str, failure_count: int) -> None:
        """Disconnect the VPN and mark it disabled in config after threshold."""
        # Use async disconnect — the result isn't critical since we're disabling anyway.
        op = self.vpn_manager.disconnect_vpn_async(vpn_name, parent=self)
        op.finished.connect(lambda *_: op.deleteLater())
        op.start()

        reason = f"Failed {failure_count} consecutive health checks"
        self.vpn_disabled.emit(vpn_name, reason)

        vpn_config = self.config_manager.get_vpn_config(vpn_name)
        if vpn_config:
            vpn_config['enabled'] = False
            self.config_manager.update_vpn_config(vpn_name, vpn_config)

    def _emit_data_point(self, vpn_name: str, cycle_elapsed_ms: float,
                         all_passed: bool, bounce_triggered: bool,
                         assert_details: List[Dict]) -> None:
        data_point = {
            'timestamp': datetime.now().isoformat(),
            'vpn_name': vpn_name,
            'latency_ms': round(cycle_elapsed_ms, 1),
            'success': all_passed,
            'bounce_triggered': bounce_triggered,
            'assert_details': assert_details,
        }
        self.check_completed.emit(vpn_name, data_point)


class VPNCheckSession(QObject):
    """
    One check cycle for a single VPN: runs each configured assert serially
    through its async variant and emits `finished` when done.

    Signals:
      - `assert_completed(bool, str)` per assert (matches the old
        `MonitorThread.assert_result` payload minus the vpn_name, which the
        controller injects)
      - `log_message(str)` for status/log lines
      - `finished(all_passed, assert_details, cycle_elapsed_ms)` when done
    """

    assert_completed = pyqtSignal(bool, str)
    log_message = pyqtSignal(str)
    finished = pyqtSignal(bool, list, float)

    def __init__(self, vpn_name: str, asserts_config: List[Dict],
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._vpn_name = vpn_name
        self._asserts_config = list(asserts_config)
        self._details: List[Dict] = []
        self._all_passed = True
        self._cycle_start = 0.0
        self._assert_start = 0.0
        self._current_assert: Optional[QObject] = None
        self._cancelled = False
        self._done = False

    def start(self) -> None:
        if self._done or self._cancelled:
            return
        self._cycle_start = time.perf_counter()
        self._run_next()

    def cancel(self) -> None:
        """Cancel an in-flight session (called by controller.stop)."""
        self._cancelled = True
        if self._current_assert is not None:
            self._current_assert.deleteLater()
            self._current_assert = None

    def _run_next(self) -> None:
        if self._cancelled or self._done:
            return
        if not self._asserts_config:
            self._finish()
            return
        cfg = self._asserts_config.pop(0)
        try:
            self._current_assert = create_async_assert(cfg, parent=self)
        except ValueError as e:
            logger.error(f"{self._vpn_name}: Assert error: {e}")
            self.log_message.emit(f"{self._vpn_name}: Assert error: {e}")
            self._details.append({
                'type': cfg.get('type', 'unknown'),
                'latency_ms': 0.0,
                'success': False,
            })
            self._all_passed = False
            self._run_next()
            return

        self._assert_start = time.perf_counter()
        self._current_assert.completed.connect(
            lambda result, _cfg=cfg: self._on_assert_completed(_cfg, result)
        )
        self._current_assert.start()

    def _on_assert_completed(self, cfg: Dict, result: AssertResult) -> None:
        if self._cancelled or self._done:
            return
        elapsed_ms = (time.perf_counter() - self._assert_start) * 1000.0
        self._details.append({
            'type': cfg.get('type', 'unknown'),
            'latency_ms': round(elapsed_ms, 1),
            'success': result.success,
        })
        self.assert_completed.emit(result.success, result.message)
        if not result.success:
            logger.warning(f"{self._vpn_name}: Assert failed: {result.message}")
            self.log_message.emit(f"{self._vpn_name}: {result.message}")
            self._all_passed = False
        else:
            logger.debug(f"{self._vpn_name}: Assert passed: {result.message}")

        if self._current_assert is not None:
            self._current_assert.deleteLater()
            self._current_assert = None
        self._run_next()

    def _finish(self) -> None:
        if self._done:
            return
        self._done = True
        elapsed_ms = (time.perf_counter() - self._cycle_start) * 1000.0
        self.finished.emit(self._all_passed, self._details, elapsed_ms)
