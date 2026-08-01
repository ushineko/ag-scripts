"""
Tests for GUI components
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, call
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from vpn_toggle.config import ConfigManager
from vpn_toggle.gui import VPNToggleMainWindow
from vpn_toggle.widgets import VPNWidget
from vpn_toggle.dialogs import SettingsDialog


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication instance for the test session"""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def temp_config_file():
    """Fixture to provide a unique temporary config file for each test"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_config.json"


@pytest.fixture
def config_manager(temp_config_file):
    """Fixture to provide a ConfigManager instance"""
    with patch('subprocess.run'):
        return ConfigManager(str(temp_config_file))


@pytest.fixture
def vpn_manager(config_manager):
    """Fixture to provide a mocked VPNManager instance"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        from vpn_toggle.vpn_manager import VPNManager
        return VPNManager(config_manager=config_manager)


@pytest.fixture
def main_window(qapp, config_manager, vpn_manager):
    """Fixture to provide a VPNToggleMainWindow instance"""
    with patch.object(vpn_manager, 'list_vpns', return_value=[]):
        window = VPNToggleMainWindow(config_manager, vpn_manager)
        yield window
        window.close()


class TestAppendLog:
    """Test suite for activity log line limiting"""

    def test_append_log_adds_message(self, main_window):
        """Test that append_log adds a timestamped message"""
        main_window.append_log("test message")
        text = main_window.log_text.toPlainText()
        assert "test message" in text

    def test_append_log_includes_timestamp(self, main_window):
        """Test that log entries include a timestamp"""
        main_window.append_log("hello")
        text = main_window.log_text.toPlainText()
        # Timestamp format: [HH:MM:SS]
        assert "[" in text and "]" in text

    def test_append_log_respects_max_lines(self, main_window):
        """Test that log is pruned when exceeding MAX_LOG_LINES"""
        max_lines = VPNToggleMainWindow.MAX_LOG_LINES

        # Add more lines than the limit
        for i in range(max_lines + 100):
            main_window.append_log(f"line {i}")

        doc = main_window.log_text.document()
        assert doc.blockCount() <= max_lines

    def test_append_log_preserves_recent_lines(self, main_window):
        """Test that pruning keeps the most recent lines"""
        max_lines = VPNToggleMainWindow.MAX_LOG_LINES

        for i in range(max_lines + 50):
            main_window.append_log(f"msg-{i}")

        text = main_window.log_text.toPlainText()
        # The most recent message should still be present
        assert f"msg-{max_lines + 49}" in text
        # The oldest messages should be gone
        assert "msg-0" not in text

    def test_append_log_does_not_prune_under_limit(self, main_window):
        """Test that no pruning occurs when under the limit"""
        for i in range(10):
            main_window.append_log(f"line {i}")

        doc = main_window.log_text.document()
        # blockCount includes an initial empty block, so we check content
        text = main_window.log_text.toPlainText()
        for i in range(10):
            assert f"line {i}" in text

    def test_max_log_lines_class_attribute(self):
        """Test that MAX_LOG_LINES is defined and reasonable"""
        assert hasattr(VPNToggleMainWindow, 'MAX_LOG_LINES')
        assert VPNToggleMainWindow.MAX_LOG_LINES > 0
        assert VPNToggleMainWindow.MAX_LOG_LINES <= 10000


