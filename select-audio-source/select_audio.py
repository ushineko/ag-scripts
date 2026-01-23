import sys
import json
import subprocess
import re
import os
import argparse
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QListWidget, QListWidgetItem, QPushButton, QCheckBox, 
                             QLabel, QMessageBox, QGroupBox, QHBoxLayout,
                             QAbstractItemView, QSystemTrayIcon, QMenu)
from PyQt6.QtCore import QTimer, Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QIcon, QAction
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

class ConnectThread(QThread):
    finished_signal = pyqtSignal(bool, str) # success, message

    def __init__(self, mac):
        super().__init__()
        self.mac = mac

    def run(self):
        # Run blocking connect command
        try:
            # We don't use AudioController.run_command to separate concerns/threading
            result = subprocess.run(
                ['bluetoothctl', 'connect', self.mac],
                capture_output=True, text=True
            )
            # bluetoothctl returns 0 on success usually, but output matters too
            if result.returncode == 0:
                self.finished_signal.emit(True, "Connection command sent.")
            else:
                self.finished_signal.emit(False, f"Connection failed: {result.stdout}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

class ConfigManager:
    """Handles persistence of device order and preferences."""
    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/select-audio-source")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.ensure_config_dir()
        
    def ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def load_config(self):
        if not os.path.exists(self.config_file):
            return {"device_priority": [], "auto_switch": False}
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {"device_priority": [], "auto_switch": False}

    def save_config(self, data):
        try:
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

class HeadsetController:
    """Handles interaction with headsetcontrol for SteelSeries devices."""
    
    @staticmethod
    def get_battery_status():
        """
        Returns battery percentage (int) or None if disconnected/error.
        Uses 'headsetcontrol -b -c' which returns just the number (e.g. '87').
        """
        try:
            # -b: battery, -c: compact (just the number)
            result = subprocess.run(
                ['headsetcontrol', '-b', '-c'], 
                capture_output=True, text=True, check=True
            )
            output = result.stdout.strip()
            # -1 usually means charging or full/wired depending on device, 
            # but usually it's a number. If it fails it usually throws error.
            if output:
                try:
                    val = int(output)
                    # User reported negative values indicate disconnection
                    if val < 0: return None
                    return f"{val}%"
                except ValueError:
                    return None
            return None
        except Exception:
            return None

class AudioController:
    """Handles interactions with the system audio via pactl."""
    
    def __init__(self):
        self.headset = HeadsetController()

    @staticmethod
    def run_command(args, ignore_errors=False):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if not ignore_errors:
                print(f"Error running command {args}: {e}")
            return None

    def get_sinks(self, bt_cache=None):
        """
        Returns a list of sinks with smart naming.
        bt_cache: Dict[mac_str, device_name] containing known BT devices.
        """
        json_output = self.run_command(['pactl', '--format=json', 'list', 'sinks'])
        if not json_output:
            return []
        
        try:
            sinks_data = json.loads(json_output)
        except json.JSONDecodeError:
            return []

        default_sink = self.get_default_sink()
        sinks = []
        for sink in sinks_data:
            name = sink.get('name', '')
            props = sink.get('properties', {})
            ports = sink.get('ports', [])
            active_port_name = sink.get('active_port')
            
            # Smart Naming Logic
            display_name = ""
            
            # 1. Try BT Cache/Alias
            if 'bluez' in name or props.get('device.api') == 'bluez':
                # Try to extract MAC from name (e.g. bluez_output.XX_XX... or bluez_output.XX:XX...)
                # Regex allows both : and _ as separators
                mac_match = re.search(r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})', name, re.IGNORECASE)
                if mac_match:
                    mac = mac_match.group(1).replace('_', ':').upper()
                    if bt_cache and mac in bt_cache:
                        display_name = bt_cache[mac]
                
                if not display_name:
                    display_name = props.get('bluez.alias')

            # 2. Try Vendor + Product
            if not display_name:
                vendor = props.get('device.vendor.name', '')
                product = props.get('device.product.name', props.get('device.model', ''))
                if vendor and product:
                    display_name = f"{vendor} {product}"
            
            # 3. Fallback to description
            if not display_name:
                display_name = props.get('device.description', '')
            
            # Cleanup "(null)" garbage
            if display_name:
                display_name = display_name.replace("(null)", "").strip()

            # 4. Final Fallback to raw name
            if not display_name:
                display_name = name

            # Special case for Arctis Nova to show battery/connection status
            # We assume there is only one such headset connected via USB usually
            if "Arctis Nova" in display_name or "SteelSeries" in display_name:
                # Check for wireless/headset interface. 
                # The USB sink is always present, so we check the actual headset status.
                status = self.headset.get_battery_status()
                if status:
                    display_name += f" [{status}]"
                else:
                    display_name += " [Disconnected]"

            # Append active port if useful
            active_port_desc = ""
            if active_port_name and ports:
                for port in ports:
                    if port['name'] == active_port_name:
                        active_port_desc = port.get('description', active_port_name)
                        break
            
            # Avoid redundant port info (e.g. "AirPods Pro - Headphones" is OK, but " - Headphones" is bad)
            # and don't append if it's generic "Analog Output" unless we have no other name
            if active_port_desc and active_port_desc != "Analog Output":
                 display_name += f" - {active_port_desc}"

            # Calculate Stable ID for Priority
            # For Bluetooth: "bt:MAC"
            # For others: raw Name
            priority_id = name
            
            # Extract MAC from name if possible (BlueZ)
            # Regex allows both : and _ as separators
            mac_match = re.search(r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})', name, re.IGNORECASE)
            if mac_match:
               # It's likely a BT device
               found_mac = mac_match.group(1).replace('_', ':').upper()
               priority_id = f"bt:{found_mac}"

            sinks.append({
                'name': name, # The actual pulse sink name (for switching)
                'priority_id': priority_id, # for config/ordering
                'display_name': display_name,
                'is_default': (name == default_sink),
                'connected': not ("[Disconnected]" in display_name) # Used for graying out
            })
        return sinks

    def get_default_sink(self):
        return self.run_command(['pactl', 'get-default-sink'])

    def set_default_sink(self, sink_name):
        self.run_command(['pactl', 'set-default-sink', sink_name])

    def move_input_streams(self, sink_name):
        output = self.run_command(['pactl', 'list', 'short', 'sink-inputs'])
        if not output: return
        for line in output.split('\n'):
            if line.strip():
                parts = line.split()
                if parts:
                    self.run_command(['pactl', 'move-sink-input', parts[0], sink_name], ignore_errors=True)

