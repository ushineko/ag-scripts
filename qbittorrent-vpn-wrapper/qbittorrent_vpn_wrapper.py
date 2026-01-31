#!/usr/bin/env python3
import sys
import subprocess
import time
import requests
import signal
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QTextEdit, QPushButton, 
                             QDialog, QComboBox, QProgressBar, QMessageBox, QCheckBox)
from PyQt6.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QIcon, QFont

# --- configuration ---
VERSION = "1.0.3"
VPN_CONNECTION_NAME = "us_las_vegas-aes-128-cbc-udp-dns"
EXPECTED_CITY = "Las Vegas"
EXPECTED_REGION = "Nevada"
QBITTORRENT_CMD = ["qbittorrent"]
WEBUI_API_URL = "http://localhost:8080/api/v2"
POLL_INTERVAL_SECONDS = 30
STARTUP_WAIT_SECONDS = 10 

DOWNLOADING_STATES = {
    'downloading', 'metaDL', 'forcedDL', 'stallingDL', 'checkingDL',
    'queuedDL', 'checkingResumeData', 'moving'
}

SEEDING_STATES = {
    'uploading', 'seeding', 'forcedUP', 'stallingUP', 'checkingUP', 
    'queuedUP'
}

ACTIVE_STATES = DOWNLOADING_STATES | SEEDING_STATES

# --- Seeding Dialog ---
class SeedingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Seeding Complete")
        self.resize(400, 300)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Info
        lbl = QLabel("Downloads are finished, but torrents are seeding. What would you like to do?")
        lbl.setWordWrap(True)
        lbl.setFont(QFont("Sans", 11))
        layout.addWidget(lbl)
        
        # Options
        btn_layout = QVBoxLayout()
        
        # 1. Keep Seeding
        btn_keep = QPushButton("Keep Seeding (Do Nothing)")
        btn_keep.clicked.connect(self.on_keep)
        btn_layout.addWidget(btn_keep)
        
        # 2. Shutdown Now
        btn_shutdown = QPushButton("Shutdown Now")
        btn_shutdown.clicked.connect(self.on_shutdown)
        btn_layout.addWidget(btn_shutdown)

        # 3. Schedule
        h_sched = QHBoxLayout()
        self.combo_timer = QComboBox()
        self.combo_timer.addItems(["1 minute", "30 minutes", "1 hour", "2 hours"])
        
        h_sched.addWidget(QLabel("Schedule Shutdown:"))
        h_sched.addWidget(self.combo_timer)
        btn_layout.addLayout(h_sched)
        
        self.chk_remove = QCheckBox("Remove torrents when shutting down")
        btn_layout.addWidget(self.chk_remove)

        btn_schedule = QPushButton("Start Timer")
        btn_schedule.clicked.connect(self.on_schedule)
        btn_layout.addWidget(btn_schedule)
        
        layout.addLayout(btn_layout)
        
        # Results
        self.result_action = "keep"
        self.timer_minutes = 0
        self.remove_torrents = False

    def on_keep(self):
        self.result_action = "keep"
        self.accept()

    def on_shutdown(self):
        self.result_action = "shutdown"
        self.accept()

    def on_schedule(self):
        self.result_action = "schedule"
        self.remove_torrents = self.chk_remove.isChecked()
        txt = self.combo_timer.currentText()
        if "1 minute" in txt: self.timer_minutes = 1
        elif "30" in txt: self.timer_minutes = 30
        elif "1" in txt: self.timer_minutes = 60
        elif "2" in txt: self.timer_minutes = 120
        self.accept()

