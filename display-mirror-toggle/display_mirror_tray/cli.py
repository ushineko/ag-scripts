"""Entry point for the display-mirror-toggle tray.

Single-instance via QLocalSocket — re-running raises the existing tray
to the foreground instead of starting a second copy. The original
display-mirror-toggle.sh remains the canonical CLI; this entry point
only spawns the GUI.
"""

from __future__ import annotations

import argparse
import logging
import sys

from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from . import __version__
from .tray import TrayApp

SINGLE_INSTANCE_SOCKET = "display-mirror-tray"


def _setup_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="display-mirror-tray",
        description="System-tray frontend for display-mirror-toggle.",
    )
    parser.add_argument(
        "--version", action="version",
        version=f"display-mirror-tray v{__version__}",
    )
    parser.add_argument("--debug", action="store_true", help="Verbose logging.")
    args = parser.parse_args()

    _setup_logging(args.debug)

    app = QApplication(sys.argv)
    app.setApplicationName("Display Mirror Toggle")
    app.setApplicationVersion(__version__)
    app.setDesktopFileName("display-mirror-toggle")
    app.setQuitOnLastWindowClosed(False)

    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SOCKET)
    if socket.waitForConnected(500):
        socket.write(b"ping")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        print("display-mirror-tray already running.", file=sys.stderr)
        return 0
    socket.deleteLater()

    QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
    server = QLocalServer(app)
    if not server.listen(SINGLE_INSTANCE_SOCKET):
        logging.warning(
            f"Could not bind single-instance socket: {server.errorString()}"
        )

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            "System tray unavailable",
            "No system tray detected. display-mirror-tray needs an active "
            "system-tray host (e.g. KDE Plasma's panel).",
        )
        return 1

    tray = TrayApp(app)
    tray.start()

    # Bring-to-front on second-launch ping has no real "window" to raise
    # for a pure tray app — show a balloon so the user sees something.
    def _on_new_connection() -> None:
        conn = server.nextPendingConnection()
        if conn is None:
            return
        conn.readAll()
        conn.disconnectFromServer()
        tray.tray.showMessage(
            "Display Mirror Toggle",
            "Already running in the system tray.",
            QSystemTrayIcon.MessageIcon.Information,
            2500,
        )

    server.newConnection.connect(_on_new_connection)

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
