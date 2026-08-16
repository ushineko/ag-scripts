#!/usr/bin/env python3
"""Dialog that re-derives the save key from the game files.

Needed after a game update rotates the baked-in constants, at which point every
known key stops working and saves cannot be opened. The search runs on a worker
thread so the window stays responsive and can be cancelled.
"""

import os

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog,
                             QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QProgressBar, QPushButton,
                             QTextBrowser, QVBoxLayout)

from megabonker.derive import DeriveError, derive, find_game_dir
from megabonker.keys import save_key
from megabonker.savefile import ENCRYPTED_NAMES


class DeriveWorker(QThread):
    """Runs the key search off the GUI thread."""

    progress_updated = pyqtSignal(str, int, int)
    search_finished = pyqtSignal(object)   # DeriveResult, or None if not found
    search_failed = pyqtSignal(str)

    def __init__(self, game_dir, save_blobs, exhaustive=False):
        super().__init__()
        self.game_dir = game_dir
        self.save_blobs = save_blobs
        self.exhaustive = exhaustive
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            result = derive(
                self.game_dir,
                self.save_blobs,
                progress=lambda stage, done, total: self.progress_updated.emit(stage, done, total),
                should_cancel=lambda: self._cancelled,
                exhaustive=self.exhaustive,
            )
        except DeriveError as e:
            self.search_failed.emit(str(e))
            return
        except Exception as e:  # a crash here must not take the app down
            self.search_failed.emit(f"unexpected error: {e}")
            return
        self.search_finished.emit(result)


class DeriveDialog(QDialog):
    """Locate the game, search it for the key, and optionally keep the result."""

    def __init__(self, profile_dir, parent=None):
        super().__init__(parent)
        self.profile_dir = profile_dir
        self.worker = None
        self.result_obj = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Recover Save Key")
        self.resize(680, 460)
        layout = QVBoxLayout(self)

        intro = QLabel(
            "Megabonk's key and IV are constants compiled into the game, so they "
            "change when the game updates. This searches the installed game files "
            "for the pair that decrypts your saves. Nothing is modified."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # --- Game location ---
        game_group = QGroupBox("Game Installation")
        game_layout = QHBoxLayout()
        game_group.setLayout(game_layout)
        self.game_edit = QLineEdit(find_game_dir() or "")
        self.game_edit.setPlaceholderText("path to .../steamapps/common/Megabonk")
        self.browse_btn = QPushButton("Browse...")
        self.browse_btn.clicked.connect(self.on_browse)
        game_layout.addWidget(self.game_edit)
        game_layout.addWidget(self.browse_btn)
        layout.addWidget(game_group)

        # --- Progress ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log_browser = QTextBrowser()
        layout.addWidget(self.log_browser)

        # --- Actions ---
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Search")
        self.start_btn.clicked.connect(self.on_start)
        self.cancel_btn = QPushButton("Cancel Search")
        self.cancel_btn.clicked.connect(self.on_cancel)
        self.cancel_btn.setEnabled(False)
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Close
        )
        self.save_button = self.button_box.button(QDialogButtonBox.StandardButton.Save)
        self.save_button.setText("Save Key && Reload")
        self.save_button.setEnabled(False)
        self.button_box.accepted.connect(self.on_save)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def log(self, message: str):
        self.log_browser.append(message)

    def on_browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select the Megabonk install directory")
        if path:
            self.game_edit.setText(path)

    def _load_save_blobs(self) -> list[bytes]:
        blobs = []
        for name in ENCRYPTED_NAMES:
            full = os.path.join(self.profile_dir, name)
            if os.path.exists(full):
                blobs.append(open(full, "rb").read())
        return blobs

    def on_start(self):
        if self.worker and self.worker.isRunning():
            return
        game_dir = self.game_edit.text().strip()
        if not os.path.isdir(game_dir):
            QMessageBox.warning(self, "Error", f"Not a directory:\n{game_dir}")
            return
        blobs = self._load_save_blobs()
        if not blobs:
            QMessageBox.warning(
                self, "Error",
                f"No encrypted save files found in:\n{self.profile_dir}"
            )
            return
        if len(blobs) == 1:
            self.log("⚠️ Only one save file available; two would make the result "
                     "much more trustworthy.")

        self.log_browser.clear()
        self.log(f"Game:    {game_dir}")
        self.log(f"Profile: {self.profile_dir}")
        self.log(f"Testing against {len(blobs)} save file(s).")
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)
        self.start_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.save_button.setEnabled(False)

        self.worker = DeriveWorker(game_dir, blobs)
        self.worker.progress_updated.connect(self.on_progress)
        self.worker.search_finished.connect(self.on_finished)
        self.worker.search_failed.connect(self.on_failed)
        self.worker.start()

    def on_cancel(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log("Cancelling...")

    def on_progress(self, stage, done, total):
        if self.progress_bar.format() != stage:
            self.progress_bar.setFormat(stage)
            self.log(f"• {stage}")
        if total:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)

    def _search_done(self):
        self.progress_bar.setVisible(False)
        self.start_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)

    def on_failed(self, message):
        self._search_done()
        self.log(f"🔴 {message}")
        QMessageBox.critical(self, "Error", f"Key recovery failed: {message}")

    def on_finished(self, result):
        self._search_done()
        if result is None:
            self.log("🔴 No key found.")
            self.log("Try the CLI with --exhaustive: megabonker derive-key --exhaustive")
            return
        self.result_obj = result
        self.log("🟢 Key recovered.")
        self.log(f"    key = {result.key.hex()}")
        self.log(f"    iv  = {result.iv.hex()}")
        self.log(f"    key found at {result.key_location}")
        self.log(f"    iv  found at {result.iv_location}")
        self.save_button.setEnabled(True)

    def on_save(self):
        if not self.result_obj:
            self.reject()
            return
        try:
            save_key(self.result_obj.to_save_key())
        except OSError as e:
            QMessageBox.critical(self, "Error", f"Failed to save the key: {e}")
            return
        self.accept()

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
        super().closeEvent(event)
