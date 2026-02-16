
import sys
import json
import unittest
from unittest.mock import MagicMock
import importlib.util

# Paths
import os
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(TEST_DIR)
MODULE_PATH = os.path.join(PROJECT_DIR, "peripheral-battery.py")
sys.path.append(PROJECT_DIR)

# 1. Define Dummy Classes to replace Qt Classes
class MockQWidget:
    def __init__(self, *args, **kwargs): pass
    def setWindowFlags(self, *args): pass
    def setAttribute(self, *args): pass
    def setWindowIcon(self, *args): pass
    def setWindowTitle(self, *args): pass
    def setMinimumWidth(self, *args): pass
    def adjustSize(self): pass
    def move(self, *args): pass
    def show(self): pass
    def setStyleSheet(self, *args): pass
    def setToolTip(self, *args): pass
    def windowHandle(self): return None

class MockQFrame(MockQWidget):
    def setObjectName(self, name): pass

class MockLayout:
    def __init__(self, *args, **kwargs): pass
    def setContentsMargins(self, *args): pass
    def setSpacing(self, *args): pass
    def addWidget(self, *args): pass
    def addLayout(self, *args, **kwargs): pass
    def setAlignment(self, *args): pass
    def addStretch(self, *args): pass

class MockQApplication:
    def __init__(self, argv): pass
    def setApplicationName(self, name): pass
    def setDesktopFileName(self, name): pass
    @staticmethod
    def instance(): return MagicMock()

class MockQLabel(MockQWidget):
    def setObjectName(self, name): pass
    def setAlignment(self, align): pass
    def setFixedSize(self, w, h): pass
    def setPixmap(self, pixmap): pass
    def setText(self, text): pass

class MockQAction:
    def __init__(self, *args, **kwargs): pass
    def setData(self, data): pass
    def setChecked(self, checked): pass
    # trigger connect needs to be mocked to avoid errors if used
    @property
    def triggered(self): return MagicMock()

class MockQProgressBar(MockQWidget):
    def __init__(self, *args, **kwargs): pass
    def setObjectName(self, name): pass
    def setMinimum(self, val): pass
    def setMaximum(self, val): pass
    def setValue(self, val): pass
    def setTextVisible(self, visible): pass
    def setFormat(self, fmt): pass
    def setFixedHeight(self, h): pass

# 2. Inject Mocks into sys.modules
mock_qt_widgets = MagicMock()
mock_qt_widgets.QWidget = MockQWidget
mock_qt_widgets.QFrame = MockQFrame
mock_qt_widgets.QApplication = MockQApplication
mock_qt_widgets.QLabel = MockQLabel
mock_qt_widgets.QVBoxLayout = MockLayout
mock_qt_widgets.QHBoxLayout = MockLayout
mock_qt_widgets.QGridLayout = MockLayout
mock_qt_widgets.QMenu = MagicMock
mock_qt_widgets.QAction = MockQAction
mock_qt_widgets.QActionGroup = MagicMock
mock_qt_widgets.QProgressBar = MockQProgressBar

sys.modules['PyQt6'] = MagicMock()
sys.modules['PyQt6.QtWidgets'] = mock_qt_widgets
sys.modules['PyQt6.QtCore'] = MagicMock()
sys.modules['PyQt6.QtGui'] = MagicMock()

# 3. Import BatteryInfo (real class)
import battery_reader
from battery_reader import BatteryInfo

# 4. Load the Module
spec = importlib.util.spec_from_file_location("pb", MODULE_PATH)
pb = importlib.util.module_from_spec(spec)
sys.modules["pb"] = pb
spec.loader.exec_module(pb)