class BluetoothController:
    """Handles interaction with bluetoothctl."""
    
    @staticmethod
    def run_command(command):
        try:
            result = subprocess.run(
                ['bluetoothctl'] + command, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_devices(self):
        """Returns list of {mac, name, connected}"""
        output = self.run_command(['devices'])
        if not output: return []

        devices = []
        for line in output.split('\n'):
            match = re.search(r'Device\s+([0-9A-F:]+)\s+(.+)', line)
            if match:
                mac = match.group(1)
                name = match.group(2)
                
                # We need connection status. 
                # Optimization: 'info' takes time. 
                # But we need it for 'connected' status and detecting if it's audio.
                info_out = self.run_command(['info', mac])
                connected = False
                if info_out:
                    if "Connected: yes" in info_out:
                        connected = True
                    
                    # Try to get Alias or Name from info for better naming
                    alias_match = re.search(r'Alias:\s+(.+)', info_out)
                    if alias_match:
                        name = alias_match.group(1)
                    elif "Name:" in info_out:
                        name_match = re.search(r'Name:\s+(.+)', info_out)
                        if name_match:
                            name = name_match.group(1)

                is_audio = False
                if info_out and ("UUID: Audio Sink" in info_out or 
                                 "UUID: Audio Source" in info_out or 
                                 "UUID: Headset" in info_out or
                                 "Icon: audio-" in info_out):
                    is_audio = True
                
                if is_audio:
                    devices.append({'mac': mac, 'name': name, 'connected': connected})

        return devices

    def connect(self, mac):
        self.run_command(['connect', mac])
    
    def disconnect(self, mac):
        self.run_command(['disconnect', mac])


class MainWindow(QMainWindow):
    def __init__(self, target_device=None):
        super().__init__()
        self.audio = AudioController()
        self.bt = BluetoothController()
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load_config()
        self.cache_bt_devices = []
        self.target_device_cli = target_device
        
        # Load cache immediately
        self.cache_bt_devices = self.bt.get_devices()

        if self.target_device_cli:
            # Headless Mode
            # We don't build the UI. We just try to Connect/Switch and exit.
            print(f"CLI: Attempting to connect/switch to '{self.target_device_cli}'")
            self.move_streams_cb = QCheckBox() 
            self.move_streams_cb.setChecked(True) # Mock for logic
            self.status_label = QLabel() # Mock
            
            # Re-use existing logic methods where possible? 
            # Or simplified flow.
            # Simplified flow is better for CLI.
            QTimer.singleShot(0, self.handle_cli_command)
            return

        self.setWindowTitle("Audio Source Switcher")
        self.resize(500, 600)
        
        # Window Icon
        icon = QIcon.fromTheme("audio-card")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-volume-high")
        self.setWindowIcon(icon)

        # Menu Bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.quit_app)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)


        # --- Audio Devices Section ---
        audio_group = QGroupBox("Audio Outputs (Drag to Reorder Priority)")
        audio_layout = QVBoxLayout()
        audio_group.setLayout(audio_layout)
        
        self.sink_list = QListWidget()
        self.sink_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.sink_list.itemDoubleClicked.connect(self.on_sink_activated)
        # Hook into model change to save order
        self.sink_list.model().rowsMoved.connect(self.on_list_reordered)
        
        # Context Menu for Copying ID/Command
        self.sink_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sink_list.customContextMenuRequested.connect(self.on_sink_list_menu)
        
        audio_layout.addWidget(self.sink_list)
        
        main_layout.addWidget(audio_group)


        # --- Bluetooth Section ---
        bt_group = QGroupBox("Bluetooth Devices")
        bt_layout = QVBoxLayout()
        bt_group.setLayout(bt_layout)
        
        self.bt_list = QListWidget()
        self.bt_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        bt_layout.addWidget(self.bt_list)
        
        btn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.on_bt_connect)
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.clicked.connect(self.on_bt_disconnect)
        btn_layout.addWidget(self.btn_connect)
        btn_layout.addWidget(self.btn_disconnect)
        bt_layout.addLayout(btn_layout)
        
        main_layout.addWidget(bt_group)

        # --- Footer Controls ---
        controls_group = QGroupBox("Settings")
        controls_layout = QVBoxLayout()
        controls_group.setLayout(controls_layout)
        
        self.move_streams_cb = QCheckBox("Move playing audio on switch")
        self.move_streams_cb.setChecked(True)
        controls_layout.addWidget(self.move_streams_cb)
        
        self.auto_switch_cb = QCheckBox("Auto-switch to highest priority device")
        self.auto_switch_cb.setChecked(self.config.get("auto_switch", False))
        self.auto_switch_cb.toggled.connect(self.on_auto_switch_toggled)
        controls_layout.addWidget(self.auto_switch_cb)

        self.status_label = QLabel("Ready")
        controls_layout.addWidget(self.status_label)

        self.refresh_btn = QPushButton("Refresh All")
        self.refresh_btn.clicked.connect(self.refresh_all_force)
        controls_layout.addWidget(self.refresh_btn)
        
        main_layout.addWidget(controls_group)

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(5000) 

        self.refresh_all()

        # System Tray Setup
        self.setup_tray()

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        
        # specific icon for KDE/Linux
        icon = QIcon.fromTheme("audio-card")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-volume-high")
        
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Audio Source Switcher")
        
        # Menu
        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def show_about(self):
        QMessageBox.about(
            self,
            "About Audio Source Switcher",
            "<p><b>Audio Source Switcher</b></p>"
            "<p>A utility to manage audio output devices and Bluetooth connections "
            "with priority-based auto-switching.</p>"
            "<p>Copyright (c) 2026 ushineko</p>"
        )

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            # self.tray_icon.showMessage("Audio Switcher", "App minimized to tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            event.accept()

    def quit_app(self):
        QApplication.quit()

    def on_auto_switch_toggled(self, checked):
        self.config["auto_switch"] = checked
        self.config_mgr.save_config(self.config)

    def on_list_reordered(self):
        # Save new order
        priority_list = []
        for i in range(self.sink_list.count()):
            item = self.sink_list.item(i)
            # We store priority_id in UserRole
            priority_list.append(item.data(Qt.ItemDataRole.UserRole))
        
        self.config["device_priority"] = priority_list
        self.config_mgr.save_config(self.config)
        self.status_label.setText("Priority saved.")

    def refresh_all_force(self):
        self.refresh_all()
        self.status_label.setText("Refreshed.")

    def refresh_all(self):
        # Fetch BT devices first (slowest part, but needed for names)
        # In a real async app we'd thread this. For now, it blocks briefly.
        self.cache_bt_devices = self.bt.get_devices()
        
        self.refresh_bt_list_ui()
        self.refresh_sinks_ui()
        
        if self.auto_switch_cb.isChecked():
            self.run_auto_switch()

    def run_auto_switch(self):
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        sink_map = {s['priority_id']: s for s in sinks}
        
        # Get Current Default Info
        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        
        # Check if current default is "connected"
        current_is_valid = False
        if default_sink_name:
             # Find the sink object for default
             for s in sinks:
                 if s['name'] == default_sink_name:
                     current_is_valid = s.get('connected', True)
                     break
        
        # Iterate config priority list
        priority_list = self.config.get("device_priority", [])
        target_sink_obj = None
        
        for pid in priority_list:
            if pid in sink_map:
                s = sink_map[pid]
                if s.get('connected', True):
                    target_sink_obj = s
                    break
        
        # Logic: 
        # 1. If we found a high priority target
        # 2. And it's NOT the current default
        # 3. OR the current default is "Disconnected" (invalid) -> Force switch to best available
        
        should_switch = False
        if target_sink_obj:
            if target_sink_obj['name'] != default_sink_name:
                should_switch = True
            elif not current_is_valid:
                 # We are on the target, but it's disconnected? 
                 # Wait, if target_sink_obj is found via loop, it IS connected.
                 # So if we are on it, and it's connected, we are good.
                 pass
        
        # Fallback: If current is invalid, and no priority target found?
        # Try to switch to ANY connected device?
        if not target_sink_obj and not current_is_valid and sinks:
             # Just pick the first connected one
             for s in sinks:
                 if s.get('connected', True):
                     target_sink_obj = s
                     should_switch = True
                     break

        if should_switch and target_sink_obj:
            target_name = target_sink_obj['name']
            print(f"Auto-switching to {target_name}")
            # Use shared method to ensure notifications fire
            self.switch_to_sink(target_name, target_sink_obj['display_name'])

    def update_list_widget(self, list_widget, new_items_data):
        """
        Generic in-place updater for QListWidget to preserve selection and clicks.
        new_items_data: list of dicts with:
            'id': unique identifier (UserRole),
            'text': display text,
            'bold': bool,
            'color': QColor (optional)
        """
        # Create map of ID -> Index for existing items
        existing_ids = {}
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            uid = item.data(Qt.ItemDataRole.UserRole)
            existing_ids[uid] = item

        items_to_keep = set()
        
        # Iterate new data order
        for idx, new_item in enumerate(new_items_data):
            uid = new_item['id']
            items_to_keep.add(uid)
            
            if uid in existing_ids:
                # Update existing
                item = existing_ids[uid]
                # Move if order changed? QListWidget doesn't easily support move without takeItem
                # For simplicity, if order is wrong, we might just assume it's OK or accept slight wrong order until full rebuild.
                # But simpler: just update properties.
                
                if item.text() != new_item['text']:
                    item.setText(new_item['text'])
                
                font = item.font()
                if font.bold() != new_item['bold']:
                    font.setBold(new_item['bold'])
                    item.setFont(font)
                
                if new_item.get('color'):
                    item.setForeground(QBrush(new_item['color']))
                else:
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
            else:
                # Add new
                item = QListWidgetItem(new_item['text'])
                item.setData(Qt.ItemDataRole.UserRole, uid)
                
                font = item.font()
                font.setBold(new_item['bold'])
                item.setFont(font)
                
                if new_item.get('color'):
                    item.setForeground(QBrush(new_item['color']))
                else:
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
                
                list_widget.insertItem(idx, item) # Insert at correct position

        # Remove items not in new list
        # Iterate backwards to avoid index shifting issues
        for i in range(list_widget.count() - 1, -1, -1):
            item = list_widget.item(i)
            uid = item.data(Qt.ItemDataRole.UserRole)
            if uid not in items_to_keep:
                list_widget.takeItem(i)

    def refresh_sinks_ui(self):
        # Create BT Map for naming
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        
    def refresh_sinks_ui(self):
        # Create BT Map for naming
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        
        current_sinks = self.audio.get_sinks(bt_map)
        # Map priority_id -> sink object
        sink_map = {s['priority_id']: s for s in current_sinks}
        
        # Also map MAC -> BT device for offline items
        bt_obj_map = {d['mac']: d for d in self.cache_bt_devices}
        
        # Load priority list
        priority_list = self.config.get("device_priority", [])
        
        final_list = []
        seen_ids = set()
        
        # Helper to create an offline item
        def make_offline_item(pid):
            display = pid
            # specific logic for bt:MAC
            if pid.startswith("bt:"):
                mac = pid[3:]
                if mac in bt_map:
                    display = f"{bt_map[mac]} [Offline]"
                else:
                    display = f"{mac} [Offline]"
            else:
                 display = f"{pid} [Offline]"
                 
            return {
                'priority_id': pid,
                'display_name': display,
                'is_default': False,
                'connected': False,
                'name': None # Cannot switch to it
            }

        # 1. Add Configured Items (in order)
        for pid in priority_list:
            if pid in sink_map:
                # Online Sink
                final_list.append(sink_map[pid])
            else:
                # Offline
                final_list.append(make_offline_item(pid))
            seen_ids.add(pid)
            
        # 2. Add Active Sinks not in config
        for sink in current_sinks:
            pid = sink['priority_id']
            if pid not in seen_ids:
                final_list.append(sink)
                seen_ids.add(pid)
                
        # 3. Add Known Bluetooth Devices (Paired) not in config AND not active
        # This allows prioritizing devices that are paired but currently offline/not sinks
        for mac, dev in bt_obj_map.items():
            pid = f"bt:{mac}"
            if pid not in seen_ids:
                # add as offline item
                # Check if it *was* in sink_map? Already handled in step 2 if active.
                final_list.append(make_offline_item(pid))
                seen_ids.add(pid)
        
        data_list = []
        for sink in final_list:
            text = sink['display_name']
            if sink.get('is_default'):
                text += " (Active)"
            
            # Use priority_id as the list item ID
            color = None
            if not sink.get('connected', True):
                color = Qt.GlobalColor.gray

            data_list.append({
                'id': sink['priority_id'],
                'text': text,
                'bold': sink.get('is_default', False),
                'color': color
            })
            
        self.update_list_widget(self.sink_list, data_list)

    def refresh_bt_list_ui(self):
        data_list = []
        for dev in self.cache_bt_devices:
            state = "Connected" if dev['connected'] else "Disconnected"
            text = f"{dev['name']} [{state}]"
            color = Qt.GlobalColor.darkGreen if dev['connected'] else Qt.GlobalColor.gray
            
            data_list.append({
                'id': dev['mac'],
                'text': text,
                'bold': dev['connected'],
                'color': color
            })
            
        self.update_list_widget(self.bt_list, data_list)

    def on_sink_activated(self, item):
        priority_id = item.data(Qt.ItemDataRole.UserRole)
        
        # 1. Try to find active sink FIRST
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        
        target_sink = None
        for s in sinks:
            if s['priority_id'] == priority_id:
                target_sink = s['name']
                break
        
        if target_sink:
            # Already connected/active -> Switch
            self.switch_to_sink(target_sink, item.text())
        else:
            # Encoutered Offline Device
            if priority_id.startswith("bt:"):
                mac = priority_id[3:]
                self.status_label.setText(f"Connecting to {mac}...")
                self.sink_list.setEnabled(False) # Prevent double clicks
                
                # Start Thread
                self.connect_thread = ConnectThread(mac)
                self.connect_thread.finished_signal.connect(lambda s, m: self.on_connect_finished(s, m, priority_id))
                self.connect_thread.start()
            else:
                self.status_label.setText("Device is offline (non-BT), cannot switch.")

    def on_connect_finished(self, success, msg, priority_id):
        if not success:
            self.status_label.setText(msg)
            self.sink_list.setEnabled(True)
            return

        self.status_label.setText("Connected! Waiting for audio device...")
        # Now we poll for the sink to appear. 
        # Give it up to 10 seconds.
        self.poll_attempts = 0
        self.max_poll_attempts = 20 # 20 * 500ms = 10s
        self.pending_switch_id = priority_id
        
        self.connect_poll_timer = QTimer()
        self.connect_poll_timer.timeout.connect(self.check_sink_available)
        self.connect_poll_timer.start(500)

    def check_sink_available(self):
        self.poll_attempts += 1
        
        # Refresh data
        self.refresh_all() # This updates lists and cache
        
        # Check if our ID is now in the online sinks
        # We can look at sink_list items or re-query.
        # Let's peek at the items we just refreshed.
        
        # Hacky: extract s from UI or just re-get
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        
        target_sink = None
        for s in sinks:
            if s['priority_id'] == self.pending_switch_id:
                target_sink = s['name']
                break
        
        if target_sink:
            # Found it!
            self.connect_poll_timer.stop()
            self.switch_to_sink(target_sink, self.pending_switch_id) # Name might be raw ID but that's ok
            self.sink_list.setEnabled(True)
            self.status_label.setText(f"Connected & Switched to {self.pending_switch_id}")
        
        elif self.poll_attempts >= self.max_poll_attempts:
            self.connect_poll_timer.stop()
            self.sink_list.setEnabled(True)
            self.status_label.setText("Connection successful, but audio device did not appear.")

    def send_notification(self, title, message, icon="audio-card"):
        try:
            subprocess.run([
                'notify-send', 
                '-a', 'Audio Switcher', 
                '-i', icon, 
                title, 
                message
            ])
        except Exception:
            # Fallback to Qt if notify-send missing (unlikely here)
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    title, 
                    message, 
                    QSystemTrayIcon.MessageIcon.NoIcon, 
                    3000
                )

    def switch_to_sink(self, sink_name, display_text):
        self.audio.set_default_sink(sink_name)
        if self.move_streams_cb.isChecked():
            self.audio.move_input_streams(sink_name)
        self.refresh_sinks_ui()
        clean_text = display_text.replace(" (Active)", "")
        self.status_label.setText(f"Switched to: {clean_text}")
        
        # System Notification
        self.send_notification("Audio Switched", f"Active Device: {clean_text}")

    def get_selected_bt_mac(self):
        item = self.bt_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def on_bt_connect(self):
        mac = self.get_selected_bt_mac()
        if mac:
            self.status_label.setText(f"Connecting {mac}...")
            QApplication.processEvents()
            self.bt.connect(mac)
            self.refresh_all()
            self.status_label.setText(f"Connected {mac}")

    def on_bt_disconnect(self):
        mac = self.get_selected_bt_mac()
        if mac:
            self.status_label.setText(f"Disconnecting {mac}...")
            QApplication.processEvents()
            self.bt.disconnect(mac)
            self.refresh_all()
            self.status_label.setText(f"Disconnected {mac}")

    def handle_cli_command(self):
        target = self.target_device_cli
        
        # 1. Resolve Target
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        
        found_sink = None
        found_priority_id = None
        
        # Fuzzy match logic
        # Try exact match on priority_id first
        for s in sinks:
            if s['priority_id'] == target:
                found_sink = s
                found_priority_id = s['priority_id']
                break
        
        # Try substring match on display_name or name
        if not found_sink:
            target_lower = target.lower()
            for s in sinks:
                if target_lower in s['display_name'].lower() or \
                   target_lower in s['name'].lower() or \
                   target_lower in s['priority_id'].lower():
                    found_sink = s
                    found_priority_id = s['priority_id']
                    break
        
        # Try offline BT cache
        if not found_sink:
             target_lower = target.lower()
             
             # If target is "bt:MAC", strip prefix for matching
             search_target = target_lower
             if search_target.startswith("bt:"):
                 search_target = search_target[3:]
                 
             for d in self.cache_bt_devices:
                 if search_target in d['name'].lower() or \
                    search_target in d['mac'].lower():
                     # Construct a fake sink obj for logic reuse
                     found_priority_id = f"bt:{d['mac']}"
                     found_sink = {'priority_id': found_priority_id, 'name': None, 'display_name': d['name']} # Offline
                     break

        if found_sink:
            print(f"CLI: Found match -> {found_priority_id}")
            
            # Logic from on_sink_activated:
            target_name = found_sink.get('name')
            if target_name:
                print("CLI: Device is online. Switching...")
                self.switch_to_sink(target_name, found_sink.get('display_name', target))
                sys.exit(0)
            else:
                # Offline
                if found_priority_id.startswith("bt:"):
                   mac = found_priority_id[3:]
                   print(f"CLI: Device offline. Connecting to {mac}...")
                   self.send_notification("Connecting...", f"Connecting to {mac}")
                   
                   # We need to wait for connection.
                   self.connect_thread = ConnectThread(mac)
                   self.connect_thread.finished_signal.connect(
                       lambda s, m: self.on_cli_connect_finished(s, m, found_priority_id)
                   )
                   self.connect_thread.start()
                else:
                   msg = "Error - Device is offline and not Bluetooth."
                   print(f"CLI: {msg}")
                   self.send_notification("Switch Failed", msg, "dialog-error")
                   sys.exit(1)
        else:
            msg = f"Error - Device '{target}' not found."
            print(f"CLI: {msg}")
            self.send_notification("Switch Failed", msg, "dialog-error")
            sys.exit(1)

    def on_cli_connect_finished(self, success, msg, priority_id):
        if not success:
            print(f"CLI: Connection Failed: {msg}")
            self.send_notification("Connection Failed", msg, "dialog-error")
            sys.exit(1)
        
        print("CLI: Connected. Waiting for sink...")
        self.poll_attempts = 0
        self.max_poll_attempts = 20
        self.pending_switch_id = priority_id
        
        self.connect_poll_timer = QTimer()
        self.connect_poll_timer.timeout.connect(self.check_sink_available_cli)
        self.connect_poll_timer.start(500)

    def check_sink_available_cli(self):
        self.poll_attempts += 1
        
        # Refresh Logic (Simplified)
        sinks = self.audio.get_sinks({}) # Don't need full BT map update for this check
        
        target_sink = None
        for s in sinks:
            if s['priority_id'] == self.pending_switch_id:
                target_sink = s['name']
                break
        
        if target_sink:
            self.connect_poll_timer.stop()
            print("CLI: Sink appeared. Switching...")
            self.switch_to_sink(target_sink, self.pending_switch_id)
            sys.exit(0)
        
        elif self.poll_attempts >= self.max_poll_attempts:
            msg = "Timeout waiting for sink."
            print(f"CLI: {msg}")
            self.send_notification("Connection Timeout", msg, "dialog-error")
            sys.exit(1)

    def on_sink_list_menu(self, pos):
        item = self.sink_list.itemAt(pos)
        if not item: return
        
        menu = QMenu()
        copy_cmd_action = QAction("Copy Hotkey Command", self)
        copy_cmd_action.triggered.connect(lambda: self.copy_switch_command(item))
        menu.addAction(copy_cmd_action)
        
        menu.exec(self.sink_list.mapToGlobal(pos))
        
    def copy_switch_command(self, item):
        # User prefers the logical name (e.g. "Papa's AirPods Pro")
        # We need to clean the status text from the item label
        raw_text = item.text()
        
        # Regex to remove status suffixes like " [Disconnected]", " [87%]", " (Active)"
        # matches anything in [] or () at the end of the string
        clean_name = re.sub(r'\s*\[.*?\]|\s*\(.*?\)', '', raw_text).strip()
        
        # Fallback to ID if name became empty (unlikely)
        if not clean_name:
            clean_name = item.data(Qt.ItemDataRole.UserRole)

        # Construct path to this script
        script_path = os.path.abspath(__file__)
        cmd = f"python3 {script_path} --connect \"{clean_name}\""
        
        clipboard = QApplication.clipboard()
        clipboard.setText(cmd)
        
        # Notify user (Tray or Status)
        self.status_label.setText(f"Copied: {clean_name}")


