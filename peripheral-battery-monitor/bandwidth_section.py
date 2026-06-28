"""Bandwidth section widget.

A self-contained QFrame that renders per-interface real-time + cumulative
bandwidth rows. Owns its own QTimer (2 s) and polls `bandwidth_reader` in
process. Pure UI / state code — no /proc parsing lives here.

Public API
----------
- `BandwidthSection(initial_settings, on_settings_changed)`: construct
- `add_interface(name)` / `remove_interface(name)`
- `reset_cumulative(name)`
- `set_visible(visible: bool)`
- `update_style(opacity_alpha, font_scale)`
- `current_interfaces() -> list[str]`

The widget calls back into `on_settings_changed(settings_dict)` whenever the
persisted state (`bandwidth_interfaces`, `bandwidth_cumulative`) changes so
the main monitor can save settings without the widget knowing about the file.
"""

from __future__ import annotations

import logging
from typing import Callable

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

import bandwidth_reader

_log = logging.getLogger(__name__)


# How often we persist cumulative totals back to settings (seconds of wall clock
# via timer ticks; we tick every POLL_INTERVAL_MS so this is roughly 30 s).
PERSIST_EVERY_N_TICKS = 15  # 15 ticks * 2s = 30s
POLL_INTERVAL_MS = 2000


# Fixed-width formatting: number column is 5 chars right-aligned; unit column is
# (max unit length) + len(suffix) chars left-aligned. With monospace font this
# gives a stable pixel width across magnitude changes (e.g., 999.9 KiB/s → 1.0 MiB/s
# does not jitter the layout). Numeric format is `{int:>5}` for bytes (no decimal)
# and `{:>5.1f}` for KiB+ (always one decimal). Max realistic number is "999.9".
_BW_UNITS = ("B", "KiB", "MiB", "GiB", "TiB")
_BW_NUM_WIDTH = 5
_BW_MAX_UNIT_LEN = max(len(u) for u in _BW_UNITS)  # 3


def _format_bytes(n: float, *, suffix: str = "") -> str:
    """Format a byte count as a fixed-width human-readable string (IEC binary prefixes).

    When `suffix` is "/s", produces a per-second rate; the unit column widens to
    accommodate the suffix so rate and non-rate strings each have a stable width.
    """
    if n < 0:
        n = 0
    unit_width = _BW_MAX_UNIT_LEN + len(suffix)
    for unit in _BW_UNITS:
        if n < 1024 or unit == "TiB":
            num_str = f"{int(n):>{_BW_NUM_WIDTH}}" if unit == "B" else f"{n:>{_BW_NUM_WIDTH}.1f}"
            return f"{num_str} {(unit + suffix):<{unit_width}}"
        n /= 1024
    # Unreachable in practice — kept for completeness.
    return f"{n:>{_BW_NUM_WIDTH}.1f} {('TiB' + suffix):<{unit_width}}"


def _format_rate(bytes_per_sec: float) -> str:
    return _format_bytes(bytes_per_sec, suffix="/s")


# Placeholder strings sized to match the fixed-width formatter output, so missing
# rows don't change the column width.
_BW_RATE_PLACEHOLDER = f"{'--':>{_BW_NUM_WIDTH}} {'':<{_BW_MAX_UNIT_LEN + 2}}"  # "/s"
_BW_BYTES_PLACEHOLDER = f"{'--':>{_BW_NUM_WIDTH}} {'':<{_BW_MAX_UNIT_LEN}}"