# --- Idle Dialog ---
class IdleDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloads Complete - Idle Detected")
        self.resize(400, 250)
        self.setModal(True)
        
        layout = QVBoxLayout(self)
        
        # Info
        lbl = QLabel("qBittorrent has been idle. What would you like to do?")
        lbl.setWordWrap(True)
        lbl.setFont(QFont("Sans", 11))
        layout.addWidget(lbl)
        
        # Countdown
        self.timer_lbl = QLabel("Auto-shutdown in 60 seconds...")
        self.timer_lbl.setStyleSheet("color: red; font-weight: bold;")
        layout.addWidget(self.timer_lbl)
        
        # Options
        btn_layout = QVBoxLayout()
        
        # 1. Snooze
        h_snooze = QHBoxLayout()
        self.combo_snooze = QComboBox()
        self.combo_snooze.addItems(["5 minutes", "15 minutes", "30 minutes", "1 hour"])
        btn_snooze = QPushButton("Wait / Snooze")
        btn_snooze.clicked.connect(self.on_snooze)
        h_snooze.addWidget(self.combo_snooze)
        h_snooze.addWidget(btn_snooze)
        btn_layout.addLayout(h_snooze)
        
        # 2. Kill App Only
        btn_kill_app = QPushButton("Stop qBittorrent Only (Keep VPN)")
        btn_kill_app.clicked.connect(self.on_kill_app)
        btn_layout.addWidget(btn_kill_app)
        
        # 3. Shutdown All
        btn_shutdown = QPushButton("Shutdown Everything (Default)")
        btn_shutdown.clicked.connect(self.on_shutdown)
        btn_shutdown.setStyleSheet("font-weight: bold;")
        btn_layout.addWidget(btn_shutdown)
        
        layout.addLayout(btn_layout)
        
        # Logic
        self.result_action = "shutdown" # default
        self.snooze_minutes = 0
        self.remaining_sec = 60
        
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_timer)
        self.timer.start(1000)
        
    def update_timer(self):
        self.remaining_sec -= 1
        self.timer_lbl.setText(f"Auto-shutdown in {self.remaining_sec} seconds...")
        if self.remaining_sec <= 0:
            self.on_shutdown()
            
    def on_snooze(self):
        self.timer.stop()
        self.result_action = "snooze"
        txt = self.combo_snooze.currentText()
        if "5" in txt: self.snooze_minutes = 5
        elif "15" in txt: self.snooze_minutes = 15
        elif "30" in txt: self.snooze_minutes = 30
        elif "1" in txt: self.snooze_minutes = 60
        self.accept()
        
    def on_kill_app(self):
        self.timer.stop()
        self.result_action = "kill_app"
        self.accept()
        
    def on_shutdown(self):
        self.timer.stop()
        self.result_action = "shutdown"
        self.accept()

