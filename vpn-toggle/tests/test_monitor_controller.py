"""
Tests for MonitorController (spec 009).

Replaces the retired test_monitor.py. Drives the event-loop-based controller
via QCoreApplication.processEvents and fakes the async VPNManager / assert
primitives so tests stay in-process and deterministic.
"""
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QCoreApplication, QObject, QTimer, pyqtSignal

from vpn_toggle.config import ConfigManager
from vpn_toggle.monitor import MonitorController, MonitorState, VPNCheckSession
from vpn_toggle.vpn_manager import VPNManager


@pytest.fixture(scope="module")
def qapp():
    app = QCoreApplication.instance() or QCoreApplication([])
    yield app


@pytest.fixture
def temp_config_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_config.json"


@pytest.fixture
def config_manager(temp_config_file):
    with patch('subprocess.run'):
        return ConfigManager(str(temp_config_file))


@pytest.fixture
def vpn_manager():
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        return VPNManager()


def pump_events(timeout_ms: int = 1000, predicate=None):
    start = time.monotonic()
    while (time.monotonic() - start) * 1000 < timeout_ms:
        QCoreApplication.processEvents()
        if predicate is None or predicate():
            return True
        time.sleep(0.005)
    return False


class FakeIsActiveOp(QObject):
    """Fake VPNManager.is_vpn_active_async op."""
    finished = pyqtSignal(bool)

    def __init__(self, is_active: bool, parent=None):
        super().__init__(parent)
        self._is_active = is_active

    def start(self):
        QTimer.singleShot(0, lambda: self.finished.emit(self._is_active))


class FakeBounceOp(QObject):
    """Fake VPNManager.bounce_vpn_async op."""
    finished = pyqtSignal(bool, str)

    def __init__(self, success: bool, message: str, parent=None):
        super().__init__(parent)
        self._success = success
        self._message = message

    def start(self):
        QTimer.singleShot(0, lambda: self.finished.emit(self._success, self._message))


