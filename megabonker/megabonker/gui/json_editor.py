#!/usr/bin/env python3
"""Editable tree view over a decoded JSON document.

Scalar leaves are edited in place and written straight back into the dict that
was handed in, so the owning widget can just re-serialise it. Values are coerced
back to the type they had when loaded - a field the game wrote as an int stays
an int - because Megabonk deserialises into typed C# fields and a silently
stringified number would be rejected or reset on load.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor
from PyQt6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator

# Column indices
COL_KEY = 0
COL_VALUE = 1
COL_TYPE = 2

_PATH_ROLE = Qt.ItemDataRole.UserRole
_TYPE_ROLE = Qt.ItemDataRole.UserRole + 1

SUSPECT_COLOR = "#D9534F"

# Containers are shown but not editable; only these leaf types can be changed.
_EDITABLE = (str, int, float, bool)


class CoercionError(ValueError):
    """Raised when typed text cannot be converted back to the original type."""


def coerce(text: str, original):
    """Convert edited text back to the type `original` had."""
    if isinstance(original, bool):
        lowered = text.strip().lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        raise CoercionError(f"'{text}' is not a boolean")
    if isinstance(original, int):
        return int(text.strip())
    if isinstance(original, float):
        return float(text.strip())
    if original is None:
        return None if text.strip() in ("", "null") else text
    return text


def format_value(value) -> str:
    """Render a scalar the way JSON would, so edits round-trip visually."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


class JsonTreeWidget(QTreeWidget):
    """Tree editor bound to a live dict/list structure."""

    data_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data = None
        self._loading = False
        self.init_ui()

    def init_ui(self):
        self.setColumnCount(3)
        self.setHeaderLabels(["Key", "Value", "Type"])
        self.setAlternatingRowColors(True)
        self.setUniformRowHeights(True)
        self.header().setStretchLastSection(False)
        self.setColumnWidth(COL_KEY, 280)
        self.setColumnWidth(COL_VALUE, 220)
        self.itemChanged.connect(self._on_item_changed)

    def load(self, data):
        """Populate from `data`, which is then edited in place."""
        self._loading = True
        self.clear()
        self._data = data
        self._add_children(self.invisibleRootItem(), data, ())
        self._loading = False
        self.expandToDepth(0)

    def _add_children(self, parent, container, path):
        items = container.items() if isinstance(container, dict) else enumerate(container)
        for key, value in items:
            self._add_node(parent, key, value, path + (key,))

    def _add_node(self, parent, key, value, path):
        item = QTreeWidgetItem(parent)
        item.setText(COL_KEY, str(key))
        item.setData(COL_KEY, _PATH_ROLE, path)
        if isinstance(value, dict):
            item.setText(COL_VALUE, f"{{{len(value)}}}")
            item.setText(COL_TYPE, "object")
            item.setForeground(COL_VALUE, QBrush(QColor("gray")))
            self._add_children(item, value, path)
        elif isinstance(value, list):
            item.setText(COL_VALUE, f"[{len(value)}]")
            item.setText(COL_TYPE, "array")
            item.setForeground(COL_VALUE, QBrush(QColor("gray")))
            self._add_children(item, value, path)
        else:
            item.setText(COL_VALUE, format_value(value))
            item.setText(COL_TYPE, type(value).__name__)
            item.setData(COL_VALUE, _TYPE_ROLE, type(value).__name__)
            if isinstance(value, _EDITABLE):
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsEditable)
        return item

    def _lookup(self, path):
        """Return (container, final_key) for a stored path."""
        container = self._data
        for step in path[:-1]:
            container = container[step]
        return container, path[-1]

    def _on_item_changed(self, item, column):
        if self._loading or column != COL_VALUE or self._data is None:
            return
        path = item.data(COL_KEY, _PATH_ROLE)
        if not path:
            return
        container, key = self._lookup(path)
        original = container[key]
        try:
            new_value = coerce(item.text(COL_VALUE), original)
        except (CoercionError, ValueError):
            # Reject the edit and restore what was there; the type column tells
            # the user what was expected.
            self._loading = True
            item.setText(COL_VALUE, format_value(original))
            self._loading = False
            return
        if new_value == original and type(new_value) is type(original):
            return
        container[key] = new_value
        self._loading = True
        item.setText(COL_VALUE, format_value(new_value))
        self._loading = False
        self.data_changed.emit()

    def mark_suspects(self, suspects: dict[str, list[str]]):
        """Highlight leaf values flagged by validation.

        `suspects` maps a top-level field name to the values under it that the
        game does not appear to recognise. Previous marks are cleared first so
        the highlighting always reflects the current edit state.
        """
        tooltip = ("Not found in the game's identifiers. Likely a typo - the game "
                   "silently ignores ids it does not recognise.")
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            path = item.data(COL_KEY, _PATH_ROLE)
            if item.childCount():
                # Container row - keep its gray "{n}" / "[n]" styling.
                iterator += 1
                continue
            suspect = (
                path and len(path) == 2 and path[0] in suspects
                and item.text(COL_VALUE) in suspects[path[0]]
            )
            if suspect:
                item.setForeground(COL_VALUE, QBrush(QColor(SUSPECT_COLOR)))
                item.setToolTip(COL_VALUE, tooltip)
            else:
                item.setData(COL_VALUE, Qt.ItemDataRole.ForegroundRole, None)
                item.setToolTip(COL_VALUE, "")
            iterator += 1

    def filter_items(self, text: str):
        """Hide rows whose key and value do not contain `text`.

        A matching row keeps its ancestors visible so the match stays reachable.
        """
        needle = text.strip().lower()
        iterator = QTreeWidgetItemIterator(self)
        while iterator.value():
            item = iterator.value()
            if needle:
                match = (needle in item.text(COL_KEY).lower()
                         or needle in item.text(COL_VALUE).lower())
                item.setHidden(not match)
                if match:
                    parent = item.parent()
                    while parent:
                        parent.setHidden(False)
                        parent.setExpanded(True)
                        parent = parent.parent()
            else:
                item.setHidden(False)
            iterator += 1