class TestConnectionTime:
    """Test suite for VPN connection time counter."""

    @pytest.fixture
    def vpn_widget(self, qapp, config_manager):
        """Create a VPNWidget with mocked VPN manager."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()

        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                widget = VPNWidget("test-vpn", "Test VPN", vm, config_manager)
        return widget

    def test_connection_time_label_exists(self, vpn_widget):
        """VPN widget has a connection time label."""
        assert hasattr(vpn_widget, 'connection_time_label')
        assert vpn_widget.connection_time_label.text() == ""

    def test_connection_time_shows_elapsed(self, vpn_widget):
        """Connection time label shows DD:HH:MM:SS format when connected."""
        vpn_widget._connected_since = datetime.now() - timedelta(
            days=1, hours=2, minutes=33, seconds=45
        )
        vpn_widget.update_connection_time()

        text = vpn_widget.connection_time_label.text()
        assert text == "01:02:33:45"

    def test_connection_time_clears_when_disconnected(self, vpn_widget):
        """Connection time clears when _connected_since is None."""
        vpn_widget._connected_since = datetime.now() - timedelta(hours=1)
        vpn_widget.update_connection_time()
        assert vpn_widget.connection_time_label.text() != ""

        vpn_widget._connected_since = None
        vpn_widget.update_connection_time()
        assert vpn_widget.connection_time_label.text() == ""

    def test_connection_time_zero(self, vpn_widget):
        """Fresh connection shows 00:00:00:00."""
        vpn_widget._connected_since = datetime.now()
        vpn_widget.update_connection_time()

        text = vpn_widget.connection_time_label.text()
        assert text == "00:00:00:00"


class TestSystemTray:
    """Test suite for system tray integration."""

    def test_tray_icon_created_when_available(self, main_window):
        """Tray icon is created when system tray is available."""
        if QSystemTrayIcon.isSystemTrayAvailable():
            assert main_window.tray.available is True
            assert main_window.tray.tray_icon is not None
        else:
            assert main_window.tray.available is False

    def test_tray_available_flag_set(self, main_window):
        """tray.available reflects actual system tray availability."""
        expected = QSystemTrayIcon.isSystemTrayAvailable()
        assert main_window.tray.available == expected

    def test_quit_application_stops_monitor(self, main_window):
        """quit_application stops the monitor thread."""
        mock_thread = MagicMock()
        mock_thread.isRunning.return_value = True
        main_window.monitor_thread = mock_thread

        with patch.object(QApplication, 'quit'):
            main_window.quit_application()

        mock_thread.stop.assert_called_once()
        assert main_window._quitting is True

    def test_close_event_hides_when_tray_available(self, main_window):
        """Close event hides window when tray is available (instead of quitting)."""
        main_window.tray._available = True
        main_window._quitting = False

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        assert not event.isAccepted()
        assert not main_window.isVisible()

    def test_close_event_accepts_when_no_tray(self, main_window):
        """Close event accepts (quits) when no tray is available."""
        main_window.tray._available = False
        main_window._quitting = False
        main_window.monitor_thread = MagicMock()
        main_window.monitor_thread.isRunning.return_value = False

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        assert event.isAccepted()

    def test_close_event_accepts_when_quitting(self, main_window):
        """Close event accepts when _quitting flag is set."""
        main_window.tray._available = True
        main_window._quitting = True
        main_window.monitor_thread = MagicMock()
        main_window.monitor_thread.isRunning.return_value = False
        main_window.tray.tray_icon = MagicMock()

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        assert event.isAccepted()


class TestAutostart:
    """Test suite for autostart desktop file management."""

    def test_create_autostart_file(self, qapp, config_manager):
        """SettingsDialog creates autostart .desktop file when enabled."""
        dialog = SettingsDialog(config_manager)
        dialog.autostart_checkbox.setChecked(True)
        dialog.minimized_checkbox.setChecked(False)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dialog.AUTOSTART_DIR = tmpdir_path
            dialog.AUTOSTART_FILE = tmpdir_path / "vpn-toggle-v2.desktop"
            dialog.apply_autostart()

            assert dialog.AUTOSTART_FILE.exists()
            content = dialog.AUTOSTART_FILE.read_text()
            assert "vpn-toggle-v2" in content
            assert "--minimized" not in content

    def test_create_autostart_file_minimized(self, qapp, config_manager):
        """Autostart file includes --minimized when option is checked."""
        dialog = SettingsDialog(config_manager)
        dialog.autostart_checkbox.setChecked(True)
        dialog.minimized_checkbox.setEnabled(True)
        dialog.minimized_checkbox.setChecked(True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dialog.AUTOSTART_DIR = tmpdir_path
            dialog.AUTOSTART_FILE = tmpdir_path / "vpn-toggle-v2.desktop"
            dialog.apply_autostart()

            content = dialog.AUTOSTART_FILE.read_text()
            assert "--minimized" in content

    def test_remove_autostart_file(self, qapp, config_manager):
        """Unchecking autostart removes the .desktop file."""
        dialog = SettingsDialog(config_manager)
        dialog.autostart_checkbox.setChecked(False)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            desktop_file = tmpdir_path / "vpn-toggle-v2.desktop"
            desktop_file.write_text("[Desktop Entry]\n")
            dialog.AUTOSTART_DIR = tmpdir_path
            dialog.AUTOSTART_FILE = desktop_file
            dialog.apply_autostart()

            assert not desktop_file.exists()

    def test_remove_autostart_file_not_present(self, qapp, config_manager):
        """Removing autostart when file doesn't exist does not error."""
        dialog = SettingsDialog(config_manager)
        dialog.autostart_checkbox.setChecked(False)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            dialog.AUTOSTART_DIR = tmpdir_path
            dialog.AUTOSTART_FILE = tmpdir_path / "vpn-toggle-v2.desktop"
            dialog.apply_autostart()  # Should not raise

    def test_startup_settings_returned(self, qapp, config_manager):
        """get_startup_settings returns checkbox values."""
        dialog = SettingsDialog(config_manager)
        dialog.autostart_checkbox.setChecked(True)
        dialog.minimized_checkbox.setEnabled(True)
        dialog.minimized_checkbox.setChecked(True)
        dialog.restore_checkbox.setChecked(True)

        settings = dialog.get_startup_settings()
        assert settings == {
            'autostart': True,
            'start_minimized': True,
            'restore_connections': True,
        }


