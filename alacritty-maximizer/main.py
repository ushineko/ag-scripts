import argparse
import sys
import subprocess
import shutil
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QLabel, QListWidget, QListWidgetItem, QMessageBox,
                             QCheckBox, QHBoxLayout)
from PyQt6.QtCore import Qt

from config import (get_default_monitor, set_default_monitor, clear_default_monitor,
                     is_autostart_enabled, set_autostart, install_autostart_entry,
                     remove_autostart_entry)

__version__ = "2.1.0"


def get_screen_positions(app: QApplication) -> list[dict]:
    screens = app.screens()
    indexed_screens = list(enumerate(screens))
    indexed_screens.sort(key=lambda s: s[1].geometry().x())

    xs = [s[1].geometry().x() for s in indexed_screens]
    min_x = min(xs) if xs else 0
    max_x = max(xs) if xs else 0

    result = []
    for _i, screen in indexed_screens:
        size = screen.size()
        width = size.width()
        height = size.height()

        orientation = "Vertical" if height > width else "Landscape"

        geo = screen.geometry()
        x = geo.x()
        y = geo.y()

        pos_desc = ""
        if len(screens) > 1:
            if x == min_x:
                pos_desc = " (Left)"
            elif x == max_x:
                pos_desc = " (Right)"
            else:
                pos_desc = " (Center)"

        text = f"{orientation} Monitor{pos_desc} - {width}x{height}"
        position_id = f"pos-{x}_{y}"
        result.append({"text": text, "position_id": position_id})

    return result


def launch_alacritty(position_id: str | None) -> bool:
    alacritty_path = shutil.which("alacritty")
    if not alacritty_path:
        return False

    cmd = [alacritty_path]

    if position_id and position_id.startswith("pos-"):
        coords = position_id.removeprefix("pos-")
        instance_name = f"alacritty-pos-{coords}"
        cmd.extend(["--class", f"{instance_name},{instance_name}"])

    print(f"Launching: {' '.join(cmd)}")
    subprocess.Popen(cmd, start_new_session=True)
    return True


class AlacrittyLauncher(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Alacritty Launcher")
        self.resize(450, 400)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        self.setLayout(layout)

        label = QLabel("Select Launch Option:")
        label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(label)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget)

        normal_item = QListWidgetItem("Start Alacritty Normally")
        normal_item.setData(Qt.ItemDataRole.UserRole, "normal")
        self.list_widget.addItem(normal_item)

        screens = get_screen_positions(QApplication.instance())
        current_default = get_default_monitor()

        for screen_info in screens:
            text = screen_info["text"]
            if screen_info["position_id"] == current_default:
                text += "  [default]"
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, screen_info["position_id"])
            self.list_widget.addItem(item)

        self.list_widget.setCurrentRow(0)

        self.default_checkbox = QCheckBox("Save as default (auto-launch next time)")
        layout.addWidget(self.default_checkbox)

        self.autostart_checkbox = QCheckBox("Launch on login (KDE autostart)")
        self.autostart_checkbox.setChecked(is_autostart_enabled())
        layout.addWidget(self.autostart_checkbox)

        btn_layout = QHBoxLayout()

        launch_btn = QPushButton("Launch")
        launch_btn.clicked.connect(self.launch)
        launch_btn.setDefault(True)
        btn_layout.addWidget(launch_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        if current_default:
            clear_btn = QPushButton("Clear Default")
            clear_btn.clicked.connect(self.clear_default)
            layout.addWidget(clear_btn)

        self.list_widget.itemDoubleClicked.connect(self.launch)

    def launch(self):
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        item = selected_items[0]
        data = item.data(Qt.ItemDataRole.UserRole)

        alacritty_path = shutil.which("alacritty")
        if not alacritty_path:
            QMessageBox.critical(self, "Error", "Could not find 'alacritty' in PATH.\nPlease ensure it is installed.")
            return

        position_id = data if data != "normal" else None

        if self.default_checkbox.isChecked():
            if position_id:
                set_default_monitor(position_id)
                print(f"Saved default monitor: {position_id}")
            else:
                clear_default_monitor()
                print("Cleared default monitor (normal mode selected)")

        main_script = str(Path(__file__).resolve())
        if self.autostart_checkbox.isChecked():
            set_autostart(True)
            install_autostart_entry(main_script)
            print("Autostart enabled")
        else:
            set_autostart(False)
            remove_autostart_entry()
            print("Autostart disabled")

        if not launch_alacritty(position_id):
            QMessageBox.critical(self, "Error", "Could not find 'alacritty' in PATH.\nPlease ensure it is installed.")
            return

        self.close()

    def clear_default(self):
        clear_default_monitor()
        QMessageBox.information(self, "Default Cleared", "Default monitor cleared. The GUI will show on next launch.")
        self.close()
        # Reopen to refresh the UI
        window = AlacrittyLauncher()
        window.show()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Alacritty Maximizer - launch Alacritty on a specific monitor")
    parser.add_argument("--choose", action="store_true", help="Show monitor selection GUI even if a default is saved")
    parser.add_argument("--clear-default", action="store_true", help="Clear the saved default monitor and exit")
    parser.add_argument("--autostart", action="store_true", help="Session autostart mode: launch default monitor silently, exit if none saved")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser.parse_args()


def main():
    args = parse_args()

    app = QApplication(sys.argv)

    if args.clear_default:
        clear_default_monitor()
        print("Default monitor cleared.")
        return

    if args.autostart:
        default = get_default_monitor()
        if not default:
            return
        screens = get_screen_positions(app)
        valid_ids = {s["position_id"] for s in screens}
        if default in valid_ids:
            launch_alacritty(default)
        return

    if not args.choose:
        default = get_default_monitor()
        if default:
            screens = get_screen_positions(app)
            valid_ids = {s["position_id"] for s in screens}
            if default in valid_ids:
                if launch_alacritty(default):
                    return
                else:
                    print("alacritty not found in PATH, falling back to GUI")
            else:
                print(f"Saved default '{default}' does not match any current monitor, showing GUI")

    window = AlacrittyLauncher()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
