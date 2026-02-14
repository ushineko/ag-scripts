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

from vpn_toggle.config import ConfigManager
from vpn_toggle.gui import VPNToggleMainWindow, VPNWidget, SettingsDialog


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
def vpn_manager():
    """Fixture to provide a mocked VPNManager instance"""
    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
        from vpn_toggle.vpn_manager import VPNManager
        return VPNManager()


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
            assert main_window._tray_available is True
            assert hasattr(main_window, 'tray_icon')
        else:
            assert main_window._tray_available is False

    def test_tray_available_flag_set(self, main_window):
        """_tray_available reflects actual system tray availability."""
        expected = QSystemTrayIcon.isSystemTrayAvailable()
        assert main_window._tray_available == expected

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
        main_window._tray_available = True
        main_window._quitting = False
        # Need tray_show_action for hide-to-tray path
        if not hasattr(main_window, '_tray_show_action'):
            from PyQt6.QtGui import QAction
            main_window._tray_show_action = QAction("Hide", main_window)

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        assert not event.isAccepted()
        assert not main_window.isVisible()

    def test_close_event_accepts_when_no_tray(self, main_window):
        """Close event accepts (quits) when no tray is available."""
        main_window._tray_available = False
        main_window._quitting = False
        main_window.monitor_thread = MagicMock()
        main_window.monitor_thread.isRunning.return_value = False

        from PyQt6.QtGui import QCloseEvent
        event = QCloseEvent()
        main_window.closeEvent(event)

        assert event.isAccepted()

    def test_close_event_accepts_when_quitting(self, main_window):
        """Close event accepts when _quitting flag is set."""
        main_window._tray_available = True
        main_window._quitting = True
        main_window.monitor_thread = MagicMock()
        main_window.monitor_thread.isRunning.return_value = False
        if hasattr(main_window, 'tray_icon'):
            main_window.tray_icon = MagicMock()

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
        config_manager.update_startup_settings(restore_connections=True)
        config_manager.add_restore_vpn("vpn-1")
        config_manager.add_restore_vpn("vpn-2")

        with patch.object(vpn_manager, 'list_vpns', return_value=[]):
            with patch.object(vpn_manager, 'is_vpn_active', return_value=False):
                with patch.object(vpn_manager, 'connect_vpn', return_value=(True, "Connected")) as mock_connect:
                    window = VPNToggleMainWindow(config_manager, vpn_manager)
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
        """Clicking connect adds VPN to restore list."""
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout='/usr/bin/nmcli\n')
            from vpn_toggle.vpn_manager import VPNManager
            vm = VPNManager()

        with patch.object(vm, 'is_vpn_active', return_value=False):
            with patch.object(vm, 'get_connection_timestamp', return_value=None):
                widget = VPNWidget("test-vpn", "Test", vm, config_manager)

        with patch.object(vm, 'connect_vpn', return_value=(True, "ok")):
            with patch.object(widget, 'update_status'):
                widget.on_connect()

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
