"""
Tests for OpenVPN3Backend
"""
import pytest
from unittest.mock import patch, MagicMock
from vpn_toggle.backends.openvpn3 import OpenVPN3Backend

NO_SESSIONS = "No sessions available"

SESSIONS_CONNECTED = (
    "        Path: /net/openvpn/v3/sessions/abc123\n"
    "     Created: 2026-03-27 12:53:06\n"
    "       Owner: user\n"
    " Config name: aiqlabs\n"
    "      Status: Connection, Client connected\n"
)

SESSIONS_AUTH_PENDING = (
    "        Path: /net/openvpn/v3/sessions/abc123\n"
    "     Created: 2026-03-27 12:53:06\n"
    "       Owner: user\n"
    " Config name: aiqlabs\n"
    "      Status: Web authentication required to connect\n"
)

CONFIGS_OUTPUT = (
    "Configuration Name                                        Last used\n"
    "------------------------------------------------------------------------------\n"
    "aiqlabs                                                   2026-03-17 15:26:07\n"
    "------------------------------------------------------------------------------\n"
)


class TestOpenVPN3Backend:
    """Test suite for OpenVPN3Backend"""

    @patch('subprocess.run')
    def test_available_when_openvpn3_found(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n')
        backend = OpenVPN3Backend()
        assert backend.available is True
        assert backend.name == 'openvpn3'

    @patch('subprocess.run')
    def test_unavailable_when_openvpn3_missing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        backend = OpenVPN3Backend()
        assert backend.available is False

    @patch('subprocess.run')
    def test_list_vpns_empty(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            MagicMock(returncode=0, stdout='Configuration Name    Last used\n---\n---\n', stderr=''),
        ]
        backend = OpenVPN3Backend()
        assert backend.list_vpns() == []

    @patch('subprocess.run')
    def test_list_vpns_with_configs(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            MagicMock(returncode=0, stdout=CONFIGS_OUTPUT, stderr=''),
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
        ]
        backend = OpenVPN3Backend()
        vpns = backend.list_vpns()
        assert len(vpns) == 1
        assert vpns[0].name == 'aiqlabs'
        assert vpns[0].active is False
        assert vpns[0].connection_type == 'openvpn3'

    @patch('subprocess.run')
    def test_list_vpns_with_active_session(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            MagicMock(returncode=0, stdout=CONFIGS_OUTPUT, stderr=''),
            MagicMock(returncode=0, stdout=SESSIONS_CONNECTED, stderr=''),
        ]
        backend = OpenVPN3Backend()
        vpns = backend.list_vpns()
        assert len(vpns) == 1
        assert vpns[0].active is True

    @patch('subprocess.run')
    def test_is_vpn_active_connected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # _get_sessions_for_config -> sessions-list
            MagicMock(returncode=0, stdout=SESSIONS_CONNECTED, stderr=''),
        ]
        backend = OpenVPN3Backend()
        assert backend.is_vpn_active('aiqlabs') is True

    @patch('subprocess.run')
    def test_is_vpn_active_not_connected(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
        ]
        backend = OpenVPN3Backend()
        assert backend.is_vpn_active('aiqlabs') is False

    @patch('subprocess.run')
    def test_disconnect_vpn_success(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # _get_sessions_for_config -> sessions-list
            MagicMock(returncode=0, stdout=SESSIONS_CONNECTED, stderr=''),
            # _disconnect_by_path
            MagicMock(returncode=0, stdout='', stderr=''),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.disconnect_vpn('aiqlabs')
        assert success is True
        assert 'Disconnected' in message

    @patch('subprocess.run')
    def test_disconnect_vpn_no_session(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # _get_sessions_for_config -> no sessions
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.disconnect_vpn('aiqlabs')
        assert success is True
        assert 'No active session' in message

    @patch.object(OpenVPN3Backend, '_raise_browser')
    @patch('time.sleep')
    @patch('subprocess.run')
    def test_connect_vpn_success(self, mock_run, mock_sleep, mock_raise):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # check for stale sessions
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
            # session-start
            MagicMock(returncode=0, stdout='Session started\n', stderr=''),
            # first poll — connected
            MagicMock(returncode=0, stdout=SESSIONS_CONNECTED, stderr=''),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.connect_vpn('aiqlabs', auth_timeout=10)
        assert success is True
        assert 'Connected' in message
        mock_raise.assert_called_once()

    @patch.object(OpenVPN3Backend, '_raise_browser')
    @patch('time.sleep')
    @patch('subprocess.run')
    def test_connect_vpn_cleans_stale_sessions(self, mock_run, mock_sleep, mock_raise):
        """Connect cleans up existing sessions before starting a new one."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # check for stale sessions - finds one
            MagicMock(returncode=0, stdout=SESSIONS_AUTH_PENDING, stderr=''),
            # _disconnect_all_sessions -> sessions-list
            MagicMock(returncode=0, stdout=SESSIONS_AUTH_PENDING, stderr=''),
            # _disconnect_by_path
            MagicMock(returncode=0, stdout='', stderr=''),
            # session-start
            MagicMock(returncode=0, stdout='Session started\n', stderr=''),
            # poll — connected
            MagicMock(returncode=0, stdout=SESSIONS_CONNECTED, stderr=''),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.connect_vpn('aiqlabs', auth_timeout=10)
        assert success is True

    @patch.object(OpenVPN3Backend, '_raise_browser')
    @patch('time.sleep')
    @patch('subprocess.run')
    def test_connect_vpn_auth_timeout(self, mock_run, mock_sleep, mock_raise):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # check for stale sessions
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
            # session-start
            MagicMock(returncode=0, stdout='Session started\n', stderr=''),
            # polls — never connected
        ] + [MagicMock(returncode=0, stdout=SESSIONS_AUTH_PENDING, stderr='')] * 10 + [
            # _disconnect_all_sessions -> sessions-list
            MagicMock(returncode=0, stdout=SESSIONS_AUTH_PENDING, stderr=''),
            # _disconnect_by_path
            MagicMock(returncode=0, stdout='', stderr=''),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.connect_vpn('aiqlabs', auth_timeout=4)
        assert success is False
        assert 'timed out' in message.lower()

    @patch('subprocess.run')
    def test_connect_vpn_start_failure(self, mock_run):
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n'),
            # check for stale sessions
            MagicMock(returncode=0, stdout=NO_SESSIONS, stderr=''),
            # session-start fails
            MagicMock(returncode=1, stdout='', stderr='No config found'),
        ]
        backend = OpenVPN3Backend()
        success, message = backend.connect_vpn('nonexistent')
        assert success is False
        assert 'Failed' in message

    @patch('subprocess.run')
    def test_get_connection_timestamp_returns_none(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n')
        backend = OpenVPN3Backend()
        assert backend.get_connection_timestamp('aiqlabs') is None

    @patch('subprocess.run')
    def test_unavailable_returns_empty_list(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        backend = OpenVPN3Backend()
        assert backend.list_vpns() == []
        assert backend.is_vpn_active('foo') is False

    @patch('subprocess.run')
    def test_parse_configs_list_multiple(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n')
        backend = OpenVPN3Backend()

        output = (
            "Configuration Name                                        Last used\n"
            "------------------------------------------------------------------------------\n"
            "aiqlabs                                                   2026-03-17 15:26:07\n"
            "work-vpn                                                  2026-03-10 09:00:00\n"
            "------------------------------------------------------------------------------\n"
        )
        names = backend._parse_configs_list(output)
        assert names == ['aiqlabs', 'work-vpn']

    @patch('subprocess.run')
    def test_parse_sessions(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/openvpn3\n')
        backend = OpenVPN3Backend()

        output = (
            "        Path: /net/openvpn/v3/sessions/abc123\n"
            "     Created: 2026-03-27 12:53:06\n"
            "       Owner: user\n"
            " Config name: aiqlabs\n"
            "      Status: Client connected\n"
            "\n"
            "        Path: /net/openvpn/v3/sessions/def456\n"
            "     Created: 2026-03-27 12:54:00\n"
            "       Owner: user\n"
            " Config name: aiqlabs\n"
            "      Status: Web authentication required to connect\n"
        )
        sessions = backend._parse_sessions(output)
        assert len(sessions) == 2
        assert sessions[0]['path'] == '/net/openvpn/v3/sessions/abc123'
        assert sessions[0]['config_name'] == 'aiqlabs'
        assert sessions[0]['status'] == 'Client connected'
        assert sessions[1]['path'] == '/net/openvpn/v3/sessions/def456'
        assert sessions[1]['status'] == 'Web authentication required to connect'