class TestBatteryLogic(unittest.TestCase):
    
    def test_airpods_fallback(self):
        """Test that update_single_device retains last_known level if new is -1 but Connected"""
        
        # Patch load_settings to avoid file I/O
        pb.PeripheralMonitor.load_settings = MagicMock(return_value={})
        
        # Instantiate
        monitor = pb.PeripheralMonitor()
        monitor.settings = {} 
        
        # Mock _update_label_block to strict verification
        monitor._update_label_block = MagicMock()
        
        ui_dict = {
            'last_info': None,
            'name_lbl': MagicMock(),
            'val_lbl': MagicMock(),
            'stat_lbl': MagicMock(),
            'icon_lbl': MagicMock(),
            'default_name': 'AirPods'
        }
        
        # 1. Update with Good Info
        info_1 = BatteryInfo(level=80, status="Discharging", voltage=None, device_name="AirPods")
        monitor.update_single_device(ui_dict, lambda: info_1, use_offline_cache=False)
        
        self.assertEqual(ui_dict['last_info'].level, 80)
        
        # 2. Update with Connected / Unknown
        info_2 = BatteryInfo(level=-1, status="Connected", voltage=None, device_name="AirPods")
        monitor.update_single_device(ui_dict, lambda: info_2, use_offline_cache=False)
        
        # Check Fallback
        args = monitor._update_label_block.call_args[0]
        # args: (name_lbl, val_lbl, stat_lbl, icon_lbl, current_info, last_info, default_name)
        display_info = args[4]
        
        print(f"Fallback Result Level: {display_info.level}")
        self.assertEqual(display_info.level, 80)
        self.assertEqual(display_info.status, "Connected")
        
        # 3. Update with Disconnected (None)
        monitor.update_single_device(ui_dict, lambda: None, use_offline_cache=False)
        
        # Should be None if cache is False
        args = monitor._update_label_block.call_args[0]
        self.assertIsNone(args[4])

    def test_case_display_string(self):
        """Test the string formatting logic inside _update_label_block"""
        
        pb.PeripheralMonitor.load_settings = MagicMock(return_value={})
        monitor = pb.PeripheralMonitor()
        
        lbl_name = MockQLabel()
        lbl_name.setText = MagicMock()
        
        lbl_val = MockQLabel()
        lbl_val.setText = MagicMock()
        
        lbl_stat = MockQLabel()
        lbl_stat.setText = MagicMock()
        
        lbl_icon = MockQLabel()
        
        # Info with L, R, C
        details = {'left': 100, 'right': 100, 'case': 50}
        info = BatteryInfo(level=50, status="Case Only", voltage=None, device_name="AirPods", details=details)
        
        # Call REAL method
        monitor._update_label_block(lbl_name, lbl_val, lbl_stat, lbl_icon, info, None, "AirPods")
        
        call_args = lbl_val.setText.call_args[0][0]
        print(f"CASE FORMAT OUTPUT: {call_args}")
        
        self.assertIn("L:100%", call_args)
        self.assertIn("R:100%", call_args)
        self.assertIn("C:50%", call_args)
        self.assertIn("#4caf50", call_args)

class TestKeyboardBatteryPriority(unittest.TestCase):
    """Test that Bluetooth battery is prioritized over Wired status"""

    def test_bluetooth_priority_over_wired(self):
        """
        When keyboard is plugged in via USB but also connected via Bluetooth,
        the Bluetooth battery percentage should be returned (not 'Wired').
        """
        from unittest.mock import patch, mock_open

        # Mock UPower to return a valid Bluetooth keyboard with battery
        upower_enum = MagicMock()
        upower_enum.returncode = 0
        upower_enum.stdout = "/org/freedesktop/UPower/devices/keyboard_dev_XX_XX_XX_XX_XX_XX\n"

        upower_info = MagicMock()
        upower_info.returncode = 0
        upower_info.stdout = """
  native-path:          /sys/devices/virtual/misc/uhid/0005:3434:0287.000C/power_supply/hid-dc:2c:26:XX:XX:XX-battery
  model:                Keychron K4 HE
  percentage:           75%
  state:                discharging
"""

        # Mock USB devices to show wired keyboard IS connected
        usb_vendor = "3434"
        usb_product = "0e40"

        def mock_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == 'upower':
                if '-e' in cmd:
                    return upower_enum
                if '-i' in cmd:
                    return upower_info
            return MagicMock(returncode=1)

        def mock_listdir(path):
            if path == "/sys/bus/usb/devices":
                return ["1-1", "1-2", "1-3"]
            return []

        def mock_open_file(path, *args, **kwargs):
            if "idVendor" in path:
                return mock_open(read_data=usb_vendor)()
            if "idProduct" in path:
                return mock_open(read_data=usb_product)()
            raise FileNotFoundError()

        with patch('battery_reader.subprocess.run', side_effect=mock_subprocess_run):
            with patch('battery_reader.os.path.exists', return_value=True):
                with patch('battery_reader.os.listdir', side_effect=mock_listdir):
                    with patch('builtins.open', side_effect=mock_open_file):
                        result = battery_reader.get_keyboard_battery()

        # Should return Bluetooth battery, NOT Wired status
        self.assertIsNotNone(result)
        self.assertEqual(result.level, 75)
        self.assertEqual(result.status, "Discharging")
        self.assertIn("Keychron", result.device_name)

    def test_wired_fallback_when_no_bluetooth(self):
        """
        When keyboard is plugged in via USB but NO Bluetooth battery available,
        should return 'Wired' status.
        """
        from unittest.mock import patch, mock_open

        # Mock UPower to return no keyboard
        upower_enum = MagicMock()
        upower_enum.returncode = 0
        upower_enum.stdout = "/org/freedesktop/UPower/devices/battery_BAT0\n"

        # Mock USB devices to show wired keyboard IS connected
        usb_vendor = "3434"
        usb_product = "0e40"

        def mock_subprocess_run(cmd, *args, **kwargs):
            if cmd[0] == 'upower' and '-e' in cmd:
                return upower_enum
            return MagicMock(returncode=1)

        def mock_listdir(path):
            if path == "/sys/bus/usb/devices":
                return ["1-1"]
            return []

        def mock_open_file(path, *args, **kwargs):
            if "idVendor" in path:
                return mock_open(read_data=usb_vendor)()
            if "idProduct" in path:
                return mock_open(read_data=usb_product)()
            raise FileNotFoundError()

        with patch('battery_reader.subprocess.run', side_effect=mock_subprocess_run):
            with patch('battery_reader.os.path.exists', return_value=True):
                with patch('battery_reader.os.listdir', side_effect=mock_listdir):
                    with patch('builtins.open', side_effect=mock_open_file):
                        result = battery_reader.get_keyboard_battery()

        # Should return Wired status since no BT battery
        self.assertIsNotNone(result)
        self.assertEqual(result.level, -1)
        self.assertEqual(result.status, "Wired")


