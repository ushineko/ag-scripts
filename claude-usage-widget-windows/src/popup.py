"""Detail popup window using CustomTkinter."""

import tkinter as tk
from typing import Callable, Optional

import customtkinter as ctk

from .claude_stats import format_tokens


class PopupWindow:
    """Detail popup window showing Claude usage statistics."""

    def __init__(self, get_stats: Callable[[], dict]):
        """
        Initialize the popup window.

        Args:
            get_stats: Callable that returns current stats dict
        """
        self.get_stats = get_stats
        self.window: Optional[ctk.CTkToplevel] = None
        self.root: Optional[ctk.CTk] = None

        # Widget references for updating
        self.window_label: Optional[ctk.CTkLabel] = None
        self.progress_bar: Optional[ctk.CTkProgressBar] = None
        self.percentage_label: Optional[ctk.CTkLabel] = None
        self.tokens_label: Optional[ctk.CTkLabel] = None
        self.calls_label: Optional[ctk.CTkLabel] = None
        self.cache_read_label: Optional[ctk.CTkLabel] = None
        self.cache_create_label: Optional[ctk.CTkLabel] = None

    def _get_color_hex(self, color: str) -> str:
        """Convert color name to hex."""
        colors = {
            "green": "#22c55e",
            "yellow": "#eab308",
            "red": "#ef4444",
            "gray": "#6b7280",
        }
        return colors.get(color, colors["gray"])

    def show(self):
        """Show the popup window."""
        if self.window is not None and self.window.winfo_exists():
            # Window exists, bring to front
            self.window.lift()
            self.window.focus_force()
            self._update_display()
            return

        # Create hidden root if needed (for Toplevel)
        if self.root is None:
            self.root = ctk.CTk()
            self.root.withdraw()  # Hide root window

        # Set appearance
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Create popup window
        self.window = ctk.CTkToplevel(self.root)
        self.window.title("Claude Code Usage")
        self.window.geometry("320x260")
        self.window.resizable(False, False)

        # Keep on top
        self.window.attributes("-topmost", True)

        # Position near bottom-right of screen
        screen_width = self.window.winfo_screenwidth()
        screen_height = self.window.winfo_screenheight()
        x = screen_width - 340
        y = screen_height - 320
        self.window.geometry(f"+{x}+{y}")

        # Build UI
        self._build_ui()

        # Update display
        self._update_display()

        # Handle close
        self.window.protocol("WM_DELETE_WINDOW", self.hide)

    def _build_ui(self):
        """Build the popup UI."""
        # Main container with padding
        container = ctk.CTkFrame(self.window, corner_radius=0)
        container.pack(fill="both", expand=True, padx=10, pady=10)

        # Title
        title_label = ctk.CTkLabel(
            container,
            text="Claude Code Usage",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        title_label.pack(pady=(0, 10))

        # Window time
        self.window_label = ctk.CTkLabel(
            container,
            text="Window: --:-- - --:--  (N/A)",
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af",
        )
        self.window_label.pack(pady=(0, 15))

        # Progress bar frame
        progress_frame = ctk.CTkFrame(container, fg_color="transparent")
        progress_frame.pack(fill="x", pady=(0, 5))

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            width=260,
            height=20,
            corner_radius=5,
        )
        self.progress_bar.pack(side="left")
        self.progress_bar.set(0)

        self.percentage_label = ctk.CTkLabel(
            progress_frame,
            text="0%",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=40,
        )
        self.percentage_label.pack(side="right", padx=(10, 0))

        # Token count
        self.tokens_label = ctk.CTkLabel(
            container,
            text="Tokens: 0 / 0",
            font=ctk.CTkFont(size=14),
        )
        self.tokens_label.pack(pady=(10, 5))

        # API calls
        self.calls_label = ctk.CTkLabel(
            container,
            text="API Calls: 0",
            font=ctk.CTkFont(size=12),
            text_color="#9ca3af",
        )
        self.calls_label.pack(pady=2)

        # Separator
        separator = ctk.CTkFrame(container, height=1, fg_color="#374151")
        separator.pack(fill="x", pady=10)

        # Cache stats frame
        cache_frame = ctk.CTkFrame(container, fg_color="transparent")
        cache_frame.pack(fill="x")

        self.cache_read_label = ctk.CTkLabel(
            cache_frame,
            text="Cache Read: 0",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        )
        self.cache_read_label.pack(side="left", expand=True)

        self.cache_create_label = ctk.CTkLabel(
            cache_frame,
            text="Cache Created: 0",
            font=ctk.CTkFont(size=11),
            text_color="#6b7280",
        )
        self.cache_create_label.pack(side="right", expand=True)

    def _update_display(self):
        """Update the display with current stats."""
        if self.window is None or not self.window.winfo_exists():
            return

        stats = self.get_stats()

        # Update window time
        self.window_label.configure(
            text=f"Window: {stats['window_str']}  ({stats['countdown_str']} left)"
        )

        # Update progress bar
        progress_value = stats["percentage"] / 100.0
        self.progress_bar.set(progress_value)

        # Update progress bar color
        color = self._get_color_hex(stats["color"])
        self.progress_bar.configure(progress_color=color)

        # Update percentage
        self.percentage_label.configure(
            text=f"{stats['percentage']:.0f}%", text_color=color
        )

        # Update tokens
        self.tokens_label.configure(
            text=f"Tokens: {format_tokens(stats['session_tokens'])} / {format_tokens(stats['budget'])}"
        )

        # Update API calls
        self.calls_label.configure(text=f"API Calls: {stats['api_calls']}")

        # Update cache stats
        self.cache_read_label.configure(
            text=f"Cache Read: {format_tokens(stats['cache_read'])}"
        )
        self.cache_create_label.configure(
            text=f"Cache Created: {format_tokens(stats['cache_create'])}"
        )

    def hide(self):
        """Hide the popup window."""
        if self.window is not None and self.window.winfo_exists():
            self.window.withdraw()

    def toggle(self):
        """Toggle popup visibility."""
        if self.window is None or not self.window.winfo_exists():
            self.show()
        elif self.window.state() == "withdrawn":
            self.window.deiconify()
            self._update_display()
        else:
            self.hide()

    def destroy(self):
        """Destroy the popup window."""
        if self.window is not None:
            self.window.destroy()
            self.window = None
        if self.root is not None:
            self.root.destroy()
            self.root = None

    def mainloop(self):
        """Run the tkinter mainloop (if needed)."""
        if self.root is not None:
            self.root.mainloop()