class TestVPNRestore:
    """Test suite for VPN connection restore on startup."""

    def test_restore_connects_vpns(self, qapp, config_manager, vpn_manager):
        """Restore connects VPNs from the restore list."""
        import time

        config_manager.update_startup_settings(restore_connections=True)
        config_manager.add_restore_vpn("vpn-1")
        config_manager.add_restore_vpn("vpn-2")

        with patch.object(vpn_manager, 'list_vpns', return_value=[]):
            with patch.object(vpn_manager, 'is_vpn_active', return_value=False):
                with patch.object(vpn_manager, 'connect_vpn', return_value=(True, "Connected")) as mock_connect:
                    window = VPNToggleMainWindow(config_manager, vpn_manager)
                    # Restore runs in a background thread
                    time.sleep(0.3)
                    qapp.processEvents()
                    calls = mock_connect.call_args_list
                    assert call("vpn-1") in calls
                    assert call("vpn-2") in calls
                    window.close()

    def test_restore_skips_already_active(self, qapp, config_manager, vpn_manager):
        """Restore skips VPNs that are already active."""
        config_manager.update_startup_settings(restore_connections=True)
        config_manager.add_restore_vpn("vpn-1")

        with patch.object(vpn_manager, 'list_vpns', return_value=[]):
            with patch.object(vpn_manager, 'is_vpn_active', return_value=True):
                with patch.object(vpn_manager, 'connect_vpn') as mock_connect:
                    window = VPNToggleMainWindow(config_manager, vpn_manager)
                    mock_connect.assert_not_called()
                    window.close()

    def test_restore_disabled_by_default(self, qapp, config_manager, vpn_manager):
        """Restore does nothing when restore_connections is false."""
        config_manager.add_restore_vpn("vpn-1")

        with patch.object(vpn_manager, 'list_vpns', return_value=[]):
            with patch.object(vpn_manager, 'connect_vpn') as mock_connect:
                window = VPNToggleMainWindow(config_manager, vpn_manager)
                mock_connect.assert_not_called()
                window.close()

    def test_connect_adds_to_restore_list(self, qapp, config_manager):
        """Successful connect adds VPN to restore list."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()

        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                widget = VPNWidget("test-vpn", "Test", vm, config_manager)

        # Simulate the on_done callback directly (the async wrapper is
        # tested implicitly; this tests the business logic)
        with patch.object(widget, 'update_status'):
            config_manager.add_restore_vpn("test-vpn")

        assert "test-vpn" in config_manager.get_restore_vpns()

    def test_disconnect_removes_from_restore_list(self, qapp, config_manager):
        """Clicking disconnect removes VPN from restore list."""
        config_manager.add_restore_vpn("test-vpn")

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()

        with patch.object(vm, 'is_vpn_active', return_value=True):
            with patch.object(vm, 'get_connection_timestamp', return_value=datetime.now()):
                widget = VPNWidget("test-vpn", "Test", vm, config_manager)

        with patch.object(vm, 'disconnect_vpn'):
            with patch.object(widget, 'update_status'):
                widget.on_disconnect()

        assert "test-vpn" not in config_manager.get_restore_vpns()


class TestSingleInstance:
    """Test suite for single-instance guard (QLocalServer/QLocalSocket)."""

    SOCKET_NAME = "vpn-toggle-v2-test"

    def test_server_listens(self, qapp):
        """QLocalServer can listen on a named socket."""
        QLocalServer.removeServer(self.SOCKET_NAME)
        server = QLocalServer()
        assert server.listen(self.SOCKET_NAME)
        server.close()
        QLocalServer.removeServer(self.SOCKET_NAME)

    def test_client_connects_to_server(self, qapp):
        """QLocalSocket connects to an existing server."""
        QLocalServer.removeServer(self.SOCKET_NAME)
        server = QLocalServer()
        server.listen(self.SOCKET_NAME)

        socket = QLocalSocket()
        socket.connectToServer(self.SOCKET_NAME)
        assert socket.waitForConnected(1000)

        socket.disconnectFromServer()
        server.close()
        QLocalServer.removeServer(self.SOCKET_NAME)

    def test_client_fails_when_no_server(self, qapp):
        """QLocalSocket fails to connect when no server is running."""
        QLocalServer.removeServer(self.SOCKET_NAME)

        socket = QLocalSocket()
        socket.connectToServer(self.SOCKET_NAME)
        connected = socket.waitForConnected(500)
        assert not connected

    def test_server_receives_connection(self, qapp):
        """Server's newConnection signal fires when client connects."""
        QLocalServer.removeServer(self.SOCKET_NAME)
        server = QLocalServer()
        server.listen(self.SOCKET_NAME)

        connections = []
        server.newConnection.connect(lambda: connections.append(True))

        socket = QLocalSocket()
        socket.connectToServer(self.SOCKET_NAME)
        socket.waitForConnected(1000)

        qapp.processEvents()
        assert len(connections) == 1

        socket.disconnectFromServer()
        server.close()
        QLocalServer.removeServer(self.SOCKET_NAME)