class FakeDisconnectOp(QObject):
    """Fake VPNManager.disconnect_vpn_async op."""
    finished = pyqtSignal(bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    def start(self):
        QTimer.singleShot(0, lambda: self.finished.emit(True, "Disconnected"))


class FakeConnectOp(QObject):
    """Fake VPNManager.connect_vpn_async op."""
    finished = pyqtSignal(bool, str)

    def __init__(self, success: bool, message: str, parent=None):
        super().__init__(parent)
        self._success = success
        self._message = message

    def start(self):
        QTimer.singleShot(0, lambda: self.finished.emit(self._success, self._message))


class FakeAssert(QObject):
    """Fake AsyncAssert that emits a preset result."""
    completed = pyqtSignal(object)

    def __init__(self, success: bool, message: str, parent=None):
        super().__init__(parent)
        self._result = MagicMock(success=success, message=message)

    def start(self):
        QTimer.singleShot(0, lambda: self.completed.emit(self._result))


class TestControllerBasics:

    def test_init(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        assert mc.config_manager is config_manager
        assert mc.vpn_manager is vpn_manager
        assert mc.monitoring_enabled is False
        assert mc.failure_counts == {}
        assert mc.last_check_times == {}

    def test_enable_monitoring_updates_settings(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.enable_monitoring()
        assert mc.monitoring_enabled is True
        assert config_manager.get_monitor_settings()['enabled'] is True

    def test_disable_monitoring_updates_settings(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        mc.disable_monitoring()
        assert mc.monitoring_enabled is False
        assert config_manager.get_monitor_settings()['enabled'] is False

    def test_reset_vpn_state(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.failure_counts['test_vpn'] = 5
        mc.reset_vpn_state('test_vpn')
        assert mc.failure_counts['test_vpn'] == 0
        assert 'test_vpn' in mc.connection_times
        assert mc.vpn_states['test_vpn'] == MonitorState.GRACE_PERIOD

    def test_get_vpn_status_tracked(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.failure_counts['test_vpn'] = 2
        mc.vpn_states['test_vpn'] = MonitorState.MONITORING
        status = mc.get_vpn_status('test_vpn')
        assert status['state'] == MonitorState.MONITORING.value
        assert status['failure_count'] == 2

    def test_get_vpn_status_untracked_defaults_to_idle(
            self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        status = mc.get_vpn_status('unknown_vpn')
        assert status['state'] == MonitorState.IDLE.value
        assert status['failure_count'] == 0

    def test_is_running_false_before_start(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        assert mc.isRunning() is False

    def test_is_running_true_after_start(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.start_monitoring()
        try:
            assert mc.isRunning() is True
        finally:
            mc.stop()
        assert mc.isRunning() is False


class TestTickFlow:
    """Exercise _on_is_active + session start/complete on a single VPN."""

    def _build_controller(self, config_manager, vpn_manager, active: bool,
                          assert_success: bool = True, grace: int = 15):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        # Set connection time past the grace window so asserts run.
        mc.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=grace + 30)
        # This fixture models an established tunnel, so it is recovery-eligible.
        mc._seen_connected.add('test_vpn')

        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            active, parent=parent)
        vpn_manager.bounce_vpn_async = lambda name, parent=None: FakeBounceOp(
            True, "Reconnected", parent=parent)
        vpn_manager.disconnect_vpn_async = lambda name, parent=None: FakeDisconnectOp(
            parent=parent)
        vpn_manager.connect_vpn_async = lambda name, parent=None: FakeConnectOp(
            True, "Connected", parent=parent)
        return mc

    def test_down_vpn_enters_recovery_not_idle(self, qapp, config_manager, vpn_manager):
        """Spec 010: a down VPN is a recoverable condition, not a silent IDLE."""
        mc = self._build_controller(config_manager, vpn_manager, active=False)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })
        mc._tick()
        pump_events(
            predicate=lambda: mc.vpn_states.get('test_vpn') == MonitorState.GRACE_PERIOD)
        # The reconnect succeeded, so the VPN lands back in the normal flow.
        assert mc.vpn_states['test_vpn'] == MonitorState.GRACE_PERIOD

    def test_sets_idle_when_not_connected_and_recovery_disabled(
            self, qapp, config_manager, vpn_manager):
        mc = self._build_controller(config_manager, vpn_manager, active=False)
        config_manager.update_monitor_settings(auto_recovery=False)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })
        mc._tick()
        pump_events(predicate=lambda: mc.vpn_states.get('test_vpn') == MonitorState.IDLE)
        assert mc.vpn_states['test_vpn'] == MonitorState.IDLE

    def test_grace_period_skip(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        mc.connection_times['test_vpn'] = datetime.now()  # just connected

        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            True, parent=parent)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })
        mc._tick()
        pump_events(
            predicate=lambda: mc.vpn_states.get('test_vpn') == MonitorState.GRACE_PERIOD)
        assert mc.vpn_states['test_vpn'] == MonitorState.GRACE_PERIOD

    def test_all_pass_emits_check_completed_success(self, qapp, config_manager, vpn_manager):
        mc = self._build_controller(config_manager, vpn_manager, active=True)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })

        emitted: List[tuple] = []
        mc.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch('vpn_toggle.monitor.create_async_assert',
                   side_effect=lambda cfg, parent=None: FakeAssert(True, "ok", parent=parent)):
            mc._tick()
            pump_events(predicate=lambda: len(emitted) > 0)

        assert len(emitted) == 1
        vpn_name, dp = emitted[0]
        assert vpn_name == 'test_vpn'
        assert dp['success'] is True
        assert dp['bounce_triggered'] is False
        assert 'assert_details' in dp and len(dp['assert_details']) == 1

    def test_failure_triggers_bounce(self, qapp, config_manager, vpn_manager):
        mc = self._build_controller(config_manager, vpn_manager, active=True)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })

        bounce_calls: List[str] = []
        vpn_manager.bounce_vpn_async = lambda name, parent=None: (
            bounce_calls.append(name) or FakeBounceOp(True, "OK", parent=parent)
        )

        emitted: List[tuple] = []
        mc.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch('vpn_toggle.monitor.create_async_assert',
                   side_effect=lambda cfg, parent=None: FakeAssert(False, "fail", parent=parent)):
            mc._tick()
            pump_events(predicate=lambda: len(emitted) > 0)
            pump_events(predicate=lambda: len(bounce_calls) > 0, timeout_ms=500)

        assert mc.failure_counts['test_vpn'] == 1
        assert bounce_calls == ['test_vpn']
        assert emitted[0][1]['bounce_triggered'] is True

    def test_threshold_exceeded_disables_vpn(self, qapp, config_manager, vpn_manager):
        mc = self._build_controller(config_manager, vpn_manager, active=True)
        mc.failure_counts['test_vpn'] = 2  # one more failure will tip past threshold=3
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })
        config_manager.update_monitor_settings(failure_threshold=3)

        disabled_emitted: List[tuple] = []
        mc.vpn_disabled.connect(lambda v, r: disabled_emitted.append((v, r)))

        with patch('vpn_toggle.monitor.create_async_assert',
                   side_effect=lambda cfg, parent=None: FakeAssert(False, "fail", parent=parent)):
            mc._tick()
            pump_events(predicate=lambda: len(disabled_emitted) > 0, timeout_ms=1500)

        assert mc.failure_counts['test_vpn'] == 3
        assert mc.vpn_states['test_vpn'] == MonitorState.DISABLED
        assert len(disabled_emitted) == 1
        assert disabled_emitted[0][0] == 'test_vpn'
        # Config persisted — vpn_config.enabled flipped to False
        assert config_manager.get_vpn_config('test_vpn')['enabled'] is False


