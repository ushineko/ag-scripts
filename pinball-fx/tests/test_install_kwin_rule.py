import configparser
from pathlib import Path

import install_kwin_rule as ikr


def _read(path: Path) -> configparser.ConfigParser:
    cp = configparser.ConfigParser(strict=False)
    cp.optionxform = str
    cp.read(path)
    return cp


def test_install_creates_rule_with_geometry(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    ikr.install_rule(x=3840, y=0, width=2160, height=3840, config_path=cfg_path, reconfigure=False)

    parsed = _read(cfg_path)
    rules = [r for r in parsed["General"]["rules"].split(",") if r]
    assert len(rules) == 1
    sec = rules[0]
    assert parsed[sec]["Description"] == ikr.RULE_DESCRIPTION
    assert parsed[sec]["wmclass"] == "gamescope"
    assert parsed[sec]["wmclassmatch"] == "1"
    assert parsed[sec]["position"] == "3840,0"
    assert parsed[sec]["positionrule"] == "2"
    assert parsed[sec]["size"] == "2160,3840"
    assert parsed[sec]["sizerule"] == "2"
    assert parsed[sec]["fullscreen"] == "true"
    assert parsed[sec]["fullscreenrule"] == "2"
    assert parsed[sec]["noborder"] == "true"
    assert parsed[sec]["noborderrule"] == "2"


def test_install_is_idempotent_and_updates_geometry(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    ikr.install_rule(x=0, y=0, width=1920, height=1080, config_path=cfg_path, reconfigure=False)
    ikr.install_rule(x=3840, y=0, width=2160, height=3840, config_path=cfg_path, reconfigure=False)

    parsed = _read(cfg_path)
    rules = [r for r in parsed["General"]["rules"].split(",") if r]
    assert len(rules) == 1, "second install must update, not append"
    assert parsed[rules[0]]["position"] == "3840,0"
    assert parsed[rules[0]]["size"] == "2160,3840"


def test_install_preserves_unrelated_rules(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    cfg_path.write_text(
        "[General]\n"
        "count=1\n"
        "rules=99\n\n"
        "[99]\n"
        "Description=Unrelated\n"
        "wmclass=other-app\n"
    )

    ikr.install_rule(x=0, y=0, width=2160, height=3840, config_path=cfg_path, reconfigure=False)

    parsed = _read(cfg_path)
    rules = sorted([r for r in parsed["General"]["rules"].split(",") if r])
    assert "99" in rules
    assert len(rules) == 2
    assert parsed["99"]["Description"] == "Unrelated"


def test_install_migrates_legacy_rule(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    cfg_path.write_text(
        "[General]\n"
        "count=1\n"
        "rules=42\n\n"
        "[42]\n"
        f"Description={ikr.LEGACY_RULE_DESCRIPTION}\n"
        "wmclass=^.*pinballfx-win64-shipping\\.exe.*$\n"
    )

    ikr.install_rule(x=3840, y=0, width=2160, height=3840, config_path=cfg_path, reconfigure=False)

    parsed = _read(cfg_path)
    rules = [r for r in parsed["General"]["rules"].split(",") if r]
    descriptions = [parsed[r].get("Description") for r in rules]
    assert ikr.LEGACY_RULE_DESCRIPTION not in descriptions
    assert ikr.RULE_DESCRIPTION in descriptions
    assert "42" not in parsed.sections() or parsed.get("42", "Description", fallback=None) is None


def test_uninstall_removes_current_and_legacy_rules(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    cfg_path.write_text(
        "[General]\n"
        "count=2\n"
        "rules=1,2\n\n"
        "[1]\n"
        f"Description={ikr.LEGACY_RULE_DESCRIPTION}\n"
        "wmclass=foo\n\n"
        "[2]\n"
        f"Description={ikr.RULE_DESCRIPTION}\n"
        "wmclass=gamescope\n"
    )
    removed = ikr.uninstall_rule(config_path=cfg_path, reconfigure=False)
    assert removed == 2

    parsed = _read(cfg_path)
    assert parsed["General"].get("rules", "") == ""
    assert "1" not in parsed.sections()
    assert "2" not in parsed.sections()


def test_uninstall_is_noop_when_missing(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    removed = ikr.uninstall_rule(config_path=cfg_path, reconfigure=False)
    assert removed == 0


def test_uninstall_preserves_unrelated(tmp_path):
    cfg_path = tmp_path / "kwinrulesrc"
    cfg_path.write_text(
        "[General]\n"
        "count=2\n"
        "rules=1,2\n\n"
        "[1]\n"
        "Description=Unrelated\n"
        "wmclass=other\n\n"
        "[2]\n"
        f"Description={ikr.RULE_DESCRIPTION}\n"
        "wmclass=gamescope\n"
    )
    removed = ikr.uninstall_rule(config_path=cfg_path, reconfigure=False)
    assert removed == 1

    parsed = _read(cfg_path)
    assert parsed["General"]["rules"] == "1"
    assert parsed["1"]["Description"] == "Unrelated"
