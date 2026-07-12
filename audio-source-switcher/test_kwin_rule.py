"""Tests for the volume OSD KWin rule installer (spec 009)."""

import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(__file__))

import install_kwin_rule as kr  # noqa: E402


@pytest.fixture
def temp_rulesrc(tmp_path, monkeypatch):
    path = tmp_path / "kwinrulesrc"
    monkeypatch.setattr(kr, "CONFIG_PATH", path)
    monkeypatch.setattr(kr, "_kwin_reconfigure", lambda: None)
    return path


@pytest.fixture
def fake_screens(monkeypatch):
    # Two screens mirroring the target machine (landscape + portrait).
    monkeypatch.setattr(kr, "_screen_osd_targets", lambda: [
        ("ass-volume-osd@0_1120", 1100, 1780),
        ("ass-volume-osd@2560_0", 3100, 1220),
    ])


def _read(path: Path):
    import configparser
    c = configparser.ConfigParser(strict=False)
    c.optionxform = str
    c.read(path)
    return c


def test_install_writes_forced_centered_rules(temp_rulesrc, fake_screens):
    kr.install_rules()
    c = _read(temp_rulesrc)

    rules = [r for r in c["General"]["rules"].split(",") if r]
    assert len(rules) == 2
    assert c["General"]["count"] == "2"

    osd_sections = [s for s in rules
                    if c[s].get("Description", "").startswith(kr.DESCRIPTION_PREFIX)]
    assert len(osd_sections) == 2

    by_title = {c[s]["title"]: c[s] for s in osd_sections}
    rule = by_title["ass-volume-osd@0_1120"]
    assert rule["position"] == "1100,1780"
    assert rule["positionrule"] == kr.FORCE
    assert rule["above"] == "true" and rule["aboverule"] == kr.FORCE
    assert rule["noborder"] == "true"
    assert rule["skiptaskbar"] == "true"
    assert rule["titlematch"] == kr.MATCH_EXACT


def test_install_is_idempotent(temp_rulesrc, fake_screens):
    kr.install_rules()
    kr.install_rules()
    c = _read(temp_rulesrc)
    rules = [r for r in c["General"]["rules"].split(",") if r]
    # No duplicate sections created on re-install.
    assert len(rules) == 2
    assert c["General"]["count"] == "2"


def test_install_preserves_foreign_rules(temp_rulesrc, fake_screens):
    # Seed an unrelated pre-existing rule.
    import configparser
    c = configparser.ConfigParser(strict=False)
    c.optionxform = str
    c["General"] = {"rules": "1", "count": "1"}
    c["1"] = {"Description": "Some Other App", "wmclass": "other", "above": "true"}
    with open(temp_rulesrc, "w") as f:
        c.write(f, space_around_delimiters=False)

    kr.install_rules()
    c2 = _read(temp_rulesrc)
    rules = [r for r in c2["General"]["rules"].split(",") if r]
    assert len(rules) == 3  # 1 foreign + 2 OSD
    assert "1" in rules and c2["1"]["Description"] == "Some Other App"


def test_uninstall_removes_only_osd_rules(temp_rulesrc, fake_screens):
    import configparser
    c = configparser.ConfigParser(strict=False)
    c.optionxform = str
    c["General"] = {"rules": "1", "count": "1"}
    c["1"] = {"Description": "Some Other App", "wmclass": "other"}
    with open(temp_rulesrc, "w") as f:
        c.write(f, space_around_delimiters=False)

    kr.install_rules()
    kr.uninstall_rules()

    c2 = _read(temp_rulesrc)
    rules = [r for r in c2["General"]["rules"].split(",") if r]
    assert rules == ["1"]  # only the foreign rule survives
    assert c2["General"]["count"] == "1"


def test_uninstall_no_file_is_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(kr, "CONFIG_PATH", tmp_path / "nope")
    monkeypatch.setattr(kr, "_kwin_reconfigure", lambda: None)
    kr.uninstall_rules()  # must not raise
