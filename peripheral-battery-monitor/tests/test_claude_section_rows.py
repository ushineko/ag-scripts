"""Spec 016: the Claude section renders one row per configured account.

Runs the real Qt widgets on the offscreen platform, so the row construction and
the per-account render paths are exercised without a display. Only the Claude
section is driven — the rest of the monitor (battery readers, KWin, tray) is
not constructed.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

pytest.importorskip("PyQt6", reason="PyQt6 is only present on the system python")

import accounts  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402


def _load_monitor_module():
    """Import peripheral-battery.py, whose filename is not a valid module name."""
    spec = importlib.util.spec_from_file_location(
        "peripheral_battery", os.path.join(ROOT, "peripheral-battery.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(scope="module")
def pb(qapp):
    return _load_monitor_module()


@pytest.fixture
def section(pb, qapp):
    """A monitor instance with only the Claude section constructed.

    Subclassing and calling QWidget's initializer directly skips
    PeripheralMonitor.__init__ (battery readers, KWin, tray, timers) while
    still producing a properly constructed Qt object.
    """

    class _ClaudeOnly(pb.PeripheralMonitor):
        def __init__(self):
            super(pb.PeripheralMonitor, self).__init__()

    monitor = _ClaudeOnly()
    monitor.settings = {"claude_section_enabled": True}
    monitor.claude_frame = None
    monitor.claude_section_visible = True
    monitor._last_good_usage = None
    monitor._last_good_usage_time = 0.0
    monitor.create_claude_section()
    return monitor


def _account(name, subscription_type):
    return accounts.Account(
        name=name,
        store_dir=f"/tmp/{name}",
        subscription_type=subscription_type,
        is_default=(name == "max"),
    )


def _limits(five=12.0, seven=34.0):
    return {
        "five_hour": {"utilization": five, "resets_at": "2099-01-01T00:00:00+00:00"},
        "seven_day": {"utilization": seven, "resets_at": "2099-01-01T00:00:00+00:00"},
    }


def _credits(minor=27900, percent=1):
    return {
        "spend": {
            "enabled": True,
            "used": {"amount_minor": minor, "currency": "USD", "exponent": 2},
            "limit": {"amount_minor": 2000000, "currency": "USD", "exponent": 2},
            "percent": percent,
            "severity": "normal",
        }
    }


class TestRowConstruction:
    def test_single_account_builds_one_unlabeled_row(self, section):
        section.update_claude_section([(_account("max", "max"), _limits())])

        assert len(section.claude_rows) == 1
        assert section.claude_rows["max"]["account"] is None   # no label column

    def test_two_accounts_build_two_labeled_rows(self, section):
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ])

        assert section.claude_rows_order == ["max", "work"]
        assert section.claude_rows["max"]["account"].text().strip() == "max   M"
        assert section.claude_rows["work"]["account"].text().strip() == "work  E"
        # Full type stays available on hover.
        assert section.claude_rows["work"]["account"].toolTip() == "work — Enterprise"

    def test_header_title_appears_once(self, section):
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ])

        from PyQt6.QtWidgets import QLabel

        titles = [
            w for w in section.claude_frame.findChildren(QLabel)
            if w.objectName() == "ClaudeTitle"
        ]
        assert len(titles) == 1          # one section, not two

    def test_rows_rebuild_when_account_set_changes(self, section):
        section.update_claude_section([(_account("max", "max"), _limits())])
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ])
        assert section.claude_rows_order == ["max", "work"]

        section.update_claude_section([(_account("max", "max"), _limits())])
        assert section.claude_rows_order == ["max"]


class TestPerAccountRendering:
    def test_each_row_renders_its_own_shape(self, section):
        section.update_claude_section([
            (_account("max", "max"), _limits(five=12.0, seven=34.0)),
            (_account("work", "enterprise"), _credits()),
        ])

        # Rate-limit account shows percentages; credits account shows dollars.
        assert section.claude_rows["max"]["five"].text() == "5h: 12%"
        assert "$279.00" in section.claude_rows["work"]["five"].text()

    def test_one_account_failing_leaves_the_other_intact(self, section):
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), {"error": "offline"}),
        ])

        assert section.claude_rows["max"]["five"].text() == "5h: 12%"
        assert section.claude_rows["work"]["five"].text() == "Offline"

    def test_a_failing_account_falls_back_to_its_own_last_good(self, section):
        both = [
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ]
        section.update_claude_section(both)

        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), {"error": "rate_limited"}),
        ])

        # work keeps showing its last good credits reading, not an error
        assert "$279.00" in section.claude_rows["work"]["five"].text()

    def test_bare_dict_is_treated_as_the_default_account(self, section):
        """The pre-spec-016 calling convention still works."""
        section.update_claude_section(_limits())

        assert len(section.claude_rows) == 1
        assert section.claude_rows[section.claude_rows_order[0]]["five"].text() == "5h: 12%"


class TestAccountTypeChanges:
    """Regression: a profile's plan can change while its name does not.

    Logging `claude-max` from an Enterprise seat into a Max account left the
    row labeled `E` next to Max rate-limit data, because rows were only rebuilt
    when the set of account *names* changed.
    """

    def test_label_follows_a_plan_change_on_the_same_profile(self, section):
        section.update_claude_section([
            (_account("max", "enterprise"), _credits()),
            (_account("work", "enterprise"), _credits()),
        ])
        assert section.claude_rows["max"]["account"].text().strip() == "max   E"

        # Same profile names, but `max` is now a Max account.
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ])

        assert section.claude_rows["max"]["account"].text().strip() == "max   M"
        assert section.claude_rows["max"]["account"].toolTip() == "max — Max"
        # ...and the other row is left alone.
        assert section.claude_rows["work"]["account"].text().strip() == "work  E"

    def test_label_change_does_not_discard_last_known_good(self, section):
        section.update_claude_section([
            (_account("max", "enterprise"), _credits()),
            (_account("work", "enterprise"), _credits()),
        ])
        section.update_claude_section([
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), {"error": "offline"}),
        ])

        # work fell back to its own cached credits rather than blanking
        assert "$279.00" in section.claude_rows["work"]["five"].text()

    def test_unchanged_type_leaves_the_label_untouched(self, section):
        both = [
            (_account("max", "max"), _limits()),
            (_account("work", "enterprise"), _credits()),
        ]
        section.update_claude_section(both)
        before = section.claude_rows["max"]["account"]

        section.update_claude_section(both)

        # Same widget object — refreshed in place, not rebuilt.
        assert section.claude_rows["max"]["account"] is before
