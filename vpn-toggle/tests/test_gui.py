"""
Tests for GUI components
"""
import pytest
from unittest.mock import MagicMock, patch
import tempfile
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from vpn_toggle.config import ConfigManager
from vpn_toggle.gui import VPNToggleMainWindow


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
