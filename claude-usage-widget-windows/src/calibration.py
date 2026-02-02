"""Calibration dialog for syncing with Claude's actual usage percentage."""

from typing import Callable, Optional

import customtkinter as ctk
import structlog

from .config import get_setting, set_setting
from .claude_stats import format_tokens

log = structlog.get_logger(__name__)


class CalibrationDialog:
    """Dialog for calibrating the widget to match Claude's actual percentage."""

    def __init__(
        self,
        current_tokens: int,
        on_complete: Callable[[], None] = None,
        parent: ctk.CTk = None,
    ):
        """
        Initialize the calibration dialog.

        Args:
            current_tokens: Current session token count (without offset)
            on_complete: Callback when calibration is complete
            parent: Parent window (optional)
        """
        self.current_tokens = current_tokens
        self.on_complete = on_complete
        self.parent = parent
        self.window: Optional[ctk.CTkToplevel] = None
        self.root: Optional[ctk.CTk] = None

        # Current settings
        self.budget = get_setting("session_budget", 500000)
        self.offset = get_setting("token_offset", 0)
        self.adjusted_tokens = self.current_tokens + self.offset
        self.current_percentage = (
            int(self.adjusted_tokens / self.budget * 100) if self.budget > 0 else 0
        )

        # Widget references
        self.percentage_slider: Optional[ctk.CTkSlider] = None
        self.percentage_entry: Optional[ctk.CTkEntry] = None
        self.mode_var: Optional[ctk.StringVar] = None
        self.preview_value_label: Optional[ctk.CTkLabel] = None
        self.preview_result_label: Optional[ctk.CTkLabel] = None

        log.debug(
            "calibration_dialog_init",
            current_tokens=current_tokens,
            budget=self.budget,
            offset=self.offset,
            adjusted_tokens=self.adjusted_tokens,
            current_percentage=self.current_percentage,
        )

    def show(self):
        """Show the calibration dialog."""
        log.info("showing_calibration_dialog")

        # Create root if needed
        if self.parent is None:
            self.root = ctk.CTk()
            self.root.withdraw()
            parent = self.root
        else:
            parent = self.parent
            self.root = None

        # Set appearance
        ctk.set_appearance_mode("dark")

        # Create dialog window
        self.window = ctk.CTkToplevel(parent)
        self.window.title("Calibrate Claude Usage")
        self.window.geometry("420x440")
        self.window.resizable(False, False)
        self.window.attributes("-topmost", True)

        # Center on screen
        self.window.update_idletasks()
        x = (self.window.winfo_screenwidth() - 420) // 2
        y = (self.window.winfo_screenheight() - 440) // 2
        self.window.geometry(f"+{x}+{y}")

        # Build UI
        self._build_ui()

        # Focus the entry
        self.percentage_entry.focus_set()

        # Handle close - X button and Escape key
        self.window.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.window.bind("<Escape>", lambda e: self._on_cancel())

        # Make modal
        self.window.grab_set()
        self.window.focus_force()

        # Run if we created root
        if self.root is not None:
            self.root.mainloop()

    def _create_group_frame(self, parent, title: str) -> ctk.CTkFrame:
        """Create a grouped frame with a title label (similar to QGroupBox)."""
        outer = ctk.CTkFrame(parent, corner_radius=8, fg_color="#2b2b2b")

        # Title label
        title_label = ctk.CTkLabel(
            outer,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#9ca3af",
        )
        title_label.pack(anchor="w", padx=12, pady=(8, 4))

        # Content frame
        content = ctk.CTkFrame(outer, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        return outer, content

    def _build_ui(self):
        """Build the dialog UI."""
        container = ctk.CTkFrame(self.window, corner_radius=0)
        container.pack(fill="both", expand=True, padx=15, pady=15)

        # ========== Current Values Group ==========
        current_outer, current_frame = self._create_group_frame(
            container, "Current Values"
        )
        current_outer.pack(fill="x", pady=(0, 10))

        # Row: Tokens used
        row1 = ctk.CTkFrame(current_frame, fg_color="transparent")
        row1.pack(fill="x", pady=2)
        ctk.CTkLabel(row1, text="Tokens used:", width=100, anchor="w").pack(
            side="left"
        )
        ctk.CTkLabel(
            row1, text=f"{format_tokens(self.adjusted_tokens)} tokens", anchor="w"
        ).pack(side="left")

        # Row: Budget
        row2 = ctk.CTkFrame(current_frame, fg_color="transparent")
        row2.pack(fill="x", pady=2)
        ctk.CTkLabel(row2, text="Budget:", width=100, anchor="w").pack(side="left")
        ctk.CTkLabel(
            row2, text=f"{format_tokens(self.budget)} budget", anchor="w"
        ).pack(side="left")

        # Row: Percentage
        row3 = ctk.CTkFrame(current_frame, fg_color="transparent")
        row3.pack(fill="x", pady=2)
        ctk.CTkLabel(row3, text="Percentage:", width=100, anchor="w").pack(side="left")
        ctk.CTkLabel(row3, text=f"{self.current_percentage}%", anchor="w").pack(
            side="left"
        )

        # ========== Calibrate Group ==========
        calibrate_outer, calibrate_frame = self._create_group_frame(
            container, "Calibrate to Known Value"
        )
        calibrate_outer.pack(fill="x", pady=(0, 10))

        # Instructions
        instructions = ctk.CTkLabel(
            calibrate_frame,
            text="Run /usage in Claude CLI and enter the percentage shown:",
            font=ctk.CTkFont(size=11),
            text_color="#9ca3af",
        )
        instructions.pack(anchor="w", pady=(0, 8))

        # Target percentage row with slider and entry
        target_row = ctk.CTkFrame(calibrate_frame, fg_color="transparent")
        target_row.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(target_row, text="Target:", width=60, anchor="w").pack(side="left")

        # Slider (1-200%)
        self.percentage_slider = ctk.CTkSlider(
            target_row,
            from_=1,
            to=200,
            number_of_steps=199,
            width=180,
            command=self._on_slider_change,
        )
        self.percentage_slider.set(
            self.current_percentage if self.current_percentage > 0 else 25
        )
        self.percentage_slider.pack(side="left", padx=(0, 10))

        # Entry for precise input
        self.percentage_entry = ctk.CTkEntry(target_row, width=60, justify="center")
        self.percentage_entry.insert(
            0, str(self.current_percentage if self.current_percentage > 0 else 25)
        )
        self.percentage_entry.pack(side="left")
        self.percentage_entry.bind("<KeyRelease>", self._on_entry_change)

        ctk.CTkLabel(target_row, text="%").pack(side="left", padx=(4, 0))

        # Mode selection (ComboBox style)
        mode_row = ctk.CTkFrame(calibrate_frame, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(mode_row, text="Adjust:", width=60, anchor="w").pack(side="left")

        self.mode_var = ctk.StringVar(value="budget")
        mode_menu = ctk.CTkOptionMenu(
            mode_row,
            values=["Adjust budget (recommended)", "Adjust token count (offset)"],
            variable=self.mode_var,
            width=250,
            command=self._on_mode_change,
        )
        mode_menu.pack(side="left")

        # ========== Preview Result Group ==========
        preview_outer, preview_frame = self._create_group_frame(
            container, "Preview Result"
        )
        preview_outer.pack(fill="x", pady=(0, 15))

        # New value row
        value_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        value_row.pack(fill="x", pady=2)
        ctk.CTkLabel(value_row, text="New value:", width=80, anchor="w").pack(
            side="left"
        )
        self.preview_value_label = ctk.CTkLabel(
            value_row,
            text="--",
            font=ctk.CTkFont(weight="bold"),
            text_color="#22c55e",
            anchor="w",
        )
        self.preview_value_label.pack(side="left", fill="x", expand=True)

        # Result row (showing calculation)
        result_row = ctk.CTkFrame(preview_frame, fg_color="transparent")
        result_row.pack(fill="x", pady=2)
        ctk.CTkLabel(result_row, text="Result:", width=80, anchor="w").pack(side="left")
        self.preview_result_label = ctk.CTkLabel(
            result_row,
            text="--",
            text_color="#9ca3af",
            anchor="w",
        )
        self.preview_result_label.pack(side="left", fill="x", expand=True)

        # ========== Buttons ==========
        button_frame = ctk.CTkFrame(container, fg_color="transparent")
        button_frame.pack(fill="x")

        cancel_button = ctk.CTkButton(
            button_frame,
            text="Cancel",
            width=100,
            fg_color="#374151",
            hover_color="#4b5563",
            command=self._on_cancel,
        )
        cancel_button.pack(side="left", expand=True)

        apply_button = ctk.CTkButton(
            button_frame,
            text="Apply",
            width=100,
            command=self._on_apply,
        )
        apply_button.pack(side="right", expand=True)

        # Initial preview update
        self._update_preview()

    def _on_slider_change(self, value):
        """Handle slider value change."""
        int_value = int(round(value))
        self.percentage_entry.delete(0, "end")
        self.percentage_entry.insert(0, str(int_value))
        self._update_preview()

    def _on_entry_change(self, event=None):
        """Handle entry value change."""
        try:
            value = int(self.percentage_entry.get())
            if 1 <= value <= 200:
                self.percentage_slider.set(value)
        except ValueError:
            pass
        self._update_preview()

    def _on_mode_change(self, _value=None):
        """Handle mode selection change."""
        self._update_preview()

    def _update_preview(self):
        """Update the preview labels based on current settings."""
        try:
            percentage = int(self.percentage_entry.get())
            if percentage < 1 or percentage > 200:
                self.preview_value_label.configure(
                    text="Percentage must be 1-200%", text_color="#ef4444"
                )
                self.preview_result_label.configure(text="--")
                return

            mode = self.mode_var.get()
            is_budget_mode = "budget" in mode.lower()

            if is_budget_mode:
                # Calculate new budget: current_tokens / (percentage / 100)
                if percentage > 0:
                    new_budget = int(self.adjusted_tokens / (percentage / 100))
                    self.preview_value_label.configure(
                        text=f"Budget → {format_tokens(new_budget)}",
                        text_color="#22c55e",
                    )
                    self.preview_result_label.configure(
                        text=f"{format_tokens(self.adjusted_tokens)} / {format_tokens(new_budget)} = {percentage}%"
                    )
                    log.debug(
                        "preview_budget_mode",
                        target_pct=percentage,
                        new_budget=new_budget,
                    )
                else:
                    self.preview_value_label.configure(
                        text="Invalid percentage", text_color="#ef4444"
                    )
                    self.preview_result_label.configure(text="--")
            else:
                # Calculate new token offset
                if self.budget > 0:
                    target_tokens = int(self.budget * (percentage / 100))
                    new_offset = target_tokens - self.current_tokens
                    self.preview_value_label.configure(
                        text=f"Tokens → {format_tokens(target_tokens)} (offset: {new_offset:+,})",
                        text_color="#22c55e",
                    )
                    self.preview_result_label.configure(
                        text=f"{format_tokens(target_tokens)} / {format_tokens(self.budget)} = {percentage}%"
                    )
                    log.debug(
                        "preview_offset_mode",
                        target_pct=percentage,
                        target_tokens=target_tokens,
                        new_offset=new_offset,
                    )
                else:
                    self.preview_value_label.configure(
                        text="Budget is zero", text_color="#ef4444"
                    )
                    self.preview_result_label.configure(text="Cannot calibrate")

        except ValueError:
            if self.percentage_entry.get():
                self.preview_value_label.configure(
                    text="Enter a valid number", text_color="#ef4444"
                )
            else:
                self.preview_value_label.configure(text="--", text_color="#6b7280")
            self.preview_result_label.configure(text="--")

    def _on_apply(self):
        """Apply the calibration."""
        try:
            percentage = int(self.percentage_entry.get())
            if percentage < 1 or percentage > 200:
                log.warning("calibration_invalid_percentage", percentage=percentage)
                self.preview_value_label.configure(
                    text="Invalid percentage (1-200%)", text_color="#ef4444"
                )
                return

            mode = self.mode_var.get()
            is_budget_mode = "budget" in mode.lower()

            if is_budget_mode:
                if percentage > 0:
                    new_budget = int(self.adjusted_tokens / (percentage / 100))
                    set_setting("session_budget", new_budget)
                    log.info(
                        "calibration_applied_budget",
                        target_pct=percentage,
                        new_budget=new_budget,
                        old_budget=self.budget,
                    )
                    # Show confirmation
                    self.preview_value_label.configure(
                        text=f"✓ Budget set to {format_tokens(new_budget)}",
                        text_color="#22c55e",
                    )
            else:
                target_tokens = int(self.budget * (percentage / 100))
                new_offset = target_tokens - self.current_tokens
                set_setting("token_offset", new_offset)
                log.info(
                    "calibration_applied_offset",
                    target_pct=percentage,
                    new_offset=new_offset,
                    old_offset=self.offset,
                )
                # Show confirmation
                self.preview_value_label.configure(
                    text=f"✓ Offset set to {new_offset:+,}",
                    text_color="#22c55e",
                )

            self.preview_result_label.configure(text="Settings applied! Closing...")

            # Delay close to show confirmation
            if self.window:
                self.window.after(800, self._close_and_complete)

        except ValueError:
            log.warning("calibration_value_error")
            self.preview_value_label.configure(
                text="Enter a valid number", text_color="#ef4444"
            )

    def _close_and_complete(self):
        """Close dialog and call completion callback."""
        self._close()
        if self.on_complete:
            self.on_complete()

    def _on_cancel(self):
        """Cancel and close the dialog."""
        log.debug("calibration_cancelled")
        self._close()

    def _close(self):
        """Close the dialog."""
        if self.window is not None:
            self.window.grab_release()
            self.window.destroy()
            self.window = None

        if self.root is not None:
            self.root.destroy()
            self.root = None
