import argparse
import subprocess
import sys

from PyQt6.QtWidgets import QApplication
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from audio_source_switcher.controllers.audio import AudioController
from audio_source_switcher.controllers.pipewire import PipeWireController
from audio_source_switcher.gui.main_window import MainWindow


def handle_volume_command(direction: str):
    """direction: 'up' or 'down'. Bypasses standard volume control to handle JamesDSP."""
    audio = AudioController()
    pw = PipeWireController()

    default = audio.get_default_sink()
    target_sink = default

    if default == "jamesdsp_sink":
        hw_target = pw.get_jamesdsp_target()
        if hw_target:
            target_sink = hw_target

    step = "+5%" if direction == "up" else "-5%"
    subprocess.run(['pactl', 'set-sink-volume', target_sink, step])

    try:
        new_vol = audio.get_sink_volume(target_sink)
        if new_vol is not None:
            subprocess.run([
                'notify-send',
                '-h', f'int:value:{new_vol}',
                '-h', 'string:synchronous:volume',
                '-t', '2000',
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
        socket_name = "ag_audio_source_switcher"
        socket = QLocalSocket()
        socket.connectToServer(socket_name)

        if socket.waitForConnected(500):
            print("Application already running. Bringing to front.")
            socket.write(b"SHOW")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            sys.exit(0)

        QLocalServer.removeServer(socket_name)
        server = QLocalServer()
        if not server.listen(socket_name):
            print(f"Warning: Could not start local server on {socket_name}.")

    window = MainWindow(target_device=args.connect)

    if not args.connect:
        def handle_new_connection():
            client_socket = server.nextPendingConnection()
            if not client_socket:
                return
            client_socket.waitForReadyRead(1000)
            data = client_socket.readAll().data()
            if b"SHOW" in data:
                window.show_window()
            client_socket.disconnectFromServer()
        server.newConnection.connect(handle_new_connection)

        window.show()

    sys.exit(app.exec())