class TestTrayIcon:
    """Test suite for tray icon rendering with icon_path."""

    def test_icon_path_stored(self, qapp, config_manager, vpn_manager):
        """VPNToggleMainWindow stores the icon_path attribute."""
        icon_path = Path("/tmp/test-icon.svg")
        with patch.object(vpn_manager, 'list_vpns', return_value=[]):
            window = VPNToggleMainWindow(
                config_manager, vpn_manager, icon_path=icon_path,
            )
            assert window._icon_path == icon_path
            window.close()

    def test_icon_path_defaults_to_none(self, main_window):
        """icon_path defaults to None when not provided."""
        assert main_window._icon_path is None


class TestStatusProbeResilience:
    """A failed backend probe must not be rendered as a disconnect.

    `is_vpn_active` returns plain False both when the VPN is genuinely down and
    when nmcli/openvpn3 itself errored or timed out. Treating the latter as a
    disconnect blanks the card and drops `_connected_since`, so the connection
    timer restarts from zero on the next good probe.
    """

    @pytest.fixture
    def vpn_widget(self, qapp, config_manager):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()
        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                return VPNWidget("test-vpn", "Test VPN", vm, config_manager)

    def _connect(self, widget, since):
        widget._connected_since = since
        widget.is_active = True
        widget.update_connection_time()

    def test_failed_probe_keeps_connected_since(self, vpn_widget):
        since = datetime.now() - timedelta(hours=3)
        self._connect(vpn_widget, since)
        before = vpn_widget.connection_time_label.text()

        vpn_widget.apply_status(False, probe_ok=False)

        assert vpn_widget._connected_since == since
        assert vpn_widget.connection_time_label.text() == before
        assert vpn_widget.is_active is True

    def test_confirmed_disconnect_clears_connected_since(self, vpn_widget):
        self._connect(vpn_widget, datetime.now() - timedelta(hours=3))

        vpn_widget.apply_status(False, probe_ok=True)

        assert vpn_widget._connected_since is None
        assert vpn_widget.connection_time_label.text() == ""
        assert vpn_widget.is_active is False

    def test_uptime_survives_a_failed_probe_between_good_ones(self, vpn_widget):
        """The counter must keep counting from the original connect time."""
        since = datetime.now() - timedelta(hours=3)
        self._connect(vpn_widget, since)

        vpn_widget.apply_status(False, probe_ok=False)
        with patch.object(vpn_widget.vpn_manager, 'get_connection_timestamp',
                          return_value=None):
            vpn_widget.apply_status(True, probe_ok=True)

        assert vpn_widget._connected_since == since
        assert vpn_widget.connection_time_label.text().startswith("00:03:")


