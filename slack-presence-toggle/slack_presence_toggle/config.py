from __future__ import annotations

import logging
import tomllib
from dataclasses import asdict, dataclass, fields
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "slack-presence-toggle" / "config.toml"
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "slack-presence-toggle" / "token"


@dataclass
class Config:
    enabled: bool = True
    grace_seconds: int = 30
    token_file: str = str(DEFAULT_TOKEN_PATH)
    notifications: bool = True
    debug: bool = False
    slack_resource_class: str = "Slack"
    status_text: str = "Heads down"
    status_emoji: str = ":dart:"
    status_safety_buffer_seconds: int = 3600

    @classmethod
    def load(cls, path: Path = DEFAULT_CONFIG_PATH) -> Config:
        if not path.exists():
            return cls()
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as e:
            log.warning("config file %s is not valid TOML (%s); using defaults", path, e)
            return cls()
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def save(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for k, v in asdict(self).items():
                f.write(f"{k} = {_toml_value(v)}\n")


def _toml_value(v: object) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        # Escape backslashes and double quotes; TOML basic strings don't need more.
        escaped = v.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(v, int):
        return str(v)
    raise TypeError(f"unsupported config value type: {type(v).__name__}")
