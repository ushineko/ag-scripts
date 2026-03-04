"""Logging configuration using structlog."""

import logging
import os
import sys
from pathlib import Path

import structlog


def get_log_dir() -> Path:
    """Get the log directory, using LOCALAPPDATA on Windows."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    if localappdata:
        return Path(localappdata) / "claude-usage-widget" / "logs"
    return Path.home() / ".claude-usage-widget" / "logs"


def setup_logging(debug: bool = False, log_file: Path | None = None) -> None:
    """Configure structlog for the application."""
    log_level = logging.DEBUG if debug else logging.INFO

    handlers: list[logging.Handler] = []

    console_handler = logging.StreamHandler(sys.stdout)
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
            structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
