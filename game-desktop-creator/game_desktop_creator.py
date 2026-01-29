#!/usr/bin/env python3
"""
Game Desktop File Creator - Create start menu launchers for games.

A PyQt6 GUI application that discovers installed games from Steam and Heroic
(Epic Games, GOG) and allows creating/removing .desktop launcher files.
"""

import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QListWidget, QListWidgetItem, QStatusBar,
    QMessageBox, QAbstractItemView
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

VERSION = "1.1.0"

# Steam tools/runtimes to filter out (not actual games)
STEAM_FILTERED_APPIDS = {
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
APPLICATIONS_DIR = Path.home() / ".local" / "share" / "applications"
ICONS_DIR = Path.home() / ".local" / "share" / "icons" / "hicolor" / "256x256" / "apps"

# Steam paths
STEAM_ROOT = Path.home() / ".steam" / "steam"
STEAM_LIBRARY_VDF = STEAM_ROOT / "steamapps" / "libraryfolders.vdf"
STEAM_ICON_CACHE = STEAM_ROOT / "appcache" / "librarycache"

# Heroic paths
HEROIC_CONFIG = Path.home() / ".config" / "heroic"
HEROIC_LEGENDARY_INSTALLED = HEROIC_CONFIG / "legendaryConfig" / "legendary" / "installed.json"
HEROIC_GOG_INSTALLED = HEROIC_CONFIG / "gogdlConfig" / "gog" / "installed.json"
HEROIC_ICONS = HEROIC_CONFIG / "icons"


@dataclass
class Game:
    """Represents an installed game from any source."""
    id: str
    name: str
    source: str  # "steam", "epic", "gog"

    @property
    def desktop_file_name(self) -> str:
        if self.source == "steam":
            return f"steam-game-{self.id}.desktop"
        else:
            return f"heroic-{self.source}-{self.id}.desktop"

    @property
    def desktop_file_path(self) -> Path:
        return APPLICATIONS_DIR / self.desktop_file_name

    @property
    def icon_name(self) -> str:
        if self.source == "steam":
            return f"steam-game-{self.id}"
        else:
            return f"heroic-game-{self.id}"

    @property
    def has_desktop_file(self) -> bool:
        return self.desktop_file_path.exists()

    @property
    def source_label(self) -> str:
        return {"steam": "Steam", "epic": "Epic", "gog": "GOG"}.get(self.source, self.source)

    def get_icon_source(self) -> Optional[Path]:
        """Get path to source icon file."""
        if self.source == "steam":
            # Steam stores icons in subdirectories: librarycache/<appid>/logo.png or header.jpg
            game_cache = STEAM_ICON_CACHE / self.id
            if game_cache.exists():
                # Prefer logo.png (square), fall back to header.jpg
                logo = game_cache / "logo.png"
                if logo.exists():
                    return logo
                header = game_cache / "header.jpg"
                if header.exists():
                    return header
            return None
        else:
            path = HEROIC_ICONS / f"{self.id}.jpg"
            return path if path.exists() else None

    def get_launch_command(self) -> str:
        """Get the command to launch this game."""
        if self.source == "steam":
            return f"steam steam://rungameid/{self.id}"
        elif self.source == "epic":
            return f"xdg-open heroic://launch/legendary/{self.id}"
        elif self.source == "gog":
            return f"xdg-open heroic://launch/gog/{self.id}"
        return ""

    def get_fallback_icon(self) -> str:
        """Get fallback icon name if game icon not found."""
        return "steam" if self.source == "steam" else "heroic"


# =============================================================================
# VDF Parser (for Steam)
# =============================================================================

def parse_vdf(content: str) -> dict:
    """Parse Valve Data Format (VDF) content into a dictionary."""
    result = {}
    stack = [result]
    current_key = None

    token_pattern = re.compile(r'"([^"]*)"|(\{)|(\})')

    for match in token_pattern.finditer(content):
        quoted_string, open_brace, close_brace = match.groups()

        if open_brace:
            new_dict = {}
            if current_key is not None:
                stack[-1][current_key] = new_dict
                stack.append(new_dict)
                current_key = None
        elif close_brace:
            if len(stack) > 1:
                stack.pop()
            current_key = None
        elif quoted_string is not None:
            if current_key is None:
                current_key = quoted_string
            else:
                stack[-1][current_key] = quoted_string
                current_key = None

    return result


# =============================================================================
# Steam Scanner
# =============================================================================

def get_steam_library_paths() -> list[Path]:
    """Get all Steam library paths from libraryfolders.vdf."""
    if not STEAM_LIBRARY_VDF.exists():
        return []

    content = STEAM_LIBRARY_VDF.read_text()
    data = parse_vdf(content)

    paths = []
    if 'libraryfolders' in data:
        for key, value in data['libraryfolders'].items():
            if isinstance(value, dict) and 'path' in value:
                paths.append(Path(value['path']))

    return paths


def scan_steam_library(library_path: Path) -> list[Game]:
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

                if appid in STEAM_FILTERED_APPIDS:
                    continue

                name = app_state.get('name', f'Unknown ({appid})')
                games.append(Game(id=str(appid), name=name, source="steam"))
        except Exception as e:
            print(f"Error parsing {manifest_path}: {e}")

    return games


def get_steam_games() -> list[Game]:
    """Get all installed Steam games."""
    games = []
    for library_path in get_steam_library_paths():
        games.extend(scan_steam_library(library_path))
    return games


# =============================================================================
# Heroic Scanner
# =============================================================================

def get_heroic_games() -> list[Game]:
    """Get all installed Heroic games (Epic + GOG)."""
    games = []

    # Epic Games (legendary)
    if HEROIC_LEGENDARY_INSTALLED.exists():
        try:
            data = json.loads(HEROIC_LEGENDARY_INSTALLED.read_text())
            for app_name, info in data.items():
                title = info.get("title", app_name)
                games.append(Game(id=app_name, name=title, source="epic"))
        except Exception as e:
            print(f"Error reading Epic games: {e}")

    # GOG Games
    if HEROIC_GOG_INSTALLED.exists():
        try:
            data = json.loads(HEROIC_GOG_INSTALLED.read_text())
            for app_name, info in data.items():
                title = info.get("title", app_name)
                games.append(Game(id=app_name, name=title, source="gog"))
        except Exception as e:
            print(f"Error reading GOG games: {e}")

    return games


# =============================================================================
# Combined Scanner
# =============================================================================

def get_all_games() -> list[Game]:
    """Get all installed games from all sources.

    Returns games sorted by:
    1. Launched games first (have cached icons), never-launched at bottom
    2. Within each group, sorted by source: Steam, Epic, GOG
    3. Within each source, sorted alphabetically by name
    """
    games = []
    games.extend(get_steam_games())
    games.extend(get_heroic_games())

    # Sort order for sources: Steam=0, Epic=1, GOG=2
    source_order = {"steam": 0, "epic": 1, "gog": 2}

    def sort_key(game: Game) -> tuple:
        has_icon = game.get_icon_source() is not None
        return (
            0 if has_icon else 1,           # Launched games first
            source_order.get(game.source, 9),  # Then by source
            game.name.lower()               # Then alphabetically
        )

    games.sort(key=sort_key)
    return games


# =============================================================================
# Desktop File Management
# =============================================================================

def install_game_icon(game: Game) -> str:
    """Install game icon to system icons directory, return icon name."""
    source_icon = game.get_icon_source()

    if source_icon is None:
        return game.get_fallback_icon()

    ICONS_DIR.mkdir(parents=True, exist_ok=True)
    dest_icon = ICONS_DIR / f"{game.icon_name}.png"

    try:
        pixmap = QPixmap(str(source_icon))
        if not pixmap.isNull():
            pixmap.save(str(dest_icon), "PNG")
            return game.icon_name
    except Exception as e:
        print(f"Error installing icon for {game.name}: {e}")

    return game.get_fallback_icon()


def remove_game_icon(game: Game) -> None:
    """Remove game icon from system icons directory."""
    icon_path = ICONS_DIR / f"{game.icon_name}.png"
    if icon_path.exists():
        icon_path.unlink()


def create_desktop_file(game: Game) -> None:
    """Create a .desktop file for a game."""
    icon_name = install_game_icon(game)
    launcher = "Steam" if game.source == "steam" else "Heroic"

    content = f"""[Desktop Entry]
Name={game.name}
Comment=Launch {game.name} via {launcher}
Exec={game.get_launch_command()}
Icon={icon_name}
Terminal=false
Type=Application
Categories=Game;
Keywords={game.source};game;
StartupNotify=true
"""

    APPLICATIONS_DIR.mkdir(parents=True, exist_ok=True)
    game.desktop_file_path.write_text(content)

    try:
        subprocess.run(
            ["update-desktop-database", str(APPLICATIONS_DIR)],
            capture_output=True,
            timeout=10
        )
    except Exception:
        pass


def remove_desktop_file(game: Game) -> None:
    """Remove the .desktop file for a game."""
    if game.desktop_file_path.exists():
        game.desktop_file_path.unlink()

    remove_game_icon(game)

    try:
        subprocess.run(
            ["update-desktop-database", str(APPLICATIONS_DIR)],
            capture_output=True,
            timeout=10
        )
    except Exception:
        pass


# =============================================================================
# GUI
# =============================================================================

class GameListItem(QListWidgetItem):
    """Custom list item for displaying a game."""

    def __init__(self, game: Game):
        super().__init__()
        self.game = game
        self.update_display()
        self.setFlags(self.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        self.setCheckState(Qt.CheckState.Unchecked)

    def update_display(self):
        """Update the display text based on current state."""
        status = "[Installed]" if self.game.has_desktop_file else ""
        self.setText(f"[{self.game.source_label}] {self.game.name}  {status}")

        icon_path = self.game.get_icon_source()
        if icon_path:
            self.setIcon(QIcon(str(icon_path)))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.games: list[Game] = []
        self.init_ui()
        self.refresh_games()

    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle(f"Game Desktop Creator v{VERSION}")
        self.setMinimumSize(650, 450)

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
        """Refresh the list of games."""
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

        steam_count = sum(1 for g in self.games if g.source == "steam")
        epic_count = sum(1 for g in self.games if g.source == "epic")
        gog_count = sum(1 for g in self.games if g.source == "gog")

        sources = []
        if steam_count:
            sources.append(f"{steam_count} Steam")
        if epic_count:
            sources.append(f"{epic_count} Epic")
        if gog_count:
            sources.append(f"{gog_count} GOG")

        source_str = ", ".join(sources) if sources else "0 games"
        self.status_bar.showMessage(f"{installed}/{total} installed | {source_str}")

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
    app.setApplicationName("Game Desktop Creator")
    app.setApplicationVersion(VERSION)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
