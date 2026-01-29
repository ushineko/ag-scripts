#!/usr/bin/env python3
"""
Steam Desktop File Creator - Create start menu launchers for Steam games.

A PyQt6 GUI application that discovers installed Steam games across all library
folders and allows creating/removing .desktop launcher files for the start menu.
"""

import os
import re
import glob
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QLabel, QStatusBar,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

VERSION = "1.0.0"

# Steam tools/runtimes to filter out (not actual games)
FILTERED_APPIDS = {
    228980,   # Steamworks Common Redistributables
    1070560,  # Steam Linux Runtime 1.0 (scout)
    1391110,  # Steam Linux Runtime 2.0 (soldier)
    1628350,  # Steam Linux Runtime 3.0 (sniper)
    1493710,  # Proton Experimental
    2180100,  # Proton Hotfix
    961940,   # Proton 6.3
    1161040,  # Proton 5.13
    1245040,  # Proton 5.0
    1420170,  # Proton 7.0
    1887720,  # Proton 8.0
    2348590,  # Proton 9.0 (beta)
    2805730,  # Proton 9.0
}

# Paths
STEAM_ROOT = Path.home() / ".steam" / "steam"
LIBRARY_FOLDERS_VDF = STEAM_ROOT / "steamapps" / "libraryfolders.vdf"
ICON_CACHE = STEAM_ROOT / "appcache" / "librarycache"
APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
ICONS_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"


@dataclass
class SteamGame:
    """Represents an installed Steam game."""
    appid: int
    name: str
    install_dir: str
    library_path: Path

    @property
    def desktop_file_path(self) -> Path:
        return APPLICATIONS_DIR / f"steam-game-{self.appid}.desktop"

    @property
    def icon_name(self) -> str:
        return f"steam-game-{self.appid}"

    @property
    def has_desktop_file(self) -> bool:
        return self.desktop_file_path.exists()


def parse_vdf(content: str) -> dict:
    """
    Parse Valve Data Format (VDF) content into a dictionary.

    VDF is a simple key-value format used by Steam:
    "key" "value"
    "key" { nested content }
    """
    result = {}
    stack = [result]
    current_key = None

    # Tokenize: match quoted strings or braces separately
    # Using named groups to distinguish token types
    token_pattern = re.compile(r'"([^"]*)"|(\{)|(\})')

    for match in token_pattern.finditer(content):
        quoted_string, open_brace, close_brace = match.groups()

        if open_brace:
            # Start of nested dict
            new_dict = {}
            if current_key is not None:
                stack[-1][current_key] = new_dict
                stack.append(new_dict)
                current_key = None
        elif close_brace:
            # End of nested dict
            if len(stack) > 1:
                stack.pop()
            current_key = None
        elif quoted_string is not None:
            # It's a quoted string (including empty strings)
            if current_key is None:
                current_key = quoted_string
            else:
                stack[-1][current_key] = quoted_string
                current_key = None

    return result


def get_library_paths() -> list[Path]:
    """Get all Steam library paths from libraryfolders.vdf."""
    if not LIBRARY_FOLDERS_VDF.exists():
        return []

    content = LIBRARY_FOLDERS_VDF.read_text()
    data = parse_vdf(content)

    paths = []
    if 'libraryfolders' in data:
        for key, value in data['libraryfolders'].items():
            if isinstance(value, dict) and 'path' in value:
                paths.append(Path(value['path']))

    return paths


def scan_library(library_path: Path) -> list[SteamGame]:
    """Scan a Steam library for installed games."""
    games = []
    steamapps = library_path / "steamapps"

    if not steamapps.exists():
        return games

    for manifest_path in steamapps.glob("appmanifest_*.acf"):
        try:
            content = manifest_path.read_text()
            data = parse_vdf(content)

            if 'AppState' in data:
                app_state = data['AppState']
                appid = int(app_state.get('appid', 0))

                # Skip filtered apps (tools, runtimes, etc.)
                if appid in FILTERED_APPIDS:
                    continue

                name = app_state.get('name', f'Unknown ({appid})')
                install_dir = app_state.get('installdir', '')

                games.append(SteamGame(
                    appid=appid,
                    name=name,
                    install_dir=install_dir,
                    library_path=library_path
                ))
        except Exception as e:
            print(f"Error parsing {manifest_path}: {e}")

    return games


def get_all_games() -> list[SteamGame]:
    """Get all installed Steam games across all libraries."""
    games = []
    for library_path in get_library_paths():
        games.extend(scan_library(library_path))

    # Sort by name
    games.sort(key=lambda g: g.name.lower())
    return games


def get_game_icon_path(appid: int) -> Optional[Path]:
    """Get the path to a game's icon in Steam's cache."""
    # Steam stores icons as <appid>_icon.jpg
    icon_path = ICON_CACHE / f"{appid}_icon.jpg"
    if icon_path.exists():
        return icon_path
    return None


def install_game_icon(game: SteamGame) -> str:
    """Install game icon to system icons directory, return icon name."""
    source_icon = get_game_icon_path(game.appid)

    if source_icon is None:
        return "steam"  # Fallback to Steam icon

    # Ensure icons directory exists
    ICONS_DIR.mkdir(parents=True, exist_ok=True)

    dest_icon = ICONS_DIR / f"steam-game-{game.appid}.png"

    try:
        # Use Qt to convert JPG to PNG
        pixmap = QPixmap(str(source_icon))
        if not pixmap.isNull():
            pixmap.save(str(dest_icon), "PNG")
            return game.icon_name
    except Exception as e:
        print(f"Error installing icon for {game.name}: {e}")

    return "steam"