# --- Worker Thread ---
class MonitorWorker(QThread):
    log_signal = pyqtSignal(str)
    status_signal = pyqtSignal(str, str) # state, details
    idle_detected_signal = pyqtSignal()
    seeding_detected_signal = pyqtSignal()
    request_shutdown_signal = pyqtSignal()
    
    def __init__(self, start_args):
        super().__init__()
        self.start_args = start_args
        self.running = True
        self.paused = False
        self.snooze_until = 0
        self.qb_proc = None
        self.remove_on_timer = False
        self.shutdown_on_timer = False
        
    def run_cmd(self, cmd_list, check=True):
        self.log_signal.emit(f"[CMD] {' '.join(cmd_list)}")
        result = subprocess.run(cmd_list, capture_output=True, text=True)
        if check and result.returncode != 0:
            self.log_signal.emit(f"[ERROR] {result.stderr.strip()}")
            return False
        return True

    def connect_vpn(self):
        self.log_signal.emit("Checking VPN status...")
        res = subprocess.run(
            ["nmcli", "--terse", "--fields", "NAME", "connection", "show", "--active"],
            capture_output=True, text=True
        )
        if VPN_CONNECTION_NAME in res.stdout:
            self.log_signal.emit("VPN is already active.")
            return True

        self.log_signal.emit("VPN not active. Connecting...")
        if self.run_cmd(["nmcli", "connection", "up", VPN_CONNECTION_NAME]):
            self.log_signal.emit("VPN connected successfully.")
            time.sleep(5) # Wait for routes
            return True
        return False

    def verify_ip(self):
        self.log_signal.emit("Verifying public IP location...")
        
        # Retry parameters
        max_retries = 3
        wait_seconds = 5
        
        for attempt in range(max_retries):
            if attempt > 0:
                self.log_signal.emit(f"Retry {attempt}/{max_retries-1} in {wait_seconds}s...")
                time.sleep(wait_seconds)
                
            try:
                resp = requests.get("http://ip-api.com/json", timeout=15)
                data = resp.json()
                city = data.get("city", "Unknown")
                region = data.get("regionName", "Unknown")
                query_ip = data.get("query", "Unknown")
                
                self.log_signal.emit(f"Detected IP: {query_ip} | Location: {city}, {region}")
                
                if EXPECTED_CITY in city or EXPECTED_REGION in region:
                    self.log_signal.emit("Location verification PASSED.")
                    return True
                else:
                    self.log_signal.emit(f"Location verification FAILED. Expected {EXPECTED_CITY}/{EXPECTED_REGION}.")
            except Exception as e:
                self.log_signal.emit(f"Error during IP verification: {e}")
        
        self.log_signal.emit("All IP verification attempts failed.")
        return False

    def start_qbittorrent(self):
        # Check if already running
        try:
            subprocess.check_output(["pgrep", "-x", "qbittorrent"])
            self.log_signal.emit("qBittorrent is already running. Attaching to existing instance.")
            
            # Wake up the existing instance by calling the executable again
            # This triggers the single-instance mechanism to bring the window to front
            wake_cmd = QBITTORRENT_CMD + (self.start_args if self.start_args else [])
            self.log_signal.emit(f"Waking up instance with: {wake_cmd}")
            subprocess.run(wake_cmd, check=False)
            
            return None
        except subprocess.CalledProcessError:
            pass

        self.log_signal.emit("Starting qBittorrent...")
        cmd = QBITTORRENT_CMD.copy()
        if self.start_args:
            cmd.extend(self.start_args)
            
        self.qb_proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        self.log_signal.emit(f"qBittorrent started with PID {self.qb_proc.pid}. Waiting for WebUI...")
        time.sleep(STARTUP_WAIT_SECONDS)
        return self.qb_proc

    def get_active_count(self):
        try:
            resp = requests.get(f"{WEBUI_API_URL}/torrents/info?filter=all", timeout=10)
            if resp.status_code == 200:
                torrents = resp.json()
                dl_count = 0
                seed_count = 0
                dl_names = []
                seed_names = []
                for t in torrents:
                    state = t.get('state')
                    if state in DOWNLOADING_STATES:
                        dl_count += 1
                        dl_names.append(t.get('name')[:10])
                    elif state in SEEDING_STATES:
                        seed_count += 1
                        seed_names.append(t.get('name')[:10])
                
                if dl_count > 0:
                    self.log_signal.emit(f"Downloading: {dl_count} ({', '.join(dl_names)})")
                if seed_count > 0:
                    self.log_signal.emit(f"Seeding: {seed_count} ({', '.join(seed_names)})")
                
                return dl_count, seed_count
            else:
                self.log_signal.emit(f"WebUI Status: {resp.status_code}")
                return -1, -1
        except Exception:
            return -1, -1

    def remove_torrents(self):
        self.log_signal.emit("Removing seeding torrents...")
        try:
            resp = requests.get(f"{WEBUI_API_URL}/torrents/info?filter=all", timeout=10)
            if resp.status_code == 200:
                torrents = resp.json()
                hashes = [t.get('hash') for t in torrents if t.get('state') in SEEDING_STATES]
                if hashes:
                    requests.post(
                        f"{WEBUI_API_URL}/torrents/delete",
                        data={'hashes': '|'.join(hashes), 'deleteFiles': 'true'},
                        timeout=10
                    )
                    self.log_signal.emit(f"Removed {len(hashes)} seeding torrents.")
                else:
                    self.log_signal.emit("No seeding torrents found to remove.")
        except Exception as e:
            self.log_signal.emit(f"Error removing torrents: {e}")

    def kill_qb(self):
        self.log_signal.emit("Stopping qBittorrent...")
        subprocess.run(["pkill", "qbittorrent"], check=False)
        if self.qb_proc:
            try:
                self.qb_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.qb_proc.kill()

    def disconnect_vpn(self):
        self.log_signal.emit("Disconnecting VPN...")
        subprocess.run(["nmcli", "connection", "down", VPN_CONNECTION_NAME], check=False)

    def run(self):
        self.status_signal.emit("Starting", "Initializing...")
        
        # 1. VPN
        if not self.connect_vpn():
            self.status_signal.emit("Error", "VPN Connection Failed")
            return
            
        # 2. IP
        if not self.verify_ip():
            self.status_signal.emit("Error", "IP Verification Failed")
            self.disconnect_vpn()
            return
            
        # 3. Start App
        self.start_qbittorrent()
        
        # 4. Loop
        self.status_signal.emit("Monitoring", "Secure Connection Active")
        
        while self.running:
            if self.paused:
                # Check snooze/timer
                if time.time() > self.snooze_until:
                    if self.shutdown_on_timer:
                        if self.remove_on_timer:
                            self.remove_torrents()
                        self.request_shutdown_signal.emit()
                        self.running = False
                        break
                    
                    self.paused = False
                    self.log_signal.emit("Timer finished. Resuming monitoring.")
                    self.status_signal.emit("Monitoring", "Resumed after timer")
                else:
                    self.msleep(1000)
                    continue

            dl_count, seed_count = self.get_active_count()
            
            if dl_count > 0:
                self.status_signal.emit("Active", f"{dl_count} downloads active")
            elif seed_count > 0:
                self.status_signal.emit("Seeding", f"{seed_count} torrents seeding")
                # Trigger seeding dialog 
                self.seeding_detected_signal.emit()
                self.paused = True 
            elif dl_count == 0:
                self.status_signal.emit("Idle", "No active torrents")
            else:
                self.status_signal.emit("Warning", "WebUI Unreachable")
            
            # Sleep step
            for _ in range(POLL_INTERVAL_SECONDS):
                if not self.running: break
                self.msleep(1000)

