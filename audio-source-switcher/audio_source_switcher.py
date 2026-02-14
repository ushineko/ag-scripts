import sys
import json
import subprocess
import re
import os
import argparse
import dbus
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QListWidget, QListWidgetItem, QPushButton, QCheckBox, 
                             QLabel, QMessageBox, QGroupBox, QHBoxLayout,
                             QAbstractItemView, QSystemTrayIcon, QMenu, QDialog, 
                             QTextBrowser, QDialogButtonBox, QSlider, QSpinBox, 
                             QComboBox)
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
        self.config_dir = os.path.expanduser("~/.config/audio-source-switcher")
        self.config_file = os.path.join(self.config_dir, "config.json")
        self.ensure_config_dir()
        
    def ensure_config_dir(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)

    def load_config(self):
        if not os.path.exists(self.config_file):
            return {"device_priority": [], "auto_switch": False, "arctis_idle_minutes": 0, "mic_links": {}}
        try:
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                # Ensure defaults
                if "mic_links" not in data: data["mic_links"] = {}
                return data
        except Exception as e:
            print(f"Error loading config: {e}")
            return {"device_priority": [], "auto_switch": False, "arctis_idle_minutes": 0, "mic_links": {}}

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
    
    @staticmethod
    def set_inactive_time(minutes):
        """
        Sets the inactive time (disconnect on idle).
        minutes: 0 to disable, or 1-90.
        """
        try:
            # headsetcontrol -i <minutes>
            subprocess.run(
                ['headsetcontrol', '-i', str(minutes)],
                capture_output=True, text=True, check=True
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"Error setting inactive time: {e}")
            return False
        except Exception as e:
            print(f"Unexpected error setting inactive time: {e}")
            return False

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
            if 'bluez' in name or 'bluez' in props.get('device.api', ''):
                # Try to extract MAC from name (e.g. bluez_output.XX_XX... or bluez_output.XX:XX...)
                # Regex allows both : and _ as separators
                mac_match = re.search(r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})', name, re.IGNORECASE)
                if mac_match:
                    mac = mac_match.group(1).replace('_', ':').upper()
                    if bt_cache and mac in bt_cache:
                        display_name = bt_cache[mac]

                if not display_name:
                    display_name = props.get('bluez.alias') or props.get('device.alias')

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

            # Append active port if useful, and check availability
            active_port_desc = ""
            is_physically_available = True
            
            if active_port_name and ports:
                for port in ports:
                    if port['name'] == active_port_name:
                        active_port_desc = port.get('description', active_port_name)
                        # Check physical availability (Jack detection)
                        availability = port.get('availability', 'unknown')
                        if availability == 'not available':
                            is_physically_available = False
                        break
            
            # Avoid redundant port info (e.g. "AirPods Pro - Headphones" is OK, but " - Headphones" is bad)
            # and don't append if it's generic "Analog Output" unless we have no other name
            if active_port_desc and active_port_desc != "Analog Output":
                 display_name += f" - {active_port_desc}"

            # Append Disconnected status if physically unplugged
            if not is_physically_available and "[Disconnected]" not in display_name:
                display_name += " [Disconnected]"

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
                'connected': not ("[Disconnected]" in display_name), # Used for graying out
                'properties': props # Store properties for Mic association logic
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

    def get_sink_volume(self, sink_name):
        """
        Returns the volume percentage (integer) of the sink.
        Returns None if failed.
        """
        try:
            # pactl get-sink-volume <sink>
            # Output format:
            # Volume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
            output = self.run_command(['pactl', 'get-sink-volume', sink_name])
            if not output: return None
            
            # Extract first percentage found
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            print(f"Error getting volume for {sink_name}: {e}")
            return None

    def set_sink_volume(self, sink_name, volume_percent):
        """
        Sets sink volume to specific percentage.
        """
        # cap at 100% or allow boost? Usually limit to 100% to avoid blasting.
        # But if user wants >100, we might clip.
        if volume_percent > 150: volume_percent = 150
        if volume_percent < 0: volume_percent = 0
        
        self.run_command(['pactl', 'set-sink-volume', sink_name, f"{volume_percent}%"])

    def get_line_in_source(self):
        """Finds the Line-In source name dynamically."""
        # We look for a source containing 'Line__source'
        output = self.run_command(['pactl', 'list', 'short', 'sources'])
        if not output: return None
        for line in output.split('\n'):
            if "Line__source" in line:
                return line.split()[1]
        return None

    def get_loopback_state(self, source_name):
        """
        Returns (is_loaded, module_id).
        Checks if module-loopback is loaded for the specific source.
        """
        if not source_name: return (False, None)
        
        output = self.run_command(['pactl', 'list', 'short', 'modules'])
        if not output: return (False, None)
        
        # Output format: ID module-name argument
        # 536 module-loopback source=...
        for line in output.split('\n'):
            if "module-loopback" in line and f"source={source_name}" in line:
                parts = line.split()
                try:
                    module_id = parts[0]
                    return (True, module_id)
                except IndexError:
                    pass
        return (False, None)

    def set_loopback_state(self, enable, source_name):
        is_loaded, module_id = self.get_loopback_state(source_name)
        
        if enable and not is_loaded:
            print(f"Loading loopback for {source_name}")
            # latency_msec=1 is too aggressive for USB audio. 50ms is stable.
            self.run_command(['pactl', 'load-module', 'module-loopback', f'source={source_name}', 'latency_msec=50'])
            
        elif not enable and is_loaded:
            print(f"Unloading loopback module {module_id}")
            self.run_command(['pactl', 'unload-module', module_id])

    def get_sources(self, bt_cache=None):
        """Returns a list of source dicts."""
        json_output = self.run_command(['pactl', '--format=json', 'list', 'sources'])
        if not json_output: return []
        
        try:
            sources_data = json.loads(json_output)
        except json.JSONDecodeError:
            return []

        sources = []
        for src in sources_data:
            name = src.get('name', '')
            # Skip monitors usually? 
            # Users rarely want to use a monitor as a mic, except for streaming loopback.
            # But let's filter monitors of JamesDSP or Null sinks to avoid clutter?
            # Actually, "Monitor of..." is determined by 'monitor' class usually or having 'monitor' in name?
            # 'pactl' returns 'device.class' = 'monitor' property.
            props = src.get('properties', {})
            if props.get('device.class') == 'monitor':
                continue
            
            display_name = ""
            
            # 1. Try BT Cache/Alias for Sources too
            if 'bluez' in name or 'bluez' in props.get('device.api', ''):
                mac_match = re.search(r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})', name, re.IGNORECASE)
                if mac_match:
                    mac = mac_match.group(1).replace('_', ':').upper()
                    if bt_cache and mac in bt_cache:
                        display_name = bt_cache[mac]

            if not display_name:
                alias = props.get('bluez.alias') or props.get('device.alias')
                if alias and alias != '(null)':
                    display_name = alias

            if not display_name:
                display_name = props.get('device.description', '')
                
            # Cleanup "(null)" garbage
            if display_name:
                display_name = display_name.replace("(null)", "").strip()
            
            # Smart Naming (similar to Sinks)
            if not display_name:
                vendor = props.get('device.vendor.name', '')
                product = props.get('device.product.name', props.get('device.model', ''))
                if vendor and product:
                    display_name = f"{vendor} {product}"
            
            if not display_name:
                 display_name = name
            
            sources.append({
                'name': name,
                'display_name': display_name,
                'properties': props
            })
        return sources

    def set_default_source(self, source_name):
        self.run_command(['pactl', 'set-default-source', source_name])
    
    def find_associated_source(self, sink_props, sources):
        """
        Tries to find a source that matches the sink properties (Same Card / Serial).
        """
        sink_card = sink_props.get('alsa.card')
        sink_serial = sink_props.get('device.serial')
        sink_bus = sink_props.get('device.bus_path') # USB bus path is very specific matching
        sink_bluez_addr = sink_props.get('api.bluez5.address')
        sink_device_name = sink_props.get('device.name')

        # 1. Try BlueZ Address (Bluetooth)
        if sink_bluez_addr:
             for src in sources:
                 if src['properties'].get('api.bluez5.address') == sink_bluez_addr:
                     return src

        # 2. Try Serial Match (Strongest for USB usually, but fails for BlueZ)
        if sink_serial:
            for src in sources:
                if src['properties'].get('device.serial') == sink_serial:
                    return src
        
        # 3. Try Bus Path (Next Strongest - e.g. same USB port/hub)
        if sink_bus:
            for src in sources:
                if src['properties'].get('device.bus_path') == sink_bus:
                    return src

        # 4. Try Device Name (Card Name) - often shared between Sink/Source of same card
        if sink_device_name:
             for src in sources:
                 # Note: device.name for sink might be 'bluez_card.X' and source also 'bluez_card.X'
                 if src['properties'].get('device.name') == sink_device_name:
                     return src

        # 5. Try ALSA Card Index (Weakest? Card index can change, but usually paired)
        if sink_card:
            for src in sources:
                if src['properties'].get('alsa.card') == sink_card:
                    return src
                    
        return None

