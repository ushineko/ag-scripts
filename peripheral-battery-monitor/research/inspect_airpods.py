import dbus
import json

def walk(obj):
    try:
        if isinstance(obj, dbus.Boolean):
            return bool(obj)
        if isinstance(obj, (dbus.Int16, dbus.UInt16, dbus.Int32, dbus.UInt32, dbus.Int64, dbus.UInt64)):
            return int(obj)
        if isinstance(obj, dbus.Byte):
            return int(obj)
        if isinstance(obj, dbus.String):
            return str(obj)
        if isinstance(obj, dbus.Double):
            return float(obj)
        if isinstance(obj, dbus.ObjectPath):
            return str(obj)
        if isinstance(obj, dbus.Array):
            return [walk(x) for x in obj]
        if isinstance(obj, dbus.Dictionary):
            return {walk(k): walk(v) for k, v in obj.items()}
        return str(obj)
    except Exception:
        return str(obj)

bus = dbus.SystemBus()
manager = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
objects = manager.GetManagedObjects()

target_mac = "30:7A:D2:30:CB:AD"
device_path = None

for path, ifaces in objects.items():
    if "org.bluez.Device1" in ifaces:
        props = ifaces["org.bluez.Device1"]
        if props.get("Address") == target_mac:
            print(f"Found Device: {path}")
            print(json.dumps(walk(ifaces), indent=2))
            device_path = path

if not device_path:
    print("Device not found")