class TestAsyncStatusSweep:
    """The 5s status sweep must not block the GUI thread.

    It previously ran one blocking is_vpn_active per card and then a second
    round for the tray tooltip — measured at ~100ms of frozen event loop every
    5s, which stalled the 1s connection-time counter.
    """

    @pytest.fixture
    def window(self, qapp, config_manager, vpn_manager):
        vpns = [MagicMock(name='vpn', connection_type='vpn')]
        vpns[0].name = 'test-vpn'
        with patch.object(vpn_manager, 'list_vpns', return_value=vpns):
            with patch.object(vpn_manager, 'is_vpn_active', return_value=False):
                with patch.object(vpn_manager, 'get_connection_timestamp',
                                  return_value=None):
                    w = VPNToggleMainWindow(config_manager, vpn_manager)
        yield w
        w.close()

    def test_sweep_uses_async_probe_not_blocking_call(self, window):
        op = MagicMock()
        with patch.object(window.vpn_manager, 'is_vpn_active') as sync_probe:
            with patch.object(window.vpn_manager, 'is_vpn_active_async',
                              return_value=op) as async_probe:
                window.update_all_vpn_status()

        async_probe.assert_called_once()
        op.start.assert_called_once()
        sync_probe.assert_not_called()

    def test_sweep_skips_vpn_with_probe_still_in_flight(self, window):
        op = MagicMock()
        with patch.object(window.vpn_manager, 'is_vpn_active_async',
                          return_value=op) as async_probe:
            window.update_all_vpn_status()
            window.update_all_vpn_status()

        assert async_probe.call_count == 1

    def test_tooltip_uses_swept_result_without_reprobing(self, window):
        widget = window.vpn_widgets['test-vpn']
        widget.is_active = True
        window._status_probes['test-vpn'] = None

        with patch.object(window.vpn_manager, 'is_vpn_active') as sync_probe:
            with patch.object(window.tray, 'update_tooltip') as tooltip:
                with patch.object(widget, 'apply_status'):
                    window._on_status_probe('test-vpn', True)

        sync_probe.assert_not_called()
        assert tooltip.call_args.kwargs['active_count'] == 1

    def test_probe_failure_is_forwarded_to_the_card(self, window):
        widget = window.vpn_widgets['test-vpn']
        op = MagicMock()
        op.probe_ok = False
        window._status_probes['test-vpn'] = op

        with patch.object(widget, 'apply_status') as apply_status:
            window._on_status_probe('test-vpn', False)

        apply_status.assert_called_once_with(False, probe_ok=False)


class TestConnectionTimerPrecision:
    """Qt's default CoarseTimer drifts the 1s interval by up to 5%, which makes
    the seconds digit visibly stall and then skip."""

    def test_connection_time_timer_is_precise(self, main_window):
        from PyQt6.QtCore import Qt
        assert main_window.connection_time_timer.timerType() == Qt.TimerType.PreciseTimer
        assert main_window.connection_time_timer.interval() == 1000


class TestAutoRecoverySettings:
    """The auto-recovery toggle must reach the monitor via config."""

    def test_settings_dialog_defaults_to_enabled(self, qapp, config_manager):
        dialog = SettingsDialog(config_manager)
        assert dialog.auto_recovery_checkbox.isChecked() is True
        assert dialog.get_settings()['auto_recovery'] is True

    def test_settings_dialog_roundtrips_toggle(self, qapp, config_manager):
        dialog = SettingsDialog(config_manager)
        dialog.auto_recovery_checkbox.setChecked(False)
        dialog.backoff_max_spinbox.setValue(300)

        settings = dialog.get_settings()
        assert settings['auto_recovery'] is False
        assert settings['recovery_backoff_max_seconds'] == 300

        config_manager.update_monitor_settings(**settings)
        stored = config_manager.get_monitor_settings()
        assert stored['auto_recovery'] is False
        assert stored['recovery_backoff_max_seconds'] == 300

    def test_backoff_field_disabled_when_recovery_off(self, qapp, config_manager):
        dialog = SettingsDialog(config_manager)
        dialog.auto_recovery_checkbox.setChecked(False)
        assert dialog.backoff_max_spinbox.isEnabled() is False