class TestResourceLifecycle:

    def test_stop_cancels_active_session(self, qapp, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        mc.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=60)

        # An is_active op that never fires; stop() must still finish.
        class HangingOp(QObject):
            finished = pyqtSignal(bool)

            def start(self):
                pass

        vpn_manager.is_vpn_active_async = lambda name, parent=None: HangingOp(parent)
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}]
        })

        mc._tick()
        pump_events(timeout_ms=50)
        # is_active op was registered; stop() must clean it up.
        assert 'test_vpn' in mc._active_is_active_ops
        mc.stop()
        # Registry is cleared.
        assert mc._active_is_active_ops == {}
        assert mc._active_sessions == {}
        assert mc._active_bounces == {}
        assert mc.isRunning() is False


class TestVPNCheckSession:

    def test_empty_asserts_finishes_immediately(self, qapp):
        session = VPNCheckSession('vpn', [])
        results: List[tuple] = []
        session.finished.connect(lambda p, d, e: results.append((p, d, e)))
        session.start()
        pump_events(predicate=lambda: len(results) > 0)
        all_passed, details, elapsed_ms = results[0]
        assert all_passed is True
        assert details == []

    def test_single_passing_assert(self, qapp):
        session = VPNCheckSession(
            'vpn', [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}])
        results: List[tuple] = []
        session.finished.connect(lambda p, d, e: results.append((p, d, e)))

        with patch('vpn_toggle.monitor.create_async_assert',
                   side_effect=lambda cfg, parent=None: FakeAssert(True, "ok", parent=parent)):
            session.start()
            pump_events(predicate=lambda: len(results) > 0)

        all_passed, details, _ = results[0]
        assert all_passed is True
        assert details[0]['success'] is True
        assert details[0]['type'] == 'dns_lookup'

    def test_one_failing_assert_fails_session(self, qapp):
        session = VPNCheckSession(
            'vpn',
            [
                {'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'},
                {'type': 'ping', 'host': '127.0.0.1'},
            ])
        results: List[tuple] = []
        session.finished.connect(lambda p, d, e: results.append((p, d, e)))

        # First assert fails, second would pass.
        call_count = {'n': 0}
        def fake(cfg, parent=None):
            call_count['n'] += 1
            return FakeAssert(call_count['n'] != 1, "m", parent=parent)

        with patch('vpn_toggle.monitor.create_async_assert', side_effect=fake):
            session.start()
            pump_events(predicate=lambda: len(results) > 0)

        all_passed, details, _ = results[0]
        assert all_passed is False
        assert len(details) == 2

    def test_cancel_stops_the_session(self, qapp):
        class HangingAssert(QObject):
            completed = pyqtSignal(object)

            def start(self):
                pass  # never emits

        session = VPNCheckSession(
            'vpn', [{'type': 'dns_lookup', 'hostname': 'x', 'expected_prefix': '1.'}])
        results: List[tuple] = []
        session.finished.connect(lambda p, d, e: results.append((p, d, e)))

        with patch('vpn_toggle.monitor.create_async_assert',
                   side_effect=lambda cfg, parent=None: HangingAssert(parent)):
            session.start()
            pump_events(timeout_ms=50)
            session.cancel()
            pump_events(timeout_ms=50)

        # Session must not emit finished after cancel
        assert results == []


