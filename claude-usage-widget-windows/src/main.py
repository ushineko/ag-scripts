"""
Claude Usage Widget for Windows - Main entry point.

A lightweight system tray widget that displays Claude Code CLI usage metrics.
"""

import argparse
import sys
import threading
from pathlib import Path
from typing import Optional

import structlog

from .logging_config import setup_logging

# Parse args early so we can set up logging before importing other modules
def parse_args():
    parser = argparse.ArgumentParser(
        description="Claude Usage Widget - Track Claude Code CLI usage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main                  # Normal GUI mode
  python -m src.main --debug          # GUI with debug logging
  python -m src.main --no-gui         # Console mode, single scan, then exit
  python -m src.main --no-gui --debug # Console mode with debug logging
""",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging (verbose output)",
    )
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Run without GUI - scan and print stats, then exit",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        help="Write logs to file (in addition to console)",
    )
    return parser.parse_args()


# Parse args and set up logging first
args = parse_args()
setup_logging(debug=args.debug, log_file=args.log_file)
log = structlog.get_logger(__name__)

# Now import the rest (after logging is configured)
from .config import is_claude_installed, get_setting, get_claude_projects_dir
from .claude_stats import (
    get_session_window,
    get_claude_stats,
    get_time_until_reset,
    format_tokens,
    calculate_usage_percentage,
    get_usage_color,
)


def run_no_gui():
    """Run in console mode - scan and print stats, then exit."""
    log.info("starting_no_gui_mode")

    # Check Claude installation
    claude_installed = is_claude_installed()
    projects_dir = get_claude_projects_dir()

    print(f"\n{'='*60}")
    print("Claude Usage Widget - Console Mode")
    print(f"{'='*60}\n")

    print(f"Claude projects dir: {projects_dir}")
    print(f"Claude installed: {claude_installed}")
    print(f"Projects dir exists: {projects_dir.exists()}")

    if not claude_installed:
        print("\nWARNING: Claude CLI does not appear to be installed.")
        print(f"Expected directory: {projects_dir.parent}")
        log.warning("claude_not_installed", expected_dir=str(projects_dir.parent))
        return 1

    # Get settings
    budget = get_setting("session_budget", 500000)
    window_hours = get_setting("window_hours", 4)
    reset_hour = get_setting("reset_hour", 2)
    offset = get_setting("token_offset", 0)

    print(f"\nSettings:")
    print(f"  Budget: {format_tokens(budget)}")
    print(f"  Window: {window_hours} hours")
    print(f"  Reset hour: {reset_hour:02d}:00")
    print(f"  Token offset: {offset:+d}")

    # Get session window
    window_start, window_end = get_session_window()
    window_str, countdown_str, hours, minutes = get_time_until_reset(window_start, window_end)

    print(f"\nCurrent window: {window_str}")
    print(f"Time until reset: {countdown_str}")

    # Get stats
    print(f"\nScanning {projects_dir}...")
    stats = get_claude_stats(window_start, window_end)

    if stats is None:
        print("\nNo usage data found in current window.")
        log.warning("no_stats_found")
        return 0

    # Calculate percentage
    adjusted_tokens = stats["session_tokens"] + offset
    percentage = calculate_usage_percentage(stats["session_tokens"])
    color = get_usage_color(percentage)

    print(f"\n{'='*60}")
    print("RESULTS")
    print(f"{'='*60}")
    print(f"\nFiles processed: {stats['files_processed']}")
    print(f"API calls: {stats['api_calls']}")
    print(f"\nTokens:")
    print(f"  Input:  {format_tokens(stats['input_tokens'])}")
    print(f"  Output: {format_tokens(stats['output_tokens'])}")
    print(f"  Total:  {format_tokens(stats['session_tokens'])}")
    if offset != 0:
        print(f"  Adjusted (with offset): {format_tokens(adjusted_tokens)}")
    print(f"\nCache:")
    print(f"  Read:    {format_tokens(stats['cache_read'])}")
    print(f"  Created: {format_tokens(stats['cache_create'])}")
    print(f"\nUsage: {format_tokens(adjusted_tokens)} / {format_tokens(budget)} ({percentage:.1f}%)")
    print(f"Status: {color.upper()}")
    print()

    log.info(
        "scan_complete",
        tokens=stats["session_tokens"],
        percentage=percentage,
        color=color,
        api_calls=stats["api_calls"],
    )

    return 0


def run_gui():
    """Run the GUI application with floating widget."""
    from .widget import FloatingWidget
    from .tray import TrayIcon
    from .calibration import CalibrationDialog

    log.info("starting_gui_mode")

    # Shared state
    widget: Optional[FloatingWidget] = None
    tray: Optional[TrayIcon] = None

    def on_calibrate():
        """Show calibration dialog."""
        log.debug("showing_calibration")
        window_start, window_end = get_session_window()
        stats = get_claude_stats(window_start, window_end)
        current_tokens = stats["session_tokens"] if stats else 0

        def on_complete():
            if widget:
                widget.update()
            if tray:
                tray.update()

        dialog = CalibrationDialog(
            current_tokens=current_tokens,
            on_complete=on_complete,
        )
        dialog.show()

    def on_exit():
        """Exit the application."""
        log.info("exit_requested")
        if tray:
            tray.stop()
        if widget:
            widget.stop()
        sys.exit(0)

    # Check if Claude is installed
    if not is_claude_installed():
        log.warning("claude_not_installed")
        print("Warning: Claude CLI does not appear to be installed.")
        print("The widget will run but show no data until Claude is configured.")

    # Create tray icon (runs in background thread for settings access)
    log.debug("creating_tray_icon")
    tray = TrayIcon(
        on_show_popup=None,  # Widget is always visible
        on_calibrate=on_calibrate,
    )

    # Run tray in separate thread
    log.debug("starting_tray_thread")
    tray_thread = threading.Thread(target=tray.run, daemon=True)
    tray_thread.start()

    # Create and run floating widget (main thread)
    log.debug("creating_floating_widget")
    widget = FloatingWidget(
        on_calibrate=on_calibrate,
        on_exit=on_exit,
    )

    try:
        widget.run()
    except KeyboardInterrupt:
        log.info("keyboard_interrupt")
    except Exception as e:
        log.exception("fatal_error", error=str(e))
    finally:
        on_exit()


def main():
    """Main entry point."""
    log.info(
        "claude_usage_widget_starting",
        debug=args.debug,
        no_gui=args.no_gui,
        log_file=str(args.log_file) if args.log_file else None,
    )

    if args.no_gui:
        sys.exit(run_no_gui())
    else:
        run_gui()


if __name__ == "__main__":
    main()
