"""Tests for platform-branching path helpers (config + logging).

The branch is selected by the module-level ``IS_MACOS`` constant (bound at
import from ``src.platform_support``). These tests patch that constant and the
relevant env vars so the result is independent of the host OS the suite runs on
— no real filesystem dependence.
"""

from pathlib import Path
from unittest import mock

from src import config, logging_config, platform_support


class TestPlatformSupport:

    def test_constants_are_mutually_exclusive(self):
        flags = [
            platform_support.IS_WINDOWS,
            platform_support.IS_MACOS,
            platform_support.IS_LINUX,
        ]
        # At most one is True on any real platform; never two at once.
        assert sum(bool(f) for f in flags) <= 1


class TestGetConfigDir:

    def test_macos_uses_library_application_support(self):
        with mock.patch.object(config, "IS_MACOS", True):
            result = config.get_config_dir()
        assert result == Path.home() / "Library" / "Application Support" / "claude-usage-widget"

    def test_windows_uses_appdata(self):
        with mock.patch.object(config, "IS_MACOS", False), \
                mock.patch.dict("os.environ", {"APPDATA": "C:\\Users\\me\\AppData\\Roaming"}):
            result = config.get_config_dir()
        assert result == Path("C:\\Users\\me\\AppData\\Roaming") / "claude-usage-widget"

    def test_generic_fallback_without_appdata(self):
        with mock.patch.object(config, "IS_MACOS", False), \
                mock.patch.dict("os.environ", {}, clear=True):
            result = config.get_config_dir()
        assert result == Path.home() / ".claude-usage-widget"


class TestGetLogDir:

    def test_macos_uses_library_logs(self):
        with mock.patch.object(logging_config, "IS_MACOS", True):
            result = logging_config.get_log_dir()
        assert result == Path.home() / "Library" / "Logs" / "claude-usage-widget"

    def test_windows_uses_localappdata(self):
        with mock.patch.object(logging_config, "IS_MACOS", False), \
                mock.patch.dict("os.environ", {"LOCALAPPDATA": "C:\\Users\\me\\AppData\\Local"}):
            result = logging_config.get_log_dir()
        assert result == Path("C:\\Users\\me\\AppData\\Local") / "claude-usage-widget" / "logs"

    def test_generic_fallback_without_localappdata(self):
        with mock.patch.object(logging_config, "IS_MACOS", False), \
                mock.patch.dict("os.environ", {}, clear=True):
            result = logging_config.get_log_dir()
        assert result == Path.home() / ".claude-usage-widget" / "logs"
