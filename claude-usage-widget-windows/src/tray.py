"""System tray integration using pystray."""

import threading
from typing import Callable, Optional

import pystray
import structlog
from PIL import Image, ImageDraw

from .config import get_setting, set_setting, is_claude_installed
from .claude_stats import (
    get_session_window,
    get_time_until_reset,
    get_claude_stats,
    format_tokens,
    calculate_usage_percentage,
    get_usage_color,
)

log = structlog.get_logger(__name__)


class TrayIcon:
    """System tray icon manager."""

    def __init__(
        self,
        on_show_popup: Callable = None,
        on_calibrate: Callable = None,
        on_settings: Callable = None,
    ):
        self.on_show_popup = on_show_popup
        self.on_calibrate = on_calibrate
        self.on_settings = on_settings

        self.icon: Optional[pystray.Icon] = None
        self.current_color = "green"
        self.current_percentage = 0.0
        self.last_stats = None
        self.update_timer: Optional[threading.Timer] = None
        self.running = False
        log.debug("tray_icon_initialized")

    def create_icon_image(self, color: str = "green", percentage: float = 0) -> Image:
        """Create a tray icon image with the specified color and percentage."""
        size = 64
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Color mapping
        colors = {
            "green": "#22c55e",
            "yellow": "#eab308",
            "red": "#ef4444",
            "gray": "#6b7280",
        }
        fill_color = colors.get(color, colors["gray"])

        # Draw outer circle (border)
        border_width = 4
        draw.ellipse(
            [border_width, border_width, size - border_width, size - border_width],
            outline=fill_color,
            width=border_width,
        )

        # Draw filled arc based on percentage
        if percentage > 0:
            # Draw from top (270 degrees) clockwise
            start_angle = 270
            end_angle = 270 + (percentage / 100) * 360
            draw.pieslice(
                [border_width + 4, border_width + 4, size - border_width - 4, size - border_width - 4],
                start=start_angle,
                end=end_angle,
                fill=fill_color,
            )

        log.debug("icon_image_created", color=color, percentage=percentage)
        return image

    def get_tooltip(self) -> str:
        """Generate tooltip text based on current stats."""
        if not is_claude_installed():
            return "Claude Usage Widget - Not installed"

        if self.last_stats is None:
            return "Claude Usage Widget - No activity"

        budget = get_setting("session_budget", 500000)
        offset = get_setting("token_offset", 0)
        adjusted_tokens = self.last_stats["session_tokens"] + offset

        return (
            f"Claude: {format_tokens(adjusted_tokens)} / {format_tokens(budget)} "
            f"({self.current_percentage:.0f}%)"
        )

    def build_menu(self) -> pystray.Menu:
        """Build the context menu."""
        budget = get_setting("session_budget", 500000)
        window_hours = get_setting("window_hours", 4)
        reset_hour = get_setting("reset_hour", 2)

        def make_budget_setter(value):
            def setter(icon, item):
                set_setting("session_budget", value)
                self.update()
            return setter

        def make_window_setter(value):
            def setter(icon, item):
                set_setting("window_hours", value)
                self.update()
            return setter

        def make_reset_setter(value):
            def setter(icon, item):
                set_setting("reset_hour", value)
                self.update()
            return setter

        budget_options = [
            ("100k", 100000), ("200k", 200000), ("250k", 250000), ("300k", 300000),
            ("400k", 400000), ("500k", 500000), ("750k", 750000), ("1M", 1000000),
            ("1.5M", 1500000), ("2M", 2000000),
        ]
        budget_menu = pystray.Menu(
            *[
                pystray.MenuItem(
                    label,
                    make_budget_setter(value),
                    checked=lambda item, v=value: budget == v,
                )
                for label, value in budget_options
            ]
        )

        window_options = [
            ("30 min", 0.5), ("1 hour", 1), ("1.5 hours", 1.5), ("2 hours", 2),
            ("3 hours", 3), ("4 hours", 4), ("5 hours", 5), ("6 hours", 6),
            ("8 hours", 8), ("10 hours", 10), ("12 hours", 12),
        ]
        window_menu = pystray.Menu(
            *[
                pystray.MenuItem(
                    label,
                    make_window_setter(value),
                    checked=lambda item, v=value: window_hours == v,
                )
                for label, value in window_options
            ]
        )

        reset_menu = pystray.Menu(
            *[
                pystray.MenuItem(
                    f"{h:02d}:00",
                    make_reset_setter(h),
                    checked=lambda item, hour=h: reset_hour == hour,
                )
                for h in range(0, 24)  # All 24 hours
            ]
        )

        log.debug("menu_built")
        return pystray.Menu(
            pystray.MenuItem("Show Details", self._on_left_click, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Budget", budget_menu),
            pystray.MenuItem("Window Duration", window_menu),
            pystray.MenuItem("Reset Hour", reset_menu),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Calibrate...", self._on_calibrate),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", self._on_exit),
        )

    def _on_left_click(self, icon=None, item=None):
        """Handle left-click to show popup."""
        log.debug("left_click")
        if self.on_show_popup:
            self.on_show_popup()

    def _on_calibrate(self, icon=None, item=None):
        """Handle calibrate menu item."""
        log.debug("calibrate_clicked")
        if self.on_calibrate:
            self.on_calibrate()

    def _on_settings(self, icon=None, item=None):
        """Handle settings menu item."""
        log.debug("settings_clicked")
        if self.on_settings:
            self.on_settings()

    def _on_exit(self, icon=None, item=None):
        """Handle exit menu item."""
        log.info("exit_requested")
        self.stop()

    def update(self):
        """Update the icon based on current stats."""
        log.debug("update_started")
        if not self.icon:
            log.warning("update_skipped_no_icon")
            return

        # Get current stats
        window_start, window_end = get_session_window()
        self.last_stats = get_claude_stats(window_start, window_end)

        if self.last_stats:
            self.current_percentage = calculate_usage_percentage(
                self.last_stats["session_tokens"]
            )
            self.current_color = get_usage_color(self.current_percentage)
            log.info(
                "update_complete",
                percentage=self.current_percentage,
                color=self.current_color,
                tokens=self.last_stats["session_tokens"],
            )
        else:
            self.current_percentage = 0.0
            self.current_color = "gray"
            log.info("update_complete_no_stats", color="gray")

        # Update icon
        self.icon.icon = self.create_icon_image(
            self.current_color, self.current_percentage
        )
        self.icon.title = self.get_tooltip()

    def _schedule_update(self):
        """Schedule the next update."""
        if not self.running:
            return

        interval = get_setting("update_interval_seconds", 30)
        self.update_timer = threading.Timer(interval, self._update_loop)
        self.update_timer.daemon = True
        self.update_timer.start()
        log.debug("update_scheduled", interval_seconds=interval)

    def _update_loop(self):
        """Update loop that runs periodically."""
        if not self.running:
            return

        try:
            self.update()
        except Exception as e:
            log.exception("update_error", error=str(e))
        self._schedule_update()

    def run(self):
        """Start the tray icon."""
        log.info("tray_starting")
        self.running = True

        # Initial icon
        initial_image = self.create_icon_image("gray", 0)

        self.icon = pystray.Icon(
            "claude-usage",
            initial_image,
            "Claude Usage Widget",
            menu=self.build_menu(),
        )
        log.info("tray_icon_created")

        # Do initial update
        self.update()

        # Schedule periodic updates
        self._schedule_update()

        # Run the icon (blocking)
        log.info("tray_running")
        self.icon.run()

    def stop(self):
        """Stop the tray icon."""
        log.info("tray_stopping")
        self.running = False

        if self.update_timer:
            self.update_timer.cancel()
            self.update_timer = None

        if self.icon:
            self.icon.stop()
            self.icon = None
        log.info("tray_stopped")

    def get_current_stats(self) -> dict:
        """Get the current stats for display in popup."""
        if self.last_stats is None:
            return {
                "session_tokens": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_read": 0,
                "cache_create": 0,
                "api_calls": 0,
                "percentage": 0.0,
                "color": "gray",
                "window_str": "--:-- - --:--",
                "countdown_str": "N/A",
                "budget": get_setting("session_budget", 500000),
            }

        window_start, window_end = get_session_window()
        window_str, countdown_str, _, _ = get_time_until_reset(window_start, window_end)
        offset = get_setting("token_offset", 0)

        return {
            "session_tokens": self.last_stats["session_tokens"] + offset,
            "input_tokens": self.last_stats["input_tokens"],
            "output_tokens": self.last_stats["output_tokens"],
            "cache_read": self.last_stats["cache_read"],
            "cache_create": self.last_stats["cache_create"],
            "api_calls": self.last_stats["api_calls"],
            "percentage": self.current_percentage,
            "color": self.current_color,
            "window_str": window_str,
            "countdown_str": countdown_str,
            "budget": get_setting("session_budget", 500000),
        }