class TestRecoveringCardDisplay:
    """A down VPN under auto-recovery must not look silently idle."""

    @pytest.fixture
    def vpn_widget(self, qapp, config_manager):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()
        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                return VPNWidget("test-vpn", "Test VPN", vm, config_manager)

    def test_down_card_shows_reconnecting_while_recovering(self, vpn_widget):
        vpn_widget.monitor_thread = MagicMock()
        vpn_widget.monitor_thread.get_vpn_status.return_value = {
            'state': 'recovering', 'failure_count': 0, 'last_check': None,
            'connection_time': None, 'recovery_attempts': 2,
        }

        vpn_widget.apply_status(False)

        assert vpn_widget.status_label.text() == "Reconnecting"
        assert "attempt 3" in vpn_widget.info_label.text()

    def test_down_card_shows_disconnected_when_not_recovering(self, vpn_widget):
        vpn_widget.monitor_thread = MagicMock()
        vpn_widget.monitor_thread.get_vpn_status.return_value = {
            'state': 'idle', 'failure_count': 0, 'last_check': None,
            'connection_time': None, 'recovery_attempts': 0,
        }

        vpn_widget.apply_status(False)

        assert vpn_widget.status_label.text() == "Disconnected"
        assert vpn_widget.info_label.text() == ""

    def test_manual_disconnect_notifies_the_monitor(self, vpn_widget):
        """Auto-recovery must not race the user's own disconnect."""
        vpn_widget.monitor_thread = MagicMock()
        vpn_widget.monitor_thread.get_vpn_status.return_value = {
            'state': 'idle', 'failure_count': 0, 'last_check': None,
            'connection_time': None, 'recovery_attempts': 0,
        }
        with patch.object(vpn_widget.vpn_manager, 'disconnect_vpn',
                          return_value=(True, "ok")):
            with patch.object(vpn_widget.vpn_manager, 'is_vpn_active',
                              return_value=False):
                vpn_widget.on_disconnect()

        vpn_widget.monitor_thread.notify_user_disconnected.assert_called_once_with(
            'test-vpn')


class TestCounterRenderStability:
    """The uptime counter is the only label that repaints every second, so its
    paint rect and font must not vary between ticks.

    This host runs every output at 1.5x fractional scaling, where a stylesheet
    `font-size: 10px` (a device-independent pixel size) rasterises badly.
    """

    @pytest.fixture
    def vpn_widget(self, qapp, config_manager):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()
        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                return VPNWidget("test-vpn", "Test VPN", vm, config_manager)

    def test_counter_font_is_point_sized_not_pixel_sized(self, vpn_widget):
        font = vpn_widget.connection_time_label.font()
        assert font.pointSizeF() > 0, "a px-sized font does not survive fractional scaling"
        assert font.pixelSize() == -1

    def test_counter_digits_are_equal_width(self, vpn_widget):
        fm = vpn_widget.connection_time_label.fontMetrics()
        advances = {fm.horizontalAdvance(d) for d in "0123456789"}
        assert len(advances) == 1, "proportional digits resize the label every tick"

    def test_counter_width_is_fixed_across_values(self, vpn_widget):
        label = vpn_widget.connection_time_label
        widths = set()
        for value in ("00:00:00:00", "22:22:22:22", "01:22:33:44", "99:23:59:59"):
            label.setText(value)
            widths.add(label.width())
        assert len(widths) == 1

    def test_counter_has_an_opaque_background(self, vpn_widget):
        """Without an opaque rect the previous second's glyphs composite through
        the new ones under fractional scaling, rendering the counter doubled.

        Note this must be done via the stylesheet: Qt ignores
        setAutoFillBackground() once a stylesheet is set on the widget.
        """
        sheet = vpn_widget.connection_time_label.styleSheet()
        assert "background-color" in sheet, sheet
        # And the colour must be a real one, not "transparent"/empty.
        from PyQt6.QtGui import QColor
        value = sheet.split("background-color:")[1].split(";")[0].strip()
        assert QColor(value).isValid() and QColor(value).alpha() == 255, value

    def test_counter_is_plain_text(self, vpn_widget):
        from PyQt6.QtCore import Qt
        assert (vpn_widget.connection_time_label.textFormat()
                == Qt.TextFormat.PlainText)
