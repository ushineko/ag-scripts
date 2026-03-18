import json
import re
import subprocess

from audio_source_switcher.controllers.headset import HeadsetController


class AudioController:
    """Handles interactions with the system audio via pactl."""

    LOOPBACK_SERVICE = "audio-loopback.service"

    def __init__(self):
        self.headset = HeadsetController()
        self._loopback_process = None  # Direct pw-loopback subprocess (tier 2)

    @staticmethod
    def run_command(args: list[str], ignore_errors: bool = False) -> str | None:
        try:
            result = subprocess.run(args, capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            if not ignore_errors:
                print(f"Error running command {args}: {e}")
            return None

    def get_sinks(self, bt_cache: dict | None = None) -> list[dict]:
        """Returns a list of sinks with smart naming.
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

            display_name = self._resolve_display_name(name, props, bt_cache)
            display_name = self._append_headset_status(display_name)
            display_name, is_physically_available = self._append_port_info(display_name, ports, active_port_name)
            priority_id = self._compute_priority_id(name)

            sinks.append({
                'name': name,
                'priority_id': priority_id,
                'display_name': display_name,
                'is_default': (name == default_sink),
                'connected': "[Disconnected]" not in display_name,
                'properties': props
            })
        return sinks

    def _resolve_display_name(self, name: str, props: dict, bt_cache: dict | None) -> str:
        display_name = ""

        # 1. Try BT Cache/Alias
        if 'bluez' in name or 'bluez' in props.get('device.api', ''):
            mac_match = re.search(
                r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})',
                name, re.IGNORECASE
            )
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

        return display_name

    def _append_headset_status(self, display_name: str) -> str:
        if "Arctis Nova" in display_name or "SteelSeries" in display_name:
            status = self.headset.get_battery_status()
            if status:
                display_name += f" [{status}]"
            else:
                display_name += " [Disconnected]"
        return display_name

    def _append_port_info(self, display_name: str, ports: list, active_port_name: str | None) -> tuple[str, bool]:
        active_port_desc = ""
        is_physically_available = True

        if active_port_name and ports:
            for port in ports:
                if port['name'] == active_port_name:
                    active_port_desc = port.get('description', active_port_name)
                    availability = port.get('availability', 'unknown')
                    if availability == 'not available':
                        is_physically_available = False
                    break

        if active_port_desc and active_port_desc != "Analog Output":
            display_name += f" - {active_port_desc}"

        if not is_physically_available and "[Disconnected]" not in display_name:
            display_name += " [Disconnected]"

        return display_name, is_physically_available

    def _compute_priority_id(self, name: str) -> str:
        mac_match = re.search(
            r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})',
            name, re.IGNORECASE
        )
        if mac_match:
            found_mac = mac_match.group(1).replace('_', ':').upper()
            return f"bt:{found_mac}"
        return name

    def get_default_sink(self) -> str | None:
        return self.run_command(['pactl', 'get-default-sink'])

    def set_default_sink(self, sink_name: str):
        self.run_command(['pactl', 'set-default-sink', sink_name])

    def move_input_streams(self, sink_name: str):
        output = self.run_command(['pactl', 'list', 'short', 'sink-inputs'])
        if not output:
            return
        for line in output.split('\n'):
            if line.strip():
                parts = line.split()
                if parts:
                    self.run_command(['pactl', 'move-sink-input', parts[0], sink_name], ignore_errors=True)

    def get_sink_volume(self, sink_name: str) -> int | None:
        """Returns the volume percentage (integer) of the sink, or None if failed."""
        try:
            output = self.run_command(['pactl', 'get-sink-volume', sink_name])
            if not output:
                return None
            match = re.search(r'(\d+)%', output)
            if match:
                return int(match.group(1))
            return None
        except Exception as e:
            print(f"Error getting volume for {sink_name}: {e}")
            return None

    def set_sink_volume(self, sink_name: str, volume_percent: int):
        """Sets sink volume to specific percentage."""
        volume_percent = max(0, min(150, volume_percent))
        self.run_command(['pactl', 'set-sink-volume', sink_name, f"{volume_percent}%"])

    def get_line_in_source(self) -> str | None:
        """Finds the Line-In source name dynamically by port type."""
        json_output = self.run_command(['pactl', '--format=json', 'list', 'sources'])
        if not json_output:
            return None
        try:
            sources = json.loads(json_output)
        except json.JSONDecodeError:
            return None
        for source in sources:
            name = source.get('name', '')
            if '.monitor' in name:
                continue
            active_port = source.get('active_port', '')
            for port in source.get('ports', []):
                if port.get('name') == active_port and port.get('type') == 'Line':
                    return name
        return None

    def has_loopback_service(self) -> bool:
        """Check if audio-loopback.service is installed (not necessarily running)."""
        result = self.run_command(
            ['systemctl', '--user', 'cat', self.LOOPBACK_SERVICE],
            ignore_errors=True
        )
        return result is not None

    def get_loopback_state(self, source_name: str) -> tuple[bool, str | None]:
        """Returns (is_active, mode) where mode is 'service', 'direct', or None."""
        if not source_name:
            return (False, None)

        # Tier 1: check systemd service
        if self.has_loopback_service():
            result = self.run_command(
                ['systemctl', '--user', 'is-active', self.LOOPBACK_SERVICE],
                ignore_errors=True
            )
            is_active = result and result.strip() == 'active'
            return (is_active, 'service')

        # Tier 2: check direct pw-loopback process
        if self._loopback_process and self._loopback_process.poll() is None:
            return (True, 'direct')

        return (False, 'direct')

    def _get_loopback_target_sink(self) -> str:
        """Determine the best sink for pw-loopback: JamesDSP if present, else default."""
        sinks = self.run_command(['pactl', '--format=json', 'list', 'short', 'sinks'])
        if sinks:
            try:
                for sink in json.loads(sinks):
                    if 'jamesdsp' in sink.get('name', '').lower():
                        return sink['name']
            except (json.JSONDecodeError, KeyError):
                pass
        return '@DEFAULT_SINK@'

    def set_loopback_state(self, enable: bool, source_name: str):
        is_active, mode = self.get_loopback_state(source_name)

        if enable and not is_active:
            if mode == 'service':
                print(f"Starting {self.LOOPBACK_SERVICE} for {source_name}")
                self.run_command(['systemctl', '--user', 'start', self.LOOPBACK_SERVICE])
            else:
                target_sink = self._get_loopback_target_sink()
                print(f"Starting pw-loopback: {source_name} -> {target_sink}")
                self._loopback_process = subprocess.Popen(
                    ['pw-loopback', '-C', source_name, '-P', target_sink],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )

        elif not enable and is_active:
            if mode == 'service':
                print(f"Stopping {self.LOOPBACK_SERVICE}")
                self.run_command(['systemctl', '--user', 'stop', self.LOOPBACK_SERVICE])
            else:
                print("Stopping direct pw-loopback")
                self.cleanup_loopback()

    def cleanup_loopback(self):
        """Kill any direct pw-loopback subprocess. Safe to call multiple times."""
        if self._loopback_process and self._loopback_process.poll() is None:
            self._loopback_process.terminate()
            try:
                self._loopback_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._loopback_process.kill()
        self._loopback_process = None

    def get_sources(self, bt_cache: dict | None = None) -> list[dict]:
        """Returns a list of source dicts."""
        json_output = self.run_command(['pactl', '--format=json', 'list', 'sources'])
        if not json_output:
            return []

        try:
            sources_data = json.loads(json_output)
        except json.JSONDecodeError:
            return []

        sources = []
        for src in sources_data:
            name = src.get('name', '')
            props = src.get('properties', {})
            if props.get('device.class') == 'monitor':
                continue

            display_name = self._resolve_source_display_name(name, props, bt_cache)
            sources.append({
                'name': name,
                'display_name': display_name,
                'properties': props
            })
        return sources

    def _resolve_source_display_name(self, name: str, props: dict, bt_cache: dict | None) -> str:
        display_name = ""

        # 1. Try BT Cache/Alias for Sources
        if 'bluez' in name or 'bluez' in props.get('device.api', ''):
            mac_match = re.search(
                r'([0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2}[:_][0-9A-F]{2})',
                name, re.IGNORECASE
            )
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

        if display_name:
            display_name = display_name.replace("(null)", "").strip()

        if not display_name:
            vendor = props.get('device.vendor.name', '')
            product = props.get('device.product.name', props.get('device.model', ''))
            if vendor and product:
                display_name = f"{vendor} {product}"

        if not display_name:
            display_name = name

        return display_name

    def set_default_source(self, source_name: str):
        self.run_command(['pactl', 'set-default-source', source_name])

    def find_associated_source(self, sink_props: dict, sources: list[dict]) -> dict | None:
        """Tries to find a source that matches the sink properties (Same Card / Serial)."""
        sink_bluez_addr = sink_props.get('api.bluez5.address')
        sink_serial = sink_props.get('device.serial')
        sink_bus = sink_props.get('device.bus_path')
        sink_device_name = sink_props.get('device.name')
        sink_card = sink_props.get('alsa.card')

        # Priority order: BlueZ address > Serial > Bus path > Device name > ALSA card
        match_keys = [
            ('api.bluez5.address', sink_bluez_addr),
            ('device.serial', sink_serial),
            ('device.bus_path', sink_bus),
            ('device.name', sink_device_name),
            ('alsa.card', sink_card),
        ]

        for prop_key, sink_value in match_keys:
            if not sink_value:
                continue
            for src in sources:
                if src['properties'].get(prop_key) == sink_value:
                    return src

        return None
