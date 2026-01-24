
import sys
import signal
import json
import os
from PyQt6.QtWidgets import QApplication, QLabel, QWidget, QMenu, QVBoxLayout, QFrame
from PyQt6.QtCore import Qt, QTimer, QPoint
from PyQt6.QtGui import QAction, QIcon, QActionGroup, QCursor

import battery_reader

CONFIG_PATH = os.path.expanduser("~/.config/peripheral-battery-monitor.json")

class PeripheralMonitor(QWidget):
    def __init__(self):
        super().__init__()
        self.last_mouse_info = None
        self.last_kb_info = None
        self.settings = self.load_settings()
        
        self.initUI()
        self.setup_timer()
        
        # Delay initial update so window shows up first
        QTimer.singleShot(100, self.update_status)

    def load_settings(self):
        default_settings = {"opacity": 0.95}
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
        
        # Layout inside the container
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(10, 8, 10, 8)
        container_layout.setSpacing(0)

        # --- Mouse Section ---
        self.mouseNameLabel = QLabel("Mouse", self)
        self.mouseNameLabel.setObjectName("NameLabel")
        self.mouseNameLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.mouseNameLabel)

        self.mouseValueLabel = QLabel("--%", self)
        self.mouseValueLabel.setObjectName("ValueLabel")
        self.mouseValueLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.mouseValueLabel)
        
        self.mouseStatusLabel = QLabel("", self)
        self.mouseStatusLabel.setObjectName("StatusLabel")
        self.mouseStatusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.mouseStatusLabel)

        # Separator (with minimal height)
        line = QFrame()
        line.setObjectName("Separator")
        line.setFrameShape(QFrame.Shape.HLine)
        container_layout.addWidget(line)

        # --- Keyboard Section ---
        self.kbNameLabel = QLabel("Keyboard", self)
        self.kbNameLabel.setObjectName("NameLabel")
        self.kbNameLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.kbNameLabel)

        self.kbValueLabel = QLabel("--%", self)
        self.kbValueLabel.setObjectName("ValueLabel")
        self.kbValueLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.kbValueLabel)
        
        self.kbStatusLabel = QLabel("", self)
        self.kbStatusLabel.setObjectName("StatusLabel")
        self.kbStatusLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.kbStatusLabel)

        main_layout.addWidget(self.container)

        self.setMinimumWidth(110)
        self.update_style()
        self.adjustSize()
        
        # Default position
        self.move(100, 100)

    def update_style(self):
        opacity = self.settings.get("opacity", 0.95)
        alpha = int(opacity * 255)
        
        # We style the container specifically, not the global QWidget
        self.setStyleSheet(f"""
            QFrame#MainContainer {{
                background-color: rgba(43, 43, 43, {alpha});
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
            }}
            QLabel {{
                color: #e0e0e0;
                font-family: sans-serif;
                background: transparent;
            }}
            QLabel#ValueLabel {{
                font-size: 20px;
                font-weight: bold;
            }}
            QLabel#NameLabel {{
                font-size: 11px;
                color: #aaaaaa;
                font-weight: bold;
            }}
            QLabel#StatusLabel {{
                font-size: 10px;
                color: #888888;
                font-style: italic;
            }}
            QFrame#Separator {{
                background-color: rgba(255, 255, 255, 30);
                max-height: 1px;
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

    def setup_timer(self):
        # Update every 1 minute
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_status)
        self.timer.start(60000) 

    def update_status(self):
        # 1. Update Mouse
        try:
            current_m_info = battery_reader.get_mouse_battery()
            if current_m_info:
                self.last_mouse_info = current_m_info
            self._update_label_block(self.mouseNameLabel, self.mouseValueLabel, self.mouseStatusLabel, current_m_info, self.last_mouse_info, "No Mouse")
        except Exception:
            pass

        # 2. Update Keyboard
        try:
            current_k_info = battery_reader.get_keyboard_battery()
            if current_k_info:
                self.last_kb_info = current_k_info
            self._update_label_block(self.kbNameLabel, self.kbValueLabel, self.kbStatusLabel, current_k_info, self.last_kb_info, "No Keyboard")
        except Exception:
            pass
        
        self.setToolTip(f"Last updated: {self.format_time()}")
        self.adjustSize()

    def _update_label_block(self, name_lbl, val_lbl, stat_lbl, current_info, last_info, fallback_name):
        info = current_info or last_info
        is_offline = current_info is None and last_info is not None
        
        if info:
            level = info.level
            color = "#4caf50" if not is_offline else "#558b2f"
            if level <= 20:
                color = "#f44336" if not is_offline else "#c62828"
            elif level <= 50:
                color = "#ff9800" if not is_offline else "#ef6c00"
            
            name_lbl.setText(info.device_name)
            val_lbl.setText(f'<span style="color: {color};">{level}%</span>')
            
            status_text = info.status
            if "BatteryStatus." in status_text:
                status_text = status_text.replace("BatteryStatus.", "").capitalize()
            elif status_text == "Unknown":
                status_text = ""
                
            if is_offline:
                status_text = "(Offline)"
                
            stat_lbl.setText(status_text)
        else:
            name_lbl.setText(fallback_name)
            val_lbl.setText('<span style="color: gray;">N/A</span>')
            stat_lbl.setText("Disconnected")

    def format_time(self):
        from PyQt6.QtCore import QTime
        return QTime.currentTime().toString("HH:mm:ss")

if __name__ == '__main__':
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.setApplicationName("peripheral-battery-monitor")
    app.setDesktopFileName("peripheral-battery-monitor")
    
    ex = PeripheralMonitor()
    ex.show()
    
    sys.exit(app.exec())