class TestClaudeUsage(unittest.TestCase):
    """Test Claude Code OAuth usage API integration"""

    def test_is_claude_installed_true(self):
        from unittest.mock import patch
        with patch('shutil.which', return_value='/usr/bin/claude'):
            self.assertTrue(pb.is_claude_installed())

    def test_is_claude_installed_false(self):
        from unittest.mock import patch
        with patch('shutil.which', return_value=None):
            self.assertFalse(pb.is_claude_installed())

    def test_get_time_until_reset(self):
        """Behavioral contract: countdown string contains hours and minutes for future reset times."""
        from datetime import datetime, timezone, timedelta
        future = datetime.now(timezone.utc) + timedelta(hours=1, minutes=30)
        result = pb.get_time_until_reset(future.isoformat())
        self.assertIn("h", result)
        self.assertIn("m", result)
        self.assertIn("Resets in", result)

    def test_get_time_until_reset_short(self):
        """Behavioral contract: sub-hour resets show only minutes."""
        from datetime import datetime, timezone, timedelta
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        result = pb.get_time_until_reset(future.isoformat())
        self.assertIn("m", result)
        self.assertIn("Resets in", result)
        self.assertNotIn("h", result)

    def test_get_time_until_reset_past(self):
        """Behavioral contract: past reset times show 'Resetting...'."""
        from datetime import datetime, timezone, timedelta
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        result = pb.get_time_until_reset(past.isoformat())
        self.assertEqual(result, "Resetting...")

    def test_get_time_until_reset_invalid(self):
        """Behavioral contract: invalid input returns 'Unknown'."""
        self.assertEqual(pb.get_time_until_reset("not-a-date"), "Unknown")
        self.assertEqual(pb.get_time_until_reset(None), "Unknown")

    def test_fetch_claude_usage_success(self):
        """Behavioral contract: valid API response is returned as parsed dict."""
        from unittest.mock import patch, mock_open
        import io

        sample_creds = {
            "claudeAiOauth": {
                "accessToken": "test-token",
                "refreshToken": "test-refresh",
                "expiresAt": 9999999999999,
            }
        }
        sample_response = {
            "five_hour": {"utilization": 70.0, "resets_at": "2026-02-16T22:00:00+00:00"},
            "seven_day": {"utilization": 25.0, "resets_at": "2026-02-21T00:00:00+00:00"},
        }
        response_bytes = json.dumps(sample_response).encode()

        mock_resp = MagicMock()
        mock_resp.read.return_value = response_bytes
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch('builtins.open', mock_open(read_data=json.dumps(sample_creds))):
            with patch.object(pb.urllib.request, 'urlopen', return_value=mock_resp):
                result = pb.fetch_claude_usage()

        self.assertIsNotNone(result)
        self.assertEqual(result["five_hour"]["utilization"], 70.0)
        self.assertEqual(result["seven_day"]["utilization"], 25.0)

    def test_fetch_claude_usage_network_error(self):
        """Behavioral contract: network errors return error dict, not None."""
        from unittest.mock import patch, mock_open

        sample_creds = {
            "claudeAiOauth": {
                "accessToken": "test-token",
                "refreshToken": "test-refresh",
                "expiresAt": 9999999999999,
            }
        }

        with patch('builtins.open', mock_open(read_data=json.dumps(sample_creds))):
            with patch.object(pb.urllib.request, 'urlopen', side_effect=pb.urllib.error.URLError("timeout")):
                result = pb.fetch_claude_usage()

        self.assertIsNotNone(result)
        self.assertEqual(result["error"], "offline")

    def test_fetch_claude_usage_missing_credentials(self):
        """Behavioral contract: missing credentials file returns None."""
        from unittest.mock import patch
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = pb.fetch_claude_usage()
        self.assertIsNone(result)

    def test_fetch_claude_usage_expired_token_refresh(self):
        """Behavioral contract: expired token triggers refresh, new token is used."""
        from unittest.mock import patch, mock_open, call

        sample_creds = {
            "claudeAiOauth": {
                "accessToken": "old-token",
                "refreshToken": "test-refresh",
                "expiresAt": 0,
            }
        }
        refresh_response = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        usage_response = {
            "five_hour": {"utilization": 50.0, "resets_at": "2026-02-16T22:00:00+00:00"},
            "seven_day": {"utilization": 10.0, "resets_at": "2026-02-21T00:00:00+00:00"},
        }

        def make_mock_response(data):
            resp = MagicMock()
            resp.read.return_value = json.dumps(data).encode()
            resp.__enter__ = MagicMock(return_value=resp)
            resp.__exit__ = MagicMock(return_value=False)
            return resp

        refresh_resp = make_mock_response(refresh_response)
        usage_resp = make_mock_response(usage_response)

        urlopen_calls = [refresh_resp, usage_resp]

        m_open = mock_open(read_data=json.dumps(sample_creds))
        with patch('builtins.open', m_open):
            with patch.object(pb.urllib.request, 'urlopen', side_effect=urlopen_calls):
                result = pb.fetch_claude_usage()

        self.assertIsNotNone(result)
        self.assertEqual(result["five_hour"]["utilization"], 50.0)

        # Verify credentials were written back (token refresh persisted)
        write_calls = [c for c in m_open().write.call_args_list]
        self.assertTrue(len(write_calls) > 0, "Credentials should have been written back after refresh")

    def test_update_claude_section_with_api_data(self):
        """Behavioral contract: API data sets correct labels and progress bar."""
        from datetime import datetime, timezone, timedelta

        pb.PeripheralMonitor.load_settings = MagicMock(return_value={'claude_section_enabled': True})
        monitor = pb.PeripheralMonitor()
        monitor.claude_frame = MagicMock()
        monitor.claude_section_visible = True
        monitor.claude_progress = MockQProgressBar()
        monitor.claude_progress.setValue = MagicMock()
        monitor.claude_progress.setStyleSheet = MagicMock()
        monitor.claude_five_hour_lbl = MockQLabel()
        monitor.claude_five_hour_lbl.setText = MagicMock()
        monitor.claude_seven_day_lbl = MockQLabel()
        monitor.claude_seven_day_lbl.setText = MagicMock()
        monitor.claude_duration_lbl = MockQLabel()
        monitor.claude_duration_lbl.setText = MagicMock()

        future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()
        usage_data = {
            "five_hour": {"utilization": 70.0, "resets_at": future},
            "seven_day": {"utilization": 25.0, "resets_at": "2026-02-21T00:00:00+00:00"},
        }

        monitor.update_claude_section(usage_data)

        monitor.claude_progress.setValue.assert_called_with(70)
        monitor.claude_five_hour_lbl.setText.assert_called_with("5h: 70%")
        monitor.claude_seven_day_lbl.setText.assert_called_with("7d: 25%")
        duration_text = monitor.claude_duration_lbl.setText.call_args[0][0]
        self.assertIn("Resets in", duration_text)

    def test_update_claude_section_no_data(self):
        """Behavioral contract: None usage data shows 'No data' state."""
        pb.PeripheralMonitor.load_settings = MagicMock(return_value={'claude_section_enabled': True})
        monitor = pb.PeripheralMonitor()
        monitor.claude_frame = MagicMock()
        monitor.claude_section_visible = True
        monitor.claude_progress = MockQProgressBar()
        monitor.claude_progress.setValue = MagicMock()
        monitor.claude_five_hour_lbl = MockQLabel()
        monitor.claude_five_hour_lbl.setText = MagicMock()
        monitor.claude_seven_day_lbl = MockQLabel()
        monitor.claude_seven_day_lbl.setText = MagicMock()
        monitor.claude_duration_lbl = MockQLabel()
        monitor.claude_duration_lbl.setText = MagicMock()

        monitor.update_claude_section(None)

        monitor.claude_progress.setValue.assert_called_with(0)
        monitor.claude_five_hour_lbl.setText.assert_called_with("5h: --")
        monitor.claude_duration_lbl.setText.assert_called_with("No data")


if __name__ == '__main__':
    unittest.main()
