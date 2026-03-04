"""Claude Usage Widget for Windows — Main entry point.

Displays Claude Code API usage as a floating desktop widget with system tray icon.
Uses the Anthropic OAuth API for authoritative usage data.
"""

import argparse
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
    parser.add_argument("--log-file", type=Path, help="Write logs to file")
    return parser.parse_args()


args = parse_args()
setup_logging(debug=args.debug, log_file=args.log_file)
log = structlog.get_logger(__name__)


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
    from PySide6.QtCore import QTimer, QLockFile, QStandardPaths, QThread, Signal, QObject
    from PySide6.QtWidgets import QApplication

    from .config import get_setting, load_config
    from .oauth import fetch_claude_usage, reset_oauth_backoff
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

    # Worker for background API calls
    class UsageWorker(QThread):
        result_ready = Signal(object)

        def run(self):
            data = fetch_claude_usage()
            self.result_ready.emit(data)

    # State
    worker: UsageWorker | None = None
    last_data: dict | None = None

    # Load config
    config = load_config()
    opacity = config.get("opacity", 0.95)
    position = config.get("widget_position")

    # Create widget and tray
    def on_toggle_widget():
        if widget.isVisible():
            widget.hide()
        else:
            widget.show()
            widget.raise_()

    def on_refresh():
        reset_oauth_backoff()
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
    )

    tray = SystemTray(
        on_toggle_widget=on_toggle_widget,
        on_refresh=on_refresh,
        on_exit=on_exit,
    )

    def on_data_ready(data):
        nonlocal worker, last_data
        last_data = data
        widget.update_usage(data)
        tray.update_usage(data)
        # Clean up worker
        if worker:
            worker.deleteLater()
            worker = None

    def trigger_update():
        nonlocal worker
        if worker is not None and worker.isRunning():
            log.debug("update_skipped_worker_busy")
            return
        worker = UsageWorker()
        worker.result_ready.connect(on_data_ready)
        worker.start()

    # Timer for periodic updates
    interval_ms = config.get("update_interval_seconds", 30) * 1000
    timer = QTimer()
    timer.timeout.connect(trigger_update)
    timer.start(interval_ms)

    # Initial fetch
    trigger_update()

    widget.show()
    log.info("gui_running")
    sys.exit(app.exec())


def main():
    log.info("claude_usage_widget_starting", debug=args.debug, no_gui=args.no_gui)
    if args.no_gui:
        sys.exit(run_no_gui())
    else:
        run_gui()


if __name__ == "__main__":
    main()
