"""
Tests for MonitorThread
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
import tempfile
from pathlib import Path

from vpn_toggle.monitor import MonitorThread, MonitorState
from vpn_toggle.config import ConfigManager
from vpn_toggle.vpn_manager import VPNManager


@pytest.fixture
def temp_config_file():
    """Fixture to provide a unique temporary config file for each test"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_config.json"


@pytest.fixture
def config_manager(temp_config_file):
    """Fixture to provide a ConfigManager instance"""
    with patch('subprocess.run'):  # Mock subprocess for VPNManager init
        return ConfigManager(str(temp_config_file))


@pytest.fixture
def vpn_manager():
    """Fixture to provide a mocked VPNManager instance"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        return VPNManager()


class TestMonitorThread:
    """Test suite for MonitorThread"""

    def test_init(self, config_manager, vpn_manager):
        """Test monitor thread initialization"""
        monitor = MonitorThread(config_manager, vpn_manager)

        assert monitor.config_manager == config_manager
        assert monitor.vpn_manager == vpn_manager
        assert monitor.running is True
        assert monitor.monitoring_enabled is False
        assert monitor.failure_counts == {}
        assert monitor.last_check_times == {}

    def test_enable_monitoring(self, config_manager, vpn_manager):
        """Test enabling monitoring"""
        monitor = MonitorThread(config_manager, vpn_manager)

        monitor.enable_monitoring()

        assert monitor.monitoring_enabled is True
        settings = config_manager.get_monitor_settings()
        assert settings['enabled'] is True

    def test_disable_monitoring(self, config_manager, vpn_manager):
        """Test disabling monitoring"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.monitoring_enabled = True

        monitor.disable_monitoring()

        assert monitor.monitoring_enabled is False
        settings = config_manager.get_monitor_settings()
        assert settings['enabled'] is False

    def test_reset_vpn_state(self, config_manager, vpn_manager):
        """Test resetting VPN state"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.failure_counts['test_vpn'] = 5

        monitor.reset_vpn_state('test_vpn')

        assert monitor.failure_counts['test_vpn'] == 0
        assert 'test_vpn' in monitor.connection_times
        assert monitor.vpn_states['test_vpn'] == MonitorState.GRACE_PERIOD

    def test_get_vpn_status(self, config_manager, vpn_manager):
        """Test getting VPN status"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.failure_counts['test_vpn'] = 2
        monitor.vpn_states['test_vpn'] = MonitorState.MONITORING

        status = monitor.get_vpn_status('test_vpn')

        assert status['state'] == MonitorState.MONITORING.value
        assert status['failure_count'] == 2

    def test_get_vpn_status_not_tracked(self, config_manager, vpn_manager):
        """Test getting status for VPN that hasn't been tracked"""
        monitor = MonitorThread(config_manager, vpn_manager)

        status = monitor.get_vpn_status('unknown_vpn')

        assert status['state'] == MonitorState.IDLE.value
        assert status['failure_count'] == 0

    @patch('time.sleep')
    def test_check_vpn_not_connected(self, mock_sleep, config_manager, vpn_manager):
        """Test checking VPN when it's not connected"""
        monitor = MonitorThread(config_manager, vpn_manager)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': []
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        with patch.object(vpn_manager, 'is_vpn_active', return_value=False):
            monitor._check_vpn(vpn_config, monitor_settings)

        # Should set state to IDLE
        assert monitor.vpn_states.get('test_vpn') == MonitorState.IDLE

    @patch('time.sleep')
    def test_check_vpn_grace_period(self, mock_sleep, config_manager, vpn_manager):
        """Test checking VPN during grace period"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now()  # Just connected

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': []
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            monitor._check_vpn(vpn_config, monitor_settings)

        # Should be in grace period
        assert monitor.vpn_states.get('test_vpn') == MonitorState.GRACE_PERIOD

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_vpn_assert_passes(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        """Test checking VPN when asserts pass"""
        monitor = MonitorThread(config_manager, vpn_manager)
        # Set connection time to past (beyond grace period)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)
        monitor.failure_counts['test_vpn'] = 2  # Had previous failures

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        # Mock assert to pass
        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=True, message="DNS check passed")
        mock_create_assert.return_value = mock_assert

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            monitor._check_vpn(vpn_config, monitor_settings)

        # Failure count should be reset
        assert monitor.failure_counts['test_vpn'] == 0
        assert monitor.vpn_states.get('test_vpn') == MonitorState.MONITORING

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_vpn_assert_fails_auto_reconnect(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        """Test checking VPN when assert fails and auto-reconnect is triggered"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        # Mock assert to fail
        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=False, message="DNS check failed")
        mock_create_assert.return_value = mock_assert

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            with patch.object(vpn_manager, 'bounce_vpn', return_value=(True, "Reconnected")) as mock_bounce:
                monitor._check_vpn(vpn_config, monitor_settings)

        # Failure count should be incremented
        assert monitor.failure_counts['test_vpn'] == 1
        # VPN should have been bounced
        mock_bounce.assert_called_once_with('test_vpn')

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_vpn_threshold_exceeded(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        """Test checking VPN when failure threshold is exceeded"""
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)
        monitor.failure_counts['test_vpn'] = 2  # Already at 2 failures

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        # Mock assert to fail
        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=False, message="DNS check failed")
        mock_create_assert.return_value = mock_assert

        # Track signal emissions
        disabled_emitted = []
        monitor.vpn_disabled.connect(lambda vpn, reason: disabled_emitted.append((vpn, reason)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            with patch.object(vpn_manager, 'disconnect_vpn', return_value=(True, "Disconnected")) as mock_disconnect:
                monitor._check_vpn(vpn_config, monitor_settings)

        # Failure count should be 3 (threshold)
        assert monitor.failure_counts['test_vpn'] == 3
        # VPN should be disabled
        assert monitor.vpn_states['test_vpn'] == MonitorState.DISABLED
        # VPN should have been disconnected
        mock_disconnect.assert_called_once_with('test_vpn')
        # Signal should have been emitted
        assert len(disabled_emitted) == 1
        assert disabled_emitted[0][0] == 'test_vpn'

    @patch('vpn_toggle.monitor.create_assert')
    def test_run_assert_with_retry_success(self, mock_create_assert, config_manager, vpn_manager):
        """Test running assert with retry on success"""
        monitor = MonitorThread(config_manager, vpn_manager)

        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=True, message="Passed")

        with patch('time.sleep'):
            result = monitor._run_assert_with_retry(mock_assert, retries=2)

        assert result.success is True
        # Should only call once if it succeeds
        assert mock_assert.check.call_count == 1

    @patch('vpn_toggle.monitor.create_assert')
    def test_run_assert_with_retry_failure_then_success(self, mock_create_assert, config_manager, vpn_manager):
        """Test running assert with retry when it fails then succeeds"""
        monitor = MonitorThread(config_manager, vpn_manager)

        mock_assert = MagicMock()
        mock_assert.check.side_effect = [
            MagicMock(success=False, message="Failed"),
            MagicMock(success=True, message="Passed")
        ]

        with patch('time.sleep'):
            result = monitor._run_assert_with_retry(mock_assert, retries=2)

        assert result.success is True
        # Should call twice (fail, then succeed)
        assert mock_assert.check.call_count == 2

    @patch('vpn_toggle.monitor.create_assert')
    def test_run_assert_with_retry_all_failures(self, mock_create_assert, config_manager, vpn_manager):
        """Test running assert with retry when all attempts fail"""
        monitor = MonitorThread(config_manager, vpn_manager)

        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=False, message="Failed")

        with patch('time.sleep'):
            result = monitor._run_assert_with_retry(mock_assert, retries=2)

        assert result.success is False
        # Should call 3 times (initial + 2 retries)
        assert mock_assert.check.call_count == 3

    def test_get_monitored_vpns(self, config_manager, vpn_manager):
        """Test getting list of monitored VPNs"""
        monitor = MonitorThread(config_manager, vpn_manager)

        # Add some VPNs to config
        config_manager.update_vpn_config('vpn1', {'name': 'vpn1', 'enabled': True})
        config_manager.update_vpn_config('vpn2', {'name': 'vpn2', 'enabled': False})

        vpns = monitor._get_monitored_vpns()

        assert len(vpns) == 2
        assert any(vpn['name'] == 'vpn1' for vpn in vpns)
        assert any(vpn['name'] == 'vpn2' for vpn in vpns)


