"""Logging configuration using structlog."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import structlog

from .platform_support import IS_MACOS


def get_log_dir() -> Path:
    """Get the log directory.

    macOS: ``~/Library/Logs/claude-usage-widget`` (native).
    Windows: ``%LOCALAPPDATA%\\claude-usage-widget\\logs``.
    Other: ``~/.claude-usage-widget/logs``.
    """
    if IS_MACOS:
        return Path.home() / "Library" / "Logs" / "claude-usage-widget"
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        return Path(localappdata) / "claude-usage-widget" / "logs"
    return Path.home() / ".claude-usage-widget" / "logs"


def setup_logging(
    debug: bool = False,
    log_file: Path | None = None,
    stream=None,
    console: bool = True,
) -> None:
    """Configure structlog for the application.

    ``stream`` selects where console logs go (default stdout). The ``--fetch-json``
    child process routes logs to stderr so that stdout carries only the JSON
    payload the parent QProcess parses.

    ``console=False`` keeps logs off the terminal entirely — used by the live
    terminal modes (``--tui``/``--line``), which own the pane (stderr would
    render right over the redrawn status line). Logs then go to ``log_file`` if
    given, otherwise they are discarded.
    """
    log_level = logging.DEBUG if debug else logging.INFO

    # Resolve the single sink structlog (and the stdlib root logger) write to.
    if console:
        out = sys.stdout if stream is None else stream
    elif log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        out = open(log_file, "a", encoding="utf-8")
        log_file = None  # written via `out`; don't add a duplicate handler below
    else:
        out = open(os.devnull, "w")

    handlers: list[logging.Handler] = []

    console_handler = logging.StreamHandler(out)
    console_handler.setLevel(log_level)
    handlers.append(console_handler)

    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(log_level)
        handlers.append(file_handler)

    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=handlers,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer(colors=out.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=out),
        cache_logger_on_first_use=True,
    )
