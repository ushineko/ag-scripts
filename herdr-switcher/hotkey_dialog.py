"""Modal key-capture dialog for choosing the switcher hotkey.

Opened from the tray menu. Grabs the next real key chord the user presses
(modifiers + a non-modifier key), shows it as Qt portable text, and returns it
on Apply. The caller validates the string with `global_shortcut.parse_hotkey`
and rebinds via KGlobalAccel.

Key presses are intercepted in `event()` (before Qt's Tab focus navigation
consumes them) so a chord like `Ctrl+Meta+Tab` can be captured verbatim.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, Qt, QKeyCombination
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
    QWidget,
)

# Lone presses of these are ignored — we wait for a non-modifier key so the
# captured chord always has a committable "real" key.
_MODIFIER_KEYS = {
    Qt.Key.Key_Control,
    Qt.Key.Key_Shift,
    Qt.Key.Key_Alt,
    Qt.Key.Key_Meta,
    Qt.Key.Key_Super_L,
    Qt.Key.Key_Super_R,
    Qt.Key.Key_AltGr,
}


class HotkeyCaptureDialog(QDialog):
    """Capture a single key chord and expose it via `sequence()`.

    Returns `QDialog.DialogCode.Accepted` with a non-empty `sequence()` when the
    user presses a chord and clicks Apply; `Rejected` (empty `sequence()`) on
    Cancel or Esc.
    """

    def __init__(self, current: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Set herdr-switcher hotkey")
        self.setModal(True)
        self._sequence = ""

        layout = QVBoxLayout(self)
        prompt = QLabel("Press the new shortcut…")
        prompt.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._combo_label = QLabel(current or "—")
        self._combo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = self._combo_label.font()
        font.setBold(True)
        font.setPointSize(font.pointSize() + 3)
        self._combo_label.setFont(font)
        layout.addWidget(prompt)
        layout.addWidget(self._combo_label)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
        )
        self._apply_btn = buttons.button(QDialogButtonBox.StandardButton.Apply)
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self.accept)
        buttons.rejected.connect(self.reject)
        # Keep the buttons from stealing Tab / Space / arrows from capture.
        for btn in (
            self._apply_btn,
            buttons.button(QDialogButtonBox.StandardButton.Cancel),
        ):
            if btn is not None:
                btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout.addWidget(buttons)

    def sequence(self) -> str:
        """The captured chord as Qt portable text (empty until one is pressed)."""
        return self._sequence

    # Intercept key presses before QWidget's Tab focus-navigation handles them.
    def event(self, e: QEvent) -> bool:  # type: ignore[override]
        if e.type() == QEvent.Type.KeyPress:
            self._capture(e)
            return True
        return super().event(e)

    def _capture(self, e) -> None:
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.reject()
            return
        if key in _MODIFIER_KEYS:
            return
        combined = QKeyCombination(e.modifiers(), Qt.Key(key)).toCombined()
        text = QKeySequence(combined).toString(
            QKeySequence.SequenceFormat.PortableText
        )
        if not text:
            return
        self._sequence = text
        self._combo_label.setText(text)
        self._apply_btn.setEnabled(True)
