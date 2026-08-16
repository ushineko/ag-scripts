#!/usr/bin/env python3
"""Offscreen smoke tests for the editor widgets.

Runs under QT_QPA_PLATFORM=offscreen so it works headless and in CI. Covers the
tree editor's write-back and type coercion, which is where a bug would silently
corrupt a save. See specs/001-save-editor.md.
"""

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PyQt6.QtWidgets import QApplication
    from megabonker.gui.json_editor import (CoercionError, JsonTreeWidget,
                                            coerce, format_value)
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

_app = None


def setUpModule():
    global _app
    if QT_AVAILABLE:
        _app = QApplication.instance() or QApplication([])


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 not available")
class TestCoercion(unittest.TestCase):
    """Edited text must return to the type the game wrote."""

    def test_int_stays_int(self):
        self.assertIsInstance(coerce("42", 0), int)

    def test_float_stays_float(self):
        self.assertIsInstance(coerce("1.5", 0.0), float)

    def test_bool_accepts_json_spelling(self):
        self.assertIs(coerce("true", False), True)
        self.assertIs(coerce("false", True), False)

    def test_bool_rejects_nonsense(self):
        with self.assertRaises(CoercionError):
            coerce("maybe", True)

    def test_int_rejects_nonsense(self):
        with self.assertRaises(ValueError):
            coerce("lots", 0)

    def test_bool_is_not_treated_as_int(self):
        """bool is a subclass of int, so order of checks matters."""
        self.assertIs(coerce("true", True), True)

    def test_format_value_uses_json_spelling(self):
        self.assertEqual(format_value(True), "true")
        self.assertEqual(format_value(None), "null")


@unittest.skipUnless(QT_AVAILABLE, "PyQt6 not available")
class TestJsonTreeWidget(unittest.TestCase):
    def setUp(self):
        self.data = {
            "gold": 100,
            "flag": True,
            "nested": {"deep": {"value": 7}},
            "items": [1, 2, 3],
        }
        self.tree = JsonTreeWidget()
        self.tree.load(self.data)

    def _find(self, key):
        from PyQt6.QtWidgets import QTreeWidgetItemIterator
        iterator = QTreeWidgetItemIterator(self.tree)
        while iterator.value():
            if iterator.value().text(0) == key:
                return iterator.value()
            iterator += 1
        return None

    def test_top_level_keys_present(self):
        for key in self.data:
            self.assertIsNotNone(self._find(key), f"{key} missing from tree")

    def test_nested_values_are_reachable(self):
        self.assertIsNotNone(self._find("deep"))
        self.assertIsNotNone(self._find("value"))

    def test_editing_writes_back_into_the_dict(self):
        item = self._find("gold")
        item.setText(1, "555")
        self.assertEqual(self.data["gold"], 555)
        self.assertIsInstance(self.data["gold"], int)

    def test_editing_nested_value_writes_back(self):
        item = self._find("value")
        item.setText(1, "99")
        self.assertEqual(self.data["nested"]["deep"]["value"], 99)

    def test_editing_list_element_writes_back(self):
        item = self._find("1")  # index 1 of "items"
        item.setText(1, "42")
        self.assertIn(42, self.data["items"])

    def test_invalid_edit_is_rejected_and_reverted(self):
        item = self._find("gold")
        item.setText(1, "not a number")
        self.assertEqual(self.data["gold"], 100)
        self.assertEqual(item.text(1), "100")

    def test_containers_are_not_editable(self):
        from PyQt6.QtCore import Qt
        item = self._find("nested")
        self.assertFalse(item.flags() & Qt.ItemFlag.ItemIsEditable)

    def test_filter_hides_non_matching_rows(self):
        self.tree.filter_items("gold")
        self.assertFalse(self._find("gold").isHidden())
        self.assertTrue(self._find("flag").isHidden())

    def test_clearing_filter_restores_all_rows(self):
        self.tree.filter_items("gold")
        self.tree.filter_items("")
        self.assertFalse(self._find("flag").isHidden())


if __name__ == "__main__":
    unittest.main()