class TestCheckCompletedSignal:
    """Tests for the check_completed signal and timing instrumentation"""

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_completed_emitted_on_pass(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=True, message="Passed")
        mock_create_assert.return_value = mock_assert

        emitted = []
        monitor.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            monitor._check_vpn(vpn_config, monitor_settings)

        assert len(emitted) == 1
        vpn_name, data_point = emitted[0]
        assert vpn_name == 'test_vpn'
        assert data_point['success'] is True
        assert data_point['bounce_triggered'] is False
        assert data_point['latency_ms'] >= 0
        assert data_point['vpn_name'] == 'test_vpn'
        assert 'timestamp' in data_point

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_completed_contains_assert_details(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [
                {'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'},
                {'type': 'geolocation', 'field': 'city', 'expected_value': 'Vegas'},
            ]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=True, message="Passed")
        mock_create_assert.return_value = mock_assert

        emitted = []
        monitor.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            monitor._check_vpn(vpn_config, monitor_settings)

        data_point = emitted[0][1]
        assert len(data_point['assert_details']) == 2
        assert data_point['assert_details'][0]['type'] == 'dns_lookup'
        assert data_point['assert_details'][1]['type'] == 'geolocation'
        for detail in data_point['assert_details']:
            assert 'latency_ms' in detail
            assert 'success' in detail
            assert detail['latency_ms'] >= 0

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_completed_marks_bounce(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now() - timedelta(seconds=30)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        mock_assert = MagicMock()
        mock_assert.check.return_value = MagicMock(success=False, message="Failed")
        mock_create_assert.return_value = mock_assert

        emitted = []
        monitor.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            with patch.object(vpn_manager, 'bounce_vpn', return_value=(True, "OK")):
                monitor._check_vpn(vpn_config, monitor_settings)

        data_point = emitted[0][1]
        assert data_point['success'] is False
        assert data_point['bounce_triggered'] is True

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_completed_not_emitted_when_not_connected(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        monitor = MonitorThread(config_manager, vpn_manager)

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        emitted = []
        monitor.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=False):
            monitor._check_vpn(vpn_config, monitor_settings)

        assert len(emitted) == 0

    @patch('time.sleep')
    @patch('vpn_toggle.monitor.create_assert')
    def test_check_completed_not_emitted_during_grace_period(self, mock_create_assert, mock_sleep, config_manager, vpn_manager):
        monitor = MonitorThread(config_manager, vpn_manager)
        monitor.connection_times['test_vpn'] = datetime.now()

        vpn_config = {
            'name': 'test_vpn',
            'enabled': True,
            'asserts': [{'type': 'dns_lookup', 'hostname': 'test.com', 'expected_prefix': '10.'}]
        }
        monitor_settings = {'grace_period_seconds': 15, 'failure_threshold': 3}

        emitted = []
        monitor.check_completed.connect(lambda vpn, dp: emitted.append((vpn, dp)))

        with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
            monitor._check_vpn(vpn_config, monitor_settings)

        assert len(emitted) == 0
