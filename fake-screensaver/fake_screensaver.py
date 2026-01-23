#!/usr/bin/env python3
import sys
from PyQt6.QtWidgets import QApplication, QWidget
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPalette, QColor

class FakeScreensaver(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        # Set background to black
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor('black'))
        self.setPalette(palette)
        
        # Enable fullscreen
        self.showFullScreen()
        
        # keep cursor visible - this is default behavior, but explicit is fine too if needed.
        # existing blank.html hid it, user requested NOT to hide it here.
        self.setCursor(Qt.CursorShape.ArrowCursor)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.close()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    ex = FakeScreensaver()
    sys.exit(app.exec())
