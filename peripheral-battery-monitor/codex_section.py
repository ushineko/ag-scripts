"""Codex usage section for the peripheral monitor."""

from __future__ import annotations

import time
from decimal import Decimal, InvalidOperation

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
    QVBoxLayout,
)


def window_label(minutes) -> str:
    if not isinstance(minutes, (int, float)):
        return "Limit"
    if minutes % 1440 == 0:
        return f"{int(minutes // 1440)}d"
    if minutes % 60 == 0:
        return f"{int(minutes // 60)}h"
    return f"{int(minutes)}m"


def reset_countdown(epoch) -> str:
    if not isinstance(epoch, (int, float)):
        return ""
    remaining = max(0, int(epoch - time.time()))
    days, remaining = divmod(remaining, 86400)
    hours, remaining = divmod(remaining, 3600)
    minutes = remaining // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def usage_color(percent) -> str:
    if percent is None:
        return "#6b7280"
    if percent > 80:
        return "#f44336"
    if percent >= 50:
        return "#ff9800"
    return "#4caf50"


def reported_amount(value) -> str:
    """Format app-server's decimal strings compactly without adding a unit."""
    try:
        rendered = f"{Decimal(str(value)):.2f}"
    except (InvalidOperation, ValueError):
        return str(value)
    return rendered.rstrip("0").rstrip(".")


class CodexSection(QFrame):
    def __init__(self, parent=None, on_refresh=None):
        super().__init__(parent)
        self.setObjectName("CodexSection")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._last_good = None
        self._build(on_refresh)

    def _build(self, on_refresh):
        layout = QVBoxLayout(self)
        layout.setSpacing(4)
        self.section_layout = layout

        header = QHBoxLayout()
        self.header_layout = header
        icon_label = QLabel(self)
        icon = QIcon.fromTheme("dialog-scripts", QIcon.fromTheme("utilities-terminal"))
        icon_label.setPixmap(icon.pixmap(16, 16))
        header.addWidget(icon_label)

        title = QLabel("Codex", self)
        title.setObjectName("CodexTitle")
        header.addWidget(title)
        header.addStretch()
        self.reset_label = QLabel("--", self)
        self.reset_label.setObjectName("CodexReset")
        header.addWidget(self.reset_label)
        refresh = QPushButton("↻", self)
        refresh.setObjectName("CodexRefreshBtn")
        refresh.setFixedSize(18, 18)
        refresh.setToolTip("Refresh usage stats")
        if on_refresh:
            refresh.clicked.connect(on_refresh)
        header.addWidget(refresh)
        layout.addLayout(header)

        self.progress = QProgressBar(self)
        self.progress.setObjectName("CodexProgress")
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        layout.addWidget(self.progress)

        stats = QHBoxLayout()
        self.primary_label = QLabel("Limit: --", self)
        self.primary_label.setObjectName("CodexStats")
        stats.addWidget(self.primary_label)
        stats.addStretch()
        self.individual_label = QLabel("", self)
        self.individual_label.setObjectName("CodexStats")
        stats.addWidget(self.individual_label)
        layout.addLayout(stats)

        self.status_label = QLabel("", self)
        self.status_label.setObjectName("CodexStatus")
        self.status_label.hide()
        layout.addWidget(self.status_label)
        self._set_progress(None)

    def apply_layout_metrics(self, metrics):
        """Use the same scaled geometry as the adjacent Claude section."""
        self.section_layout.setContentsMargins(
            metrics["claude_margin_h"], metrics["claude_margin_top"],
            metrics["claude_margin_h"], metrics["claude_margin_bottom"],
        )
        self.header_layout.setSpacing(metrics["claude_header_spacing"])

    def _set_progress(self, percent):
        self.progress.setValue(min(100, max(0, int(percent or 0))))
        self.progress.setStyleSheet(f"""
            QProgressBar#CodexProgress {{
                background-color: rgba(255, 255, 255, 0.1);
                border: none;
                border-radius: 4px;
            }}
            QProgressBar#CodexProgress::chunk {{
                background-color: {usage_color(percent)};
                border-radius: 4px;
            }}
        """)

    def update_usage(self, data):
        if isinstance(data, dict) and not data.get("error") and data.get("primary"):
            self._last_good = data
            self._render(data)
            self.status_label.hide()
            return
        if self._last_good is not None:
            self._render(self._last_good)
            reason = (data or {}).get("error", "no reading")
            self.status_label.setText(f"Cached · {reason.replace('_', ' ')}")
            self.status_label.show()
            return
        reason = (data or {}).get("error", "not logged in")
        self._set_progress(None)
        self.primary_label.setText(reason.replace("_", " ").capitalize())
        self.individual_label.setText("")
        self.reset_label.setText("")

    def _render(self, data):
        primary = data["primary"]
        percent = primary.get("utilization")
        label = window_label(primary.get("window_minutes"))
        self._set_progress(percent)
        self.primary_label.setText(f"{label}: {percent:.0f}%" if percent is not None else f"{label}: --")
        countdown = reset_countdown(primary.get("resets_at"))
        self.reset_label.setText(f"Resets in {countdown}" if countdown else "")
        individual = data.get("individual_limit") or {}
        used = individual.get("utilization")
        raw_used = individual.get("used")
        raw_limit = individual.get("limit")
        if used is not None and raw_used is not None and raw_limit is not None:
            text = (f"Individual: {reported_amount(raw_used)}/"
                    f"{reported_amount(raw_limit)} ({used:.0f}%)")
        elif used is not None:
            text = f"Individual: {used:.0f}%"
        else:
            text = ""
        self.individual_label.setText(text)
