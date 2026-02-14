"""
Tests for VPNManager
"""
import pytest
from unittest.mock import patch, MagicMock
from vpn_toggle.vpn_manager import VPNManager, VPNConnection, VPNStatus


class TestVPNManager:
    """Test suite for VPNManager"""

    @patch('subprocess.run')
    def test_init_nmcli_available(self, mock_run):
        """Test initialization when nmcli is available"""
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')

        manager = VPNManager()
        assert manager is not None

    @patch('subprocess.run')
    def test_init_nmcli_not_available(self, mock_run):
        """Test initialization when nmcli is not available"""
        mock_run.return_value = MagicMock(returncode=1)

        with pytest.raises(RuntimeError, match="nmcli command not found"):
            VPNManager()

    @patch('subprocess.run')
    def test_list_vpns_empty(self, mock_run):
        """Test listing VPNs when none exist"""
        # First call: which nmcli (available)
        # Second call: list connections (empty)
        # Third call: list active connections (empty)
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='', stderr=''),
            MagicMock(returncode=0, stdout='', stderr='')
        ]

        manager = VPNManager()
        vpns = manager.list_vpns()

        assert vpns == []

    @patch('subprocess.run')
    def test_list_vpns_with_connections(self, mock_run):
        """Test listing VPNs when connections exist"""
        # First call: which nmcli
        # Second call: list connections
        # Third call: list active connections
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=0,
                stdout='vpn1:vpn\nvpn2:vpn\nwifi1:802-11-wireless\n',
                stderr=''
            ),
            MagicMock(
                returncode=0,
                stdout='vpn1         123-456-789  vpn       eth0\n',
                stderr=''
            )
        ]

        manager = VPNManager()
        vpns = manager.list_vpns()

        assert len(vpns) == 2
        assert vpns[0].name == 'vpn1'
        assert vpns[0].active is True
        assert vpns[1].name == 'vpn2'
        assert vpns[1].active is False

    @patch('subprocess.run')
    def test_is_vpn_active_when_active(self, mock_run):
        """Test checking if VPN is active when it is"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=0,
                stdout='test_vpn         123-456  vpn  eth0\n',
                stderr=''
            )
        ]

        manager = VPNManager()
        is_active = manager.is_vpn_active('test_vpn')

        assert is_active is True

    @patch('subprocess.run')
    def test_is_vpn_active_when_inactive(self, mock_run):
        """Test checking if VPN is active when it isn't"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='', stderr='')
        ]

        manager = VPNManager()
        is_active = manager.is_vpn_active('test_vpn')

        assert is_active is False

    @patch('subprocess.run')
    def test_connect_vpn_success(self, mock_run):
        """Test successful VPN connection"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=0,
                stdout='Connection successfully activated\n',
                stderr=''
            )
        ]

        manager = VPNManager()
        success, message = manager.connect_vpn('test_vpn')

        assert success is True
        assert 'Connected' in message

    @patch('subprocess.run')
    def test_connect_vpn_failure(self, mock_run):
        """Test failed VPN connection"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=1,
                stdout='',
                stderr='Error: Connection activation failed\n'
            )
        ]

        manager = VPNManager()
        success, message = manager.connect_vpn('test_vpn')

        assert success is False
        assert 'Failed' in message

    @patch('subprocess.run')
    def test_disconnect_vpn_success(self, mock_run):
        """Test successful VPN disconnection"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=0,
                stdout='Connection successfully deactivated\n',
                stderr=''
            )
        ]

        manager = VPNManager()
        success, message = manager.disconnect_vpn('test_vpn')

        assert success is True
        assert 'Disconnected' in message

    @patch('subprocess.run')
    def test_disconnect_vpn_failure(self, mock_run):
        """Test failed VPN disconnection"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(
                returncode=1,
                stdout='',
                stderr='Error: Connection deactivation failed\n'
            )
        ]

        manager = VPNManager()
        success, message = manager.disconnect_vpn('test_vpn')

        assert success is False
        assert 'Failed' in message

    @patch('subprocess.run')
    @patch('time.sleep')  # Mock sleep to speed up test
    def test_bounce_vpn_success(self, mock_sleep, mock_run):
        """Test successful VPN bounce"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            # Disconnect
            MagicMock(returncode=0, stdout='Deactivated\n', stderr=''),
            # Reconnect
            MagicMock(returncode=0, stdout='Activated\n', stderr='')
        ]

        manager = VPNManager()
        success, message = manager.bounce_vpn('test_vpn')

        assert success is True
        assert 'Bounced' in message
        mock_sleep.assert_called_once_with(2)

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_bounce_vpn_reconnect_failure(self, mock_sleep, mock_run):
        """Test VPN bounce when reconnect fails"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            # Disconnect (success)
            MagicMock(returncode=0, stdout='Deactivated\n', stderr=''),
            # Reconnect (failure)
            MagicMock(returncode=1, stdout='', stderr='Connection failed\n')
        ]

        manager = VPNManager()
        success, message = manager.bounce_vpn('test_vpn')

        assert success is False
        assert 'Bounce failed' in message

    @patch('subprocess.run')
    def test_get_vpn_status_connected(self, mock_run):
        """Test getting VPN status when connected"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            # is_vpn_active call
            MagicMock(returncode=0, stdout='test_vpn  123  vpn  eth0\n', stderr=''),
            # get IP address call
            MagicMock(returncode=0, stdout='IP4.ADDRESS[1]:10.8.0.2/24\n', stderr='')
        ]

        manager = VPNManager()
        status = manager.get_vpn_status('test_vpn')

        assert status.connected is True
        assert status.ip_address == '10.8.0.2'

    @patch('subprocess.run')
    def test_get_vpn_status_disconnected(self, mock_run):
        """Test getting VPN status when disconnected"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            # is_vpn_active call
            MagicMock(returncode=0, stdout='', stderr='')
        ]

        manager = VPNManager()
        status = manager.get_vpn_status('test_vpn')

        assert status.connected is False
        assert status.ip_address is None

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_datetime(self, mock_run):
        """Test that a valid epoch timestamp is returned as datetime"""
        from datetime import datetime

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='connection.timestamp:1739371200\n', stderr='')
        ]

        manager = VPNManager()
        ts = manager.get_connection_timestamp('test_vpn')

        assert ts is not None
        assert isinstance(ts, datetime)
        assert ts == datetime.fromtimestamp(1739371200)

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_none_when_zero(self, mock_run):
        """Test that a zero timestamp returns None (never connected)"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='connection.timestamp:0\n', stderr='')
        ]

        manager = VPNManager()
        ts = manager.get_connection_timestamp('test_vpn')

        assert ts is None

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_none_on_failure(self, mock_run):
        """Test that nmcli failure returns None"""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=1, stdout='', stderr='Error')
        ]

        manager = VPNManager()
        ts = manager.get_connection_timestamp('test_vpn')

        assert ts is None

    @patch('subprocess.run')
    def test_run_nmcli_timeout(self, mock_run):
        """Test nmcli command timeout"""
        import subprocess

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            subprocess.TimeoutExpired(cmd='nmcli', timeout=30)
        ]

        manager = VPNManager()
        success, message = manager.connect_vpn('test_vpn')

        assert success is False
        assert 'timed out' in message.lower()