class _InterfaceRow:
    """Tracks per-interface state and owns one row QWidget.

    The row is a self-contained `QWidget` (not a bare QVBoxLayout). Nested
    QVBoxLayouts inside the section's `_rows_container` were causing Qt to
    compute the parent geometry one event cycle late, which let the very
    first paint render rows over the header. Using a real widget per row
    forces the size hint to propagate immediately.
    """

    def __init__(
        self,
        name: str,
        cumulative_rx: int,
        cumulative_tx: int,
        parent: QWidget,
    ):
        self.name = name
        self.cumulative_rx = cumulative_rx
        self.cumulative_tx = cumulative_tx
        # Last raw kernel counter we saw (used for delta + wrap detection).
        # None means "no baseline yet" — first poll establishes it.
        self.last_raw_rx: int | None = None
        self.last_raw_tx: int | None = None
        self.last_ts: float | None = None

        self.widget = QWidget(parent)
        row_layout = QVBoxLayout(self.widget)
        row_layout.setSpacing(0)
        row_layout.setContentsMargins(0, 2, 0, 2)

        self.name_lbl = QLabel(name, self.widget)
        self.name_lbl.setObjectName("BandwidthName")

        self.rate_lbl = QLabel(
            f"↓ {_BW_RATE_PLACEHOLDER}  ↑ {_BW_RATE_PLACEHOLDER}",
            self.widget,
        )
        self.rate_lbl.setObjectName("BandwidthRate")
        self.rate_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        self.cum_lbl = QLabel(
            f"Σ ↓ {_BW_BYTES_PLACEHOLDER}  ↑ {_BW_BYTES_PLACEHOLDER}",
            self.widget,
        )
        self.cum_lbl.setObjectName("BandwidthCumulative")
        self.cum_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.name_lbl)
        top.addStretch()
        top.addWidget(self.rate_lbl)
        row_layout.addLayout(top)

        bot = QHBoxLayout()
        bot.setContentsMargins(0, 0, 0, 0)
        bot.addStretch()
        bot.addWidget(self.cum_lbl)
        row_layout.addLayout(bot)

    def ingest_sample(self, exists: bool, raw_rx: int, raw_tx: int, ts: float) -> tuple[float, float]:
        """Update state with a new sample. Returns (rx_per_sec, tx_per_sec).

        Handles counter wrap / interface re-creation by detecting raw counters
        that went backwards; that tick contributes 0 to rate and cumulative.
        """
        if not exists:
            # Interface gone — reset baseline so a future re-appearance starts fresh.
            self.last_raw_rx = None
            self.last_raw_tx = None
            self.last_ts = None
            return 0.0, 0.0

        rx_per_sec = 0.0
        tx_per_sec = 0.0

        if self.last_raw_rx is not None and self.last_ts is not None:
            dt = ts - self.last_ts
            if dt > 0:
                drx = raw_rx - self.last_raw_rx
                dtx = raw_tx - self.last_raw_tx
                if drx >= 0 and dtx >= 0:
                    rx_per_sec = drx / dt
                    tx_per_sec = dtx / dt
                    self.cumulative_rx += drx
                    self.cumulative_tx += dtx
                # else: counter went backwards — treat as wrap; re-anchor silently.

        self.last_raw_rx = raw_rx
        self.last_raw_tx = raw_tx
        self.last_ts = ts
        return rx_per_sec, tx_per_sec

    def reset_cumulative(self):
        self.cumulative_rx = 0
        self.cumulative_tx = 0
        # Keep raw baselines so we don't double-count the next delta.

    def render(self, rx_per_sec: float, tx_per_sec: float, subtitle: str | None):
        title = self.name if not subtitle else f"{self.name}  → {subtitle}"
        self.name_lbl.setText(title)
        self.rate_lbl.setText(
            f"↓ {_format_rate(rx_per_sec)}  ↑ {_format_rate(tx_per_sec)}"
        )
        self.cum_lbl.setText(
            f"Σ ↓ {_format_bytes(self.cumulative_rx)}  "
            f"↑ {_format_bytes(self.cumulative_tx)}"
        )

    def render_missing(self):
        self.name_lbl.setText(f"{self.name}  (missing)")
        self.rate_lbl.setText(
            f"↓ {_BW_RATE_PLACEHOLDER}  ↑ {_BW_RATE_PLACEHOLDER}"
        )
        self.cum_lbl.setText(
            f"Σ ↓ {_format_bytes(self.cumulative_rx)}  "
            f"↑ {_format_bytes(self.cumulative_tx)}"
        )


