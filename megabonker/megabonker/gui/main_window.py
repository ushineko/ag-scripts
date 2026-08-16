#!/usr/bin/env python3
"""Main editor window for megabonker."""

import os
import subprocess
import sys

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (QApplication, QComboBox, QHBoxLayout, QLabel,
                             QLineEdit, QMainWindow, QMessageBox, QPushButton,
                             QTabWidget, QVBoxLayout, QWidget)

from megabonker.config import ConfigManager
from megabonker.gamedata import known_ids, steam_is_running
from megabonker.gui.derive_dialog import DeriveDialog
from megabonker.gui.json_editor import JsonTreeWidget
from megabonker.keys import load_keyring
from megabonker.savefile import (ENCRYPTED_NAMES, PLAIN_NAMES, SAVE_ROOT,
                                 SaveError, SaveFile, find_profiles,
                                 game_is_running, local_dir_for, save_roots)
from megabonker.validate import (describe, touches_steam_achievements,
                                 unknown_additions)

APP_NAME = "megabonker"
DISPLAY_NAME = "Megabonker"


class SaveTab(QWidget):
    """One decrypted save file: a filter box over an editable JSON tree."""

    dirty_changed = pyqtSignal()

    validation_changed = pyqtSignal()

    def __init__(self, save: SaveFile, vocabulary: set | None = None, parent=None):
        super().__init__(parent)
        self.save = save
        self.vocabulary = vocabulary or set()
        self.dirty = False
        self.suspects: dict = {}
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("type to narrow the tree (key or value)")
        self.filter_edit.setClearButtonEnabled(True)
        filter_layout.addWidget(self.filter_edit)
        layout.addLayout(filter_layout)

        self.tree = JsonTreeWidget()
        self.tree.load(self.save.data)
        self.tree.data_changed.connect(self.on_data_changed)
        self.filter_edit.textChanged.connect(self.tree.filter_items)
        layout.addWidget(self.tree)

        origin = "encrypted" if self.save.encrypted else "plain JSON"
        key_label = f" · key: {self.save.key.label}" if self.save.key else ""
        self.info_label = QLabel(f"{self.save.path} ({origin}{key_label})")
        self.info_label.setStyleSheet("color: gray;")
        self.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.info_label)

    def on_data_changed(self):
        self.revalidate()
        if not self.dirty:
            self.dirty = True
            self.dirty_changed.emit()

    def revalidate(self):
        """Flag ids this session added that the game does not recognise.

        Only additions are checked: the game writes ids we cannot always find a
        definition for (composite ones like "SantaHat_hat"), so validating the
        whole file would cry wolf and get ignored.
        """
        self.suspects = unknown_additions(self.save.original, self.save.data,
                                          self.vocabulary)
        self.tree.mark_suspects(self.suspects)
        self.validation_changed.emit()

    def mark_clean(self):
        self.dirty = False
        self.dirty_changed.emit()


