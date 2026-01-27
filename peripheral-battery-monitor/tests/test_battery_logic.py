
import sys
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

if __name__ == '__main__':
    unittest.main()
