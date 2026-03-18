import dbus
from PyQt6.QtCore import QThread, pyqtSignal


class ConnectThread(QThread):
    """Async Bluetooth device connection via D-Bus."""

    finished_signal = pyqtSignal(bool, str)

    def __init__(self, mac: str):
        super().__init__()
        self.mac = mac

    def run(self):
        try:
            bus = dbus.SystemBus()
            dev_path = f"/org/bluez/hci0/dev_{self.mac.replace(':', '_')}"
            device = dbus.Interface(
                bus.get_object('org.bluez', dev_path),
                'org.bluez.Device1'
            )
            device.Connect()
            self.finished_signal.emit(True, "Connection command sent.")
        except dbus.exceptions.DBusException as e:
            self.finished_signal.emit(False, f"Connection failed: {e.get_dbus_message()}")
        except Exception as e:
            self.finished_signal.emit(False, str(e))


class BluetoothController:
    """Handles interaction with BlueZ entirely via D-Bus (org.bluez.Device1)."""

    AUDIO_UUIDS = {
        '0000110b-0000-1000-8000-00805f9b34fb',  # Audio Sink
        '0000110a-0000-1000-8000-00805f9b34fb',  # Audio Source
        '00001108-0000-1000-8000-00805f9b34fb',  # Headset
        '0000111e-0000-1000-8000-00805f9b34fb',  # Handsfree
        '0000110d-0000-1000-8000-00805f9b34fb',  # Advanced Audio Distribution
    }

    @staticmethod
    def _mac_to_path(mac: str) -> str:
        return f"/org/bluez/hci0/dev_{mac.replace(':', '_')}"

    def get_devices(self) -> list[dict]:
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

    def connect(self, mac: str):
        try:
            bus = dbus.SystemBus()
            device = dbus.Interface(
                bus.get_object('org.bluez', self._mac_to_path(mac)),
                'org.bluez.Device1'
            )
            device.Connect()
        except dbus.exceptions.DBusException:
            pass

    def disconnect(self, mac: str):
        try:
            bus = dbus.SystemBus()
            device = dbus.Interface(
                bus.get_object('org.bluez', self._mac_to_path(mac)),
                'org.bluez.Device1'
            )
            device.Disconnect()
        except dbus.exceptions.DBusException:
            pass
