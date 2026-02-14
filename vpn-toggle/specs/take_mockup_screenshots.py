#!/usr/bin/env python3
"""Take screenshots of both mockup layouts for spec documentation."""
import sys
import os

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer

# Add parent to path so mockups can be imported
sys.path.insert(0, os.path.dirname(__file__))

from mockup_current_layout import MockCurrentWindow
from mockup_new_layout import MockNewWindow

SPECS_DIR = os.path.dirname(os.path.abspath(__file__))


def capture_window(window, filename):
    """Capture a window to a PNG file."""
    filepath = os.path.join(SPECS_DIR, filename)
    pixmap = window.grab()
    pixmap.save(filepath, "PNG")
    print(f"Saved: {filepath}")


def main():
    app = QApplication(sys.argv)

    current_win = MockCurrentWindow()
    current_win.show()

    new_win = MockNewWindow()
    new_win.show()

    def take_screenshots():
        capture_window(current_win, "mockup-current-layout.png")
        capture_window(new_win, "mockup-new-layout.png")
        print("Done. Closing.")
        app.quit()

    # Wait 500ms for windows to fully render before capturing
    QTimer.singleShot(500, take_screenshots)
    app.exec()


if __name__ == "__main__":
    main()
