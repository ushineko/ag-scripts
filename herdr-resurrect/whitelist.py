"""Classify pane foreground programs: which are safe to re-run, which panes are
idle shells, which are AI-agent panes (left to herdr's resume_agents_on_restore).
"""

from __future__ import annotations

import re

# Foreground process names that mean "just a shell" -> the pane is idle.
SHELLS = {
    "sh", "bash", "zsh", "fish", "dash", "ash", "ksh", "tcsh", "csh", "nu",
}

# Programs safe to relaunch verbatim after a restart. TUIs / viewers / watchers
# with no unsaved external state. Extend via config (allow); trim via config (deny).
DEFAULT_WHITELIST = {
    "btop", "htop", "top", "btm", "glances", "gtop",
    "nvtop", "nvitop", "s-tui", "bandwhich", "bottom", "zenith",
    "lazygit", "gitui", "tig", "lazydocker",
    "yazi", "ranger", "nnn", "lf",
    "nvim", "vim", "vi", "helix", "hx",
    "k9s", "kdash",
    "watch", "tail", "less", "bat", "glow", "ncdu", "ncspot", "gping",
}


def normalize_name(name: str) -> str:
    """Strip a leading '-' (login shells report '-zsh') and any path."""
    return name.lstrip("-").rsplit("/", 1)[-1]


def is_shell(name: str) -> bool:
    return normalize_name(name) in SHELLS


def is_agent_pane(agent_status: str) -> bool:
    """herdr marks non-agent panes 'unknown'; anything else is an agent pane,
    which herdr's resume_agents_on_restore already handles."""
    return agent_status not in ("", "unknown")


def foreground_program(process_info: dict) -> tuple[str, list[str]] | None:
    """Return (name, argv) of the pane's running program, or None if idle.

    A pane is idle when its only foreground process is the shell itself.
    """
    shell_pid = process_info.get("shell_pid")
    for proc in process_info.get("foreground_processes", []):
        if proc.get("pid") == shell_pid:
            continue
        name = normalize_name(proc.get("name", ""))
        if not name or name in SHELLS:
            continue
        argv = proc.get("argv") or (
            [proc["cmdline"]] if proc.get("cmdline") else [name]
        )
        return name, list(argv)
    return None


def effective_whitelist(config: dict) -> set[str]:
    wl = set(DEFAULT_WHITELIST)
    wl |= {normalize_name(x) for x in config.get("whitelist_add", [])}
    wl -= {normalize_name(x) for x in config.get("whitelist_remove", [])}
    return wl


def cmdline_patterns(config: dict) -> list[re.Pattern]:
    """Regexes matched against a pane's full command line. Lets specific
    invocations be captured even when the program name is generic (e.g.
    `python3 -m src.main --tui`)."""
    out: list[re.Pattern] = []
    for p in config.get("cmdline_patterns", []):
        try:
            out.append(re.compile(p))
        except re.error:
            continue
    return out


def is_capturable(name: str, cmdline: str, whitelist: set[str],
                  patterns: list[re.Pattern]) -> bool:
    return name in whitelist or any(p.search(cmdline) for p in patterns)