class TestAutoRecovery:
    """Spec 010: an enabled VPN that is unexpectedly down must be reconnected.

    Before this, a failed bounce left the tunnel disconnected and every later
    tick hit `if not is_connected: state = IDLE; return` — the VPN was silently
    orphaned-down until a human noticed (the ~15h 2026-06-16 outage).
    """

    def _build(self, config_manager, vpn_manager, connect_ok: bool,
               vpn_config: Optional[dict] = None,
               monitor_settings: Optional[dict] = None):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        config_manager.update_vpn_config('test_vpn', vpn_config or {
            'name': 'test_vpn', 'enabled': True, 'asserts': []
        })
        if monitor_settings:
            config_manager.update_monitor_settings(**monitor_settings)

        self.connect_calls = []

        def fake_connect(name, parent=None):
            self.connect_calls.append(name)
            return FakeConnectOp(connect_ok, "ok" if connect_ok else "timed out",
                                 parent=parent)

        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            False, parent=parent)
        vpn_manager.connect_vpn_async = fake_connect
        # These tests model a tunnel that dropped on the monitor's watch.
        mc._seen_connected.add('test_vpn')
        vpn_manager.disconnect_vpn_async = lambda name, parent=None: FakeDisconnectOp(
            parent=parent)
        return mc

    # (a) enabled-but-down VPN triggers a reconnect attempt

    def test_down_vpn_triggers_connect(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc._tick()
        pump_events(predicate=lambda: self.connect_calls)
        assert self.connect_calls == ['test_vpn']

    def test_successful_recovery_restores_normal_flow(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc._tick()
        pump_events(
            predicate=lambda: mc.vpn_states.get('test_vpn') == MonitorState.GRACE_PERIOD)
        assert mc.vpn_states['test_vpn'] == MonitorState.GRACE_PERIOD
        assert 'test_vpn' in mc.connection_times

    # (b) repeated failures follow a growing, capped backoff

    def test_failed_recovery_schedules_a_retry(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' in mc._recovery_timers)
        assert 'test_vpn' in mc._recovery_timers, "a failed recovery must retry"
        assert mc.vpn_states['test_vpn'] == MonitorState.RECOVERING
        mc.stop()

    def test_backoff_grows_and_is_capped(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False,
                         monitor_settings={'recovery_backoff_initial_seconds': 30,
                                           'recovery_backoff_max_seconds': 120})
        settings = config_manager.get_monitor_settings()
        delays = []
        for attempt in range(1, 7):
            mc.recovery_attempts['test_vpn'] = attempt
            delays.append(mc._recovery_delay_seconds('test_vpn', settings))
        assert delays == [30, 60, 120, 120, 120, 120]

    def test_backoff_uses_configured_initial_value(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False,
                         monitor_settings={'recovery_backoff_initial_seconds': 5,
                                           'recovery_backoff_max_seconds': 600})
        settings = config_manager.get_monitor_settings()
        mc.recovery_attempts['test_vpn'] = 1
        assert mc._recovery_delay_seconds('test_vpn', settings) == 5

    def test_long_outage_does_not_overflow_backoff(
            self, qapp, config_manager, vpn_manager):
        """A multi-day outage must not build an astronomically large interval."""
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        settings = config_manager.get_monitor_settings()
        mc.recovery_attempts['test_vpn'] = 500
        assert mc._recovery_delay_seconds('test_vpn', settings) == 600

    # (c) a successful reconnect resets the backoff

    def test_success_resets_backoff(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc.recovery_attempts['test_vpn'] = 4
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' not in mc.recovery_attempts)
        assert 'test_vpn' not in mc.recovery_attempts

    def test_observing_vpn_connected_clears_backoff(
            self, qapp, config_manager, vpn_manager):
        """Recovery resumes cleanly once connectivity returns on its own."""
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc.recovery_attempts['test_vpn'] = 3
        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            True, parent=parent)
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' not in mc.recovery_attempts)
        assert 'test_vpn' not in mc.recovery_attempts

    # (d) an outage must never trip the failure_threshold "disable VPN" path

    def test_outage_does_not_increment_failure_count(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        for _ in range(5):
            mc._tick()
            pump_events(timeout_ms=50)
        assert mc.failure_counts.get('test_vpn', 0) == 0
        mc.stop()

    def test_outage_never_disables_the_vpn(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        disabled = []
        mc.vpn_disabled.connect(lambda name, reason: disabled.append(name))
        for _ in range(5):
            mc._tick()
            pump_events(timeout_ms=50)
        assert disabled == []
        assert mc.vpn_states['test_vpn'] != MonitorState.DISABLED
        assert config_manager.get_vpn_config('test_vpn')['enabled'] is True
        mc.stop()

    # (e) a user-initiated disconnect is not auto-reconnected

    def test_user_disconnect_suppresses_recovery(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc.notify_user_disconnected('test_vpn')
        mc._tick()
        pump_events(timeout_ms=100)
        assert self.connect_calls == []
        assert mc.vpn_states['test_vpn'] == MonitorState.IDLE

    def test_user_reconnect_lifts_suppression(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc.notify_user_disconnected('test_vpn')
        mc.reset_vpn_state('test_vpn')  # emitted when the user reconnects
        mc._tick()
        pump_events(predicate=lambda: self.connect_calls)
        assert self.connect_calls == ['test_vpn']

    # per-VPN and global opt-out

    def test_per_vpn_opt_out_wins_over_global(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True, vpn_config={
            'name': 'test_vpn', 'enabled': True, 'asserts': [], 'auto_recovery': False,
        })
        mc._tick()
        pump_events(timeout_ms=100)
        assert self.connect_calls == []
        assert mc.vpn_states['test_vpn'] == MonitorState.IDLE

    def test_per_vpn_opt_in_wins_over_global_off(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True, vpn_config={
            'name': 'test_vpn', 'enabled': True, 'asserts': [], 'auto_recovery': True,
        }, monitor_settings={'auto_recovery': False})
        mc._tick()
        pump_events(predicate=lambda: self.connect_calls)
        assert self.connect_calls == ['test_vpn']

    # the tick loop must not bypass the backoff

    def test_tick_does_not_launch_a_second_connect_during_backoff(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' in mc._recovery_timers)
        for _ in range(3):
            mc._tick()
            pump_events(timeout_ms=50)
        assert len(self.connect_calls) == 1, "backoff must not be reset by ticks"
        mc.stop()

    # a failed bounce hands off to recovery instead of stopping

    def test_failed_bounce_schedules_recovery(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        mc._on_bounce_done('test_vpn', False, "reconnect timed out")
        assert 'test_vpn' in mc._recovery_timers, (
            "a failed bounce left the VPN down; recovery must continue")
        assert mc.recovery_attempts['test_vpn'] == 1
        mc.stop()

    def test_successful_bounce_clears_recovery_state(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=True)
        mc.recovery_attempts['test_vpn'] = 2
        mc._on_bounce_done('test_vpn', True, "ok")
        assert 'test_vpn' not in mc.recovery_attempts
        assert 'test_vpn' not in mc._recovery_timers

    # lifecycle

    def test_stop_cancels_pending_recovery(self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager, connect_ok=False)
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' in mc._recovery_timers)
        mc.stop()
        assert mc._recovery_timers == {}
        assert mc._active_recoveries == {}


class TestRecoveryOnlyRestoresWhatWasUp:
    """Auto-recovery restores tunnels that drop; it never opens new ones.

    On a fresh start the in-memory user-disconnect suppression set is empty, so
    without this guard every configured-and-enabled VPN that happens to be down
    would be connected at launch — the monitor picking connections for the user.
    """

    def _build(self, config_manager, vpn_manager):
        mc = MonitorController(config_manager, vpn_manager)
        mc.monitoring_enabled = True
        config_manager.update_vpn_config('test_vpn', {
            'name': 'test_vpn', 'enabled': True, 'asserts': []
        })
        self.connect_calls = []

        def fake_connect(name, parent=None):
            self.connect_calls.append(name)
            return FakeConnectOp(True, "ok", parent=parent)

        vpn_manager.connect_vpn_async = fake_connect
        vpn_manager.disconnect_vpn_async = lambda name, parent=None: FakeDisconnectOp(
            parent=parent)
        return mc

    def test_vpn_down_since_startup_is_not_connected(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager)
        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            False, parent=parent)

        for _ in range(3):
            mc._tick()
            pump_events(timeout_ms=50)

        assert self.connect_calls == [], (
            "a VPN that was already down at startup must be left alone")
        assert mc.vpn_states['test_vpn'] == MonitorState.IDLE

    def test_vpn_that_drops_after_being_seen_up_is_recovered(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager)

        # First tick: observed connected.
        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            True, parent=parent)
        mc._tick()
        pump_events(predicate=lambda: 'test_vpn' in mc._seen_connected)
        assert 'test_vpn' in mc._seen_connected

        # Then it drops.
        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            False, parent=parent)
        mc._tick()
        pump_events(predicate=lambda: self.connect_calls)

        assert self.connect_calls == ['test_vpn']

    def test_user_connect_makes_vpn_recovery_eligible(
            self, qapp, config_manager, vpn_manager):
        """reset_vpn_state() is emitted when the user connects from the GUI."""
        mc = self._build(config_manager, vpn_manager)
        vpn_manager.is_vpn_active_async = lambda name, parent=None: FakeIsActiveOp(
            False, parent=parent)

        mc.reset_vpn_state('test_vpn')
        mc._tick()
        pump_events(predicate=lambda: self.connect_calls)

        assert self.connect_calls == ['test_vpn']

    def test_bounce_marks_vpn_recovery_eligible(
            self, qapp, config_manager, vpn_manager):
        mc = self._build(config_manager, vpn_manager)
        vpn_manager.bounce_vpn_async = lambda name, parent=None: FakeBounceOp(
            False, "failed", parent=parent)
        mc.failure_counts['test_vpn'] = 1

        mc._start_bounce('test_vpn')

        assert 'test_vpn' in mc._seen_connected
        mc.stop()
