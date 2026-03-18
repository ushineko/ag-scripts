#!/usr/bin/env python3
"""App Audio Rerouter — Route application audio into a virtual mic for Teams meetings.

Creates PipeWire/PulseAudio virtual sinks and loopbacks to mix microphone + selected
app audio into a virtual mic source that Teams (or any conferencing app) can use.

Pipeline when sharing is active:

    real_mic ──loopback──► combined_mic (null-sink)
                                │
                                ▼
                         combined_mic.monitor  ◄── Teams selects this as mic
                                ▲
    app_stream ──► app_capture_N (null-sink)
                        │              │
                        │ loopback     │ loopback
                        ▼              ▼
                  original_speakers   combined_mic
                  (user still hears)  (Teams gets it)
"""

import atexit
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

from PyQt6.QtCore import (
    QByteArray,
    Qt,
    QTimer,
)
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtGui import QAction, QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

APP_NAME = "App Audio Rerouter"
SOCKET_NAME = "ag_app_audio_rerouter"
COMBINED_SINK_NAME = "combined_mic"
APP_CAPTURE_PREFIX = "app_capture_"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run_command(args, ignore_errors=False):
    """Run a subprocess command and return stdout, or None on failure."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        if not ignore_errors:
            print(f"Error running {args}: {e.stderr.strip() if e.stderr else e}")
        return None


def run_command_returncode(args):
    """Run a subprocess command and return (stdout, returncode)."""
    result = subprocess.run(args, capture_output=True, text=True)
    return result.stdout.strip(), result.returncode


def pactl_json(subcommand_args):
    """Run pactl --format=json <args> and return parsed JSON, or empty list."""
    output = run_command(["pactl", "--format=json"] + subcommand_args)
    if not output:
        return []
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class AppStream:
    """Represents a PulseAudio/PipeWire sink-input (an app playing audio)."""
    index: int
    name: str
    sink_index: int
    sink_name: str
    app_name: str
    media_name: str
    process_binary: str = ""

    @property
    def display_name(self):
        # Determine the best "app identity" label
        app_label = self.app_name or self.process_binary or self.name
        parts = []
        if app_label:
            parts.append(app_label)
        if self.media_name and self.media_name != app_label:
            parts.append(self.media_name)
        return " — ".join(parts) if parts else f"Stream #{self.index}"


@dataclass
class CapturedApp:
    """Tracks a captured app stream and the modules created for it."""
    stream_index: int
    original_sink_name: str
    intermediate_sink_name: str
    module_ids: list = field(default_factory=list)
    # module_ids: [null-sink, loopback-to-speakers, loopback-to-combined]


# ---------------------------------------------------------------------------
# StreamScanner — reads current audio state
# ---------------------------------------------------------------------------

class StreamScanner:
    """Reads current PulseAudio/PipeWire audio state."""

    # Sink names/app names that indicate virtual/internal streams to exclude
    EXCLUDED_OWNERS = {
        "module-loopback",
        "module-null-sink",
        "PipeWire",
        "pipewire",
    }
    EXCLUDED_APP_NAMES = {
        "loopback",
        "PipeWire",
    }

    def get_app_streams(self):
        """Return list of AppStream for real application sink-inputs."""
        data = pactl_json(["list", "sink-inputs"])
        sinks = self._get_sink_map()
        streams = []
        for si in data:
            props = si.get("properties", {})
            owner_module = props.get("module-stream-restore.id", "")
            app_name = props.get("application.name", "")
            media_name = props.get("media.name", "")

            # Filter out loopback / null-sink / internal streams
            if app_name in self.EXCLUDED_APP_NAMES:
                continue
            if owner_module in self.EXCLUDED_OWNERS:
                continue
            # Skip streams whose media name indicates a loopback
            if media_name.lower().startswith("loopback"):
                continue
            # Skip streams on our own virtual sinks
            sink_idx = si.get("sink", 0)
            sink_name = sinks.get(sink_idx, "")
            if sink_name.startswith(APP_CAPTURE_PREFIX) or sink_name == COMBINED_SINK_NAME:
                continue
            # Skip monitor streams
            if "monitor" in media_name.lower():
                continue

            process_binary = (
                props.get("application.process.binary")
                or props.get("node.name")
                or ""
            )

            streams.append(AppStream(
                index=si.get("index", 0),
                name=props.get("node.name", ""),
                sink_index=sink_idx,
                sink_name=sink_name,
                app_name=app_name,
                media_name=media_name,
                process_binary=process_binary,
            ))
        return streams

    def get_mic_sources(self):
        """Return list of real (non-monitor) sources with friendly names."""
        data = pactl_json(["list", "sources"])
        sources = []
        for src in data:
            name = src.get("name", "")
            # Skip monitors
            if ".monitor" in name:
                continue
            # Skip our combined_mic source (it's a null-sink source, not monitor)
            if name == COMBINED_SINK_NAME:
                continue
            desc = src.get("description", name)
            props = src.get("properties", {})
            # BlueZ sources often have description "(null)" — resolve from properties
            if not desc or desc == "(null)":
                desc = (
                    props.get("bluez.alias")
                    or props.get("device.alias")
                    or props.get("device.description")
                    or props.get("node.nick")
                    or props.get("node.description")
                )
            # Last resort for bluetooth: query BlueZ for the device alias
            if (not desc or desc == "(null)") and "bluez" in name:
                desc = self._get_bluez_alias(name)
            if not desc or desc == "(null)":
                desc = name
            sources.append({"name": name, "description": desc})
        return sources

    @staticmethod
    def _get_bluez_alias(source_name):
        """Extract MAC from a bluez source name and query BlueZ for the alias."""
        mac_match = re.search(
            r"([0-9A-Fa-f]{2}[.:_]){5}[0-9A-Fa-f]{2}", source_name
        )
        if not mac_match:
            return None
        mac = mac_match.group(0).replace("_", ":").replace(".", ":").upper()
        output = run_command(["bluetoothctl", "info", mac], ignore_errors=True)
        if not output:
            return None
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("Alias:"):
                alias = line.split(":", 1)[1].strip()
                if alias and alias != "(null)":
                    return alias
        return None

    def get_default_source(self):
        """Return the name of the current default source."""
        return run_command(["pactl", "get-default-source"]) or ""

    def _get_sink_map(self):
        """Return {sink_index: sink_name} mapping."""
        data = pactl_json(["list", "sinks"])
        return {s.get("index", -1): s.get("name", "") for s in data}

    def get_sink_name(self, sink_index):
        """Resolve a sink index to its name."""
        return self._get_sink_map().get(sink_index, "")

    def stream_exists(self, stream_index):
        """Check if a sink-input still exists."""
        data = pactl_json(["list", "sink-inputs"])
        return any(si.get("index") == stream_index for si in data)


# ---------------------------------------------------------------------------
# AudioPipeline — creates/destroys virtual sinks and loopbacks
# ---------------------------------------------------------------------------

class AudioPipeline:
    """Manages the virtual audio pipeline for routing app audio to a combined mic."""

    def __init__(self):
        self.scanner = StreamScanner()
        self._combined_sink_module = None
        self._mic_loopback_module = None
        self._captured_apps: dict[int, CapturedApp] = {}  # stream_index -> CapturedApp
        self._active = False
        self._mic_source = None
        atexit.register(self.teardown)

    @property
    def is_active(self):
        return self._active

    @property
    def captured_stream_indices(self):
        return set(self._captured_apps.keys())

    def setup(self, mic_source):
        """Create the combined_mic null-sink and mic loopback."""
        if self._active:
            return

        self._mic_source = mic_source

        # Create combined_mic null-sink
        result = run_command([
            "pactl", "load-module", "module-null-sink",
            f"sink_name={COMBINED_SINK_NAME}",
            f"sink_properties=device.description=\"Combined_Mic\"",
        ])
        if result is None:
            raise RuntimeError("Failed to create combined_mic null-sink")
        self._combined_sink_module = result.strip()

        # Create mic loopback: real mic -> combined_mic
        result = run_command([
            "pactl", "load-module", "module-loopback",
            f"source={mic_source}",
            f"sink={COMBINED_SINK_NAME}",
            "source_dont_move=true",
            "sink_dont_move=true",
            "latency_msec=30",
        ])
        if result is None:
            self._rollback_setup()
            raise RuntimeError("Failed to create mic loopback")
        self._mic_loopback_module = result.strip()

        self._active = True

    def add_app(self, stream_index, original_sink_name):
        """Capture an app stream: create intermediate sink, move stream, create loopbacks."""
        if not self._active:
            raise RuntimeError("Pipeline not active")
        if stream_index in self._captured_apps:
            return  # Already captured

        cap = CapturedApp(
            stream_index=stream_index,
            original_sink_name=original_sink_name,
            intermediate_sink_name=f"{APP_CAPTURE_PREFIX}{stream_index}",
        )

        # 1. Create intermediate null-sink for this app
        result = run_command([
            "pactl", "load-module", "module-null-sink",
            f"sink_name={cap.intermediate_sink_name}",
            f"sink_properties=device.description=\"App_Capture_{stream_index}\"",
        ])
        if result is None:
            raise RuntimeError(f"Failed to create intermediate sink for stream {stream_index}")
        cap.module_ids.append(result.strip())

        # 2. Move the app's stream to the intermediate sink
        _, rc = run_command_returncode([
            "pactl", "move-sink-input", str(stream_index), cap.intermediate_sink_name,
        ])
        if rc != 0:
            # Rollback: unload the sink we just created
            run_command(["pactl", "unload-module", cap.module_ids[0]], ignore_errors=True)
            raise RuntimeError(f"Failed to move stream {stream_index} to intermediate sink")

        # 3. Loopback: intermediate -> original speakers (so user still hears it)
        result = run_command([
            "pactl", "load-module", "module-loopback",
            f"source={cap.intermediate_sink_name}.monitor",
            f"sink={original_sink_name}",
            "source_dont_move=true",
            "sink_dont_move=true",
            "latency_msec=30",
        ])
        if result is None:
            # Rollback: restore stream, unload sink
            run_command(["pactl", "move-sink-input", str(stream_index), original_sink_name],
                        ignore_errors=True)
            run_command(["pactl", "unload-module", cap.module_ids[0]], ignore_errors=True)
            raise RuntimeError(f"Failed to create speaker loopback for stream {stream_index}")
        cap.module_ids.append(result.strip())

        # 4. Loopback: intermediate -> combined_mic (so Teams gets it)
        result = run_command([
            "pactl", "load-module", "module-loopback",
            f"source={cap.intermediate_sink_name}.monitor",
            f"sink={COMBINED_SINK_NAME}",
            "source_dont_move=true",
            "sink_dont_move=true",
            "latency_msec=30",
        ])
        if result is None:
            # Rollback: restore stream, unload loopback + sink
            run_command(["pactl", "move-sink-input", str(stream_index), original_sink_name],
                        ignore_errors=True)
            for mid in reversed(cap.module_ids):
                run_command(["pactl", "unload-module", mid], ignore_errors=True)
            raise RuntimeError(f"Failed to create combined loopback for stream {stream_index}")
        cap.module_ids.append(result.strip())

        self._captured_apps[stream_index] = cap

    def remove_app(self, stream_index):
        """Stop capturing an app stream: restore to original sink, unload modules."""
        cap = self._captured_apps.pop(stream_index, None)
        if cap is None:
            return

        # Restore stream to original sink (may fail if app exited — that's fine)
        run_command(
            ["pactl", "move-sink-input", str(stream_index), cap.original_sink_name],
            ignore_errors=True,
        )

        # Unload modules in reverse order (loopbacks before null-sink)
        for mid in reversed(cap.module_ids):
            run_command(["pactl", "unload-module", mid], ignore_errors=True)

    def teardown(self):
        """Full cleanup — idempotent. Restores all streams and unloads all modules."""
        # Remove all captured apps first
        for stream_index in list(self._captured_apps.keys()):
            self.remove_app(stream_index)

        # Unload mic loopback
        if self._mic_loopback_module:
            run_command(["pactl", "unload-module", self._mic_loopback_module], ignore_errors=True)
            self._mic_loopback_module = None

        # Unload combined_mic null-sink
        if self._combined_sink_module:
            run_command(["pactl", "unload-module", self._combined_sink_module], ignore_errors=True)
            self._combined_sink_module = None

        self._active = False
        self._mic_source = None

    def detect_disappeared_streams(self):
        """Check if any captured streams have disappeared (app exited). Clean up orphans."""
        disappeared = []
        for stream_index in list(self._captured_apps.keys()):
            if not self.scanner.stream_exists(stream_index):
                disappeared.append(stream_index)

        for stream_index in disappeared:
            print(f"Stream {stream_index} disappeared, cleaning up")
            self.remove_app(stream_index)

        return disappeared

    def _rollback_setup(self):
        """Rollback a partial setup()."""
        if self._combined_sink_module:
            run_command(["pactl", "unload-module", self._combined_sink_module], ignore_errors=True)
            self._combined_sink_module = None


# ---------------------------------------------------------------------------
# ConfigManager
# ---------------------------------------------------------------------------

class ConfigManager:
    """Persists user preferences."""

    def __init__(self):
        self.config_dir = os.path.expanduser("~/.config/app-audio-rerouter")
        self.config_file = os.path.join(self.config_dir, "config.json")

    def load(self):
        if not os.path.exists(self.config_file):
            return {}
        try:
            with open(self.config_file) as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading config: {e}")
            return {}

    def save(self, data):
        os.makedirs(self.config_dir, exist_ok=True)
        try:
            with open(self.config_file, "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")


# ---------------------------------------------------------------------------
# MainWindow
# ---------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.scanner = StreamScanner()
        self.pipeline = AudioPipeline()
        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load()

        self.setWindowTitle(APP_NAME)

        # Restore geometry
        geom = self.config.get("window_geometry")
        if geom:
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        else:
            self.resize(480, 420)

        icon = QIcon.fromTheme("audio-card")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-input-microphone")
        self.setWindowIcon(icon)

        # Menu bar
        menubar = self.menuBar()
        file_menu = menubar.addMenu("File")
        quit_action = QAction("Quit", self)
        quit_action.setShortcut("Ctrl+Q")
        quit_action.triggered.connect(self.quit_app)
        file_menu.addAction(quit_action)

        help_menu = menubar.addMenu("Help")
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Mic Source Section ---
        mic_group = QGroupBox("Microphone Source")
        mic_layout = QVBoxLayout()
        mic_group.setLayout(mic_layout)

        self.mic_combo = QComboBox()
        mic_layout.addWidget(self.mic_combo)

        refresh_mic_btn = QPushButton("Refresh Mics")
        refresh_mic_btn.clicked.connect(self.refresh_mics)
        mic_layout.addWidget(refresh_mic_btn)

        layout.addWidget(mic_group)

        # --- App Streams Section ---
        streams_group = QGroupBox("Application Audio Streams")
        streams_layout = QVBoxLayout()
        streams_group.setLayout(streams_layout)

        self.stream_list = QListWidget()
        streams_layout.addWidget(self.stream_list)

        refresh_btn = QPushButton("Refresh Streams")
        refresh_btn.clicked.connect(self.refresh_streams)
        streams_layout.addWidget(refresh_btn)

        layout.addWidget(streams_group)

        # --- Controls Section ---
        controls_group = QGroupBox("Controls")
        controls_layout = QVBoxLayout()
        controls_group.setLayout(controls_layout)

        btn_row = QHBoxLayout()
        self.start_stop_btn = QPushButton("Start Sharing")
        self.start_stop_btn.clicked.connect(self.on_start_stop)
        btn_row.addWidget(self.start_stop_btn)
        controls_layout.addLayout(btn_row)

        self.status_label = QLabel("Ready")
        controls_layout.addWidget(self.status_label)

        layout.addWidget(controls_group)

        # Populate mic sources and streams
        self.refresh_mics()
        self.refresh_streams()

        # Auto-refresh timer (3s) — only refreshes streams when not sharing
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._periodic_refresh)
        self.refresh_timer.start(3000)

        # Tray
        self.setup_tray()

    # --- Mic source management ---

    def refresh_mics(self):
        """Populate mic combo box, preserving current selection."""
        sources = self.scanner.get_mic_sources()
        default = self.scanner.get_default_source()
        last_used = self.config.get("last_mic_source", "")

        # Preserve current selection if user already picked one
        current_source = self.mic_combo.currentData()
        preferred = current_source or last_used

        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()

        select_idx = 0
        for i, src in enumerate(sources):
            self.mic_combo.addItem(src["description"], src["name"])
            if preferred and src["name"] == preferred:
                select_idx = i
            elif not preferred and src["name"] == default:
                select_idx = i

        if sources:
            self.mic_combo.setCurrentIndex(select_idx)
        self.mic_combo.blockSignals(False)

    # --- Stream list management ---

    def refresh_streams(self):
        """Refresh the app stream list with checkboxes."""
        streams = self.scanner.get_app_streams()
        captured = self.pipeline.captured_stream_indices

        # Build set of current checked items (by stream index) to preserve user selections
        previously_checked = set()
        for i in range(self.stream_list.count()):
            item = self.stream_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                idx = item.data(Qt.ItemDataRole.UserRole)
                if idx is not None:
                    previously_checked.add(idx)

        self.stream_list.clear()
        for stream in streams:
            item = QListWidgetItem(stream.display_name)
            item.setData(Qt.ItemDataRole.UserRole, stream.index)
            # Store sink name for pipeline use
            item.setData(Qt.ItemDataRole.UserRole + 1, stream.sink_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            if stream.index in captured:
                # Currently captured — show as checked and colored
                item.setCheckState(Qt.CheckState.Checked)
                item.setForeground(QBrush(QColor("#4CAF50")))
            elif stream.index in previously_checked:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

            self.stream_list.addItem(item)

    def _get_checked_streams(self):
        """Return list of (stream_index, sink_name) for checked items."""
        checked = []
        for i in range(self.stream_list.count()):
            item = self.stream_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                idx = item.data(Qt.ItemDataRole.UserRole)
                sink = item.data(Qt.ItemDataRole.UserRole + 1)
                if idx is not None:
                    checked.append((idx, sink))
        return checked

    # --- Start/Stop ---

    def on_start_stop(self):
        if self.pipeline.is_active:
            self._stop_sharing()
        else:
            self._start_sharing()

    def _start_sharing(self):
        checked = self._get_checked_streams()
        if not checked:
            self.status_label.setText("Select at least one app stream")
            return

        mic_source = self.mic_combo.currentData()
        if not mic_source:
            self.status_label.setText("No microphone source selected")
            return

        # Save last used mic
        self.config["last_mic_source"] = mic_source
        self.config_mgr.save(self.config)

        try:
            self.pipeline.setup(mic_source)
        except RuntimeError as e:
            self.status_label.setText(f"Setup failed: {e}")
            return

        errors = []
        for stream_index, sink_name in checked:
            try:
                self.pipeline.add_app(stream_index, sink_name)
            except RuntimeError as e:
                errors.append(f"Stream {stream_index}: {e}")

        if errors:
            self.status_label.setText(f"Sharing with errors: {'; '.join(errors)}")
        else:
            n = len(checked)
            self.status_label.setText(
                f"Sharing {n} stream{'s' if n != 1 else ''} — "
                f"select 'Combined_Mic' in Teams"
            )

        self.start_stop_btn.setText("Stop Sharing")
        self.mic_combo.setEnabled(False)
        self.refresh_streams()  # Update colors

    def _stop_sharing(self):
        self.pipeline.teardown()
        self.start_stop_btn.setText("Start Sharing")
        self.mic_combo.setEnabled(True)
        self.status_label.setText("Stopped — all streams restored")
        self.refresh_streams()

    # --- Periodic refresh ---

    def _periodic_refresh(self):
        if self.pipeline.is_active:
            # While sharing, check for disappeared streams
            disappeared = self.pipeline.detect_disappeared_streams()
            if disappeared:
                self.refresh_streams()
                remaining = len(self.pipeline.captured_stream_indices)
                if remaining == 0:
                    self._stop_sharing()
                    self.status_label.setText("All shared streams ended — stopped automatically")
                else:
                    self.status_label.setText(
                        f"{len(disappeared)} stream(s) ended, {remaining} still sharing"
                    )
        else:
            self.refresh_mics()
            self.refresh_streams()

    # --- Tray ---

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)
        icon = QIcon.fromTheme("audio-input-microphone")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-card")
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip(APP_NAME)

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        menu.addAction(show_action)

        start_stop_action = QAction("Start/Stop", self)
        start_stop_action.triggered.connect(self.on_start_stop)
        menu.addAction(start_stop_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)

        menu.addSeparator()
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        geom = self.config.get("window_geometry")
        if geom:
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        self.show()
        self.raise_()
        self.activateWindow()

    # --- Window events ---

    def closeEvent(self, event):
        self._save_geometry()
        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def quit_app(self):
        self._save_geometry()
        self.pipeline.teardown()
        QApplication.quit()

    def _save_geometry(self):
        self.config["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.config_mgr.save(self.config)

    # --- About ---

    def show_about(self):
        QMessageBox.about(
            self,
            f"About {APP_NAME}",
            f"{APP_NAME}\n\n"
            "Routes application audio into a virtual microphone\n"
            "for sharing in Teams meetings.\n\n"
            "Select apps to share, click Start, then choose\n"
            "'Combined_Mic' as your mic in Teams.",
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setDesktopFileName("app-audio-rerouter")

    # Single-instance check
    socket = QLocalSocket()
    socket.connectToServer(SOCKET_NAME)
    if socket.waitForConnected(500):
        print("Already running — bringing to front.")
        socket.write(b"SHOW")
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        sys.exit(0)

    QLocalServer.removeServer(SOCKET_NAME)
    server = QLocalServer()
    if not server.listen(SOCKET_NAME):
        print(f"Warning: Could not start local server on {SOCKET_NAME}")

    window = MainWindow()

    def handle_new_connection():
        client = server.nextPendingConnection()
        if not client:
            return
        client.waitForReadyRead(1000)
        data = client.readAll().data()
        if b"SHOW" in data:
            window.show_window()
        client.disconnectFromServer()

    server.newConnection.connect(handle_new_connection)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
