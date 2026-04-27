from __future__ import annotations

import textwrap

import pytest

from slack_presence_toggle.config import Config


def test_defaults_when_file_missing(tmp_path):
    cfg = Config.load(tmp_path / "nonexistent.toml")
    assert cfg.enabled is True
    assert cfg.grace_seconds == 30
    assert cfg.slack_resource_class == "Slack"
    assert cfg.status_text == "Heads down"
    assert cfg.status_emoji == ":dart:"
    assert cfg.status_safety_buffer_seconds == 3600


def test_round_trip(tmp_path):
    p = tmp_path / "config.toml"
    cfg = Config(grace_seconds=120, status_text="Focus", debug=True, enabled=False)
    cfg.save(p)
    loaded = Config.load(p)
    assert loaded.grace_seconds == 120
    assert loaded.status_text == "Focus"
    assert loaded.debug is True
    assert loaded.enabled is False


def test_corrupt_toml_returns_defaults(tmp_path, caplog):
    p = tmp_path / "config.toml"
    p.write_text("not [valid toml [[[")
    cfg = Config.load(p)
    assert cfg.grace_seconds == 30
    assert any("not valid TOML" in rec.message for rec in caplog.records)


def test_unknown_field_ignored(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent("""\
        grace_seconds = 60
        future_field = "ignore me"
        """))
    cfg = Config.load(p)
    assert cfg.grace_seconds == 60


def test_partial_file_uses_defaults_for_missing(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('status_text = "Custom"\n')
    cfg = Config.load(p)
    assert cfg.status_text == "Custom"
    assert cfg.grace_seconds == 30
    assert cfg.enabled is True


def test_save_creates_parent_dir(tmp_path):
    p = tmp_path / "subdir" / "config.toml"
    Config().save(p)
    assert p.exists()


def test_save_serializes_quotes_and_backslashes(tmp_path):
    p = tmp_path / "config.toml"
    cfg = Config(status_text='He said "go" \\away', status_emoji=":wave:")
    cfg.save(p)
    loaded = Config.load(p)
    assert loaded.status_text == 'He said "go" \\away'
    assert loaded.status_emoji == ":wave:"


@pytest.mark.parametrize("flag", ["enabled", "notifications", "debug"])
def test_bool_round_trip(tmp_path, flag):
    p = tmp_path / "config.toml"
    cfg = Config(**{flag: False})
    cfg.save(p)
    loaded = Config.load(p)
    assert getattr(loaded, flag) is False
