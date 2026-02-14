#!/usr/bin/env python3
import sys
import argparse
from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont


class BlueScreenOfDelight(QWidget):
    """Easter egg: a Windows-style 'Blue Screen of Delight' overlay."""

    BSOD_TEXT = (
        "Your PC ran into a problem and has joined the choir invisible. "
        "It's Microsoft's fault, so install Linux instead.\n\n"
        "-100% (estimated time: approximate heat death of the universe)\n\n"
    )
    STOP_CODE = "STOP CODE: CRITICAL_PROCESS_HATES_YOU"

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setAutoFillBackground(True)
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#0078d7"))
        self.setPalette(palette)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(100, 100, 100, 100)
        layout.setSpacing(0)

        face = QLabel(":)")
        face.setFont(QFont("Segoe UI", 120))
        face.setStyleSheet("color: white; background: transparent;")
        layout.addWidget(face)

        layout.addSpacing(30)

        body = QLabel(self.BSOD_TEXT)
        body.setFont(QFont("Segoe UI", 22))
        body.setStyleSheet("color: white; background: transparent;")
        body.setWordWrap(True)
        body.setMaximumWidth(800)
        layout.addWidget(body)

        stop = QLabel(self.STOP_CODE)
        stop.setFont(QFont("Segoe UI", 14))
        stop.setStyleSheet("color: rgba(255,255,255,0.8); background: transparent;")
        layout.addWidget(stop)

        layout.addStretch()

        self.setCursor(Qt.CursorShape.BlankCursor)
        self.hide()

class FakeScreensaver(QWidget):
    def __init__(self, screen_index, app_ref):
        super().__init__()
        self.target_screen_index = screen_index
        self.app_ref = app_ref # Keep reference to app to quit all windows
        self.initUI()

    def initUI(self):
        # Set background to black
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('black'))
        self.setPalette(palette)
        
        screens = QApplication.screens()
        selected_screen = None
        
        if 0 <= self.target_screen_index < len(screens):
            selected_screen = screens[self.target_screen_index]
        else:
            print(f"Error: Screen index {self.target_screen_index} out of range.")
            self.close()
            return

        if selected_screen:
            # Important: setGeometry first, then setScreen, then showFullScreen
            self.setGeometry(selected_screen.geometry())
            self.setScreen(selected_screen)
            self.showFullScreen()
            print(f"Blanking screen {self.target_screen_index}: {selected_screen.name()}")
        
        # Keep cursor visible (explicitly set)
        self.setCursor(Qt.CursorShape.ArrowCursor)

        # Setup reminder label
        self.label = QLabel("Press ESC to exit", self)
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label.setFont(QFont("Arial", 48, QFont.Weight.Bold))
        self.label.setStyleSheet("color: white; background-color: transparent;")
        self.label.hide()
        
        # Center the label
        self.label.resize(self.width(), 200)
        self.label.move(0, (self.height() - self.label.height()) // 2)

        # Timer to hide label
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.label.hide)

        # Easter egg: Blue Screen of Delight overlay
        self.bsod = BlueScreenOfDelight(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'bsod'):
            self.bsod.setGeometry(0, 0, self.width(), self.height())

    def mousePressEvent(self, event):
        if self.bsod.isVisible():
            return
        # Show reminder on click
        self.label.resize(self.width(), 200)
        self.label.move(0, (self.height() - self.label.height()) // 2)
        self.label.show()
        self.hide_timer.start(2000) # Hide after 2 seconds

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.app_ref.quit()
        elif event.key() == Qt.Key.Key_B:
            self._toggle_bsod()

    def _toggle_bsod(self):
        if self.bsod.isVisible():
            self.bsod.hide()
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            self.bsod.setGeometry(0, 0, self.width(), self.height())
            self.bsod.show()
            self.bsod.raise_()
            self.label.hide()
            self.setCursor(Qt.CursorShape.BlankCursor)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Fake Screensaver")
    parser.add_argument('--screen', type=int, nargs='*', help="Index of the screen(s) to display on. Default: All screens.")
    args = parser.parse_args()

    app = QApplication(sys.argv)
    
    screens = QApplication.screens()
    print(f"Available screens ({len(screens)}):")
    for i, s in enumerate(screens):
        print(f"  {i}: {s.name()} {s.geometry()}")

    target_indices = []
    if args.screen is not None and len(args.screen) > 0:
        target_indices = args.screen
    else:
        # Default to all screens
        target_indices = list(range(len(screens)))

    windows = []
    print(f"Targeting screens: {target_indices}")
    
    for idx in target_indices:
        win = FakeScreensaver(screen_index=idx, app_ref=app)
        windows.append(win)

    # If no windows created (e.g. invalid index), exit
    if not windows:
        print("No valid screens selected.")
        sys.exit(1)

    sys.exit(app.exec())