def main():
    parser = argparse.ArgumentParser(description="Audio Source Switcher")
    parser.add_argument("--connect", "-c", type=str, help="Name or ID of device to switch to")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    # 1. Single Instance Check
    # Only if NOT running a connect command (we want to allow connect commands to run parallel/independent, 
    # OR we want them to just work. Actually, if main app is running, and we run CLI, 
    # we don't want to bring main app to front. We want to execute command.)
    
    if not args.connect:
        socket_name = "ag_select_audio_source_v1"
        socket = QLocalSocket()
        socket.connectToServer(socket_name)
        
        if socket.waitForConnected(500):
            print("Application already running. Bringing to front.")
            socket.write(b"SHOW")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            sys.exit(0)
    
        # Create Local Server
        QLocalServer.removeServer(socket_name)
        server = QLocalServer()
        if not server.listen(socket_name):
            print(f"Warning: Could not start local server on {socket_name}.")
    
    window = MainWindow(target_device=args.connect)
    
    if not args.connect:
        # Only setup server listener if not in CLI mode
        def handle_new_connection():
            client_socket = server.nextPendingConnection()
            if not client_socket: return
            client_socket.waitForReadyRead(1000)
            data = client_socket.readAll().data()
            if b"SHOW" in data:
                window.show_window()
            client_socket.disconnectFromServer()
        server.newConnection.connect(handle_new_connection)
        
        window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
