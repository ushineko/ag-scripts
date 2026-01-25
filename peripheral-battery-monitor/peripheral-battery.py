
import sys
import signal
import json
import os
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu, QVBoxLayout, QGridLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, QPoint, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QCursor

import battery_reader

__version__ = "1.1.0"

CONFIG_PATH = os.path.expanduser("~/.config/peripheral-battery-monitor.json")

class UpdateThread(QThread):
    data_ready = pyqtSignal(dict)

    def run(self):
        results = {}
        # Fetch subprocess/async data in background. 
        # Mouse check removed from here as it involves GObject/Solaar which may be unsafe in a thread.
        try:
            results['kb'] = battery_reader.get_keyboard_battery()
        except: pass
        try:
            results['headset'] = battery_reader.get_headset_battery()
        except: pass
        try:
            results['airpods'] = battery_reader.get_airpods_battery()
        except: pass
        
        self.data_ready.emit(results)

class PeripheralMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = self.load_settings()
        
        self.initUI()
        self.setup_timer()
        
        # Delay initial update so window shows up first
        QTimer.singleShot(100, self.update_status)

    def load_settings(self):
        default_settings = {"opacity": 0.95, "font_scale": 1.0}
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH, 'r') as f:
                    return {**default_settings, **json.load(f)}
            except Exception:
                pass
        return default_settings

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, 'w') as f:
                json.dump(self.settings, f)
        except Exception:
            pass

    def initUI(self):
        # Window flags: Frameless + StaysOnTop. Removed Tool to avoid Wayland coordinate bugs.
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Set icon
        icon = QIcon.fromTheme("input-mouse")
        if icon.isNull():
             icon = QIcon.fromTheme("battery-full")
        self.setWindowIcon(icon)
        self.setWindowTitle("Battery Monitor")

        # Main Layout for the top-level widget
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        # Container Frame - This is what we style and what the user sees
        self.container = QFrame(self)
        self.container.setObjectName("MainContainer")
        
        # Layout inside the container - Grid 2x2
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setContentsMargins(15, 12, 15, 12)
        self.grid_layout.setSpacing(15)

        # Create device widgets
        self.mouse_ui = self.create_device_cell("Mouse")
        self.kb_ui = self.create_device_cell("Keyboard")
        self.headset_ui = self.create_device_cell("Headset")
        self.airpods_ui = self.create_device_cell("AirPods")

        # Add to grid
        # (Row, Col)
        self.grid_layout.addLayout(self.mouse_ui['layout'], 0, 0)
        self.grid_layout.addLayout(self.kb_ui['layout'], 0, 1)
        self.grid_layout.addLayout(self.headset_ui['layout'], 1, 0)
        self.grid_layout.addLayout(self.airpods_ui['layout'], 1, 1)

        main_layout.addWidget(self.container)

        self.setMinimumWidth(260) # Increased for 2x2 grid to avoid cutoff names on start
        self.update_style()
        self.adjustSize()
        
        # Default position
        self.move(100, 100)

    def create_device_cell(self, default_name):
        layout = QVBoxLayout()
        layout.setSpacing(2)
        
        name_lbl = QLabel(default_name, self)
        name_lbl.setObjectName("NameLabel")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(name_lbl)

        val_lbl = QLabel("--%", self)
        val_lbl.setObjectName("ValueLabel")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(val_lbl)
        
        stat_lbl = QLabel("Disconnected", self)
        stat_lbl.setObjectName("StatusLabel")
        stat_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(stat_lbl)
        
        return {
            'layout': layout, 
            'name_lbl': name_lbl, 
            'val_lbl': val_lbl, 
            'stat_lbl': stat_lbl, 
            'last_info': None,
            'default_name': default_name
        }

    def update_style(self):
        opacity = self.settings.get("opacity", 0.95)
        scale = self.settings.get("font_scale", 1.0)
        
        alpha = int(opacity * 255)
        
        # Base sizes
        val_size = int(22 * scale)
        name_size = int(11 * scale)
        stat_size = int(10 * scale)

        # We style the container specifically, not the global QWidget
        self.setStyleSheet(f"""
            QFrame#MainContainer {{
                background-color: rgba(43, 43, 43, {alpha});
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 12px;
            }}
            QLabel {{
                color: #e0e0e0;
                font-family: sans-serif;
                background: transparent;
            }}
            QLabel#ValueLabel {{
                font-size: {val_size}px;
                font-weight: bold;
                margin-bottom: 2px;
            }}
            QLabel#NameLabel {{
                font-size: {name_size}px;
                color: #aaaaaa;
                font-weight: bold;
            }}
            QLabel#StatusLabel {{
                font-size: {stat_size}px;
                color: #888888;
                font-style: italic;
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.windowHandle():
                self.windowHandle().startSystemMove()

    def contextMenuEvent(self, event):
        contextMenu = QMenu(self)
        
        # Set dark theme for menu
        contextMenu.setStyleSheet("""
            QMenu {
                background-color: #2b2b2b;
                color: #e0e0e0;
                border: 1px solid #444;
            }
            QMenu::item:selected {
                background-color: #3d3d3d;
            }
        """)

        # Opacity Submenu
        opacityMenu = contextMenu.addMenu("Opacity")
        opacity_group = QActionGroup(self)
        
        levels = [
            ("100%", 1.0),
            ("95%", 0.95),
            ("90%", 0.9),
            ("80%", 0.8),
            ("70%", 0.7),
        ]
        
        current_opacity = self.settings.get("opacity", 0.95)
        
        for label, val in levels:
            action = QAction(label, self, checkable=True)
            action.setData(val)
            action.triggered.connect(lambda checked, v=val: self.set_opacity(v))
            if abs(current_opacity - val) < 0.01:
                action.setChecked(True)
            opacity_group.addAction(action)
            opacityMenu.addAction(action)

        # Font Size Submenu
        fontMenu = contextMenu.addMenu("Font Size")
        font_group = QActionGroup(self)
        
        font_sizes = [
            ("Small", 0.8),
            ("Medium", 1.0),
            ("Large", 1.3),
        ]
        
        current_scale = self.settings.get("font_scale", 1.0)
        
        for label, val in font_sizes:
            action = QAction(label, self, checkable=True)
            action.setData(val)
            action.triggered.connect(lambda checked, v=val: self.set_font_scale(v))
            if abs(current_scale - val) < 0.01:
                action.setChecked(True)
            font_group.addAction(action)
            fontMenu.addAction(action)

        contextMenu.addSeparator()

        refreshAct = QAction("Refresh Now", self)
        refreshAct.triggered.connect(self.update_status)
        contextMenu.addAction(refreshAct)

        quitAct = QAction("Quit", self)
        quitAct.triggered.connect(QApplication.instance().quit)
        contextMenu.addAction(quitAct)
        
        # Use popup() and global cursor position, verified to be the most reliable combo on Wayland.
        contextMenu.popup(QCursor.pos())

    def set_opacity(self, val):
        self.settings["opacity"] = val
        self.update_style()
        self.save_settings()

    def set_font_scale(self, val):
        self.settings["font_scale"] = val
        self.update_style()
        self.adjustSize()
        self.save_settings()

    def setup_timer(self):
        # Update every 1 minute
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(60000) 

    def update_status(self):
        # Start worker thread
        self.worker = UpdateThread()
        self.worker.data_ready.connect(self.on_data_ready)
        self.worker.start()
    
    def on_data_ready(self, results):
        # 1. Update Mouse (Run in Main Thread to avoid GObject/DBus threading issues)
        self.update_single_device(self.mouse_ui, battery_reader.get_mouse_battery, use_offline_cache=True)
        
        # 2. Update Keyboard
        self.update_single_device(self.kb_ui, lambda: results.get('kb'), use_offline_cache=True)

        # 3. Update Headset - User wants immediate "Disconnected" state, no offline cache
        self.update_single_device(self.headset_ui, lambda: results.get('headset'), use_offline_cache=False)

        # 4. Update AirPods - User wants "Disconnected", no offline cache
        self.update_single_device(self.airpods_ui, lambda: results.get('airpods'), use_offline_cache=False)
        
        self.setToolTip(f"Last updated: {self.format_time()}")
        self.adjustSize()
        
        # Clean up worker
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def update_single_device(self, ui_dict, func_to_call, use_offline_cache=True):
        try:
            current_info = func_to_call()
            
            # If we got info, update last known.
            if current_info:
                ui_dict['last_info'] = current_info
            
            # Decide what info to pass to display logic
            # If use_offline_cache is False and current_info is None, we act as if we have no info at all
            # (ignoring last_info), effectively forcing "Disconnected" state.
            display_info = current_info
            last_valid = ui_dict['last_info']
            
            if use_offline_cache:
                display_info = current_info or last_valid
            else:
                # If cache is disabled, we only show current info.
                # However we still keep 'last_info' updated in case we toggle mode later? 
                # Yes, we updated it above.
                pass
            
            self._update_label_block(
                ui_dict['name_lbl'], 
                ui_dict['val_lbl'], 
                ui_dict['stat_lbl'], 
                display_info, 
                last_valid if use_offline_cache else None, # pass None as last_info to disable offline-mode in helper
                ui_dict['default_name']
            )
        except Exception as e:
            # print(f"Error updating {ui_dict['default_name']}: {e}")
            pass

    def _update_label_block(self, name_lbl, val_lbl, stat_lbl, current_info, last_info, fallback_name):
        info = current_info or last_info
        
        is_offline = current_info is None and last_info is not None
        
        if info:
            level = info.level
            
            # Handle special "Unknown Level but Connected" state
            if level == -1:
                val_text = '<span style="color: #e0e0e0;">--%</span>' # Light gray/white for connected
            elif info.details and ('left' in info.details or 'right' in info.details):
                # We have L/R details
                parts = []
                if 'left' in info.details: 
                    l = info.details['left']
                    c_l = "#4caf50" if l > 20 else "#f44336"
                    parts.append(f'<span style="color:{c_l}">L:{l}%</span>')
                if 'right' in info.details:
                    r = info.details['right']
                    c_r = "#4caf50" if r > 20 else "#f44336"
                    parts.append(f'<span style="color:{c_r}">R:{r}%</span>')
                
                # Use a smaller font size for the combined string
                joined = " ".join(parts)
                val_text = f'<span style="font-size: 15px;">{joined}</span>'
            elif info.details and 'case' in info.details:
                # Only Case is known (e.g. earbuds in case/closed?)
                c = info.details['case']
                col = "#4caf50" if c > 20 else "#f44336"
                val_text = f'<span style="color:{col}; font-size: 16px;">Case: {c}%</span>'
            else:
                color = "#4caf50" if not is_offline else "#558b2f"
                if level <= 20:
                    color = "#f44336" if not is_offline else "#c62828"
                elif level <= 50:
                    color = "#ff9800" if not is_offline else "#ef6c00"
                val_text = f'<span style="color: {color};">{level}%</span>'
            
            # Use device name if available, otherwise fallback
            disp_name = info.device_name if info.device_name else fallback_name
            # Truncate if too long?
            if len(disp_name) > 20: 
                disp_name = disp_name[:18] + ".."
            
            name_lbl.setText(disp_name)
            val_lbl.setText(val_text)
            
            status_text = info.status
            if "BatteryStatus." in status_text:
                status_text = status_text.replace("BatteryStatus.", "").capitalize()
            elif status_text == "Unknown":
                status_text = "Connected"
                
            if is_offline:
                status_text = "(Offline)"
                
            stat_lbl.setText(status_text)
        else:
            name_lbl.setText(fallback_name)
            val_lbl.setText('<span style="color: gray;">--%</span>')
            stat_lbl.setText("Disconnected")

    def format_time(self):
        from PyQt6.QtCore import QTime
        return QTime.currentTime().toString("HH:mm:ss")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    if "--debug" in sys.argv:
        battery_reader.set_debug_mode(True)
        print("Debug mode enabled via CLI.")
    
    app = QApplication(sys.argv)
    app.setApplicationName("peripheral-battery-monitor")
    app.setDesktopFileName("peripheral-battery-monitor")
    
    ex = PeripheralMonitor()
    ex.show()
    
    sys.exit(app.exec())
