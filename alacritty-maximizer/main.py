import sys
import subprocess
import shutil
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton, 
                             QLabel, QListWidget, QListWidgetItem, QMessageBox)
from PyQt6.QtGui import QIcon, QScreen
from PyQt6.QtCore import Qt

class AlacrittyLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alacritty Launcher")
        self.resize(450, 350) 
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        label = QLabel("Select Launch Option:")
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(label)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        # Add "Normal Start" option
        normal_item = QListWidgetItem("Start Alacritty Normally")
        normal_item.setData(Qt.ItemDataRole.UserRole, "normal")
        self.list_widget.addItem(normal_item)
        
        # Detect Screens and Generate Descriptions
        screens = QApplication.screens()
        
        # Sort screens by x position to help with "Left", "Right" labels
        # Create a list of (index, screen) tuples
        indexed_screens = list(enumerate(screens))
        indexed_screens.sort(key=lambda s: s[1].geometry().x())
        
        # Determine total valid bounds to guess relative positions
        xs = [s[1].geometry().x() for s in indexed_screens]
        min_x = min(xs) if xs else 0
        max_x = max(xs) if xs else 0
        
        for i, screen in indexed_screens:
            # i is the index in QApplication.screens(), which aligns with our rule installer logic
            
            size = screen.size()
            width = size.width()
            height = size.height()
            
            # 1. Orientation
            if height > width:
                orientation = "Vertical"
            else:
                orientation = "Landscape"
            
            # 2. Position Description
            # Simple heuristic for 2 monitors:
            geo = screen.geometry()
            x = geo.x()
            y = geo.y()
            
            pos_desc = ""
            if len(screens) > 1:
                if x == min_x:
                    pos_desc = " (Left)"
                elif x == max_x: # If they overlap or strictly ordered
                    pos_desc = " (Right)"
                else:
                    pos_desc = " (Center)"
            
            # 3. Primary? (Usually info not easily available cross-platform in simple PyQT without platform extras, skipping for now)

            # Combined Label
            # e.g. "Vertical Monitor (Left) - 1440x2560"
            text = f"{orientation} Monitor{pos_desc} - {width}x{height}"
            
            # Add Monitor Index for clarity if needed, but user wanted plain English
            # Maybe small text?
            # Let's just stick to the descriptive text.
            
            item = QListWidgetItem(text)
            # Store the coordinates which are stable
            item.setData(Qt.ItemDataRole.UserRole, f"pos-{x}_{y}")
            self.list_widget.addItem(item)

        # Select first item by default
        self.list_widget.setCurrentRow(0)

        # Buttons
        launch_btn = QPushButton("Launch")
        launch_btn.clicked.connect(self.launch)
        # Make default button
        launch_btn.setDefault(True)
        layout.addWidget(launch_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        layout.addWidget(cancel_btn)
        
        # Double click to launch
        self.list_widget.itemDoubleClicked.connect(self.launch)

    def launch(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)
        
        # Check if alacritty is in path
        alacritty_path = shutil.which("alacritty")
        if not alacritty_path:
            QMessageBox.critical(self, "Error", "Could not find 'alacritty' in PATH.\nPlease ensure it is installed.")
            return

        cmd = [alacritty_path]
        
        if data == "normal":
            # Just run alacritty
            pass
        elif data.startswith("pos-"):
            # Format: pos-X_Y
            try:
                coords = data.removeprefix("pos-")
                # Launch with specific class to trigger KWin rule
                # --class <instance>,<general>
                # KWin Rule is looking for wmclass=alacritty-pos-X_Y
                instance_name = f"alacritty-pos-{coords}"
                cmd.extend(["--class", f"{instance_name},{instance_name}"])
            except (ValueError, IndexError) as e:
                QMessageBox.critical(self, "Error", f"Invalid monitor data: {data}\n{e}")
                return
            except NameError as e:
                 QMessageBox.critical(self, "Bug", f"Internal Error: {e}")
                 return

        print(f"Launching: {' '.join(cmd)}")
        try:
            # Popen to detach
            subprocess.Popen(cmd, start_new_session=True)
            self.close()
        except OSError as e:
            QMessageBox.critical(self, "Launch Error", f"Failed to execute alacritty:\n{e}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred:\n{e}")

def main():
    app = QApplication(sys.argv)
    window = AlacrittyLauncher()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
