"""
Tests for VPNManager facade and NMBackend
"""
import pytest
from unittest.mock import patch, MagicMock
from vpn_toggle.vpn_manager import VPNManager, VPNConnection, VPNStatus
from vpn_toggle.backends.nm import NMBackend


class TestNMBackend:
    """Test suite for NMBackend directly"""

    @patch('subprocess.run')
    def test_available_when_nmcli_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        backend = NMBackend()
        assert backend.available is True

    @patch('subprocess.run')
    def test_unavailable_when_nmcli_missing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        backend = NMBackend()
        assert backend.available is False

    @patch('subprocess.run')
    def test_list_vpns_empty(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='', stderr=''),
            MagicMock(returncode=0, stdout='', stderr='')
        ]
        backend = NMBackend()
        assert backend.list_vpns() == []

    @patch('subprocess.run')
    def test_list_vpns_with_connections(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='vpn1:vpn\nvpn2:vpn\nwifi1:802-11-wireless\n', stderr=''),
            MagicMock(returncode=0, stdout='vpn1         123-456-789  vpn       eth0\n', stderr='')
        ]
        backend = NMBackend()
        vpns = backend.list_vpns()
        assert len(vpns) == 2
        assert vpns[0].name == 'vpn1'
        assert vpns[0].active is True
        assert vpns[1].name == 'vpn2'
        assert vpns[1].active is False

    @patch('subprocess.run')
    def test_is_vpn_active_true(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='test_vpn         123-456  vpn  eth0\n', stderr='')
        ]
        backend = NMBackend()
        assert backend.is_vpn_active('test_vpn') is True

    @patch('subprocess.run')
    def test_is_vpn_active_false(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='', stderr='')
        ]
        backend = NMBackend()
        assert backend.is_vpn_active('test_vpn') is False

    @patch('subprocess.run')
    def test_connect_vpn_success(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='Connection successfully activated\n', stderr='')
        ]
        backend = NMBackend()
        success, message = backend.connect_vpn('test_vpn')
        assert success is True
        assert 'Connected' in message

    @patch('subprocess.run')
    def test_connect_vpn_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=1, stdout='', stderr='Error: Connection activation failed\n')
        ]
        backend = NMBackend()
        success, message = backend.connect_vpn('test_vpn')
        assert success is False
        assert 'Failed' in message

    @patch('subprocess.run')
    def test_disconnect_vpn_success(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='Connection successfully deactivated\n', stderr='')
        ]
        backend = NMBackend()
        success, message = backend.disconnect_vpn('test_vpn')
        assert success is True
        assert 'Disconnected' in message

    @patch('subprocess.run')
    def test_disconnect_vpn_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=1, stdout='', stderr='Error: Connection deactivation failed\n')
        ]
        backend = NMBackend()
        success, message = backend.disconnect_vpn('test_vpn')
        assert success is False
        assert 'Failed' in message

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_bounce_vpn_success(self, mock_sleep, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='Deactivated\n', stderr=''),
            MagicMock(returncode=0, stdout='Activated\n', stderr='')
        ]
        backend = NMBackend()
        success, message = backend.bounce_vpn('test_vpn')
        assert success is True
        assert 'Bounced' in message
        mock_sleep.assert_called_once_with(2)

    @patch('subprocess.run')
    @patch('time.sleep')
    def test_bounce_vpn_reconnect_failure(self, mock_sleep, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='Deactivated\n', stderr=''),
            MagicMock(returncode=1, stdout='', stderr='Connection failed\n')
        ]
        backend = NMBackend()
        success, message = backend.bounce_vpn('test_vpn')
        assert success is False
        assert 'Bounce failed' in message

    @patch('subprocess.run')
    def test_get_vpn_status_connected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='test_vpn  123  vpn  eth0\n', stderr=''),
            MagicMock(returncode=0, stdout='IP4.ADDRESS[1]:10.8.0.2/24\n', stderr='')
        ]
        backend = NMBackend()
        status = backend.get_vpn_status('test_vpn')
        assert status.connected is True
        assert status.ip_address == '10.8.0.2'

    @patch('subprocess.run')
    def test_get_vpn_status_disconnected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='', stderr='')
        ]
        backend = NMBackend()
        status = backend.get_vpn_status('test_vpn')
        assert status.connected is False
        assert status.ip_address is None

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_datetime(self, mock_run):
        from datetime import datetime
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='connection.timestamp:1739371200\n', stderr='')
        ]
        backend = NMBackend()
        ts = backend.get_connection_timestamp('test_vpn')
        assert ts is not None
        assert isinstance(ts, datetime)
        assert ts == datetime.fromtimestamp(1739371200)

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_none_when_zero(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=0, stdout='connection.timestamp:0\n', stderr='')
        ]
        backend = NMBackend()
        assert backend.get_connection_timestamp('test_vpn') is None

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_none_on_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            MagicMock(returncode=1, stdout='', stderr='Error')
        ]
        backend = NMBackend()
        assert backend.get_connection_timestamp('test_vpn') is None

    @patch('subprocess.run')
    def test_run_nmcli_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/nmcli\n'),
            subprocess.TimeoutExpired(cmd='nmcli', timeout=30)
        ]
        backend = NMBackend()
        success, message = backend.connect_vpn('test_vpn')
        assert success is False
        assert 'timed out' in message.lower()


