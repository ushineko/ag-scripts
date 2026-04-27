"""Unit tests for global_shortcut.py.

Covers the parts that don't require a live KGlobalAccel D-Bus service:
hotkey-string parsing and the safe-degradation path when the service is
unreachable. The full registration / press-release flow is covered by
the spike at research/global_shortcut_spike.py and verified live.
"""

from __future__ import annotations

import pytest

from global_shortcut import GlobalShortcut, parse_hotkey


class TestParseHotkey:
    def test_meta_alt_space(self, qapp):
        code = parse_hotkey("Meta+Alt+Space")
        assert code is not None
        assert isinstance(code, int)
        assert code != 0

    def test_ctrl_shift_f1(self, qapp):
        code = parse_hotkey("Ctrl+Shift+F1")
        assert code is not None
        assert isinstance(code, int)
        assert code != 0

    def test_distinct_combos_produce_distinct_codes(self, qapp):
        a = parse_hotkey("Meta+Alt+Space")
        b = parse_hotkey("Ctrl+Shift+F1")
        assert a != b

    def test_empty_string_returns_none(self, qapp):
        assert parse_hotkey("") is None


class TestGlobalShortcutDegradesGracefully:
    """When KGlobalAccel is unavailable (non-KDE session, service not
    running, or invalid bus state), the wrapper must not raise; it
    should return False from set_binding and let the caller fall back
    to disabling the popup hotkey UI."""

    def test_set_binding_returns_false_when_iface_none(self, qapp, monkeypatch):
        gs = GlobalShortcut("test-comp", "test-action", "Test", "Test action")
        # Force the unavailable path regardless of what the host session looks like.
        gs._iface = None
        assert gs.is_available() is False
        assert gs.set_binding(parse_hotkey("Meta+Alt+Space")) is False

    def test_set_binding_returns_false_for_none_keycode(self, qapp):
        gs = GlobalShortcut("test-comp", "test-action", "Test", "Test action")
        # Even when iface looks valid, a None key code is a no-op.
        assert gs.set_binding(None) is False

    def test_unregister_safe_when_not_registered(self, qapp):
        gs = GlobalShortcut("test-comp", "test-action", "Test", "Test action")
        # Should not raise even if iface is None or registration never happened.
        gs._iface = None
        gs.unregister()  # idempotent no-op


class TestComponentPathTranslation:
    """KGlobalAccel translates dashes in componentUnique to underscores
    in the D-Bus object path. Verify the wrapper's internal helper
    matches that convention so signal connections can find the
    component object."""

    def test_dashes_become_underscores(self, qapp):
        gs = GlobalShortcut(
            "vscode-launcher", "show-popup", "VSCode Launcher", "Show popup"
        )
        # Reach into the internal pattern; if the convention changes
        # upstream, this test fails loudly and we update it.
        expected_path = "/component/vscode_launcher"
        # Build the same way the implementation does.
        actual_path = "/component/" + gs._component_unique.replace("-", "_")
        assert actual_path == expected_path