class BluetoothController:
    """Handles interaction with BlueZ via D-Bus for device queries and bluetoothctl for connect/disconnect."""

    AUDIO_UUIDS = {
        '0000110b-0000-1000-8000-00805f9b34fb',  # Audio Sink
        '0000110a-0000-1000-8000-00805f9b34fb',  # Audio Source
        '00001108-0000-1000-8000-00805f9b34fb',  # Headset
        '0000111e-0000-1000-8000-00805f9b34fb',  # Handsfree
        '0000110d-0000-1000-8000-00805f9b34fb',  # Advanced Audio Distribution
    }

    def get_devices(self):
        """Returns list of {mac, name, connected} for audio BT devices via D-Bus."""
        try:
            bus = dbus.SystemBus()
            manager = dbus.Interface(
                bus.get_object('org.bluez', '/'),
                'org.freedesktop.DBus.ObjectManager'
            )
            objects = manager.GetManagedObjects()
        except dbus.exceptions.DBusException:
            return []

        devices = []
        for path, interfaces in objects.items():
            if 'org.bluez.Device1' not in interfaces:
                continue
            dev = interfaces['org.bluez.Device1']
            mac = str(dev.get('Address', ''))
            alias = str(dev.get('Alias', ''))
            name = str(dev.get('Name', ''))
            connected = bool(dev.get('Connected', False))
            icon = str(dev.get('Icon', ''))
            uuids = {str(u) for u in dev.get('UUIDs', [])}

            display_name = alias or name or mac

            is_audio = bool(self.AUDIO_UUIDS & uuids) or icon.startswith('audio-')
            if is_audio:
                devices.append({'mac': mac, 'name': display_name, 'connected': connected})

        return devices

    @staticmethod
    def _run_bluetoothctl(command):
        try:
            result = subprocess.run(
                ['bluetoothctl'] + command, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def connect(self, mac):
        self._run_bluetoothctl(['connect', mac])

    def disconnect(self, mac):
        self._run_bluetoothctl(['disconnect', mac])


class PipeWireController:
    """Handles interaction with pw-link for managing PipeWire graph."""
    
    @staticmethod
    def run_command(args):
        try:
            result = subprocess.run(
                args, capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None

    def get_links(self):
        """Returns list of lines from pw-link -l"""
        output = self.run_command(['pw-link', '-l'])
        if not output: return []
        return output.split('\n')

    def link(self, port_out, port_in):
        self.run_command(['pw-link', port_out, port_in])

    def unlink(self, port_out, port_in):
        self.run_command(['pw-link', '-d', port_out, port_in])

    def get_jamesdsp_outputs(self):
        """
        Finds the output ports for JamesDSP.
        Usually: jdsp_@PwJamesDspPlugin_JamesDsp:output_FL / FR
        """
        # We need the node name. Often it's 'jdsp_@PwJamesDspPlugin_JamesDsp'
        # But we can find it by looking for links FROM it.
        # Or better, just regex for typical JamesDSP output pattern.
        links = self.get_links()
        outputs = set()
        for line in links:
            # Lines are "Output -> Input" or "Input <- Output" ? 
            # pw-link -l output is:
            # output_port
            #   |-> input_port
            
            # We want to identify the ports that BELONG to JamesDSP.
            # Based on user `pw-link` output:
            # jdsp_@PwJamesDspPlugin_JamesDsp:output_FL
            #   |-> alsa_output...:playback_FL
            
            # So we look for ports starting with 'jdsp_' containing 'output_'
            if "jdsp_" in line and ":output_" in line:
                # This line is the header port?
                # pw-link -l format:
                # PORT_NAME
                #   |-> LINKED_PORT
                #   |-> LINKED_PORT
                pass

        # Actually, pw-link -o might be easier to just list outputs?
        # Let's use `pw-link -o` in get_outputs if needed.
        # But sticking to `pw-link -l` logic from what we saw in user terminal:
        output_ports = []
        raw_out = self.run_command(['pw-link', '-o']) # List output ports
        if raw_out:
            for line in raw_out.split('\n'):
                if "jdsp_" in line and "JamesDsp" in line and ":output_" in line:
                    output_ports.append(line.strip())
        return output_ports

    def get_sink_playback_ports(self, sink_name):
        """
        Finds the playback ports for a given sink name.
        e.g. alsa_output.usb-Generic...:playback_FL
        """
        # We can search `pw-link -i` (input ports)
        input_ports = []
        raw_in = self.run_command(['pw-link', '-i'])
        # print(f"DEBUG: Searching ports for '{sink_name}'")
        if raw_in:
             for line in raw_in.split('\n'):
                 if sink_name in line and ":playback_" in line:
                     # print(f"DEBUG: Found port {line.strip()}")
                     input_ports.append(line.strip())
        return input_ports

    def get_jamesdsp_target(self):
        """
        Returns the name of the sink that JamesDSP is currently routed to.
        Returns None if floating or not found.
        """
        jdsp_outs = self.get_jamesdsp_outputs()
        if not jdsp_outs:
            return None
            
        src = jdsp_outs[0]
        links = self.get_links()
        
        # Simplified robust parsing
        # Look for lines like:
        # <src>
        #   |-> <target>
        capture_next = False
        
        for line in links:
            sline = line.strip()
            if sline == src:
                capture_next = True
            elif capture_next and line.startswith("  |->"):
                # Found a link!
                raw_target = line.replace("  |->", "").strip()
                if ":playback_" in raw_target:
                    found_target = raw_target.split(":playback_")[0]
                    return found_target
            elif capture_next and not line.startswith("  "):
                # Indentation broken, we moved to next block
                capture_next = False
                
        return None

    def relink_jamesdsp(self, target_sink_name):
        """
        Disconnects JamesDSP from current HW and connects to target_sink_name.
        """
        jdsp_outs = self.get_jamesdsp_outputs()
        if not jdsp_outs:
            print("DEBUG: JamesDSP outputs not found (relink failed).")
            return False

        target_ins = self.get_sink_playback_ports(target_sink_name)
        if not target_ins:
            print(f"DEBUG: Target inputs for '{target_sink_name}' not found via pw-link.")
            return False
            
        # 1. DISCONNECT EXISTING LINKS FIRST
        # To avoid duplicate audio (playing from both old and new device)
        links = self.get_links()
        for out_port in jdsp_outs:
            # Find what this output is connected to
            # Parsing "out_port \n |-> target"
            capture = False
            for line in links:
                sline = line.strip()
                if sline == out_port:
                    capture = True
                elif capture and line.startswith("  |->"):
                    # Found a link to remove
                    target = line.replace("  |->", "").strip()
                    # Only remove if it's a playback port (don't break monitors if any?)
                    if ":playback_" in target:
                        # print(f"DEBUG: Unlinking {out_port} -> {target}")
                        self.unlink(out_port, target)
                elif capture and not line.startswith("  "):
                    capture = False

        # 2. CONNECT NEW LINKS
        # Sort to insure FL->FL, FR->FR
        jdsp_outs.sort()
        target_ins.sort()
        
        # Link corresponding channels
        # We assume jdsp_outs[0] is FL, target_ins[0] is FL (standard alpha sort)
        count = min(len(jdsp_outs), len(target_ins))
        for i in range(count):
            self.link(jdsp_outs[i], target_ins[i])
            
        return True
    def get_sink_volume(self, sink_name):
        """
        Returns the volume percentage (integer) of the sink.
        Returns None if failed.
        """
        try:
            # pactl get-sink-volume <sink>
            # Output format:
            # Volume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
            output = self.run_command(['pactl', 'get-sink-volume', sink_name])
            if not output: return None
            
            # Extract first percentage found
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            print(f"Error getting volume for {sink_name}: {e}")
            return None

    def set_sink_volume(self, sink_name, volume_percent):
        """
        Sets sink volume to specific percentage.
        """
        # cap at 100% or allow boost? Usually limit to 100% to avoid blasting.
        # But if user wants >100, we might clip.
        if volume_percent > 150: volume_percent = 150
        if volume_percent < 0: volume_percent = 0
        
        self.run_command(['pactl', 'set-sink-volume', sink_name, f"{volume_percent}%"])


    def get_sink_volume(self, sink_name):
        """
        Returns the volume percentage (integer) of the sink.
        Returns None if failed.
        """
        try:
            # pactl get-sink-volume <sink>
            # Output format:
            # Volume: front-left: 65536 / 100% / 0.00 dB,   front-right: 65536 / 100% / 0.00 dB
            output = self.run_command(['pactl', 'get-sink-volume', sink_name])
            if not output: return None
            
            # Extract first percentage found
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            print(f"Error getting volume for {sink_name}: {e}")
            return None

    def set_sink_volume(self, sink_name, volume_percent):
        """
        Sets sink volume to specific percentage.
        """
        # cap at 100% or allow boost? Usually limit to 100% to avoid blasting.
        # But if user wants >100, we might clip.
        if volume_percent > 150: volume_percent = 150
        if volume_percent < 0: volume_percent = 0
        
        self.run_command(['pactl', 'set-sink-volume', sink_name, f"{volume_percent}%"])


class VolumeMonitorThread(QThread):
    """
    Monitors 'pactl subscribe' for sink changes.
    When 'jamesdsp_sink' changes volume, it signals the main thread to sync.
    """
    volume_changed_signal = pyqtSignal()

    def run(self):
        # pactl subscribe output:
        # Event 'change' on sink #651 (jamesdsp_sink)
        
        # We start a subprocess that runs forever
        process = subprocess.Popen(
            ['pactl', 'subscribe'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
        
        while True:
            line = process.stdout.readline()
            if not line:
                break
            
            # DEBUG
            # print(f"DEBUG_SUB: {line.strip()}")
            
            # We are interested in "sink" events
            if "Event 'change' on sink" in line:
                # print(f"DEBUG_SUB: Detected sink change: {line.strip()}")
                self.volume_changed_signal.emit()



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
        
        # Circuit breaker for JamesDSP crashes/loops
        self.jdsp_broken_state = False

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
        
        # Restore Geometry
        geom = self.config.get("window_geometry")
        if geom:
            from PyQt6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        else:
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
        
        # JamesDSP Status Banner
        self.jdsp_label = QLabel("✨ Effects Active (JamesDSP)")
        self.jdsp_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11pt;")
        self.jdsp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.jdsp_label.hide() # Hidden by default
        audio_layout.addWidget(self.jdsp_label)
        
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

        # --- Volume Section ---
        vol_group = QGroupBox("Volume Control")
        vol_layout = QVBoxLayout()
        vol_group.setLayout(vol_layout)
        
        self.vol_label = QLabel("Volume: --%")
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_layout.addWidget(self.vol_label)
        
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 100)
        self.vol_slider.valueChanged.connect(self.on_vol_slider_changed)
        self.vol_slider.sliderReleased.connect(self.on_vol_slider_released)
        vol_layout.addWidget(self.vol_slider)
        
        main_layout.addWidget(vol_group)

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

        self.loopback_cb = QCheckBox("Enable Line-In Loopback")
        self.loopback_cb.clicked.connect(self.on_loopback_toggled)
        controls_layout.addWidget(self.loopback_cb)


        self.status_label = QLabel("Ready")
        controls_layout.addWidget(self.status_label)

        self.refresh_btn = QPushButton("Refresh All")
        self.refresh_btn.clicked.connect(self.refresh_all_force)
        controls_layout.addWidget(self.refresh_btn)
        
        main_layout.addWidget(controls_group)
        
        # --- Headset Settings Section ---
        self.headset_group = QGroupBox("Headset Settings")
        headset_layout = QVBoxLayout()
        self.headset_group.setLayout(headset_layout)
        
        h_layout = QHBoxLayout()
        
        self.idle_cb = QCheckBox("Disconnect on Idle")
        self.idle_cb.toggled.connect(self.on_idle_toggled)
        h_layout.addWidget(self.idle_cb)
        
        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 90)
        self.idle_spin.setSuffix(" min")
        self.idle_spin.setValue(10) # Default
        self.idle_spin.valueChanged.connect(self.on_idle_spin_changed)
        h_layout.addWidget(self.idle_spin)
        
        headset_layout.addLayout(h_layout)
        
        main_layout.addWidget(self.headset_group)
        
        # Initialize Headset UI State
        self.init_headset_ui()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(5000) 

        self.refresh_all()

        # System Tray Setup
        self.setup_tray()

    def get_actual_active_sink_name(self):
        """Helper to find the physical sink we should be controlling/displaying."""
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        
        if default_sink_name == "jamesdsp_sink":
            pw = PipeWireController()
            target = pw.get_jamesdsp_target()
            if target:
                return target
        
        return default_sink_name

    def refresh_volume_ui(self):
        target_name = self.get_actual_active_sink_name()
        if not target_name:
            self.vol_label.setText("Volume: --%")
            self.vol_slider.setEnabled(False)
            return

        vol = self.audio.get_sink_volume(target_name)
        if vol is not None:
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(vol)
            self.vol_slider.blockSignals(False)
            self.vol_label.setText(f"Volume: {vol}%")
            self.vol_slider.setEnabled(True)
        else:
             self.vol_label.setText("Volume: ??%")
             self.vol_slider.setEnabled(False)

    def on_vol_slider_changed(self, value):
        # Update label immediately for responsiveness
        self.vol_label.setText(f"Volume: {value}%")

    def on_vol_slider_released(self):
        # Apply volume on release to avoid spawning too many pactl processes
        val = self.vol_slider.value()
        target_name = self.get_actual_active_sink_name()
        
        if target_name:
            print(f"Setting volume of {target_name} to {val}%")
            self.audio.set_sink_volume(target_name, val)
            
            # If JamesDSP is active, ensure its virtual sink is at 100% too?
            # Usually good practice if we want full dynamic range, 
             # but user might have lowered it manually. We'll leave it alone unless requested.
            pass

    def check_and_sync_volume(self):
        """
        Polls JamesDSP volume. If != 100%, syncs to hardware.
        """
        # print("DEBUG: check_and_sync_volume tick")
        
        # 1. Quick check: Is JamesDSP default?
        # Optimization: We can check this less frequently or cache it?
        # For now, let's trust get_default_sink is fast (it runs a tiny process).
        # Actually, running a process every 200ms might be heavy-ish on Python.
        # But 'pactl get-default-sink' is very light.
        
        # Let's try to optimize: Only check volume of 'jamesdsp_sink' directly.
        # If it's not running, get_sink_volume returns None instantly.
        
        try:
            jdsp_vol = self.audio.get_sink_volume("jamesdsp_sink")
            
            # If JDSP doesn't exist or is 100%, do nothing.
            if jdsp_vol is None or jdsp_vol == 100:
                return
            
            # Volume Changed! (< 100 or > 100)
            # Find target.
            
            pw = PipeWireController()
            jdsp_outs = pw.get_jamesdsp_outputs()
            
            found_target = None
            if jdsp_outs:
                src = jdsp_outs[0]
                links = pw.get_links()
                
                # Simplified robust parsing
                # Look for lines like:
                # <src>
                #   |-> <target>
                # We iterate and keep state.
                capture_next = False
                
                for line in links:
                    sline = line.strip()
                    if sline == src:
                        capture_next = True
                    elif capture_next and line.startswith("  |->"):
                        # Found a link!
                        raw_target = line.replace("  |->", "").strip()
                        if ":playback_" in raw_target:
                            found_target = raw_target.split(":playback_")[0]
                            # print(f"DEBUG: Found target sink for volume sync: {found_target}")
                            break
                    elif capture_next and not line.startswith("  "):
                        # Indentation broken, we moved to next block
                        capture_next = False
            
            if not found_target:
                print(f"DEBUG: JamesDSP is active but floating. Cannot sync volume.")
                return 

            # Get HW Volume
            current_target_vol = self.audio.get_sink_volume(found_target)
            if current_target_vol is None: return
            
            # Calculate New
            factor = jdsp_vol / 100.0
            new_vol = int(current_target_vol * factor)
            
            print(f"Volume Sync: JDSP={jdsp_vol}%, Target={current_target_vol}% -> {new_vol}%")
            
            # Apply
            self.audio.set_sink_volume(found_target, new_vol)
            self.audio.set_sink_volume("jamesdsp_sink", 100)
            
        except Exception as e:
            print(f"Error in volume sync: {e}")
        
        try:
            default_sink = self.audio.get_default_sink()
            if default_sink != "jamesdsp_sink":
                return # Not managing JDSP volume right now
            
            # Get JDSP Volume
            # Note: This runs on Main Thread, so it might block slightly if pactl is slow.
            # But pactl is usually instant.
            jdsp_vol = self.audio.get_sink_volume("jamesdsp_sink")
            
            # DEBUG: Uncomment to trace
            # if jdsp_vol is not None and jdsp_vol != 100:
            #    print(f"DEBUG: JDSP Vol is {jdsp_vol}")
            
            if jdsp_vol is None: return
            
            # If volume is 100% (or very close), do nothing.
            # We use a small tolerance? No, exact 100% usually.
            if jdsp_vol == 100:
                return
            
            # It Changed! 
            # 1. Find target physical sink.
            # Rerunning logic or querying PW-link?
            # PW-link is safer.
            pw = PipeWireController()
            # We assume we only care about the FIRST channel link
            # Getting links every volume change might be heavy?
            # Maybe we can cache "current_target_sink"?
            # Let's try finding it dynamically first.
            
            target_sink_name = None
            jdsp_outs = pw.get_jamesdsp_outputs()
            if jdsp_outs:
                src = jdsp_outs[0]
                links = pw.get_links()
                for line in links:
                    if line.startswith("  |->") and src in previous_line:
                        # Parsing logic is tricky without state machine in simple iteration
                        pass
                
                # Re-use better parsing logic or extract to helper
                # Let's extract a fast helper in AudioController or just loop quickly
                # Quick hack: Query specifically for connections of JDSP output
                # `pw-link -l` shows entire graph.
                
                # Optimized approach:
                # We just need to know what to control.
                # If we don't know, we can't sync.
                # However, if we recently Autoswitched, we might have it stored.
                pass
            
            # Let's use `pactl list sinks` or similar to find what JDSP links to? hard.
            # Let's use the PipeWireController get_links parsing we wrote in run_auto_switch
            # But simplified.
            
            # Actually, `run_auto_switch` logic to find target is robust.
            # Let's COPY that logic here but optimized.
            
            found_target = None
            if jdsp_outs:
                src = jdsp_outs[0]
                links = pw.get_links()
                capture = False
                for line in links:
                    if line.strip() == src:
                        capture = True
                    elif capture and line.startswith("  |->"):
                        target_port = line.replace("  |->", "").strip()
                        if ":playback_" in target_port:
                            found_target = target_port.split(":playback_")[0]
                        break
                    elif capture and not line.startswith("  "):
                        capture = False
            
            if not found_target:
                print("Volume Sync: Could not find hardware sink attached to JamesDSP.")
                return 

            # 2. Get Current Target Volume
            current_target_vol = self.audio.get_sink_volume(found_target)
            if current_target_vol is None: return
            
            # 3. Calculate New Volume
            # Logic: If JDSP went to 95% (down 5%), we should lower Target by 5%?
            # OR: Simple multiplication? 
            # If user pressed "Vol Down", JDSP becomes 95%.
            # We want to apply that relative change?
            # Or just "Transfer" the delta?
            
            # Easier Logic:
            # NewTarget = OldTarget * (JDSP_Vol / 100)
            # Then Reset JDSP to 100.
            # This handles both Up and Down.
            # Example:
            # Target = 50%. User presses Vol Down -> JDSP = 95%.
            # NewTarget = 50 * 0.95 = 47.5%.
            # Reset JDSP to 100%.
            
            # Example Up:
            # Target = 50%. User presses Vol Up -> JDSP = 105%.
            # NewTarget = 50 * 1.05 = 52.5%.
            
            factor = jdsp_vol / 100.0
            new_vol = int(current_target_vol * factor)
            
            # Safety check: if factor is huge? KDE keys usually step 5%.
            
            print(f"Volume Sync: JDSP={jdsp_vol}%, Target={current_target_vol}% -> {new_vol}%")
            
            # 4. Apply
            self.audio.set_sink_volume(found_target, new_vol)
            
            # 5. Reset JDSP
            self.audio.set_sink_volume("jamesdsp_sink", 100)
            
        except Exception as e:
            print(f"Error in volume sync: {e}")

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
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)
        
        menu.addSeparator()
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def show_about(self):
        # Create custom dialog
        dlg = QDialog(self)
        dlg.setWindowTitle("Help & About")
        dlg.resize(600, 500)
        
        layout = QVBoxLayout()
        dlg.setLayout(layout)
        
        # Help Text
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self.get_help_text())
        layout.addWidget(browser)
        
        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        
        dlg.exec()

    def get_help_text(self):
        return """
        <div align="center">
            <h1>Audio Source Switcher</h1>
            <p><b>Version 11.7</b></p>
            <p>A power-user utility for managing audio outputs on Linux (PulseAudio/PipeWire).</p>
            <p>Copyright (c) 2026 ushineko</p>
        </div>
        <hr>
        
        <h3>🎧 Managing Audio</h3>
        <ul>
            <li><b>Switch Output:</b> Double-click a device in the list to switch audio to it.</li>
            <li><b>Priority:</b> Drag and drop devices to reorder them. If <i>"Auto-switch"</i> is checked, the app will automatically switch to the highest-priority connected device.</li>
            <li><b>Bluetooth:</b> Click "Connect" to pair/connect to a selected device. Offline devices can be auto-connected by double-clicking them in the main list.</li>
            <li><b>Mic Association:</b> Right-click a device to Link a specific Microphone to it (or use Auto mode).</li>
        </ul>

        <h3>🎤 Microphone Association</h3>
        <p>Automatically switch input devices when changing outputs:</p>
        <ul>
            <li><b>Link Mic:</b> Right-click an output device in the list and select <b>"Link Microphone..."</b> to choose which input should be activated when this output is selected.</li>
            <li><b>Auto-Link:</b> By default (Auto), the app tries to match the input device belonging to the same hardware (e.g., switching to AirPods Output also switches to AirPods Mic).</li>
        </ul>

        <h3>🎧 Arctis Headset Control</h3>
        <p>If a SteelSeries Arctis headset is detected:</p>
        <ul>
             <li><b>Disconnect on Idle:</b> Automatically turn off the headset to save battery when no audio is playing for a set duration. Configure the timeout (1-90 mins) in the standard settings area.</li>
        </ul>

        <h3>🔊 JamesDSP Integration</h3>
        <p>The app intelligently handles the <b>JamesDSP</b> effects processor:</p>
        <ul>
            <li><b>Effects Active:</b> Audio is routed through JamesDSP before reaching your speakers/headphones.</li>
            <li><b>Smart Switching:</b> When you select a device, the app <i>rewires</i> the internal graph so effects are preserved.</li>
            <li><b>Safety:</b> Includes a "Circuit Breaker" to prevent crashes if JamesDSP becomes unstable.</li>
        </ul>

        <h3>🎙️ Line-In Loopback</h3>
        <p>Use the <b>"Enable Line-In Loopback"</b> checkbox to listen to your Line-In device (e.g. game console input) through your current output. This toggles the system's <code>module-loopback</code>.</p>

        <h3>🧠 Smart Jack Detection</h3>
        <p>The app intelligently detects if "Front Headphones" are physically unplugged. Unplugged devices are marked as <code>[Disconnected]</code> and skipped by the auto-switcher.</p>

        <h3>⌨️ Global Hotkeys & CLI</h3>
        <p>Control the app from the terminal or system shortcuts:</p>
        <ul>
            <li><b>Switch Device:</b><br><code>--connect "Device Name"</code> (or ID)</li>
            <li><b>Hardware Volume (Bypasses DSP):</b><br><code>--vol-up</code> / <code>--vol-down</code></li>
        </ul>
        <p><i>Tip: Right-click a device in the list to copy its instant Command ID.</i></p>
        """

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        # Restore geometry if available to fix size-loss on hiding
        geom = self.config.get("window_geometry")
        if geom:
            from PyQt6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))

        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        # Save Window Geometry
        self.config["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.config_mgr.save_config(self.config)

        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
            # self.tray_icon.showMessage("Audio Switcher", "App minimized to tray.", QSystemTrayIcon.MessageIcon.Information, 2000)
        else:
            event.accept()

    def quit_app(self):
        # Save geometry before quitting
        self.config["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.config_mgr.save_config(self.config)
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
        self.refresh_volume_ui()
        
        if self.auto_switch_cb.isChecked():
            self.run_auto_switch()

    def run_auto_switch(self):
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        sink_map = {s['priority_id']: s for s in sinks}
        
        # Get Current Default Info
        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        
        self.refresh_loopback_ui()
        
        # Check if JamesDSP is available in the list
        jamesdsp_available = any(s['name'] == "jamesdsp_sink" for s in sinks)
        
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
                # JamesDSP Integration: 
                # Use regular logic, but we must NOT auto-switch TO JamesDSP sink directly if we want to use rewiring.
                # Actually, we want to find the best PHYSICAL sink.
                # So if pid == "jamesdsp_sink" (or whatever ID it has), skip it?
                # Usually JamesDSP has a specific name "jamesdsp_sink".
                if "jamesdsp_sink" in pid:
                    continue

                s = sink_map[pid]
                if s.get('connected', True):
                    target_sink_obj = s
                    break
        
        # Logic: 
        # 1. If we found a high priority target
        # 2. And it's NOT the current default
        # 3. OR the current default is "Disconnected" (invalid) -> Force switch to best available
        
        should_switch = False
        
        # Helper: function to get underlying sink of JamesDSP if it's default
        current_physical_sink = default_sink_name
        is_jdsp_active = False
        
        if default_sink_name == "jamesdsp_sink":
            is_jdsp_active = True
            # We need to find what JDSP is connected to, to know if we need to switch.
            # But that's expensive to query every 5s.
            # Maybe we just check if target_sink_obj is what we *think* it should be?
            # Or simpler: The notification/status label tells us what we switched to. 
            pass

        if target_sink_obj:
            target_name = target_sink_obj['name']
            
            # 1. Basic Mismatch: We are on a different device entirely
            if default_sink_name != target_name:
                should_switch = True
                
            # 2. JamesDSP Enforcement:
            # If we are physically on the target sink (default == target), 
            # BUT JamesDSP is available and NOT default, we should switch 
            # to trigger the 'Use JamesDSP' path in switch_to_sink().
            # Safety Fix: Only enforce if JamesDSP has valid OUTPUT PORTS (is running correctly).
            # Circuit Breaker: Don't retry if we already failed this session.
            if jamesdsp_available and default_sink_name == target_name and default_sink_name != "jamesdsp_sink":
                 if not self.jdsp_broken_state:
                     pw = PipeWireController()
                     if pw.get_jamesdsp_outputs():
                         # print("DEBUG: Enforcing JamesDSP activation for current device.")
                         should_switch = True
                     else:
                         # print("DEBUG: JamesDSP sink exists but has no outputs. Skipping.")
                         pass
                 else:
                     # print("DEBUG: JamesDSP marked broken. Skipping enforcement.")
                     pass
            
            # 3. JamesDSP Correctness:
            # If currently default IS "jamesdsp_sink", check routing.
            if default_sink_name == "jamesdsp_sink":
                try:
                    pw = PipeWireController()
                    jdsp_target = pw.get_jamesdsp_target()
                    
                    if jdsp_target:
                        if jdsp_target != target_name:
                            # It's routed to wrong physical device!
                            # print(f"DEBUG: JDSP routed to {jdsp_target}, want {target_name}. Switching.")
                            should_switch = True
                        else:
                            # Correctly routed. We are good.
                            current_is_valid = True 
                            should_switch = False
                    else:
                        # JDSP floating. Fix it.
                        # print("DEBUG: JDSP floating. Switching.")
                        should_switch = True
                        
                except Exception:
                    should_switch = True # Fallback
                    # Just check one channel
                    links = pw.get_links()
                    
                    current_targ = None
                    if jdsp_outs:
                        src = jdsp_outs[0]
                        # Find what src connects to
                        for line in links:
                            if src in line or (f"|-> {src}" in line): 
                                # Wait, get_links format: "Port |-> Target"
                                # We need more robust parsing in Controller, but we can do a quick check
                                pass
                        
                        # Re-implement simple check:
                        # Scan links for lines starting with src
                        # line: "jdsp...:output_FL"
                        # next line: "  |-> alsa_output...:playback_FL"
                        
                        found_target_name = None
                        capture_next = False
                        for line in links:
                            if line.strip() == src:
                                capture_next = True
                            elif capture_next and line.startswith("  |->"):
                                # "  |-> alsa_output.pci...:playback_FL"
                                target_port = line.replace("  |->", "").strip()
                                # Extract sink name from port (remove :playback_...)
                                if ":playback_" in target_port:
                                    found_target_name = target_port.split(":playback_")[0]
                                break
                            elif capture_next and not line.startswith("  "):
                                capture_next = False
                        
                        if found_target_name:
                            print(f"DEBUG: JDSP routed to {found_target_name}")
                            if found_target_name != target_sink_obj['name']:
                                should_switch = True
                        else:
                            # If no target found, JamesDSP is floating (disconnected).
                            # We MUST switch to re-establish connection.
                            print("DEBUG: JDSP floating (no links). Ordering switch/rewire.")
                            should_switch = True

                except Exception as e:
                    print(f"Error checking JDSP routing: {e}")

            if not current_is_valid:
                 # Current default is broken/disconnected
                 pass # should_switch might need to be forced if not already handled
        
        
        
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
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sinks = self.audio.get_sinks(bt_map)
        
        # 1. Identify "Real" Active Device
        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        # print(f"DEBUG_STARTUP: default_sink_name = {default_sink_name}")
        active_real_sink_name = default_sink_name
        
        is_jdsp_default = (default_sink_name == "jamesdsp_sink")
        
        if is_jdsp_default:
            self.jdsp_label.show()
            # JamesDSP is active. Find physical target.
            pw = PipeWireController()
            target = pw.get_jamesdsp_target()
            if target:
                active_real_sink_name = target
        else:
            self.jdsp_label.hide()

        # 2. Merge offline devices from config priority list
        priority_list = self.config.get("device_priority", [])
        
        # Map existing online sinks by ID
        online_map = {s['priority_id']: s for s in sinks}
        
        final_list = []
        seen_ids = set()
        
        # Add devices in priority order
        for pid in priority_list:
            if pid in seen_ids: continue
            
            # Hide JamesDSP
            if "jamesdsp_sink" in pid:
                continue

            if pid in online_map:
                final_list.append(online_map[pid])
                seen_ids.add(pid)
            else:
                # Add offline placeholder
                display = pid
                if pid.startswith("bt:"):
                    mac = pid[3:]
                    for d in self.cache_bt_devices:
                        if d['mac'] == mac:
                            display = d['name']
                            break
                final_list.append({
                    'name': None,
                    'priority_id': pid,
                    'display_name': f"{display} [Disconnected]",
                    'is_default': False,
                    'connected': False
                })
                seen_ids.add(pid)
        
        # Add remaining online devices
        for s in sinks:
            if s['priority_id'] not in seen_ids:
                if "jamesdsp_sink" in s['priority_id'] or s['name'] == "jamesdsp_sink":
                    continue
                final_list.append(s)
                seen_ids.add(s['priority_id'])
                
        # 3. Build Presentation Items with Highlights
        new_items = []
        active_item_index = -1
        
        for idx, s in enumerate(final_list):
            # Check overlap with active_real_sink_name
            # Note: s['name'] might be None for disconnected items
            is_active = (s['name'] is not None and s['name'] == active_real_sink_name)
            
            text = s['display_name']
            if is_active:
                text = f"✅ {text}"
                active_item_index = idx
            
            color = None
            if not s['connected']:
                color = QColor("gray")
            elif is_active:
                color = QColor("#4CAF50") # Green highlight
            
            new_items.append({
                'id': s['priority_id'],
                'text': text,
                'bold': is_active,
                'color': color,
                'is_active': is_active
            })
            
        self.update_list_widget(self.sink_list, new_items)
        
        # 4. Scroll to Active on Startup (First Run logic or if unselected)
        # Check if current selected item is NOT the active one?
        # Or just ensuring active is visible.
        # Let's force selection of the active item if nothing is selected.
        if not self.sink_list.currentItem() and active_item_index >= 0:
             item = self.sink_list.item(active_item_index)
             if item:
                 self.sink_list.setCurrentItem(item)
                 self.sink_list.scrollToItem(item)
                 
        # Update Status Label
        if active_item_index >= 0:
             clean_name = new_items[active_item_index]['text'].replace("✅ ", "")
             self.status_label.setText(f"Active: {clean_name}")
                


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
        # User manually requested a switch. Reset circuit breaker to allow retrying JamesDSP.
        self.jdsp_broken_state = False
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

    def send_notification(self, title, message, icon="audio-card", sound="message-new-instant"):
        try:
            subprocess.run([
                'notify-send',
                '-a', 'Audio Switcher',
                '-i', icon,
                '-h', f'string:sound-name:{sound}',
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

    def on_loopback_toggled(self, checked):
        source = self.audio.get_line_in_source()
        if source:
            self.audio.set_loopback_state(checked, source)
            # Update visual state immediately (though refresh will check it too)
            # Checked state is already set by click
            status = "Enabled" if checked else "Disabled"
            self.status_label.setText(f"Loopback {status}")
        else:
            self.status_label.setText("Line-In Source Not Found")
            self.loopback_cb.setChecked(False)

    def init_headset_ui(self):
        # Load config
        minutes = self.config.get("arctis_idle_minutes", 0)
        
        # Block signals during init
        self.idle_cb.blockSignals(True)
        self.idle_spin.blockSignals(True)
        
        if minutes > 0:
            self.idle_cb.setChecked(True)
            self.idle_spin.setEnabled(True)
            self.idle_spin.setValue(minutes)
        else:
            self.idle_cb.setChecked(False)
            self.idle_spin.setEnabled(False)
            # keep spin value at previous or default 10
        
        self.idle_cb.blockSignals(False)
        self.idle_spin.blockSignals(False)
        
        # Check availability
        # We only enable the group if we detect an Arctis headset?
        # Or we let it be available but only apply if connected.
        # Ideally, we check presence.
        status = self.audio.headset.get_battery_status()
        self.headset_group.setEnabled(status is not None)
        if status is None:
             self.headset_group.setTitle("Headset Settings (Not Detected)")
        else:
             self.headset_group.setTitle("Headset Settings")

    def on_idle_toggled(self, checked):
        self.idle_spin.setEnabled(checked)
        self.apply_idle_settings()

    def on_idle_spin_changed(self, value):
        self.apply_idle_settings()

    def apply_idle_settings(self):
        minutes = 0
        if self.idle_cb.isChecked():
            minutes = self.idle_spin.value()
        
        # Save to config
        self.config["arctis_idle_minutes"] = minutes
        self.config_mgr.save_config(self.config)
        
        # Apply
        success = self.audio.headset.set_inactive_time(minutes)
        if success:
            state = f"{minutes} min" if minutes > 0 else "Disabled"
            self.status_label.setText(f"Headset Idle: {state}")
        else:
            self.status_label.setText("Error applying headset settings.")

    def refresh_loopback_ui(self):
        source = self.audio.get_line_in_source()
        if not source:
            self.loopback_cb.setEnabled(False)
            self.loopback_cb.setText("Line-In Loopback (Not Found)")
            return
            
        self.loopback_cb.setEnabled(True)
        self.loopback_cb.setText("Enable Line-In Loopback")
        
        is_loaded, _ = self.audio.get_loopback_state(source)
        
        # Block signals to prevent triggering toggle logic
        self.loopback_cb.blockSignals(True)
        self.loopback_cb.setChecked(is_loaded)
        self.loopback_cb.blockSignals(False)

    def switch_to_sink(self, sink_name, display_text):
        # JamesDSP Integration (Graph Rewiring)
        # Check if JamesDSP sink exists and is active (we can assume if it's in our sink list it exists)
        # But we need to know if the USER wants to use it or bypass it.
        # Current logic: If JamesDSP sink is present in the system, we assume we want to use it
        # BUT only if we are physically switching audio.
        
        use_jamesdsp = False
        jamesdsp_sink_name = "jamesdsp_sink"
        
        # Check if JamesDSP is running/present
        # We can check self.audio.get_sinks() but that might be slow to re-fetch.
        # We can check `pactl info` or just try `pw-link`.
        # Simplest: Check if our list of sinks contains 'jamesdsp_sink' (it should if we refreshed).
        
        # Optimization: We only try this if the target is NOT JamesDSP itself.
        if sink_name != jamesdsp_sink_name:
            # Check if JDSP is available
            pw = PipeWireController()
            jdsp_outs = pw.get_jamesdsp_outputs()
            if jdsp_outs:
                use_jamesdsp = True
                print("JamesDSP detected. Attempting graph rewiring...")

        if use_jamesdsp:
            # 1. Set Default Sink to JamesDSP (so apps route there)
            self.audio.set_default_sink(jamesdsp_sink_name)
            
            # 2. Move streams to JamesDSP (if enabled)
            if self.move_streams_cb.isChecked():
                self.audio.move_input_streams(jamesdsp_sink_name)
            
            # 3. Rewire JamesDSP Output -> Target Hardware Sink
            # print(f"DEBUG: Attempting relink JDSP -> {sink_name}")
            success = pw.relink_jamesdsp(sink_name)
            if success:
                print(f"Rewired JamesDSP -> {sink_name}")
            else:
                print("Failed to rewire JamesDSP. Fallback to direct switch.")
                self.audio.set_default_sink(sink_name)
                if self.move_streams_cb.isChecked():
                    self.audio.move_input_streams(sink_name)

        else:
                self.audio.move_input_streams(sink_name)

        # --- Microphone Association Logic ---
        # 1. Look up config
        mic_links = self.config.get("mic_links", {})
        
        # Identify priority_id for this sink_name (need to reverse lookup or have passed it)
        # We passed display_text, can we get ID? 
        # Better: caller probably has ID. 
        # But for now let's lookup in sinks list (this is slightly inefficient re-fetch but safe)
        
        # Note: this re-fetch might be needed anyway to get properties if we didn't pass them
        p_id = None
        sink_props = {}
        
        # Optimization: Try to find ID from known list in memory logic? 
        # We just refreshed sinks recently in most cases.
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        current_sinks = self.audio.get_sinks(bt_map)
        
        for s in current_sinks:
             if s['name'] == sink_name:
                 p_id = s['priority_id']
                 sink_props = s.get('properties', {})
                 break
        
        target_source_name = None
        mic_msg = ""
        
        if p_id:
            link_cfg = mic_links.get(p_id, "default") # Default is "Auto" effectively if not set? No, verify requirements.
            # Actually default behavior should be "Auto" or "None"? 
            # User request: "associate... so input is switched too". Implies defaults to some logic.
            # Plan says: "Default... try to automatically find".
            
            # If not in config, treat as "auto"
            if p_id not in mic_links:
                link_cfg = "auto"
            
            if link_cfg == "default":
                 # Do not touch mic (System Default behavior)
                 pass
            
            elif link_cfg == "auto":
                 # Auto Match
                 sources = self.audio.get_sources(bt_map)
                 matched = self.audio.find_associated_source(sink_props, sources)
                 if matched:
                     target_source_name = matched['name']
                     mic_msg = f" + Mic: {matched['display_name']}"
            
            else:
                 # Specific Source Name
                 target_source_name = link_cfg
                 # Verify it exists/get display name
                 sources = self.audio.get_sources(bt_map)
                 for src in sources:
                     if src['name'] == target_source_name:
                         mic_msg = f" + Mic: {src['display_name']}"
                         break
                     
        if target_source_name:
             print(f"Switching Mic to: {target_source_name}")
             self.audio.set_default_source(target_source_name)

        # PA race condition fix: Wait for state to propagate before reading it back
        QTimer.singleShot(150, self.refresh_sinks_ui)
        
        clean_text = display_text.replace(" (Active)", "")
        self.status_label.setText(f"Switched to: {clean_text}{mic_msg}")
        
        # System Notification
        self.send_notification("Audio Switched", f"Output: {clean_text}\nInput: {mic_msg.replace(' + Mic: ', '') if mic_msg else 'Unchanged'}")

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
        
        if not item: return
        
        menu = QMenu()
        
        # Link Mic Action
        link_mic_action = QAction("Link Microphone...", self)
        link_mic_action.triggered.connect(lambda: self.show_link_mic_dialog(item))
        menu.addAction(link_mic_action)
        
        menu.addSeparator()

        copy_cmd_action = QAction("Copy Hotkey Command", self)
        copy_cmd_action.triggered.connect(lambda: self.copy_switch_command(item))
        menu.addAction(copy_cmd_action)
        
        menu.exec(self.sink_list.mapToGlobal(pos))

    def show_link_mic_dialog(self, item):
        priority_id = item.data(Qt.ItemDataRole.UserRole)
        display_name = item.text().replace("✅ ", "")
        
        dlg = QDialog(self)
        dlg.setWindowTitle("Link Microphone")
        dlg.resize(400, 150)
        
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"When switching to output: <b>{display_name}</b>"))
        layout.addWidget(QLabel("Automatically switch input (Mic) to:"))
        
        combo = QComboBox()
        combo.addItem("Auto (Match Device)", "auto")
        combo.addItem("Don't Switch (Keep Current)", "default")
        combo.insertSeparator(2)
        
        # Load Sources with BT Cache
        bt_map = {d['mac']: d['name'] for d in self.cache_bt_devices}
        sources = self.audio.get_sources(bt_map)
        
        for src in sources:
            combo.addItem(src['display_name'], src['name'])
            
        # Set Current Selection
        current_link = self.config.get("mic_links", {}).get(priority_id, "auto")
        
        index = combo.findData(current_link)
        if index >= 0:
            combo.setCurrentIndex(index)
        
        layout.addWidget(combo)
        
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_val = combo.currentData()
            
            # Save
            if "mic_links" not in self.config:
                self.config["mic_links"] = {}
                
            self.config["mic_links"][priority_id] = new_val
            self.config_mgr.save_config(self.config)
            self.status_label.setText("Microphone link saved.")
        
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


def handle_volume_command(direction):
    """
    direction: 'up' or 'down'
    Bypasses standard volume control to handle JamesDSP.
    """
    audio = AudioController()
    pw = PipeWireController()
    
    # Check Default Sink
    default = audio.get_default_sink()
    
    target_sink = default
    
    # If JamesDSP is default, we want to control the Attached Hardware Sink instead
    if default == "jamesdsp_sink":
        hw_target = pw.get_jamesdsp_target()
        if hw_target:
            target_sink = hw_target
            # print(f"Redirecting volume control to: {target_sink}")
    
    # Construct pctl command
    step = "+5%" if direction == "up" else "-5%"
    
    # pactl set-sink-volume <sink> +5%
    subprocess.run(['pactl', 'set-sink-volume', target_sink, step])
    
    # OSD / Visual Feedback
    # KDE/Standard Notification with synchronous hint to act as OSD
    try:
        # Get new volume for display
        new_vol = audio.get_sink_volume(target_sink)
        if new_vol is not None:
             # -h string:synchronous:volume makes it replace old notifications (no stacking)
             # -h int:value:XX shows progress bar on some implementations (like Plasma)
            subprocess.run([
                'notify-send',
                '-h', f'int:value:{new_vol}', 
                '-h', 'string:synchronous:volume',
                '-t', '2000', # 2 seconds
                f"Volume: {new_vol}%"
            ])
    except Exception as e:
        print(f"Error showing OSD: {e}")



def main():
    parser = argparse.ArgumentParser(description="Audio Source Switcher")
    parser.add_argument("--connect", "-c", type=str, help="Name or ID of device to switch to")
    parser.add_argument("--vol-up", action="store_true", help="Increase Volume (Smart)")
    parser.add_argument("--vol-down", action="store_true", help="Decrease Volume (Smart)")
    args = parser.parse_args()
    
    # CLI Volume Mode
    if args.vol_up:
        handle_volume_command("up")
        sys.exit(0)
    if args.vol_down:
        handle_volume_command("down")
        sys.exit(0)

    app = QApplication(sys.argv)
    app.setApplicationName("Audio Source Switcher")
    app.setApplicationDisplayName("Audio Source Switcher")
    app.setDesktopFileName("audio-source-switcher")
    
    # 1. Single Instance Check
    # Only if NOT running a connect command (we want to allow connect commands to run parallel/independent, 
    # OR we want them to just work. Actually, if main app is running, and we run CLI, 
    # we don't want to bring main app to front. We want to execute command.)
    
    if not args.connect:
        socket_name = "ag_audio_source_switcher"
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
