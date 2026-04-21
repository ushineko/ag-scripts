import os
import re
import sys
import subprocess

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QListWidget, QListWidgetItem, QPushButton, QCheckBox,
    QLabel, QGroupBox, QHBoxLayout,
    QAbstractItemView, QSystemTrayIcon, QMenu, QDialog,
    QTextBrowser, QDialogButtonBox, QSlider, QSpinBox,
    QComboBox
)
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QBrush, QColor, QIcon, QAction

from audio_source_switcher.config import ConfigManager
from audio_source_switcher.controllers.audio import AudioController
from audio_source_switcher.controllers.bluetooth import BluetoothController, ConnectThread
from audio_source_switcher.controllers.pipewire import PipeWireController


class MainWindow(QMainWindow):
    def __init__(self, target_device: str | None = None):
        super().__init__()
        self.audio = AudioController()
        self.bt = BluetoothController()

        self.config_mgr = ConfigManager()
        self.config = self.config_mgr.load_config()
        self.cache_bt_devices = []
        self.target_device_cli = target_device

        # Load cache immediately
        self.cache_bt_devices = self.bt.get_devices()

        # Circuit breaker for JamesDSP crashes/loops
        self.jdsp_broken_state = False
        # Track last physical sink to suppress redundant notifications
        self._last_physical_sink = None

        if self.target_device_cli:
            # Headless Mode — no UI, just connect/switch and exit
            print(f"CLI: Attempting to connect/switch to '{self.target_device_cli}'")
            self.move_streams_cb = QCheckBox()
            self.move_streams_cb.setChecked(True)
            self.status_label = QLabel()
            QTimer.singleShot(0, self.handle_cli_command)
            return

        self.setWindowTitle("Audio Source Switcher")

        # Restore Geometry
        geom = self.config.get("window_geometry")
        if geom:
            from PyQt6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))
        else:
            self.resize(500, 600)

        # Window Icon
        icon = QIcon.fromTheme("audio-card")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-volume-high")
        self.setWindowIcon(icon)

        # Menu Bar
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

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- Audio Devices Section ---
        audio_group = QGroupBox("Audio Outputs (Drag to Reorder Priority)")
        audio_layout = QVBoxLayout()
        audio_group.setLayout(audio_layout)

        # JamesDSP Status Banner
        self.jdsp_label = QLabel("✨ Effects Active (JamesDSP)")
        self.jdsp_label.setStyleSheet("color: #4CAF50; font-weight: bold; font-size: 11pt;")
        self.jdsp_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.jdsp_label.hide()
        audio_layout.addWidget(self.jdsp_label)

        self.sink_list = QListWidget()
        self.sink_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.sink_list.itemDoubleClicked.connect(self.on_sink_activated)
        self.sink_list.model().rowsMoved.connect(self.on_list_reordered)

        # Context Menu
        self.sink_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.sink_list.customContextMenuRequested.connect(self.on_sink_list_menu)

        audio_layout.addWidget(self.sink_list)
        main_layout.addWidget(audio_group)

        # --- Bluetooth Section ---
        bt_group = QGroupBox("Bluetooth Devices")
        bt_layout = QVBoxLayout()
        bt_group.setLayout(bt_layout)

        self.bt_list = QListWidget()
        self.bt_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        bt_layout.addWidget(self.bt_list)

        btn_layout = QHBoxLayout()
        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.on_bt_connect)
        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.clicked.connect(self.on_bt_disconnect)
        btn_layout.addWidget(self.btn_connect)
        btn_layout.addWidget(self.btn_disconnect)
        bt_layout.addLayout(btn_layout)

        main_layout.addWidget(bt_group)

        # --- Volume Section ---
        vol_group = QGroupBox("Volume Control")
        vol_layout = QVBoxLayout()
        vol_group.setLayout(vol_layout)

        self.vol_label = QLabel("Volume: --%")
        self.vol_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vol_layout.addWidget(self.vol_label)

        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(0, 150)
        self.vol_slider.valueChanged.connect(self.on_vol_slider_changed)
        self.vol_slider.sliderReleased.connect(self.on_vol_slider_released)
        vol_layout.addWidget(self.vol_slider)

        main_layout.addWidget(vol_group)

        # --- Footer Controls ---
        controls_group = QGroupBox("Settings")
        controls_layout = QVBoxLayout()
        controls_group.setLayout(controls_layout)

        self.move_streams_cb = QCheckBox("Move playing audio on switch")
        self.move_streams_cb.setChecked(True)
        controls_layout.addWidget(self.move_streams_cb)

        self.auto_switch_cb = QCheckBox("Auto-switch to highest priority device")
        self.auto_switch_cb.setChecked(self.config.get("auto_switch", False))
        self.auto_switch_cb.toggled.connect(self.on_auto_switch_toggled)
        controls_layout.addWidget(self.auto_switch_cb)

        self.loopback_cb = QCheckBox("Enable Line-In Loopback")
        self.loopback_cb.clicked.connect(self.on_loopback_toggled)
        controls_layout.addWidget(self.loopback_cb)

        self.status_label = QLabel("Ready")
        controls_layout.addWidget(self.status_label)

        self.refresh_btn = QPushButton("Refresh All")
        self.refresh_btn.clicked.connect(self.refresh_all_force)
        controls_layout.addWidget(self.refresh_btn)

        main_layout.addWidget(controls_group)

        # --- Headset Settings Section ---
        self.headset_group = QGroupBox("Headset Settings")
        headset_layout = QVBoxLayout()
        self.headset_group.setLayout(headset_layout)

        h_layout = QHBoxLayout()

        self.idle_cb = QCheckBox("Disconnect on Idle")
        self.idle_cb.toggled.connect(self.on_idle_toggled)
        h_layout.addWidget(self.idle_cb)

        self.idle_spin = QSpinBox()
        self.idle_spin.setRange(1, 90)
        self.idle_spin.setSuffix(" min")
        self.idle_spin.setValue(10)
        self.idle_spin.valueChanged.connect(self.on_idle_spin_changed)
        h_layout.addWidget(self.idle_spin)

        headset_layout.addLayout(h_layout)
        main_layout.addWidget(self.headset_group)

        # Initialize Headset UI State
        self.init_headset_ui()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh_all)
        self.timer.start(5000)

        self.refresh_all()

        # Restore direct loopback from config (only if no service manages it)
        self._restore_loopback_from_config()

        # System Tray Setup
        self.setup_tray()

    # ── Helpers ──────────────────────────────────────────────────────

    def _get_bt_map(self) -> dict[str, str]:
        return {d['mac']: d['name'] for d in self.cache_bt_devices}

    def get_actual_active_sink_name(self) -> str | None:
        """Helper to find the physical sink we should be controlling/displaying."""
        sinks = self.audio.get_sinks(self._get_bt_map())
        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)

        if default_sink_name == "jamesdsp_sink":
            pw = PipeWireController()
            target = pw.get_jamesdsp_target()
            if target:
                return target

        return default_sink_name

    # ── Volume ───────────────────────────────────────────────────────

    def refresh_volume_ui(self):
        target_name = self.get_actual_active_sink_name()
        if not target_name:
            self.vol_label.setText("Volume: --%")
            self.vol_slider.setEnabled(False)
            return

        vol = self.audio.get_sink_volume(target_name)
        if vol is not None:
            self.vol_slider.blockSignals(True)
            self.vol_slider.setValue(vol)
            self.vol_slider.blockSignals(False)
            self.vol_label.setText(f"Volume: {vol}%")
            self.vol_slider.setEnabled(True)
        else:
            self.vol_label.setText("Volume: ??%")
            self.vol_slider.setEnabled(False)

    def on_vol_slider_changed(self, value: int):
        self.vol_label.setText(f"Volume: {value}%")
        # sliderReleased only fires for handle drags. Click-on-groove, keyboard,
        # and wheel emit valueChanged without any press/release — push here when
        # the user isn't mid-drag so those paths actually apply.
        if not self.vol_slider.isSliderDown():
            self._apply_slider_volume(value)

    def on_vol_slider_released(self):
        self._apply_slider_volume(self.vol_slider.value())

    def _apply_slider_volume(self, val: int):
        target_name = self.get_actual_active_sink_name()
        if target_name:
            print(f"Setting volume of {target_name} to {val}%")
            self.audio.set_sink_volume(target_name, val)

    def check_and_sync_volume(self):
        """Polls JamesDSP volume. If != 100%, syncs to hardware."""
        try:
            jdsp_vol = self.audio.get_sink_volume("jamesdsp_sink")

            if jdsp_vol is None or jdsp_vol == 100:
                return

            pw = PipeWireController()
            jdsp_outs = pw.get_jamesdsp_outputs()

            if not jdsp_outs:
                print("DEBUG: JamesDSP is active but has no outputs. Cannot sync volume.")
                return

            found_target = pw.find_linked_sink(jdsp_outs[0])

            if not found_target:
                print("DEBUG: JamesDSP is active but floating. Cannot sync volume.")
                return

            current_target_vol = self.audio.get_sink_volume(found_target)
            if current_target_vol is None:
                return

            factor = jdsp_vol / 100.0
            new_vol = int(current_target_vol * factor)

            print(f"Volume Sync: JDSP={jdsp_vol}%, Target={current_target_vol}% -> {new_vol}%")

            self.audio.set_sink_volume(found_target, new_vol)
            self.audio.set_sink_volume("jamesdsp_sink", 100)

        except Exception as e:
            print(f"Error in volume sync: {e}")

    # ── System Tray ──────────────────────────────────────────────────

    def setup_tray(self):
        self.tray_icon = QSystemTrayIcon(self)

        icon = QIcon.fromTheme("audio-card")
        if icon.isNull():
            icon = QIcon.fromTheme("audio-volume-high")

        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("Audio Source Switcher")

        menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_window)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.quit_app)

        menu.addAction(show_action)

        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        menu.addAction(about_action)

        menu.addSeparator()
        menu.addAction(quit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.activated.connect(self.on_tray_activated)
        self.tray_icon.show()

    def show_about(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Help & About")
        dlg.resize(600, 500)

        layout = QVBoxLayout()
        dlg.setLayout(layout)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(self.get_help_text())
        layout.addWidget(browser)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        dlg.exec()

    def get_help_text(self) -> str:
        return """
        <div align="center">
            <h1>Audio Source Switcher</h1>
            <p><b>Version 12.1</b></p>
            <p>A power-user utility for managing audio outputs on Linux (PulseAudio/PipeWire).</p>
            <p>Copyright (c) 2026 ushineko</p>
        </div>
        <hr>

        <h3>🎧 Managing Audio</h3>
        <ul>
            <li><b>Switch Output:</b> Double-click a device in the list to switch audio to it.</li>
            <li><b>Priority:</b> Drag and drop devices to reorder them. If <i>"Auto-switch"</i> is checked, the app will automatically switch to the highest-priority connected device.</li>
            <li><b>Bluetooth:</b> Click "Connect" to pair/connect to a selected device. Offline devices can be auto-connected by double-clicking them in the main list.</li>
            <li><b>Mic Association:</b> Right-click a device to Link a specific Microphone to it (or use Auto mode).</li>
        </ul>

        <h3>🎤 Microphone Association</h3>
        <p>Automatically switch input devices when changing outputs:</p>
        <ul>
            <li><b>Link Mic:</b> Right-click an output device in the list and select <b>"Link Microphone..."</b> to choose which input should be activated when this output is selected.</li>
            <li><b>Auto-Link:</b> By default (Auto), the app tries to match the input device belonging to the same hardware (e.g., switching to AirPods Output also switches to AirPods Mic).</li>
        </ul>

        <h3>🎧 Arctis Headset Control</h3>
        <p>If a SteelSeries Arctis headset is detected:</p>
        <ul>
             <li><b>Disconnect on Idle:</b> Automatically turn off the headset to save battery when no audio is playing for a set duration. Configure the timeout (1-90 mins) in the standard settings area.</li>
        </ul>

        <h3>🔊 JamesDSP Integration</h3>
        <p>The app intelligently handles the <b>JamesDSP</b> effects processor:</p>
        <ul>
            <li><b>Effects Active:</b> Audio is routed through JamesDSP before reaching your speakers/headphones.</li>
            <li><b>Smart Switching:</b> When you select a device, the app <i>rewires</i> the internal graph so effects are preserved.</li>
            <li><b>Safety:</b> Includes a "Circuit Breaker" to prevent crashes if JamesDSP becomes unstable.</li>
        </ul>

        <h3>🎙️ Line-In Loopback</h3>
        <p>Use the <b>"Line-In Loopback"</b> checkbox to listen to your Line-In device (e.g. game console input, external mixer) through your current output.</p>
        <p>If an <code>audio-loopback.service</code> systemd user service is installed, the checkbox controls that service. Otherwise, the app manages a <code>pw-loopback</code> process directly. The label indicates which mode is active.</p>

        <h3>🧠 Smart Jack Detection</h3>
        <p>The app intelligently detects if "Front Headphones" are physically unplugged. Unplugged devices are marked as <code>[Disconnected]</code> and skipped by the auto-switcher.</p>

        <h3>⌨️ Global Hotkeys & CLI</h3>
        <p>Control the app from the terminal or system shortcuts:</p>
        <ul>
            <li><b>Switch Device:</b><br><code>--connect "Device Name"</code> (or ID)</li>
            <li><b>Hardware Volume (Bypasses DSP):</b><br><code>--vol-up</code> / <code>--vol-down</code></li>
        </ul>
        <p><i>Tip: Right-click a device in the list to copy its instant Command ID.</i></p>
        """

    def on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self.show_window()

    def show_window(self):
        geom = self.config.get("window_geometry")
        if geom:
            from PyQt6.QtCore import QByteArray
            self.restoreGeometry(QByteArray.fromHex(geom.encode()))

        self.show()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        self.config["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.config_mgr.save_config(self.config)

        if self.tray_icon.isVisible():
            self.hide()
            event.ignore()
        else:
            event.accept()

    def quit_app(self):
        self.config["window_geometry"] = self.saveGeometry().toHex().data().decode()
        self.config_mgr.save_config(self.config)
        self.audio.cleanup_loopback()
        QApplication.quit()

    # ── Settings Handlers ────────────────────────────────────────────

    def on_auto_switch_toggled(self, checked: bool):
        self.config["auto_switch"] = checked
        self.config_mgr.save_config(self.config)

    def on_list_reordered(self):
        priority_list = []
        for i in range(self.sink_list.count()):
            item = self.sink_list.item(i)
            priority_list.append(item.data(Qt.ItemDataRole.UserRole))

        self.config["device_priority"] = priority_list
        self.config_mgr.save_config(self.config)
        self.status_label.setText("Priority saved.")

    # ── Refresh ──────────────────────────────────────────────────────

    def refresh_all_force(self):
        self.refresh_all()
        self.status_label.setText("Refreshed.")

    def refresh_all(self):
        self.cache_bt_devices = self.bt.get_devices()

        self.refresh_bt_list_ui()
        self.refresh_sinks_ui()
        self.refresh_volume_ui()
        self.refresh_loopback_ui()

        if self.auto_switch_cb.isChecked():
            self.run_auto_switch()

    # ── Auto-Switch ──────────────────────────────────────────────────

    def run_auto_switch(self):
        bt_map = self._get_bt_map()
        sinks = self.audio.get_sinks(bt_map)
        sink_map = {s['priority_id']: s for s in sinks}

        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        jamesdsp_available = any(s['name'] == "jamesdsp_sink" for s in sinks)

        current_is_valid = False
        if default_sink_name:
            for s in sinks:
                if s['name'] == default_sink_name:
                    current_is_valid = s.get('connected', True)
                    break

        priority_list = self.config.get("device_priority", [])
        target_sink_obj = None

        for pid in priority_list:
            if pid in sink_map:
                if "jamesdsp_sink" in pid:
                    continue
                s = sink_map[pid]
                if s.get('connected', True):
                    target_sink_obj = s
                    break

        should_switch = False

        if target_sink_obj:
            target_name = target_sink_obj['name']

            # 1. Basic Mismatch
            if default_sink_name != target_name:
                should_switch = True

            # 2. JamesDSP Enforcement
            if jamesdsp_available and default_sink_name == target_name and default_sink_name != "jamesdsp_sink":
                pw = PipeWireController()
                has_outputs = bool(pw.get_jamesdsp_outputs())
                if self.jdsp_broken_state and has_outputs:
                    print("JamesDSP outputs restored. Resetting circuit breaker.")
                    self.jdsp_broken_state = False
                if not self.jdsp_broken_state and has_outputs:
                    should_switch = True

            # 3. JamesDSP Correctness
            if default_sink_name == "jamesdsp_sink":
                try:
                    pw = PipeWireController()
                    jdsp_target = pw.get_jamesdsp_target()
                    jdsp_has_outputs = bool(pw.get_jamesdsp_outputs())

                    if jdsp_target:
                        if jdsp_target != target_name:
                            should_switch = True
                        else:
                            current_is_valid = True
                            should_switch = False
                    elif not jdsp_has_outputs:
                        # JDSP plugin suspended — idle, not broken
                        current_is_valid = True
                        should_switch = False
                    else:
                        # JDSP has outputs but no links — floating, fix it
                        should_switch = True

                except Exception as e:
                    print(f"Error checking JDSP routing: {e}")
                    should_switch = True


        # Fallback: pick any connected device
        if not target_sink_obj and not current_is_valid and sinks:
            for s in sinks:
                if s.get('connected', True):
                    target_sink_obj = s
                    should_switch = True
                    break

        if should_switch and target_sink_obj:
            target_name = target_sink_obj['name']
            print(f"Auto-switching to {target_name}")
            self.switch_to_sink(target_name, target_sink_obj['display_name'])

    # ── List Widget Utils ────────────────────────────────────────────

    def update_list_widget(self, list_widget: QListWidget, new_items_data: list[dict]):
        """Generic in-place updater for QListWidget to preserve selection and clicks."""
        existing_ids = {}
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            uid = item.data(Qt.ItemDataRole.UserRole)
            existing_ids[uid] = item

        items_to_keep = set()

        for idx, new_item in enumerate(new_items_data):
            uid = new_item['id']
            items_to_keep.add(uid)

            if uid in existing_ids:
                item = existing_ids[uid]
                if item.text() != new_item['text']:
                    item.setText(new_item['text'])

                font = item.font()
                if font.bold() != new_item['bold']:
                    font.setBold(new_item['bold'])
                    item.setFont(font)

                if new_item.get('color'):
                    item.setForeground(QBrush(new_item['color']))
                else:
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
            else:
                item = QListWidgetItem(new_item['text'])
                item.setData(Qt.ItemDataRole.UserRole, uid)

                font = item.font()
                font.setBold(new_item['bold'])
                item.setFont(font)

                if new_item.get('color'):
                    item.setForeground(QBrush(new_item['color']))
                else:
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)

                list_widget.insertItem(idx, item)

        for i in range(list_widget.count() - 1, -1, -1):
            item = list_widget.item(i)
            uid = item.data(Qt.ItemDataRole.UserRole)
            if uid not in items_to_keep:
                list_widget.takeItem(i)

    # ── Sink List UI ─────────────────────────────────────────────────

    def refresh_sinks_ui(self):
        bt_map = self._get_bt_map()
        sinks = self.audio.get_sinks(bt_map)

        default_sink_name = next((s['name'] for s in sinks if s['is_default']), None)
        active_real_sink_name = default_sink_name
        is_jdsp_default = (default_sink_name == "jamesdsp_sink")

        if is_jdsp_default:
            self.jdsp_label.show()
            pw = PipeWireController()
            target = pw.get_jamesdsp_target()
            if target:
                active_real_sink_name = target
        else:
            self.jdsp_label.hide()

        # Merge offline devices from config priority list
        priority_list = self.config.get("device_priority", [])
        online_map = {s['priority_id']: s for s in sinks}

        final_list = []
        seen_ids = set()

        for pid in priority_list:
            if pid in seen_ids:
                continue
            if "jamesdsp_sink" in pid:
                continue

            if pid in online_map:
                final_list.append(online_map[pid])
                seen_ids.add(pid)
            else:
                display = pid
                if pid.startswith("bt:"):
                    mac = pid[3:]
                    for d in self.cache_bt_devices:
                        if d['mac'] == mac:
                            display = d['name']
                            break
                final_list.append({
                    'name': None,
                    'priority_id': pid,
                    'display_name': f"{display} [Disconnected]",
                    'is_default': False,
                    'connected': False
                })
                seen_ids.add(pid)

        for s in sinks:
            if s['priority_id'] not in seen_ids:
                if "jamesdsp_sink" in s['priority_id'] or s['name'] == "jamesdsp_sink":
                    continue
                final_list.append(s)
                seen_ids.add(s['priority_id'])

        # Build Presentation Items
        new_items = []
        active_item_index = -1

        for idx, s in enumerate(final_list):
            is_active = (s['name'] is not None and s['name'] == active_real_sink_name)
            text = s['display_name']
            if is_active:
                text = f"✅ {text}"
                active_item_index = idx

            color = None
            if not s['connected']:
                color = QColor("gray")
            elif is_active:
                color = QColor("#4CAF50")

            new_items.append({
                'id': s['priority_id'],
                'text': text,
                'bold': is_active,
                'color': color,
                'is_active': is_active
            })

        self.update_list_widget(self.sink_list, new_items)

        if not self.sink_list.currentItem() and active_item_index >= 0:
            item = self.sink_list.item(active_item_index)
            if item:
                self.sink_list.setCurrentItem(item)
                self.sink_list.scrollToItem(item)

        if active_item_index >= 0:
            clean_name = new_items[active_item_index]['text'].replace("✅ ", "")
            self.status_label.setText(f"Active: {clean_name}")

    def refresh_bt_list_ui(self):
        data_list = []
        for dev in self.cache_bt_devices:
            state = "Connected" if dev['connected'] else "Disconnected"
            text = f"{dev['name']} [{state}]"
            color = Qt.GlobalColor.darkGreen if dev['connected'] else Qt.GlobalColor.gray

            data_list.append({
                'id': dev['mac'],
                'text': text,
                'bold': dev['connected'],
                'color': color
            })

        self.update_list_widget(self.bt_list, data_list)

    # ── Device Switching ─────────────────────────────────────────────

    def on_sink_activated(self, item):
        self.jdsp_broken_state = False
        priority_id = item.data(Qt.ItemDataRole.UserRole)

        bt_map = self._get_bt_map()
        sinks = self.audio.get_sinks(bt_map)

        target_sink = None
        for s in sinks:
            if s['priority_id'] == priority_id:
                target_sink = s['name']
                break

        if target_sink:
            self.switch_to_sink(target_sink, item.text())
        else:
            if priority_id.startswith("bt:"):
                mac = priority_id[3:]
                self.status_label.setText(f"Connecting to {mac}...")
                self.sink_list.setEnabled(False)

                self.connect_thread = ConnectThread(mac)
                self.connect_thread.finished_signal.connect(lambda s, m: self.on_connect_finished(s, m, priority_id))
                self.connect_thread.start()
            else:
                self.status_label.setText("Device is offline (non-BT), cannot switch.")

    def on_connect_finished(self, success: bool, msg: str, priority_id: str):
        if not success:
            self.status_label.setText(msg)
            self.sink_list.setEnabled(True)
            return

        self.status_label.setText("Connected! Waiting for audio device...")
        self.poll_attempts = 0
        self.max_poll_attempts = 20
        self.pending_switch_id = priority_id

        self.connect_poll_timer = QTimer()
        self.connect_poll_timer.timeout.connect(self.check_sink_available)
        self.connect_poll_timer.start(500)

    def check_sink_available(self):
        self.poll_attempts += 1
        self.refresh_all()

        bt_map = self._get_bt_map()
        sinks = self.audio.get_sinks(bt_map)

        target_sink = None
        for s in sinks:
            if s['priority_id'] == self.pending_switch_id:
                target_sink = s['name']
                break

        if target_sink:
            self.connect_poll_timer.stop()
            self.switch_to_sink(target_sink, self.pending_switch_id)
            self.sink_list.setEnabled(True)
            self.status_label.setText(f"Connected & Switched to {self.pending_switch_id}")
        elif self.poll_attempts >= self.max_poll_attempts:
            self.connect_poll_timer.stop()
            self.sink_list.setEnabled(True)
            self.status_label.setText("Connection successful, but audio device did not appear.")

    def switch_to_sink(self, sink_name: str, display_text: str):
        use_jamesdsp = False
        jamesdsp_sink_name = "jamesdsp_sink"

        if sink_name != jamesdsp_sink_name and not self.jdsp_broken_state:
            pw = PipeWireController()
            jdsp_outs = pw.get_jamesdsp_outputs()
            if jdsp_outs:
                use_jamesdsp = True
                print("JamesDSP detected. Attempting graph rewiring...")

        if use_jamesdsp:
            self.audio.set_default_sink(jamesdsp_sink_name)
            if self.move_streams_cb.isChecked():
                self.audio.move_input_streams(jamesdsp_sink_name)

            success = pw.relink_jamesdsp(sink_name)
            if success:
                print(f"Rewired JamesDSP -> {sink_name}")
                self.jdsp_broken_state = False
            else:
                print("Failed to rewire JamesDSP. Fallback to direct switch.")
                self.jdsp_broken_state = True
                self.audio.set_default_sink(sink_name)
                if self.move_streams_cb.isChecked():
                    self.audio.move_input_streams(sink_name)
        else:
            self.audio.set_default_sink(sink_name)
            if self.move_streams_cb.isChecked():
                self.audio.move_input_streams(sink_name)

        # Microphone Association Logic
        mic_links = self.config.get("mic_links", {})
        p_id = None
        sink_props = {}

        bt_map = self._get_bt_map()
        current_sinks = self.audio.get_sinks(bt_map)

        for s in current_sinks:
            if s['name'] == sink_name:
                p_id = s['priority_id']
                sink_props = s.get('properties', {})
                break

        target_source_name = None
        mic_msg = ""

        if p_id:
            link_cfg = mic_links.get(p_id, "auto")

            if link_cfg == "default":
                pass
            elif link_cfg == "auto":
                sources = self.audio.get_sources(bt_map)
                matched = self.audio.find_associated_source(sink_props, sources)
                if matched:
                    target_source_name = matched['name']
                    mic_msg = f" + Mic: {matched['display_name']}"
            else:
                target_source_name = link_cfg
                sources = self.audio.get_sources(bt_map)
                for src in sources:
                    if src['name'] == target_source_name:
                        mic_msg = f" + Mic: {src['display_name']}"
                        break

        if target_source_name:
            print(f"Switching Mic to: {target_source_name}")
            self.audio.set_default_source(target_source_name)

        # PA race condition fix
        QTimer.singleShot(150, self.refresh_sinks_ui)

        clean_text = display_text.replace(" (Active)", "")
        self.status_label.setText(f"Switched to: {clean_text}{mic_msg}")

        physical_changed = (sink_name != self._last_physical_sink)
        self._last_physical_sink = sink_name
        if physical_changed:
            self.send_notification(
                "Audio Switched",
                f"Output: {clean_text}\nInput: {mic_msg.replace(' + Mic: ', '') if mic_msg else 'Unchanged'}"
            )

    # ── Notifications ────────────────────────────────────────────────

    def send_notification(self, title: str, message: str, icon: str = "audio-card",
                          sound: str = "message-new-instant"):
        try:
            subprocess.run([
                'notify-send',
                '-a', 'Audio Switcher',
                '-i', icon,
                '-h', f'string:sound-name:{sound}',
                title,
                message
            ])
        except Exception:
            if self.tray_icon and self.tray_icon.isVisible():
                self.tray_icon.showMessage(
                    title,
                    message,
                    QSystemTrayIcon.MessageIcon.NoIcon,
                    3000
                )

    # ── Loopback ─────────────────────────────────────────────────────

    def on_loopback_toggled(self, checked: bool):
        source = self.audio.get_line_in_source()
        if source:
            self.audio.set_loopback_state(checked, source)
            status = "Enabled" if checked else "Disabled"
            self.status_label.setText(f"Loopback {status}")
            self.config["loopback_enabled"] = checked
            self.config_mgr.save_config(self.config)
        else:
            self.status_label.setText("Line-In Source Not Found")
            self.loopback_cb.setChecked(False)

    def refresh_loopback_ui(self):
        source = self.audio.get_line_in_source()
        if not source:
            self.loopback_cb.setEnabled(False)
            self.loopback_cb.setText("Line-In Loopback (No Line-In Device Found)")
            return

        self.loopback_cb.setEnabled(True)
        is_active, mode = self.audio.get_loopback_state(source)

        if mode == 'service':
            self.loopback_cb.setText("Line-In Loopback (via audio-loopback service)")
        else:
            self.loopback_cb.setText("Line-In Loopback")

        self.loopback_cb.blockSignals(True)
        self.loopback_cb.setChecked(is_active)
        self.loopback_cb.blockSignals(False)

    def _restore_loopback_from_config(self):
        """On startup, restore direct loopback if config says it was enabled
        and no systemd service is managing it."""
        if not self.config.get("loopback_enabled", False):
            return
        source = self.audio.get_line_in_source()
        if not source:
            return
        if self.audio.has_loopback_service():
            return
        print(f"Restoring direct loopback from config for {source}")
        self.audio.set_loopback_state(True, source)
        self.refresh_loopback_ui()

    # ── Headset Settings ─────────────────────────────────────────────

    def init_headset_ui(self):
        minutes = self.config.get("arctis_idle_minutes", 0)

        self.idle_cb.blockSignals(True)
        self.idle_spin.blockSignals(True)

        if minutes > 0:
            self.idle_cb.setChecked(True)
            self.idle_spin.setEnabled(True)
            self.idle_spin.setValue(minutes)
        else:
            self.idle_cb.setChecked(False)
            self.idle_spin.setEnabled(False)

        self.idle_cb.blockSignals(False)
        self.idle_spin.blockSignals(False)

        status = self.audio.headset.get_battery_status()
        self.headset_group.setEnabled(status is not None)
        if status is None:
            self.headset_group.setTitle("Headset Settings (Not Detected)")
        else:
            self.headset_group.setTitle("Headset Settings")

    def on_idle_toggled(self, checked: bool):
        self.idle_spin.setEnabled(checked)
        self.apply_idle_settings()

    def on_idle_spin_changed(self, value: int):
        self.apply_idle_settings()

    def apply_idle_settings(self):
        minutes = 0
        if self.idle_cb.isChecked():
            minutes = self.idle_spin.value()

        self.config["arctis_idle_minutes"] = minutes
        self.config_mgr.save_config(self.config)

        success = self.audio.headset.set_inactive_time(minutes)
        if success:
            state = f"{minutes} min" if minutes > 0 else "Disabled"
            self.status_label.setText(f"Headset Idle: {state}")
        else:
            self.status_label.setText("Error applying headset settings.")

    # ── Bluetooth ────────────────────────────────────────────────────

    def get_selected_bt_mac(self) -> str | None:
        item = self.bt_list.currentItem()
        if item:
            return item.data(Qt.ItemDataRole.UserRole)
        return None

    def on_bt_connect(self):
        mac = self.get_selected_bt_mac()
        if mac:
            self.status_label.setText(f"Connecting {mac}...")
            QApplication.processEvents()
            self.bt.connect(mac)
            self.refresh_all()
            self.status_label.setText(f"Connected {mac}")

    def on_bt_disconnect(self):
        mac = self.get_selected_bt_mac()
        if mac:
            self.status_label.setText(f"Disconnecting {mac}...")
            QApplication.processEvents()
            self.bt.disconnect(mac)
            self.refresh_all()
            self.status_label.setText(f"Disconnected {mac}")

    # ── CLI Mode ─────────────────────────────────────────────────────

    def handle_cli_command(self):
        target = self.target_device_cli

        bt_map = self._get_bt_map()
        sinks = self.audio.get_sinks(bt_map)

        found_sink = None
        found_priority_id = None

        # Exact match on priority_id
        for s in sinks:
            if s['priority_id'] == target:
                found_sink = s
                found_priority_id = s['priority_id']
                break

        # Substring match on display_name or name
        if not found_sink:
            target_lower = target.lower()
            for s in sinks:
                if (target_lower in s['display_name'].lower() or
                        target_lower in s['name'].lower() or
                        target_lower in s['priority_id'].lower()):
                    found_sink = s
                    found_priority_id = s['priority_id']
                    break

        # Try offline BT cache
        if not found_sink:
            target_lower = target.lower()
            search_target = target_lower
            if search_target.startswith("bt:"):
                search_target = search_target[3:]

            for d in self.cache_bt_devices:
                if search_target in d['name'].lower() or search_target in d['mac'].lower():
                    found_priority_id = f"bt:{d['mac']}"
                    found_sink = {'priority_id': found_priority_id, 'name': None, 'display_name': d['name']}
                    break

        if found_sink:
            print(f"CLI: Found match -> {found_priority_id}")

            target_name = found_sink.get('name')
            if target_name:
                print("CLI: Device is online. Switching...")
                self.switch_to_sink(target_name, found_sink.get('display_name', target))
                sys.exit(0)
            else:
                if found_priority_id.startswith("bt:"):
                    mac = found_priority_id[3:]
                    print(f"CLI: Device offline. Connecting to {mac}...")
                    self.send_notification("Connecting...", f"Connecting to {mac}")

                    self.connect_thread = ConnectThread(mac)
                    self.connect_thread.finished_signal.connect(
                        lambda s, m: self.on_cli_connect_finished(s, m, found_priority_id)
                    )
                    self.connect_thread.start()
                else:
                    msg = "Error - Device is offline and not Bluetooth."
                    print(f"CLI: {msg}")
                    self.send_notification("Switch Failed", msg, "dialog-error")
                    sys.exit(1)
        else:
            msg = f"Error - Device '{target}' not found."
            print(f"CLI: {msg}")
            self.send_notification("Switch Failed", msg, "dialog-error")
            sys.exit(1)

    def on_cli_connect_finished(self, success: bool, msg: str, priority_id: str):
        if not success:
            print(f"CLI: Connection Failed: {msg}")
            self.send_notification("Connection Failed", msg, "dialog-error")
            sys.exit(1)

        print("CLI: Connected. Waiting for sink...")
        self.poll_attempts = 0
        self.max_poll_attempts = 20
        self.pending_switch_id = priority_id

        self.connect_poll_timer = QTimer()
        self.connect_poll_timer.timeout.connect(self.check_sink_available_cli)
        self.connect_poll_timer.start(500)

    def check_sink_available_cli(self):
        self.poll_attempts += 1

        sinks = self.audio.get_sinks({})

        target_sink = None
        for s in sinks:
            if s['priority_id'] == self.pending_switch_id:
                target_sink = s['name']
                break

        if target_sink:
            self.connect_poll_timer.stop()
            print("CLI: Sink appeared. Switching...")
            self.switch_to_sink(target_sink, self.pending_switch_id)
            sys.exit(0)
        elif self.poll_attempts >= self.max_poll_attempts:
            msg = "Timeout waiting for sink."
            print(f"CLI: {msg}")
            self.send_notification("Connection Timeout", msg, "dialog-error")
            sys.exit(1)

    # ── Context Menu ─────────────────────────────────────────────────

    def on_sink_list_menu(self, pos):
        item = self.sink_list.itemAt(pos)
        if not item:
            return

        menu = QMenu()

        link_mic_action = QAction("Link Microphone...", self)
        link_mic_action.triggered.connect(lambda: self.show_link_mic_dialog(item))
        menu.addAction(link_mic_action)

        menu.addSeparator()

        copy_cmd_action = QAction("Copy Hotkey Command", self)
        copy_cmd_action.triggered.connect(lambda: self.copy_switch_command(item))
        menu.addAction(copy_cmd_action)

        menu.exec(self.sink_list.mapToGlobal(pos))

    def show_link_mic_dialog(self, item):
        priority_id = item.data(Qt.ItemDataRole.UserRole)
        display_name = item.text().replace("✅ ", "")

        dlg = QDialog(self)
        dlg.setWindowTitle("Link Microphone")
        dlg.resize(400, 150)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"When switching to output: <b>{display_name}</b>"))
        layout.addWidget(QLabel("Automatically switch input (Mic) to:"))

        combo = QComboBox()
        combo.addItem("Auto (Match Device)", "auto")
        combo.addItem("Don't Switch (Keep Current)", "default")
        combo.insertSeparator(2)

        bt_map = self._get_bt_map()
        sources = self.audio.get_sources(bt_map)

        for src in sources:
            combo.addItem(src['display_name'], src['name'])

        current_link = self.config.get("mic_links", {}).get(priority_id, "auto")
        index = combo.findData(current_link)
        if index >= 0:
            combo.setCurrentIndex(index)

        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_val = combo.currentData()

            if "mic_links" not in self.config:
                self.config["mic_links"] = {}

            self.config["mic_links"][priority_id] = new_val
            self.config_mgr.save_config(self.config)
            self.status_label.setText("Microphone link saved.")

    def copy_switch_command(self, item):
        raw_text = item.text()
        clean_name = re.sub(r'\s*\[.*?\]|\s*\(.*?\)', '', raw_text).strip()

        if not clean_name:
            clean_name = item.data(Qt.ItemDataRole.UserRole)

        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'audio_source_switcher.py'))
        cmd = f"python3 {script_path} --connect \"{clean_name}\""

        clipboard = QApplication.clipboard()
        clipboard.setText(cmd)

        self.status_label.setText(f"Copied: {clean_name}")