class TestVPNManagerFacade:
    """Test suite for VPNManager facade dispatch"""

    @patch('subprocess.run')
    def test_init_with_nm_available(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        manager = VPNManager()
        assert 'networkmanager' in manager._backends

    @patch('subprocess.run')
    def test_init_raises_when_no_backends(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='')
        with pytest.raises(RuntimeError, match="No VPN backends available"):
            VPNManager()

    @patch('subprocess.run')
    def test_list_vpns_merges_backends(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        manager = VPNManager()

        nm_vpns = [VPNConnection("vpn1", "VPN 1", False, "vpn")]
        ov3_vpns = [VPNConnection("aiqlabs", "AIQ", True, "openvpn3")]

        mock_nm = MagicMock()
        mock_nm.list_vpns.return_value = nm_vpns
        mock_ov3 = MagicMock()
        mock_ov3.list_vpns.return_value = ov3_vpns

        manager._backends = {'networkmanager': mock_nm, 'openvpn3': mock_ov3}
        result = manager.list_vpns()
        assert len(result) == 2

    @patch('subprocess.run')
    def test_dispatch_to_correct_backend(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')

        config_mgr = MagicMock()
        config_mgr.get_vpn_config.return_value = {'backend': 'openvpn3'}

        manager = VPNManager(config_manager=config_mgr)

        mock_ov3 = MagicMock()
        mock_ov3.name = 'openvpn3'
        mock_ov3.is_vpn_active.return_value = True
        manager._backends['openvpn3'] = mock_ov3

        result = manager.is_vpn_active('aiqlabs')
        mock_ov3.is_vpn_active.assert_called_once_with('aiqlabs')
        assert result is True

    @patch('subprocess.run')
    def test_dispatch_defaults_to_nm(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')

        config_mgr = MagicMock()
        config_mgr.get_vpn_config.return_value = None  # No config entry

        manager = VPNManager(config_manager=config_mgr)

        mock_nm = MagicMock()
        mock_nm.name = 'networkmanager'
        mock_nm.connect_vpn.return_value = (True, "Connected")
        manager._backends['networkmanager'] = mock_nm

        success, msg = manager.connect_vpn('some-vpn')
        mock_nm.connect_vpn.assert_called_once_with('some-vpn')
        assert success is True

    @patch('subprocess.run')
    def test_connect_passes_auth_timeout(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')

        config_mgr = MagicMock()
        config_mgr.get_vpn_config.return_value = {
            'backend': 'openvpn3',
            'auth_timeout_seconds': 90
        }

        manager = VPNManager(config_manager=config_mgr)

        mock_ov3 = MagicMock()
        mock_ov3.name = 'openvpn3'
        mock_ov3.connect_vpn.return_value = (True, "Connected")
        manager._backends['openvpn3'] = mock_ov3

        manager.connect_vpn('aiqlabs')
        mock_ov3.connect_vpn.assert_called_once_with('aiqlabs', auth_timeout=90)
