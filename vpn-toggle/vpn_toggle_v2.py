#!/usr/bin/env python3
"""
VPN Toggle v3.2 - Integrated VPN Manager and Monitor

Main entry point for the application.
"""
import sys
import argparse

from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from vpn_toggle import __version__
from vpn_toggle.config import ConfigManager
from vpn_toggle.vpn_manager import VPNManager
from vpn_toggle.gui import VPNToggleMainWindow
from vpn_toggle.utils import setup_logging

SINGLE_INSTANCE_SOCKET = "vpn-toggle-v2"


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="VPN Toggle v2.0 - Integrated VPN Manager and Monitor",
        epilog="For more information, see the README.md file."
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file (default: ~/.config/vpn-toggle/config.json)'
    )
    parser.add_argument(
        '--version',
        action='version',
        version=f'VPN Toggle v{__version__}'
    )
    parser.add_argument(
        '--minimized',
        action='store_true',
        help='Start minimized to system tray (window hidden)'
    )
    # Legacy compatibility: accept VPN name argument but ignore it
    parser.add_argument(
        'vpn_name',
        nargs='?',
        help='(Legacy - ignored) VPN name for backward compatibility'
    )

    args = parser.parse_args()

    # Setup logging
    log_level = "DEBUG" if args.debug else "INFO"
    logger = setup_logging(level=log_level)

    # Inform about legacy argument
    if args.vpn_name:
        logger.info(
            f"Legacy argument '{args.vpn_name}' provided but ignored. "
            "v2.0 displays all VPNs in the GUI."
        )
        print(f"Note: VPN Toggle v2.0 shows all VPNs. The argument '{args.vpn_name}' is ignored.")

    try:
        # Initialize components
        logger.info("Initializing VPN Toggle v2.0")
        config_manager = ConfigManager(args.config)
        vpn_manager = VPNManager()

        # Start GUI
        app = QApplication(sys.argv)
        app.setApplicationName("VPN Toggle")
        app.setApplicationVersion(__version__)
        app.setDesktopFileName("vpn-toggle-v2")

        # Single-instance guard: check if already running
        socket = QLocalSocket()
        socket.connectToServer(SINGLE_INSTANCE_SOCKET)
        if socket.waitForConnected(500):
            socket.write(b"show")
            socket.waitForBytesWritten(1000)
            socket.disconnectFromServer()
            logger.info("Another instance is already running, activating it")
            print("VPN Toggle is already running. Bringing existing window to front.")
            sys.exit(0)
        socket.deleteLater()

        # Create single-instance server
        server = QLocalServer(app)
        QLocalServer.removeServer(SINGLE_INSTANCE_SOCKET)
        if not server.listen(SINGLE_INSTANCE_SOCKET):
            logger.warning(f"Could not create single-instance server: {server.errorString()}")

        # Set application icon - render SVG to pixmaps for reliable display
        # Resolve symlinks so icon path is correct when launched via ~/.local/bin symlink
        icon = QIcon()
        icon_path = Path(__file__).resolve().parent / "vpn_toggle" / "icon.svg"
        if icon_path.exists():
            renderer = QSvgRenderer(str(icon_path))
            for size in (16, 22, 24, 32, 48, 64, 128):
                pixmap = QPixmap(QSize(size, size))
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()
                icon.addPixmap(pixmap)
            app.setWindowIcon(icon)

        window = VPNToggleMainWindow(
            config_manager, vpn_manager, app_icon=icon,
            icon_path=icon_path if icon_path.exists() else None,
            start_minimized=args.minimized,
        )

        # Connect single-instance server to bring window to front
        def handle_new_connection():
            conn = server.nextPendingConnection()
            if conn:
                window.show()
                window.raise_()
                window.activateWindow()
                conn.deleteLater()

        server.newConnection.connect(handle_new_connection)

        if not args.minimized:
            window.show()

        logger.info("VPN Toggle v3.2 started")
        sys.exit(app.exec())

    except RuntimeError as e:
        logger.error(f"Initialization error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        print("\nPlease ensure NetworkManager is installed and running.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
