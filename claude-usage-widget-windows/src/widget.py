"""Always-on-top floating widget showing Claude usage."""

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk
import structlog

from .config import get_setting, set_setting
from .claude_stats import (
    get_session_window,
    get_time_until_reset,
    get_claude_stats,
    format_tokens,
    calculate_usage_percentage,
    get_usage_color,
)

log = structlog.get_logger(__name__)


class FloatingWidget:
    """Always-visible floating widget showing Claude usage with progress bar."""

    def __init__(self, on_calibrate: Callable = None, on_exit: Callable = None):
        """
        Initialize the floating widget.

        Args:
            on_calibrate: Callback for calibration
            on_exit: Callback for exit
        """
        self.on_calibrate = on_calibrate
        self.on_exit = on_exit

        self.root: Optional[ctk.CTk] = None
        self.update_timer: Optional[str] = None
        self.running = False

        # Widget references
        self.window_label: Optional[ctk.CTkLabel] = None
        self.progress_bar: Optional[ctk.CTkProgressBar] = None
        self.percentage_label: Optional[ctk.CTkLabel] = None
        self.tokens_label: Optional[ctk.CTkLabel] = None
        self.calls_label: Optional[ctk.CTkLabel] = None

        # Drag state
        self._drag_start_x = 0
        self._drag_start_y = 0

        # Context menu
        self.context_menu: Optional[tk.Menu] = None

        log.debug("floating_widget_initialized")

    def _get_color_hex(self, color: str) -> str:
        """Convert color name to hex."""
        colors = {
            "green": "#22c55e",
            "yellow": "#eab308",
            "red": "#ef4444",
            "gray": "#6b7280",
        }
        return colors.get(color, colors["gray"])

    def _start_drag(self, event):
        """Start dragging the widget."""
        self._drag_start_x = event.x
        self._drag_start_y = event.y

    def _drag(self, event):
        """Handle dragging the widget."""
        x = self.root.winfo_x() + (event.x - self._drag_start_x)
        y = self.root.winfo_y() + (event.y - self._drag_start_y)
        self.root.geometry(f"+{x}+{y}")

    def _build_ui(self):
        """Build the widget UI."""
        # Configure window
        self.root.title("Claude Usage")
        self.root.geometry("280x140")
        self.root.resizable(False, False)
        self.root.overrideredirect(True)  # Remove window decorations
        self.root.attributes("-topmost", True)  # Always on top
        self.root.attributes("-alpha", 0.95)  # Slight transparency

        # Position in bottom-right corner
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = screen_width - 300
        y = screen_height - 200
        self.root.geometry(f"+{x}+{y}")

        # Main frame with border
        main_frame = ctk.CTkFrame(
            self.root,
            corner_radius=10,
            border_width=2,
            border_color="#374151",
        )
        main_frame.pack(fill="both", expand=True, padx=2, pady=2)

        # Make frame draggable
        main_frame.bind("<Button-1>", self._start_drag)
        main_frame.bind("<B1-Motion>", self._drag)

        # Header frame with title and close button
        header_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        header_frame.pack(fill="x", padx=8, pady=(8, 4))

        title_label = ctk.CTkLabel(
            header_frame,
            text="Claude Code",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        title_label.pack(side="left")
        title_label.bind("<Button-1>", self._start_drag)
        title_label.bind("<B1-Motion>", self._drag)

        # Close button
        close_btn = ctk.CTkButton(
            header_frame,
            text="×",
            width=24,
            height=24,
            corner_radius=4,
            fg_color="transparent",
            hover_color="#4b5563",
            command=self._on_close,
        )
        close_btn.pack(side="right")

        # Window time label
        self.window_label = ctk.CTkLabel(
            main_frame,
            text="Window: --:-- - --:--",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
        )
        self.window_label.pack(pady=(0, 6))
        self.window_label.bind("<Button-1>", self._start_drag)
        self.window_label.bind("<B1-Motion>", self._drag)

        # Progress bar frame
        progress_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        progress_frame.pack(fill="x", padx=12, pady=(0, 4))

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            width=200,
            height=16,
            corner_radius=4,
        )
        self.progress_bar.pack(side="left")
        self.progress_bar.set(0)

        self.percentage_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=45,
        )
        self.percentage_label.pack(side="right", padx=(8, 0))

        # Stats frame
        stats_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        stats_frame.pack(fill="x", padx=12, pady=(4, 8))

        self.tokens_label = ctk.CTkLabel(
            stats_frame,
            text="0 / 0",
            font=ctk.CTkFont(size=11),
            text_color="#d1d5db",
        )
        self.tokens_label.pack(side="left")

        self.calls_label = ctk.CTkLabel(
            stats_frame,
            text="0 calls",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
        )
        self.calls_label.pack(side="right")

        # Build context menu
        self._build_context_menu()

        # Bind right-click to all widgets
        for widget in [main_frame, title_label, self.window_label,
                       self.tokens_label, self.calls_label]:
            widget.bind("<Button-3>", self._show_context_menu)

        log.debug("widget_ui_built")

    def _build_context_menu(self):
        """Build the right-click context menu with all tuning options."""
        self.context_menu = tk.Menu(self.root, tearoff=0, bg="#2b2b2b", fg="#e0e0e0",
                                    activebackground="#4b5563", activeforeground="#ffffff")

        # Budget submenu - more granular options
        budget_menu = tk.Menu(self.context_menu, tearoff=0, bg="#2b2b2b", fg="#e0e0e0",
                              activebackground="#4b5563", activeforeground="#ffffff")
        budget_options = [
            ("100k", 100000), ("200k", 200000), ("250k", 250000), ("300k", 300000),
            ("400k", 400000), ("500k", 500000), ("750k", 750000), ("1M", 1000000),
            ("1.5M", 1500000), ("2M", 2000000),
        ]
        current_budget = get_setting("session_budget", 500000)
        for label, value in budget_options:
            budget_menu.add_radiobutton(
                label=label,
                value=value,
                variable=tk.IntVar(value=current_budget),
                command=lambda v=value: self._set_budget(v),
            )
        self.context_menu.add_cascade(label="Budget", menu=budget_menu)

        # Window Duration submenu - more granular options
        window_menu = tk.Menu(self.context_menu, tearoff=0, bg="#2b2b2b", fg="#e0e0e0",
                              activebackground="#4b5563", activeforeground="#ffffff")
        window_options = [
            ("30 min", 0.5), ("1 hour", 1), ("1.5 hours", 1.5), ("2 hours", 2),
            ("3 hours", 3), ("4 hours", 4), ("5 hours", 5), ("6 hours", 6),
            ("8 hours", 8), ("10 hours", 10), ("12 hours", 12),
        ]
        current_window = get_setting("window_hours", 4)
        for label, value in window_options:
            window_menu.add_radiobutton(
                label=label,
                value=value,
                variable=tk.DoubleVar(value=current_window),
                command=lambda v=value: self._set_window_hours(v),
            )
        self.context_menu.add_cascade(label="Window Duration", menu=window_menu)

        # Reset Hour submenu - all 24 hours
        reset_menu = tk.Menu(self.context_menu, tearoff=0, bg="#2b2b2b", fg="#e0e0e0",
                             activebackground="#4b5563", activeforeground="#ffffff")
        current_reset = get_setting("reset_hour", 2)
        for hour in range(24):
            reset_menu.add_radiobutton(
                label=f"{hour:02d}:00",
                value=hour,
                variable=tk.IntVar(value=current_reset),
                command=lambda h=hour: self._set_reset_hour(h),
            )
        self.context_menu.add_cascade(label="Reset Hour", menu=reset_menu)

        self.context_menu.add_separator()

        # Calibrate option
        self.context_menu.add_command(label="Calibrate...", command=self._on_calibrate)

        self.context_menu.add_separator()

        # Exit option
        self.context_menu.add_command(label="Exit", command=self._on_close)

    def _show_context_menu(self, event):
        """Show the context menu at the cursor position."""
        try:
            # Rebuild menu to update checked states
            self._build_context_menu()
            self.context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.context_menu.grab_release()

    def _set_budget(self, value: int):
        """Set budget and update display."""
        log.info("budget_changed", value=value)
        set_setting("session_budget", value)
        self._update_display()

    def _set_window_hours(self, value: float):
        """Set window hours and update display."""
        log.info("window_hours_changed", value=value)
        set_setting("window_hours", value)
        self._update_display()

    def _set_reset_hour(self, value: int):
        """Set reset hour and update display."""
        log.info("reset_hour_changed", value=value)
        set_setting("reset_hour", value)
        self._update_display()

    def _on_calibrate(self):
        """Handle calibrate menu item."""
        log.debug("calibrate_clicked")
        if self.on_calibrate:
            self.on_calibrate()

    def _update_display(self):
        """Update the widget with current stats."""
        if not self.running or not self.root:
            return

        try:
            # Get current stats
            window_start, window_end = get_session_window()
            window_str, countdown_str, _, _ = get_time_until_reset(window_start, window_end)
            stats = get_claude_stats(window_start, window_end)

            budget = get_setting("session_budget", 500000)
            offset = get_setting("token_offset", 0)

            if stats:
                session_tokens = stats["session_tokens"] + offset
                percentage = calculate_usage_percentage(stats["session_tokens"])
                color = get_usage_color(percentage)
                api_calls = stats["api_calls"]
            else:
                session_tokens = 0
                percentage = 0.0
                color = "gray"
                api_calls = 0

            color_hex = self._get_color_hex(color)

            # Update UI
            self.window_label.configure(text=f"{window_str}  ({countdown_str} left)")

            self.progress_bar.set(percentage / 100.0)
            self.progress_bar.configure(progress_color=color_hex)

            self.percentage_label.configure(
                text=f"{percentage:.0f}%",
                text_color=color_hex,
            )

            self.tokens_label.configure(
                text=f"{format_tokens(session_tokens)} / {format_tokens(budget)}"
            )

            self.calls_label.configure(text=f"{api_calls} calls")

            log.debug(
                "widget_updated",
                percentage=percentage,
                tokens=session_tokens,
                calls=api_calls,
            )

        except Exception as e:
            log.exception("widget_update_error", error=str(e))

        # Schedule next update
        if self.running:
            interval = get_setting("update_interval_seconds", 30) * 1000
            self.update_timer = self.root.after(interval, self._update_display)

    def _on_close(self):
        """Handle close button."""
        log.info("widget_close_requested")
        if self.on_exit:
            self.on_exit()
        else:
            self.stop()

    def run(self):
        """Run the widget."""
        log.info("widget_starting")
        self.running = True

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Create window
        self.root = ctk.CTk()
        self._build_ui()

        # Initial update
        self._update_display()

        log.info("widget_running")
        # Run mainloop
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            log.info("keyboard_interrupt")
        finally:
            self.stop()

    def stop(self):
        """Stop the widget."""
        log.info("widget_stopping")
        self.running = False

        if self.update_timer and self.root:
            self.root.after_cancel(self.update_timer)
            self.update_timer = None

        if self.root:
            try:
                self.root.quit()
                self.root.destroy()
            except Exception:
                pass
            self.root = None

        log.info("widget_stopped")

    def update(self):
        """Force an update (called externally after calibration)."""
        if self.running and self.root:
            self.root.after(0, self._update_display)