class MainWindow(QMainWindow):
    """Profile picker plus one tab per save file."""

    def __init__(self, profile: str | None = None):
        super().__init__()
        self.config_manager = ConfigManager()
        self.config_data = self.config_manager.load_config()
        self.tabs_by_name: dict[str, SaveTab] = {}
        self.requested_profile = profile
        self.vocabulary = known_ids()
        self.stale = False

        # The editor serialises its whole in-memory document on save, so writing
        # a buffer that predates a play session silently reverts everything that
        # happened in between. Poll for the file changing underneath us.
        self.watch_timer = QTimer(self)
        self.watch_timer.setInterval(2000)
        self.watch_timer.timeout.connect(self.check_stale)
        self.watch_timer.start()

        self.setWindowTitle(f"{DISPLAY_NAME} - Megabonk Save Editor")
        self.setWindowIcon(QIcon.fromTheme("applications-games"))
        self.resize(900, 640)

        self.init_ui()
        self.create_menu_bar()
        self.populate_profiles()

    # ---------------------------------------------------------------- layout

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_layout = QHBoxLayout()
        top_layout.addWidget(QLabel("Profile:"))
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self.on_profile_changed)
        top_layout.addWidget(self.profile_combo, 1)
        self.reload_btn = QPushButton("Reload")
        self.reload_btn.clicked.connect(self.load_profile)
        top_layout.addWidget(self.reload_btn)
        self.save_btn = QPushButton("Save Changes")
        self.save_btn.clicked.connect(self.on_save)
        self.save_btn.setEnabled(False)
        top_layout.addWidget(self.save_btn)
        layout.addLayout(top_layout)

        self.stale_bar = QWidget()
        stale_layout = QHBoxLayout(self.stale_bar)
        stale_layout.setContentsMargins(8, 6, 8, 6)
        self.stale_label = QLabel(
            "⚠️ These saves changed on disk since they were opened - the game has "
            "written to them. Saving now would overwrite that progress."
        )
        self.stale_label.setWordWrap(True)
        stale_layout.addWidget(self.stale_label, 1)
        self.stale_reload_btn = QPushButton("Reload from disk")
        self.stale_reload_btn.clicked.connect(self.on_stale_reload)
        stale_layout.addWidget(self.stale_reload_btn)
        self.stale_override_btn = QPushButton("Keep mine")
        self.stale_override_btn.clicked.connect(self.on_stale_override)
        stale_layout.addWidget(self.stale_override_btn)
        self.stale_bar.setStyleSheet("background-color: #552222;")
        self.stale_bar.setVisible(False)
        layout.addWidget(self.stale_bar)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

    def create_menu_bar(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")
        reload_action = QAction("&Reload", self)
        reload_action.setShortcut("Ctrl+R")
        reload_action.triggered.connect(self.load_profile)
        file_menu.addAction(reload_action)
        save_action = QAction("&Save Changes", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.on_save)
        file_menu.addAction(save_action)
        file_menu.addSeparator()
        quit_action = QAction("&Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)

        tools_menu = menubar.addMenu("&Tools")
        derive_action = QAction("Recover Save &Key...", self)
        derive_action.triggered.connect(self.on_derive_key)
        tools_menu.addAction(derive_action)
        open_action = QAction("Open Save &Folder", self)
        open_action.triggered.connect(self.on_open_folder)
        tools_menu.addAction(open_action)

        help_menu = menubar.addMenu("&Help")
        about_action = QAction("&About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    # ----------------------------------------------------------- profile I/O

    def populate_profiles(self):
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        profiles = find_profiles()
        for steamid, path in profiles:
            self.profile_combo.addItem(steamid, path)
        self.profile_combo.blockSignals(False)

        if not profiles:
            roots = ", ".join(p for _, p in save_roots()) or SAVE_ROOT
            self.set_status(f"🔴 No Megabonk saves found under {roots}")
            return

        target = self.requested_profile or self.config_data.get("last_profile", "")
        index = self.profile_combo.findData(target)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.load_profile()

    def current_profile_dir(self) -> str | None:
        return self.profile_combo.currentData()

    def on_profile_changed(self, index):
        if index >= 0:
            self.load_profile()

    def _candidate_files(self, profile_dir: str) -> list[str]:
        paths = [os.path.join(profile_dir, n) for n in ENCRYPTED_NAMES]
        # LocalDir sits beside CloudDir in the same save root - resolve it from
        # the profile so a Proton profile reads that prefix's settings.
        paths += [os.path.join(local_dir_for(profile_dir), n) for n in PLAIN_NAMES]
        return [p for p in paths if os.path.exists(p)]

    def load_profile(self):
        profile_dir = self.current_profile_dir()
        if not profile_dir:
            return
        if not self.confirm_discard():
            return

        self.stale = False
        self.stale_bar.setVisible(False)
        self.tabs.clear()
        self.tabs_by_name.clear()
        keyring = load_keyring()
        failures = []

        for path in self._candidate_files(profile_dir):
            save = SaveFile(path)
            try:
                save.load(keyring)
            except SaveError as e:
                failures.append(f"{os.path.basename(path)}: {e}")
                continue
            tab = SaveTab(save, self.vocabulary)
            tab.dirty_changed.connect(self.refresh_dirty_state)
            tab.validation_changed.connect(self.refresh_validation)
            self.tabs.addTab(tab, save.name)
            self.tabs_by_name[path] = tab

        self.config_data["last_profile"] = profile_dir
        self.config_manager.save_config(self.config_data)
        self.refresh_dirty_state()
        self.report_load(failures)

    def report_load(self, failures: list[str]):
        if failures and not self.tabs_by_name:
            self.set_status("🔴 No save files could be opened. " + " | ".join(failures))
            QMessageBox.warning(
                self, "Cannot open saves",
                "None of the save files could be decrypted:\n\n"
                + "\n".join(failures)
                + "\n\nIf the game has updated, use Tools → Recover Save Key.",
            )
        elif failures:
            self.set_status("🟡 Some files could not be opened: " + " | ".join(failures))
        else:
            notes = ""
            if game_is_running():
                notes += " · ⚠️ Megabonk is running"
            if steam_is_running():
                # CloudDir is Steam Cloud synced; the cloud copy can win.
                notes += " · ⚠️ Steam is running (cloud sync may revert edits)"
            self.set_status(f"🟢 Loaded {len(self.tabs_by_name)} file(s){notes}")

    def set_status(self, text: str):
        self.status_label.setText(text)

    # ------------------------------------------------------------- edit/save

    def refresh_validation(self):
        """Surface unrecognised ids added during this session."""
        merged: dict[str, list[str]] = {}
        for tab in self.tabs_by_name.values():
            for field, values in tab.suspects.items():
                merged.setdefault(field, []).extend(values)
        if merged:
            self.set_status(f"🟡 {describe(merged)} - the game ignores ids it "
                            f"does not recognise, so check the spelling")
        elif not self.stale:
            self.set_status(f"🟢 {len(self.tabs_by_name)} file(s) loaded")

    def check_stale(self):
        """Detect the save file changing on disk behind the editor."""
        if self.stale or not self.tabs_by_name:
            return
        changed = [t for t in self.tabs_by_name.values() if t.save.is_stale()]
        if not changed:
            return
        self.stale = True
        self.stale_bar.setVisible(True)
        names = ", ".join(sorted(t.save.name for t in changed))
        self.stale_label.setText(
            f"⚠️ Changed on disk since opened: {names}. The game has written to "
            f"these. Saving now would overwrite that progress."
        )
        self.refresh_dirty_state()

    def on_stale_reload(self):
        """Discard the in-memory copy and re-read what the game wrote."""
        self.stale = False
        self.stale_bar.setVisible(False)
        for tab in self.tabs_by_name.values():
            tab.dirty = False          # reloading is the user's answer to the prompt
        self.load_profile()

    def on_stale_override(self):
        """Keep the in-memory edits and allow saving over the newer file."""
        reply = QMessageBox.warning(
            self,
            "Overwrite newer save?",
            "The file on disk is newer than what is open here - most likely the "
            "game wrote it.\n\nKeeping your version will discard whatever the "
            "game saved in the meantime, including any progress from that "
            "session.\n\nKeep the in-memory version anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.stale = False
        self.stale_bar.setVisible(False)
        # Re-baseline so the same file does not trigger the warning again.
        for tab in self.tabs_by_name.values():
            tab.save.mtime = tab.save.disk_mtime()
        self.refresh_dirty_state()

    def dirty_tabs(self) -> list[SaveTab]:
        return [t for t in self.tabs_by_name.values() if t.dirty]

    def refresh_dirty_state(self):
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            self.tabs.setTabText(index, tab.save.name + (" *" if tab.dirty else ""))
        self.save_btn.setEnabled(bool(self.dirty_tabs()) and not self.stale)

    def confirm_discard(self) -> bool:
        """Ask before throwing away unsaved edits. True means proceed."""
        if not self.dirty_tabs():
            return True
        reply = QMessageBox.warning(
            self,
            "Discard changes?",
            "There are unsaved changes.\n\nDiscard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Discard

    def on_save(self):
        dirty = self.dirty_tabs()
        if not dirty:
            return
        if self.stale:
            QMessageBox.warning(
                self, "Save changed on disk",
                "These files changed on disk after they were opened. Reload, or "
                "choose 'Keep mine', before saving.",
            )
            return
        achievement_edits = [t for t in dirty
                             if touches_steam_achievements(t.save.original, t.save.data)]
        if achievement_edits:
            reply = QMessageBox.warning(
                self,
                "This edit may reach Steam",
                "You are adding achievement ids.\n\nMegabonk mirrors its local "
                "achievement list up to Steam, so an achievement you did not earn "
                "can appear on your public Steam profile. This has been observed, "
                "not merely assumed.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        if self.config_data.get("warn_if_running", True) and game_is_running():
            reply = QMessageBox.warning(
                self,
                "Megabonk is running",
                "Megabonk is running. It holds save state in memory and will "
                "overwrite these files when it exits, discarding your edits.\n\n"
                "Save anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        backups, errors = [], []
        for tab in dirty:
            try:
                backup = tab.save.save(make_backup=self.config_data.get("backup_on_save", True))
            except SaveError as e:
                errors.append(f"{tab.save.name}: {e}")
                continue
            if backup:
                backups.append(os.path.basename(backup))
            tab.mark_clean()

        self.refresh_dirty_state()
        if errors:
            QMessageBox.critical(self, "Error",
                                 "Failed to save:\n\n" + "\n".join(errors))
            self.set_status("🔴 " + " | ".join(errors))
        else:
            detail = f" · backups: {', '.join(backups)}" if backups else ""
            self.set_status(f"🟢 Saved {len(dirty)} file(s){detail}")

    # ----------------------------------------------------------------- tools

    def on_derive_key(self):
        profile_dir = self.current_profile_dir()
        if not profile_dir:
            QMessageBox.warning(self, "Error", "No profile selected.")
            return
        dialog = DeriveDialog(profile_dir, self)
        if dialog.exec():
            # A key was recovered and stored; retry the files that failed.
            self.load_profile()

    def on_open_folder(self):
        profile_dir = self.current_profile_dir() or SAVE_ROOT
        try:
            subprocess.Popen(["xdg-open", profile_dir])
        except OSError as e:
            QMessageBox.warning(self, "Error", f"Could not open the folder: {e}")

    def show_about(self):
        QMessageBox.about(
            self,
            f"About {DISPLAY_NAME}",
            f"<b>{DISPLAY_NAME}</b><br><br>"
            "Editor for Megabonk save files, which are stored as "
            "base64(AES-256-CBC(PKCS7(JSON))).<br><br>"
            "The key and IV are constants compiled into the game and can be "
            "recovered from its own files via Tools → Recover Save Key, so the "
            "editor survives game updates.<br><br>"
            f"Saves: <code>{SAVE_ROOT}</code>",
        )

    def closeEvent(self, event):
        if not self.confirm_discard():
            event.ignore()
            return
        super().closeEvent(event)


def run(profile: str | None = None) -> int:
    """Launch the editor. Returns a process exit code."""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setDesktopFileName(APP_NAME)
    window = MainWindow(profile=profile)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(run())
