"""
Monitor thread for VPN health checking and auto-reconnect
"""
import logging
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from enum import Enum

from PyQt6.QtCore import QThread, pyqtSignal

from .config import ConfigManager
from .vpn_manager import VPNManager
from .asserts import create_assert, AssertResult

logger = logging.getLogger('vpn_toggle.monitor')


class MonitorState(Enum):
    """States for the monitor state machine"""
    IDLE = "idle"
    MONITORING = "monitoring"
    GRACE_PERIOD = "grace_period"
    RECONNECTING = "reconnecting"
    DISABLED = "disabled"


class MonitorThread(QThread):
    """
    Background thread for monitoring VPN connections.

    Periodically runs asserts on connected VPNs and auto-reconnects on failure.
    Emits signals for GUI updates.
    """

    # Signals for GUI updates
    status_changed = pyqtSignal(str, str)  # vpn_name, status_text
    assert_result = pyqtSignal(str, bool, str)  # vpn_name, success, message
    log_message = pyqtSignal(str)  # log message
    reconnect_attempted = pyqtSignal(str, int)  # vpn_name, attempt_number
    vpn_disabled = pyqtSignal(str, str)  # vpn_name, reason

    def __init__(self, config_manager: ConfigManager, vpn_manager: VPNManager):
        """
        Initialize monitor thread.

        Args:
            config_manager: Configuration manager instance
            vpn_manager: VPN manager instance
        """
        super().__init__()
        self.config_manager = config_manager
        self.vpn_manager = vpn_manager

        # Thread control
        self.running = True
        self.monitoring_enabled = False
        self.config_changed = threading.Event()  # Event to wake up monitor on config changes

        # Per-VPN state tracking
        self.failure_counts: Dict[str, int] = {}
        self.last_check_times: Dict[str, datetime] = {}
        self.connection_times: Dict[str, datetime] = {}
        self.vpn_states: Dict[str, MonitorState] = {}

    def run(self):
        """Main monitor loop."""
        logger.info("Monitor thread started")
        self.log_message.emit("Monitor thread started")

        while self.running:
            if not self.monitoring_enabled:
                time.sleep(1)
                continue

            # Get monitor settings
            monitor_settings = self.config_manager.get_monitor_settings()
            check_interval = monitor_settings.get('check_interval_seconds', 120)

            # Check each configured VPN
            vpns_to_monitor = self._get_monitored_vpns()

            if vpns_to_monitor:
                logger.debug(f"Starting check cycle for {len(vpns_to_monitor)} VPN(s)")

            for vpn_config in vpns_to_monitor:
                if not self.running:
                    break

                vpn_name = vpn_config['name']

                # Check if VPN should be monitored
                if not vpn_config.get('enabled', True):
                    continue

                self._check_vpn(vpn_config, monitor_settings)

            # Sleep for check interval, or wake up early if config changes
            self.config_changed.wait(timeout=check_interval)
            self.config_changed.clear()  # Reset the event for next cycle

        logger.info("Monitor thread stopped")
        self.log_message.emit("Monitor thread stopped")

    def _get_monitored_vpns(self) -> List[Dict]:
        """
        Get list of VPNs that should be monitored.

        Returns:
            List of VPN configuration dictionaries
        """
        return self.config_manager.get_all_vpns()

    def _check_vpn(self, vpn_config: Dict, monitor_settings: Dict):
        """
        Check a single VPN connection.

        Args:
            vpn_config: VPN configuration dictionary
            monitor_settings: Monitor settings dictionary
        """
        vpn_name = vpn_config['name']

        # Check if VPN is connected
        is_connected = self.vpn_manager.is_vpn_active(vpn_name)

        if not is_connected:
            # VPN not connected, skip monitoring
            self.vpn_states[vpn_name] = MonitorState.IDLE
            return

        # Track connection time
        if vpn_name not in self.connection_times:
            self.connection_times[vpn_name] = datetime.now()

        # Check if in grace period
        grace_period = monitor_settings.get('grace_period_seconds', 15)
        time_since_connect = (datetime.now() - self.connection_times[vpn_name]).total_seconds()

        if time_since_connect < grace_period:
            self.vpn_states[vpn_name] = MonitorState.GRACE_PERIOD
            remaining = grace_period - time_since_connect
            logger.debug(f"{vpn_name}: In grace period ({time_since_connect:.1f}s / {grace_period}s, {remaining:.0f}s remaining)")
            self.log_message.emit(f"{vpn_name}: In grace period, checks will start in {remaining:.0f}s")
            return

        # Set state to monitoring
        self.vpn_states[vpn_name] = MonitorState.MONITORING

        # Run asserts
        asserts_config = vpn_config.get('asserts', [])
        if not asserts_config:
            # No asserts configured, nothing to check
            logger.debug(f"{vpn_name}: No asserts configured, skipping")
            return

        logger.info(f"{vpn_name}: Running {len(asserts_config)} assert(s)")
        self.log_message.emit(f"{vpn_name}: Checking {len(asserts_config)} assert(s)...")
        all_passed = True
        for assert_config in asserts_config:
            if not self.running:
                break

            try:
                assert_obj = create_assert(assert_config)
                result = self._run_assert_with_retry(assert_obj)

                # Emit assert result signal
                self.assert_result.emit(vpn_name, result.success, result.message)

                if not result.success:
                    all_passed = False
                    logger.warning(f"{vpn_name}: Assert failed: {result.message}")
                    self.log_message.emit(f"{vpn_name}: {result.message}")
                else:
                    logger.debug(f"{vpn_name}: Assert passed: {result.message}")

            except Exception as e:
                logger.error(f"{vpn_name}: Assert error: {e}")
                self.log_message.emit(f"{vpn_name}: Assert error: {e}")
                all_passed = False

        # Update last check time
        self.last_check_times[vpn_name] = datetime.now()

        # Handle results
        if all_passed:
            # All asserts passed, reset failure count
            if vpn_name in self.failure_counts:
                prev_count = self.failure_counts[vpn_name]
                if prev_count > 0:
                    logger.info(f"{vpn_name}: All asserts passing, reset failure count (was {prev_count})")
                    self.log_message.emit(f"{vpn_name}: All asserts passing")
            self.failure_counts[vpn_name] = 0
        else:
            # Some asserts failed, increment failure count
            self.failure_counts[vpn_name] = self.failure_counts.get(vpn_name, 0) + 1
            failure_count = self.failure_counts[vpn_name]
            failure_threshold = monitor_settings.get('failure_threshold', 3)

            logger.warning(f"{vpn_name}: Assert failed ({failure_count}/{failure_threshold})")
            self.log_message.emit(f"{vpn_name}: Assert failed ({failure_count}/{failure_threshold})")

            if failure_count < failure_threshold:
                # Auto-reconnect
                logger.info(f"{vpn_name}: Attempting auto-reconnect (attempt {failure_count})")
                self.log_message.emit(f"{vpn_name}: Attempting auto-reconnect...")
                self.vpn_states[vpn_name] = MonitorState.RECONNECTING
                self.reconnect_attempted.emit(vpn_name, failure_count)

                success, message = self.vpn_manager.bounce_vpn(vpn_name)

                if success:
                    logger.info(f"{vpn_name}: Reconnect successful")
                    self.log_message.emit(f"{vpn_name}: Reconnected successfully")
                    # Reset connection time for new grace period
                    self.connection_times[vpn_name] = datetime.now()
                else:
                    logger.error(f"{vpn_name}: Reconnect failed: {message}")
                    self.log_message.emit(f"{vpn_name}: Reconnect failed: {message}")
            else:
                # Threshold exceeded, disable VPN and monitoring
                logger.error(f"{vpn_name}: Failure threshold exceeded, disabling VPN")
                self.log_message.emit(f"{vpn_name}: Failure threshold exceeded, disabling VPN")
                self.vpn_states[vpn_name] = MonitorState.DISABLED

                # Disconnect VPN
                self.vpn_manager.disconnect_vpn(vpn_name)

                # Emit signal for user alert
                reason = f"Failed {failure_count} consecutive health checks"
                self.vpn_disabled.emit(vpn_name, reason)

                # Disable monitoring for this VPN in config
                vpn_config['enabled'] = False
                self.config_manager.update_vpn_config(vpn_name, vpn_config)

    def _run_assert_with_retry(self, assert_obj, retries: int = 2) -> AssertResult:
        """
        Run an assert with retry logic.

        Args:
            assert_obj: Assert object to run
            retries: Number of retries on failure

        Returns:
            AssertResult from the assert check
        """
        for attempt in range(retries + 1):
            result = assert_obj.check()
            if result.success or attempt == retries:
                return result

            # Wait a bit before retry
            logger.debug(f"Assert failed, retrying ({attempt + 1}/{retries})...")
            time.sleep(2)

        return result

    def enable_monitoring(self):
        """Enable monitoring."""
        logger.info("Monitoring enabled")
        self.log_message.emit("Monitoring enabled")
        self.monitoring_enabled = True
        self.config_manager.update_monitor_settings(enabled=True)

    def disable_monitoring(self):
        """Disable monitoring."""
        logger.info("Monitoring disabled")
        self.log_message.emit("Monitoring disabled")
        self.monitoring_enabled = False
        self.config_manager.update_monitor_settings(enabled=False)

    def reset_vpn_state(self, vpn_name: str):
        """
        Reset state for a VPN (e.g., after user manually reconnects).

        Args:
            vpn_name: Name of the VPN
        """
        logger.info(f"Resetting state for {vpn_name}")
        self.failure_counts[vpn_name] = 0
        self.connection_times[vpn_name] = datetime.now()
        self.vpn_states[vpn_name] = MonitorState.GRACE_PERIOD

    def get_vpn_status(self, vpn_name: str) -> Dict:
        """
        Get current status for a VPN.

        Args:
            vpn_name: Name of the VPN

        Returns:
            Dictionary with status information
        """
        return {
            'state': self.vpn_states.get(vpn_name, MonitorState.IDLE).value,
            'failure_count': self.failure_counts.get(vpn_name, 0),
            'last_check': self.last_check_times.get(vpn_name),
            'connection_time': self.connection_times.get(vpn_name)
        }

    def notify_config_changed(self):
        """
        Notify the monitor that configuration has changed.
        This will wake up the monitor immediately to reload settings.
        """
        logger.debug("Configuration changed, waking up monitor")
        self.config_changed.set()

    def stop(self):
        """Stop the monitor thread gracefully."""
        logger.info("Stopping monitor thread...")
        self.running = False
        self.config_changed.set()  # Wake up the thread if it's sleeping
        self.wait(5000)  # Wait up to 5 seconds for thread to finish