class BandwidthSection(QFrame):
    """Bandwidth section frame. See module docstring for the public API."""

    def __init__(
        self,
        initial_settings: dict,
        on_settings_changed: Callable[[dict], None],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("BandwidthSection")

        self._on_settings_changed = on_settings_changed
        self._interfaces: list[str] = list(initial_settings.get("bandwidth_interfaces", []))
        self._cumulative: dict[str, dict] = dict(initial_settings.get("bandwidth_cumulative", {}))
        self._rows: dict[str, _InterfaceRow] = {}
        self._ticks_since_persist = 0
        self._opacity_alpha = 242  # default ~95% alpha; updated via update_style
        self._font_scale = 1.0

        self._root_layout = QVBoxLayout(self)
        self._root_layout.setContentsMargins(15, 8, 15, 10)
        self._root_layout.setSpacing(4)

        self._header_lbl = QLabel("Bandwidth")
        self._header_lbl.setObjectName("BandwidthTitle")
        self._root_layout.addWidget(self._header_lbl)

        self._rows_container = QVBoxLayout()
        self._rows_container.setSpacing(2)
        self._root_layout.addLayout(self._rows_container)

        self._placeholder = QLabel("No interfaces configured — right-click → Bandwidth")
        self._placeholder.setObjectName("BandwidthPlaceholder")
        self._placeholder.setWordWrap(True)
        self._root_layout.addWidget(self._placeholder)

        for name in self._interfaces:
            self._build_row_widget(name)

        self._refresh_placeholder()

        self._timer = QTimer(self)
        self._timer.setInterval(POLL_INTERVAL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

    # ---- public API ----

    def current_interfaces(self) -> list[str]:
        return list(self._interfaces)

    def add_interface(self, name: str):
        name = name.strip()
        if not name or name in self._interfaces:
            return
        self._interfaces.append(name)
        self._cumulative.setdefault(name, {"rx": 0, "tx": 0})
        self._build_row_widget(name)
        self._refresh_placeholder()
        self._relayout_window()
        self._emit_settings()

    def remove_interface(self, name: str):
        if name not in self._interfaces:
            return
        self._interfaces.remove(name)
        self._cumulative.pop(name, None)
        row = self._rows.pop(name, None)
        if row is not None:
            row.widget.setParent(None)
            row.widget.deleteLater()
        self._refresh_placeholder()
        self._relayout_window()
        self._emit_settings()

    def reset_cumulative(self, name: str):
        row = self._rows.get(name)
        if row is None:
            return
        row.reset_cumulative()
        self._cumulative[name] = {"rx": 0, "tx": 0}
        # Re-render immediately so the user sees the reset take effect.
        row.render(0.0, 0.0, None)
        self._emit_settings()

    def set_visible(self, visible: bool):
        self.setVisible(visible)
        if visible:
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()

    def update_style(self, alpha: int, font_scale: float):
        self._opacity_alpha = alpha
        self._font_scale = font_scale
        name_size = int(11 * font_scale)
        rate_size = int(11 * font_scale)
        cum_size = int(9 * font_scale)
        title_size = int(11 * font_scale)

        # Scale padding/spacing with the font so a small font doesn't leave
        # proportionally large whitespace.
        def s(base, lo=1):
            return max(lo, int(round(base * font_scale)))

        self._root_layout.setContentsMargins(s(15, 6), s(8, 3), s(15, 6), s(10, 4))
        self._root_layout.setSpacing(s(4, 1))
        self._rows_container.setSpacing(s(2, 0))

        self.setStyleSheet(f"""
            QFrame#BandwidthSection {{
                background-color: rgba(35, 35, 35, {alpha});
                border: 1px solid rgba(255, 255, 255, 15);
                border-radius: 8px;
                margin-top: 4px;
            }}
            QLabel {{
                color: #e0e0e0;
                background: transparent;
            }}
            QLabel#BandwidthTitle {{
                color: #aaaaaa;
                font-weight: bold;
                font-size: {title_size}px;
            }}
            QLabel#BandwidthName {{
                color: #cccccc;
                font-size: {name_size}px;
            }}
            QLabel#BandwidthRate {{
                color: #4caf50;
                font-size: {rate_size}px;
                font-family: monospace;
            }}
            QLabel#BandwidthCumulative {{
                color: #888888;
                font-size: {cum_size}px;
                font-family: monospace;
            }}
            QLabel#BandwidthPlaceholder {{
                color: #888888;
                font-style: italic;
                font-size: {cum_size}px;
            }}
        """)

    # ---- internals ----

    def _build_row_widget(self, name: str):
        cum = self._cumulative.get(name, {"rx": 0, "tx": 0})
        row = _InterfaceRow(
            name,
            int(cum.get("rx", 0)),
            int(cum.get("tx", 0)),
            parent=self,
        )
        self._rows[name] = row
        self._rows_container.addWidget(row.widget)

    def _refresh_placeholder(self):
        # Use show()/hide() rather than setVisible: in Qt a hidden widget still
        # reserves layout space until the next event tick, which caused brief
        # column-overflow when the section flipped between empty/non-empty.
        if self._interfaces:
            self._placeholder.hide()
        else:
            self._placeholder.show()

    def _relayout_window(self):
        """Force the parent window to recompute size immediately after a row
        is added or removed. Without this, Qt defers the size-hint update to
        the next paint cycle, which renders the section overflowing the
        window for one frame.
        """
        # Invalidate from this widget upward so the parent's sizeHint is fresh.
        self.updateGeometry()
        top = self.window()
        if top is not None and top is not self:
            top.adjustSize()

    def _emit_settings(self):
        # Sync row cumulatives back into the persisted dict before emitting.
        for name, row in self._rows.items():
            self._cumulative[name] = {"rx": row.cumulative_rx, "tx": row.cumulative_tx}
        self._on_settings_changed({
            "bandwidth_interfaces": list(self._interfaces),
            "bandwidth_cumulative": dict(self._cumulative),
        })

    def _poll(self):
        if not self._interfaces:
            return
        # Tailscale metadata is only requested when at least one tailscale*
        # interface is configured, so we don't shell out for non-Tailscale setups.
        want_ts_meta = any(n.startswith("tailscale") for n in self._interfaces)
        try:
            data = bandwidth_reader.read_interfaces(
                self._interfaces, include_tailscale_meta=want_ts_meta
            )
        except Exception:
            # Best-effort: a transient read failure should not kill the timer.
            # Log once via the standard logger so issues surface for debugging.
            _log.warning("bandwidth_poll_failed", exc_info=True)
            return

        ts = data.get("timestamp", 0.0)
        for entry in data.get("interfaces", []):
            row = self._rows.get(entry["name"])
            if row is None:
                continue
            if not entry.get("exists", False):
                row.render_missing()
                # Reset baseline so re-appearance doesn't produce a huge delta.
                row.ingest_sample(False, 0, 0, ts)
                continue
            rx_per_sec, tx_per_sec = row.ingest_sample(
                True, int(entry["rx_bytes"]), int(entry["tx_bytes"]), ts
            )
            subtitle = self._format_metadata(entry.get("metadata"))
            row.render(rx_per_sec, tx_per_sec, subtitle)

        self._ticks_since_persist += 1
        if self._ticks_since_persist >= PERSIST_EVERY_N_TICKS:
            self._ticks_since_persist = 0
            self._emit_settings()

    @staticmethod
    def _format_metadata(meta: dict | None) -> str | None:
        if not meta or meta.get("type") != "tailscale":
            return None
        exit_node = meta.get("exit_node")
        if exit_node:
            online = meta.get("exit_node_online")
            if online is False:
                return f"exit: {exit_node} (offline)"
            return f"exit: {exit_node}"
        backend = meta.get("backend_state")
        if backend and backend not in ("Running", "unknown"):
            return f"tailscale: {backend}"
        return None
