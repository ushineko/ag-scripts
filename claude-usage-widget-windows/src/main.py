"""Claude Usage Widget for Windows — Main entry point.

Displays Claude Code API usage as a floating desktop widget with system tray icon.
Uses the Anthropic OAuth API for authoritative usage data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import structlog

from .logging_config import setup_logging


def parse_args():
    parser = argparse.ArgumentParser(
        description="Claude Usage Widget — Track Claude Code API usage",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--no-gui", action="store_true", help="Fetch and print usage, then exit")
    parser.add_argument(
        "--fetch-json",
        action="store_true",
        help="Fetch usage and print it as JSON to stdout, then exit (used internally "
        "by the GUI's QProcess fetcher; logs go to stderr).",
    )
    parser.add_argument("--log-file", type=Path, help="Write logs to file")
    return parser.parse_args()


args = parse_args()
# In --fetch-json mode stdout must carry only the JSON payload, so send logs to
# stderr; otherwise log to stdout as usual.
setup_logging(
    debug=args.debug,
    log_file=args.log_file,
    stream=sys.stderr if args.fetch_json else sys.stdout,
)
log = structlog.get_logger(__name__)


def run_fetch_json() -> int:
    """Fetch usage and write it to stdout as JSON (the QProcess child path)."""
    from .oauth import fetch_claude_usage

    data = fetch_claude_usage()
    sys.stdout.write(json.dumps(data))
    sys.stdout.flush()
    return 0


def run_no_gui() -> int:
    """Fetch usage from the API and print to console, then exit."""
    from .oauth import fetch_claude_usage, is_claude_installed, get_time_until_reset
    from .display import format_percentage, usage_color

    log.info("starting_console_mode")

    print(f"\n{'=' * 50}")
    print("Claude Usage Widget — Console Mode")
    print(f"{'=' * 50}\n")

    if not is_claude_installed():
        print("WARNING: Claude CLI not found in PATH.")

    data = fetch_claude_usage()

    if data is None:
        print("No credentials found. Run `claude login` first.")
        return 1

    error = data.get("error")
    if error:
        print(f"Error: {error}")
        return 1

    five_hour = data.get("five_hour", {})
    seven_day = data.get("seven_day", {})

    util_5h = five_hour.get("utilization")
    util_7d = seven_day.get("utilization")
    resets_at = five_hour.get("resets_at", "")

    print(f"5-hour utilization:  {format_percentage(util_5h)}")
    if resets_at:
        print(f"5-hour resets in:    {get_time_until_reset(resets_at)}")
    print(f"7-day utilization:   {format_percentage(util_7d)}")
    print(f"Status color:        {usage_color(util_5h)}")
    print()

    log.info("console_done", five_hour=util_5h, seven_day=util_7d)
    return 0


def run_gui() -> None:
    """Run the PySide6 GUI application."""
    from PySide6.QtCore import QTimer, QLockFile, QStandardPaths
    from PySide6.QtWidgets import QApplication

    from .config import load_config
    from .oauth import reset_oauth_backoff
    from .fetcher import UsageFetcher
    from .widget import FloatingWidget
    from .tray import SystemTray

    log.info("starting_gui_mode")

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Single-instance lock
    lock_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.TempLocation)
    lock_file = QLockFile(f"{lock_dir}/claude-usage-widget.lock")
    if not lock_file.tryLock(100):
        log.warning("another_instance_running")
        print("Another instance of Claude Usage Widget is already running.")
        sys.exit(1)

    # State. Usage is fetched in a child process via QProcess (see fetcher.py),
    # driven by the Qt event loop — no worker threads.
    fetcher: UsageFetcher | None = None
    last_data: dict | None = None

    # Load config
    config = load_config()
    opacity = config.get("opacity", 0.95)
    position = config.get("widget_position")
    font_size = config.get("font_size", 9)

    # Adaptive polling. The usage endpoint rate-limits (HTTP 429); each fetch is
    # a fresh QProcess with no shared state, so the backoff lives here in the
    # long-lived GUI: on 429 we lengthen the poll interval (exponential, capped),
    # and reset to the base cadence on the next success.
    base_interval_ms = max(5, config.get("update_interval_seconds", 60)) * 1000
    MAX_INTERVAL_MS = 30 * 60 * 1000
    MAX_BACKOFF_LEVEL = 6
    backoff_level = 0

    # Create widget and tray
    def on_toggle_widget():
        if widget.isVisible():
            widget.hide()
        else:
            widget.show()
            widget.raise_()

    def on_refresh():
        nonlocal backoff_level
        reset_oauth_backoff()
        if backoff_level:
            backoff_level = 0
            timer.setInterval(base_interval_ms)
        trigger_update()

    def on_exit():
        log.info("exit_requested")
        tray.hide()
        app.quit()

    widget = FloatingWidget(
        on_refresh=on_refresh,
        on_exit=on_exit,
        opacity=opacity,
        position=position,
        font_size=font_size,
    )

    tray = SystemTray(
        on_toggle_widget=on_toggle_widget,
        on_refresh=on_refresh,
        on_exit=on_exit,
    )

    def on_data_ready(data):
        # result_ready fires once, after the child QProcess has finished, so it
        # is safe to release the fetcher here (deleteLater defers actual
        # destruction to the event loop). No QThread teardown race.
        nonlocal fetcher, last_data, backoff_level
        last_data = data
        widget.update_usage(data)
        tray.update_usage(data)
        if fetcher is not None:
            fetcher.deleteLater()
            fetcher = None

        # Adjust the poll cadence based on the result.
        err = data.get("error") if isinstance(data, dict) else "fetch_failed"
        if err == "rate_limited":
            backoff_level = min(backoff_level + 1, MAX_BACKOFF_LEVEL)
            retry_ms = (data.get("retry_after") or 0) * 1000
            next_ms = min(max(base_interval_ms * (2 ** backoff_level), retry_ms), MAX_INTERVAL_MS)
            if timer.interval() != next_ms:
                timer.setInterval(next_ms)
            log.warning("poll_backoff", level=backoff_level, next_interval_s=next_ms // 1000)
        elif err is None:
            # Genuine success — return to the base cadence.
            if backoff_level:
                backoff_level = 0
                timer.setInterval(base_interval_ms)
                log.info("poll_backoff_reset")
        else:
            # api_error / offline / fetch_failed: keep last data and the current
            # cadence; don't reset backoff (avoids hammering through a 429 window).
            log.debug("poll_soft_error", error=err)

    def trigger_update():
        nonlocal fetcher
        if fetcher is not None:
            log.debug("update_skipped_fetch_busy")
            return
        fetcher = UsageFetcher()
        fetcher.result_ready.connect(on_data_ready)
        fetcher.start()

    # Timer for periodic updates (interval adapts via on_data_ready backoff)
    timer = QTimer()
    timer.timeout.connect(trigger_update)
    timer.start(base_interval_ms)

    # Initial fetch
    trigger_update()

    widget.show()
    log.info("gui_running")
    sys.exit(app.exec())


def main():
    log.info(
        "claude_usage_widget_starting",
        debug=args.debug,
        no_gui=args.no_gui,
        fetch_json=args.fetch_json,
    )
    if args.fetch_json:
        sys.exit(run_fetch_json())
    elif args.no_gui:
        sys.exit(run_no_gui())
    else:
        run_gui()


if __name__ == "__main__":
    main()