def remove_game_icon(game: SteamGame) -> None:
    """Remove game icon from system icons directory."""
    icon_path = ICONS_DIR / f"steam-game-{game.appid}.png"
    if icon_path.exists():
        icon_path.unlink()


def create_desktop_file(game: SteamGame) -> None:
    """Create a .desktop file for a Steam game."""
    icon_name = install_game_icon(game)

    content = f"""[Desktop Entry]
Name={game.name}
Comment=Launch {game.name} via Steam
Exec=steam steam://rungameid/{game.appid}
Icon={icon_name}
Terminal=false
Type=Application
Categories=Game;
Keywords=steam;game;
StartupNotify=true
"""

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    game.desktop_file_path.write_text(content)

    # Update desktop database
    try:
        subprocess.run(
            ["update-desktop-database", str(APPLICATIONS_DIR)],
            capture_output=True,
            timeout=10
        )
    except Exception:
        pass  # Non-critical


def remove_desktop_file(game: SteamGame) -> None:
    """Remove the .desktop file for a Steam game."""
    if game.desktop_file_path.exists():
        game.desktop_file_path.unlink()

    remove_game_icon(game)

    # Update desktop database
    try:
        subprocess.run(
            ["update-desktop-database", str(APPLICATIONS_DIR)],
            capture_output=True,
            timeout=10
        )
    except Exception:
        pass


class GameListItem(QListWidgetItem):
    """Custom list item for displaying a Steam game."""

    def __init__(self, game: SteamGame):
        super().__init__()
        self.game = game
        self.update_display()
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(Qt.CheckState.Unchecked)

    def update_display(self):
        """Update the display text based on current state."""
        status = "[Installed]" if self.game.has_desktop_file else ""
        self.setText(f"{self.game.name}  {status}")

        # Set icon if available
        icon_path = get_game_icon_path(self.game.appid)
        if icon_path:
            self.setIcon(QIcon(str(icon_path)))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.games: list[SteamGame] = []
        self.init_ui()
        self.refresh_games()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(f"Steam Desktop File Creator v{VERSION}")
        self.setMinimumSize(600, 400)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # Toolbar
        toolbar = QHBoxLayout()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_games)
        toolbar.addWidget(self.refresh_btn)

        self.install_btn = QPushButton("Install Selected")
        self.install_btn.clicked.connect(self.install_selected)
        toolbar.addWidget(self.install_btn)

        self.remove_btn = QPushButton("Remove Selected")
        self.remove_btn.clicked.connect(self.remove_selected)
        toolbar.addWidget(self.remove_btn)

        toolbar.addStretch()

        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all)
        toolbar.addWidget(self.select_all_btn)

        self.select_none_btn = QPushButton("Select None")
        self.select_none_btn.clicked.connect(self.select_none)
        toolbar.addWidget(self.select_none_btn)

        layout.addLayout(toolbar)

        # Game list
        self.game_list = QListWidget()
        self.game_list.setIconSize(QSize(32, 32))
        self.game_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.game_list.itemDoubleClicked.connect(self.toggle_item_check)
        layout.addWidget(self.game_list)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

    def refresh_games(self):
        """Refresh the list of Steam games."""
        self.game_list.clear()
        self.games = get_all_games()

        for game in self.games:
            item = GameListItem(game)
            self.game_list.addItem(item)

        self.update_status()

    def update_status(self):
        """Update the status bar with current stats."""
        total = len(self.games)
        installed = sum(1 for g in self.games if g.has_desktop_file)
        self.status_bar.showMessage(f"{installed} of {total} games have desktop launchers")

    def get_checked_items(self) -> list[GameListItem]:
        """Get all checked items in the list."""
        checked = []
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            if isinstance(item, GameListItem) and item.checkState() == Qt.CheckState.Checked:
                checked.append(item)
        return checked

    def install_selected(self):
        """Install desktop files for selected games."""
        checked = self.get_checked_items()
        if not checked:
            QMessageBox.information(self, "No Selection", "Please select games to install.")
            return

        count = 0
        for item in checked:
            try:
                create_desktop_file(item.game)
                item.update_display()
                count += 1
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to create desktop file for {item.game.name}: {e}"
                )

        self.update_status()
        self.status_bar.showMessage(f"Installed {count} desktop launcher(s)", 3000)

    def remove_selected(self):
        """Remove desktop files for selected games."""
        checked = self.get_checked_items()
        if not checked:
            QMessageBox.information(self, "No Selection", "Please select games to remove.")
            return

        count = 0
        for item in checked:
            try:
                remove_desktop_file(item.game)
                item.update_display()
                count += 1
            except Exception as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Failed to remove desktop file for {item.game.name}: {e}"
                )

        self.update_status()
        self.status_bar.showMessage(f"Removed {count} desktop launcher(s)", 3000)

    def select_all(self):
        """Select all items in the list."""
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            if isinstance(item, GameListItem):
                item.setCheckState(Qt.CheckState.Checked)

    def select_none(self):
        """Deselect all items in the list."""
        for i in range(self.game_list.count()):
            item = self.game_list.item(i)
            if isinstance(item, GameListItem):
                item.setCheckState(Qt.CheckState.Unchecked)

    def toggle_item_check(self, item: QListWidgetItem):
        """Toggle the check state of a double-clicked item."""
        if isinstance(item, GameListItem):
            if item.checkState() == Qt.CheckState.Checked:
                item.setCheckState(Qt.CheckState.Unchecked)
            else:
                item.setCheckState(Qt.CheckState.Checked)


def main():
    """Application entry point."""
    import sys

    app = QApplication(sys.argv)
    app.setApplicationName("Steam Desktop File Creator")
    app.setApplicationVersion(VERSION)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
