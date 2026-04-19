#!/usr/bin/env python3
"""Print the tmux session name mapped to a given directory.

Called by the vscode-launcher zsh hook on shell startup. Given a path (PWD),
walks up parents looking for a direct match in `tmux_mappings`, and also
checks any .code-workspace mappings by resolving their `folders` entries.

Exit 0 and print the session name if a match is found; exit 1 with no output
otherwise. Always silent on errors so it can be used in shell startup without
risk of breaking the shell.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "vscode-launcher" / "workspaces.json"


def resolve_workspace_folders(workspace_file: str) -> list[str]:
    """Resolve the folder paths listed inside a .code-workspace file.

    Relative paths resolve against the workspace file's directory.
    Returns an empty list on any error.
    """
    try:
        data = json.loads(Path(workspace_file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    folders = data.get("folders", []) or []
    base = os.path.dirname(os.path.abspath(workspace_file))
    resolved: list[str] = []
    for entry in folders:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path", "")
        if not isinstance(path, str) or not path.strip():
            continue
        path = path.strip()
        if not os.path.isabs(path):
            path = os.path.normpath(os.path.join(base, path))
        else:
            path = os.path.normpath(path)
        resolved.append(path)
    return resolved


def is_under(child: str, parent: str) -> bool:
    """True if `child` equals or is contained within `parent`."""
    child = os.path.normpath(child)
    parent = os.path.normpath(parent)
    if child == parent:
        return True
    return child.startswith(parent + os.sep)


def lookup_session(pwd: str, mappings: dict[str, str]) -> str | None:
    """Find the tmux session for `pwd` using:

    1. Parent-walk: find the longest ancestor of `pwd` present in `mappings`.
    2. Workspace-folder resolution: for any `.code-workspace` key in `mappings`,
       parse its `folders` and return its session if `pwd` lies under one.
    """
    if not pwd:
        return None
    pwd = os.path.normpath(os.path.abspath(pwd))

    # 1. Parent walk
    current = pwd
    while True:
        if current in mappings:
            return mappings[current]
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    # 2. .code-workspace folders
    for key, session in mappings.items():
        if not key.endswith(".code-workspace"):
            continue
        for folder in resolve_workspace_folders(key):
            if is_under(pwd, folder):
                return session

    return None


def main() -> int:
    pwd = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PWD", "")
    if not pwd:
        return 1
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 1
    mappings = data.get("tmux_mappings", {}) or {}
    if not isinstance(mappings, dict):
        return 1
    session = lookup_session(pwd, mappings)
    if session:
        print(session)
        return 0
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Belt-and-suspenders: never let this script error out to the shell
        sys.exit(1)
