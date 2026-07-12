import argparse
import subprocess
import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from audio_source_switcher.controllers.audio import AudioController
from audio_source_switcher.controllers.pipewire import PipeWireController
from audio_source_switcher.gui.main_window import MainWindow
from audio_source_switcher.volume import adjust_volume

SOCKET_NAME = "ag_audio_source_switcher"


def _forward_to_instance(message: bytes) -> bool:
    """Send a one-shot message to a running instance. Returns True if delivered.

    Requires a QCoreApplication to exist for QLocalSocket's event handling.
    """
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if not socket.waitForConnected(300):
        return False
    socket.write(message)
    socket.waitForBytesWritten(500)
    socket.disconnectFromServer()
    return True


def handle_volume_command(direction: str):
    """direction: 'up' or 'down'.

    Prefers the running instance (which shows the OSD). Falls back to an inline
    smart volume change + notify-send when no instance is running.
    """
    # QCoreApplication is required for QLocalSocket; lighter than a GUI QApplication.
    _app = QCoreApplication(sys.argv)

    msg = b"VOL_UP" if direction == "up" else b"VOL_DOWN"
    if _forward_to_instance(msg):
        return

    # Fallback: no instance running. Apply the change inline and use notify-send.
    audio = AudioController()
    pw = PipeWireController()
    _target, new_vol, _muted = adjust_volume(audio, pw, direction)

    if new_vol is not None:
        subprocess.run([
            'notify-send',
            '-h', f'int:value:{new_vol}',
            '-h', 'string:synchronous:volume',
            '-t', '2000',
            f"Volume: {new_vol}%"
        ])


def main():
    parser = argparse.ArgumentParser(description="Audio Source Switcher")
    parser.add_argument("--connect", "-c", type=str, help="Name or ID of device to switch to")
    parser.add_argument("--vol-up", action="store_true", help="Increase Volume (Smart)")
    parser.add_argument("--vol-down", action="store_true", help="Decrease Volume (Smart)")
    args = parser.parse_args()

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

    # Single Instance Check (only for GUI mode, not --connect)
    if not args.connect:
        socket = QLocalSocket()
        socket.connectToServer(SOCKET_NAME)

        if socket.waitForConnected(500):
            print("Application already running. Bringing to front.")
            socket.write(b"SHOW")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            sys.exit(0)

        QLocalServer.removeServer(SOCKET_NAME)
        server = QLocalServer()
        if not server.listen(SOCKET_NAME):
            print(f"Warning: Could not start local server on {SOCKET_NAME}.")

    window = MainWindow(target_device=args.connect)

    if not args.connect:
        def handle_new_connection():
            client_socket = server.nextPendingConnection()
            if not client_socket:
                return
            client_socket.waitForReadyRead(1000)
            data = client_socket.readAll().data()
            if b"VOL_UP" in data:
                window.handle_volume_hotkey("up")
            elif b"VOL_DOWN" in data:
                window.handle_volume_hotkey("down")
            elif b"SHOW" in data:
                window.show_window()
            client_socket.disconnectFromServer()
        server.newConnection.connect(handle_new_connection)

        window.show()

    sys.exit(app.exec())
