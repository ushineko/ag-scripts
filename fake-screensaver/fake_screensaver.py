#!/usr/bin/env python3
import sys
import argparse
from PyQt6.QtWidgets import QApplication, QWidget, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor, QCursor, QFont

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

    def mousePressEvent(self, event):
        # Show reminder on click
        self.label.resize(self.width(), 200) # Ensure it spans full width if window resized (less relevant for fullscreen but good practice)
        self.label.move(0, (self.height() - self.label.height()) // 2)
        self.label.show()
        self.hide_timer.start(2000) # Hide after 2 seconds

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            # Close all windows
            self.app_ref.quit()

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