# --- Glue Thread ---
class GlueThread(QThread):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.running = True
        self.target_window_id = None
        self.last_pos = None
        self.last_size = None
        
    def run(self):
        while self.running:
            try:
                # 1. Find Window ID if not known or verify it exists
                # Using kdotool search
                # Try class 'qbittorrent' first (default in many distros), then 'org.qbittorrent.qBittorrent'
                cmd = ["kdotool", "search", "--class", "qbittorrent"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                
                if res.returncode != 0 or not res.stdout.strip():
                     cmd = ["kdotool", "search", "--class", "org.qbittorrent.qBittorrent"]
                     res = subprocess.run(cmd, capture_output=True, text=True)

                if res.returncode == 0 and res.stdout.strip():
                    wids = res.stdout.strip().splitlines()
                    # Just pick the last one found (often the most recently active or main one)
                    target = wids[-1] 
                    
                    # 2. Get Geometry
                    # kdotool getwindowgeometry ID
                    # Output format: 
                    # Window {ID}
                    #   Position: X,Y
                    #   Geometry: WxH
                    geo_res = subprocess.run(["kdotool", "getwindowgeometry", target], capture_output=True, text=True)
                    output = geo_res.stdout
                    
                    if "Position:" in output and "Geometry:" in output:
                        # Parse
                        pos_line = [l for l in output.splitlines() if "Position:" in l][0]
                        geo_line = [l for l in output.splitlines() if "Geometry:" in l][0]
                        
                        x, y = map(int, pos_line.split("Position:")[1].strip().split(","))
                        w, h = map(float, geo_line.split("Geometry:")[1].strip().split("x")) # Width might be float per user log
                        w, h = int(w), int(h)
                        
                        # Calculate Desired Position:
                        # "Like on the bottom third" -> Stick to top or bottom?
                        # User said: "glue the wrapper to the top of the qbitorrent window"
                        # So Wrapper Bottom edge touches qBittorrent Top edge? 
                        # Or Wrapper sits ON TOP (physically above in Z-order) at the top edge of the window frame?
                        # "stick to the top of the qbitorrent window" implies attaching it visually.
                        # Standard "glue" usually means outside.
                        # If qBt is at (x, y), we want wrapper at (x, y - wrapper_height).
                        
                        wrapper_h = self.main_window.frameGeometry().height()
                        target_x = x
                        target_y = y - wrapper_h
                        
                        # However, user said: "ignore if ... not showing"
                        # We can try to just sync it.
                        
                        # Sanity check: Ensure we don't move off screen too badly? (Managers handle it)
                        
                        # Apply Move if different
                        current_geo = (target_x, target_y, w)
                        if current_geo != self.last_pos:
                            # Move wrapper
                            # Use QMetaObject.invokeMethod to run on main thread? Or minimal Move?
                            # Threads shouldn't touch GUI widgets directly.
                            # But move() is generally safe or acceptable via signals.
                            # Best practice: emit signal.
                            self.request_move(target_x, target_y, w)
                            self.last_pos = current_geo
                    else:
                        pass # Could not parse
                else:
                    pass # Not found
                    
            except Exception:
                pass
                
            time.sleep(0.5) # Poll rate

    def request_move(self, x, y, w):
        # We can implement a signal content or just access main_window methods if careful.
        # Let's use Qt's thread-safe method via invoke or signal.
        # For simplicity in this script, a signal is cleaner.
        # But wait, I can't modify the class definition midway easily.
        # I'll rely on the fact that running `move` from a thread *might* warn but usually works on X11/Wayland if the backend handles it.
        # Better: emit signal defined in class.
        pass

# Add signal to MainWindow for thread safety
class GlueThreadSignal(QThread):
    move_signal = pyqtSignal(int, int, int)
    
    def __init__(self):
        super().__init__()
        self.running = True
        self.first_activation_done = False
        
    def run(self):
        while self.running:
            try:
                # 1. Find Window ID
                # Try class 'qbittorrent' first
                cmd = ["kdotool", "search", "--class", "qbittorrent"]
                res = subprocess.run(cmd, capture_output=True, text=True)
                
                # Try specific class if generic failed
                if res.returncode != 0 or not res.stdout.strip():
                    cmd = ["kdotool", "search", "--class", "org.qbittorrent.qBittorrent"]
                    res = subprocess.run(cmd, capture_output=True, text=True)
                
                # Fallback to name if class fails - use generous search
                if res.returncode != 0 or not res.stdout.strip():
                     cmd = ["kdotool", "search", "--name", "qBittorrent"]
                     res = subprocess.run(cmd, capture_output=True, text=True)

                if res.returncode == 0 and res.stdout.strip():
                    wids = res.stdout.strip().splitlines()
                    
                    # Target candidate - usually the last one is the most relevant window in kdotool output order (stacking order often)
                if res.returncode == 0 and res.stdout.strip():
                    wids = res.stdout.strip().splitlines()
                    
                    target = None
                    for wid in reversed(wids):
                        # Check name to ensure it's NOT us
                        name_res = subprocess.run(["kdotool", "getwindowname", wid], capture_output=True, text=True)
                        name = name_res.stdout.strip()
                        if "qBittorrent Secure VPN" in name:
                            continue
                        target = wid
                        break
                    
                    if not target:
                        continue
                    
                    # 1.5 Auto-Activate on first sighting
                    if not self.first_activation_done:
                        subprocess.run(["kdotool", "windowactivate", target], check=False)
                        self.first_activation_done = True

                    # 2. Get Geometry
                    geo_res = subprocess.run(["kdotool", "getwindowgeometry", target], capture_output=True, text=True)
                    output = geo_res.stdout
                    
                    if "Position:" in output and "Geometry:" in output:
                        pos_line = [l for l in output.splitlines() if "Position:" in l][0]
                        geo_line = [l for l in output.splitlines() if "Geometry:" in l][0]
                        
                        pos_str = pos_line.split("Position:")[1].strip()
                        geo_str = geo_line.split("Geometry:")[1].strip()
                        
                        try:
                            x, y = map(lambda s: int(float(s)), pos_str.split(","))
                            w, h = map(lambda s: int(float(s)), geo_str.split("x"))
                        except ValueError:
                            continue

                        if w > 100 and h > 100:
                            self.move_signal.emit(x, y, w)
            except Exception:
                pass
            time.sleep(0.3) # Increased poll rate for smoothness

# --- Main Window ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("qBittorrent Secure VPN")
        self.resize(600, 120) 
        
        # Ensure it stays on top 
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        
        # Build UI
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 5, 10, 5) # Compact
        
        # Header
        self.lbl_status = QLabel("Status: Initializing")
        self.lbl_status.setFont(QFont("Sans", 12, QFont.Weight.Bold))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_status)
        
        self.lbl_detail = QLabel("...")
        self.lbl_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.lbl_detail)
        
        # Log
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setStyleSheet("background-color: #222; color: #eee; font-family: Monospace; font-size: 10px;")
        self.log_area.setMinimumHeight(50)
        layout.addWidget(self.log_area)
        
        # Actions
        btn_layout = QHBoxLayout()
        btn_stop = QPushButton("Stop & Disconnect")
        btn_stop.clicked.connect(self.force_shutdown)
        btn_layout.addWidget(btn_stop)
        layout.addLayout(btn_layout)
        
        # Start Worker
        args = sys.argv[1:]
        self.worker = MonitorWorker(args)
        self.worker.log_signal.connect(self.append_log)
        self.worker.status_signal.connect(self.update_status)
        self.worker.idle_detected_signal.connect(self.show_idle_dialog)
        self.worker.seeding_detected_signal.connect(self.show_seeding_dialog)
        self.worker.request_shutdown_signal.connect(self.force_shutdown)
        self.worker.start()
        
        # Start Glue Thread
        self.glue = GlueThreadSignal()
        self.glue.move_signal.connect(self.snap_to_window)
        self.glue.start()
        
    def snap_to_window(self, target_x, target_y, target_w):
        try:
            # Must measure self via kdotool for consistency
            # Use specific name to find ourself
            cmd_search = ["kdotool", "search", "--name", "qBittorrent Secure VPN"]
            res = subprocess.run(cmd_search, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                # Filter results to find the one that IS us (usually one)
                # If we accidentally picked qBittorrent window as 'my_id', we'd move IT.
                # But qBittorrent name is "qBittorrent" (EXACT). 
                # Our name contains "Secure VPN".
                my_ids = res.stdout.strip().splitlines()
                my_id = my_ids[0]
                
                # Check for recursion: tx, ty are targets. 
                # If target window ID is SAME as my_id, ABORT.
                # However, GlueThreadSignal matches --class org.qbittorrent.qBittorrent. 
                # We are likely python3 class. So this should be safe.
                
                geo_res = subprocess.run(["kdotool", "getwindowgeometry", my_id], capture_output=True, text=True)
                if "Geometry:" in geo_res.stdout:
                    lines = geo_res.stdout.splitlines()
                    geo_line = [l for l in lines if "Geometry:" in l][0]
                    _, h_str = geo_line.split("Geometry:")[1].strip().split("x")
                    my_h = int(float(h_str))
                    
                    # Sanity check: if we are trying to move to where we already are +/- jitter?
                    # kdotool is reliable.
                
                    padding = 7
                    new_y = target_y - my_h - padding
                    
                    # Force move/resize
                    subprocess.run(["kdotool", "windowmove", my_id, str(target_x), str(new_y)], check=False)
                    if abs(self.width() - target_w) > 5:
                        subprocess.run(["kdotool", "windowsize", my_id, str(target_w), str(my_h)], check=False)
        except Exception:
            pass


    def append_log(self, text):
        msg = f"[{time.strftime('%H:%M:%S')}] {text}"
        self.log_area.append(msg)
        print(msg)
        
    def update_status(self, state, detail):
        self.lbl_status.setText(f"Status: {state}")
        self.lbl_status.setStyleSheet(f"color: {'green' if state=='Active' or state=='Monitoring' else 'orange'}; font-weight: bold;")
        self.lbl_detail.setText(detail)
        
    def show_idle_dialog(self):
        self.append_log("Showing Idle Dialog...")
        self.show() # Ensure main window is visible/raised if it was hidden
        self.raise_()
        self.activateWindow()
        
        dlg = IdleDialog(self)
        dlg.exec()
        
        action = dlg.result_action
        self.append_log(f"User chose for idle: {action}")
        
        if action == "shutdown":
            self.force_shutdown()
        elif action == "kill_app":
            self.worker.kill_qb()
            self.append_log("qBittorrent closed. VPN left active.")
            self.close()
        elif action == "snooze":
            mins = dlg.snooze_minutes
            self.append_log(f"Snoozing for {mins} minutes.")
            self.worker.snooze_until = time.time() + (mins * 60)
            self.worker.shutdown_on_timer = False
            self.worker.paused = True 

    def show_seeding_dialog(self):
        self.append_log("Seeding detected. Showing Seeding Dialog...")
        self.show()
        self.raise_()
        self.activateWindow()
        
        dlg = SeedingDialog(self)
        dlg.exec()
        
        action = dlg.result_action
        self.append_log(f"User chose for seeding: {action}")
        
        if action == "shutdown":
            self.force_shutdown()
        elif action == "schedule":
            mins = dlg.timer_minutes
            self.append_log(f"Scheduling shutdown in {mins} minutes. Remove torrents: {dlg.remove_torrents}")
            self.worker.snooze_until = time.time() + (mins * 60)
            self.worker.remove_on_timer = dlg.remove_torrents
            self.worker.shutdown_on_timer = True
            self.worker.paused = True
        else:
            # Keep seeding
            self.worker.paused = False
            self.worker.shutdown_on_timer = False

    def force_shutdown(self):
        self.append_log("Shutting down...")
        self.glue.running = False # Stop glue
        self.worker.running = False
        self.worker.kill_qb()
        self.worker.disconnect_vpn()
        self.close()
        
    def closeEvent(self, event):
        self.glue.running = False
        if self.worker.running:
            self.worker.running = False
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Set unique app metadata to avoid confusion in window managers
    app.setApplicationName("qBittorrentVPNWrapper")
    app.setDesktopFileName("qbittorrent-secure")
    
    app.setWindowIcon(QIcon.fromTheme("qbittorrent"))
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
