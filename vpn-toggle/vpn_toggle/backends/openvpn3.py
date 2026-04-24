"""
OpenVPN3 backend — manages VPN connections via openvpn3 CLI.

Provides both sync methods (used by GUI card buttons, tray, and tests) and
async variants (used by the event-driven MonitorController).
"""
import logging
import re
import subprocess
import time
from datetime import datetime
from typing import List, Tuple, Optional

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from ..models import VPNConnection, VPNStatus
from . import VPNBackend

logger = logging.getLogger('vpn_toggle.backends.openvpn3')

DEFAULT_AUTH_TIMEOUT = 60
OV3_CMD_TIMEOUT_MS = 30_000
OV3_POLL_INTERVAL_MS = 2_000


class OpenVPN3Backend(VPNBackend):
    """VPN backend using the OpenVPN3 Linux client (openvpn3 CLI)."""

    def __init__(self):
        self._available = self._check_openvpn3()

    @property
    def name(self) -> str:
        return "openvpn3"

    @property
    def available(self) -> bool:
        return self._available

    def _check_openvpn3(self) -> bool:
        try:
            result = subprocess.run(
                ['which', 'openvpn3'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.debug("openvpn3 found and available")
                return True
            else:
                logger.debug("openvpn3 command not found")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.debug("Failed to check for openvpn3")
            return False

    def _run_cmd(self, args: List[str], timeout: int = 30) -> Tuple[bool, str]:
        cmd = ['openvpn3'] + args
        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                output = result.stdout.strip()
                logger.debug(f"Command succeeded: {output[:200]}")
                return True, output
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.warning(f"Command failed: {error_msg}")
                return False, error_msg
        except subprocess.TimeoutExpired:
            error_msg = f"Command timed out after {timeout}s"
            logger.error(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Command failed with exception: {e}"
            logger.error(error_msg)
            return False, error_msg

    def list_vpns(self) -> List[VPNConnection]:
        if not self._available:
            return []

        # Get available configurations
        success, output = self._run_cmd(['configs-list'])
        if not success:
            logger.error("Failed to list OpenVPN3 configs")
            return []

        config_names = self._parse_configs_list(output)
        if not config_names:
            return []

        # Get active sessions to determine connection state
        active_configs = self._get_active_config_names()

        vpns = []
        for name in config_names:
            vpns.append(VPNConnection(
                name=name,
                display_name=name,
                active=name in active_configs,
                connection_type='openvpn3'
            ))

        logger.info(f"Found {len(vpns)} OpenVPN3 config(s)")
        return vpns

    def _parse_configs_list(self, output: str) -> List[str]:
        """
        Parse openvpn3 configs-list output.

        Format:
            Configuration Name                                        Last used
            ----------------------------------------------------------------------
            aiqlabs                                                   2026-03-17 15:26:07
            ----------------------------------------------------------------------
        """
        names = []
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            # Skip empty lines, header line, and separator lines
            if not line or line.startswith('---') or line.startswith('Configuration Name'):
                continue
            # Config name is everything before the last date-like token
            # The format is: name (padded with spaces) date
            match = re.match(r'^(\S+(?:\s+\S+)*?)\s{2,}\d{4}-\d{2}-\d{2}', line)
            if match:
                names.append(match.group(1).strip())
            elif not any(c in line for c in ['|', '=']):
                # Fallback: treat entire non-separator line as config name
                # (handles configs that have never been used — no date column)
                parts = line.split()
                if parts:
                    names.append(parts[0])

        return names

    def _parse_sessions(self, output: str) -> list:
        """
        Parse openvpn3 sessions-list output into a list of session dicts.

        Each dict has keys: path, config_name, status, device
        """
        sessions = []
        current = {}
        for line in output.split('\n'):
            path_match = re.match(r'\s*Path:\s*(.+)', line)
            if path_match:
                if current:
                    sessions.append(current)
                current = {'path': path_match.group(1).strip()}

            config_match = re.match(r'\s*Config name:\s*(.+)', line)
            if config_match and current:
                current['config_name'] = config_match.group(1).strip()

            status_match = re.match(r'\s*Status:\s*(.+)', line)
            if status_match and current:
                current['status'] = status_match.group(1).strip()

            # Device is on the same line as Owner: "Owner: user   Device: tun1"
            dev_match = re.search(r'Device:\s*(\S+)', line)
            if dev_match and current:
                current['device'] = dev_match.group(1).strip()

        if current:
            sessions.append(current)
        return sessions

    def _get_sessions_for_config(self, config_name: str) -> list:
        """Get all sessions matching a config name."""
        success, output = self._run_cmd(['sessions-list'])
        if not success or 'No sessions available' in output:
            return []
        return [s for s in self._parse_sessions(output)
                if s.get('config_name') == config_name]

    def _get_active_config_names(self) -> set:
        """Get set of config names that have active (connected) sessions."""
        success, output = self._run_cmd(['sessions-list'])
        if not success or 'No sessions available' in output:
            return set()

        active = set()
        for s in self._parse_sessions(output):
            if 'Client connected' in s.get('status', ''):
                active.add(s.get('config_name', ''))
        return active

    def _get_session_status(self, config_name: str) -> Optional[str]:
        """Get the status string for a session by config name."""
        sessions = self._get_sessions_for_config(config_name)
        if sessions:
            return sessions[0].get('status')
        return None

    def _disconnect_by_path(self, session_path: str) -> Tuple[bool, str]:
        """Disconnect a specific session by its D-Bus path."""
        return self._run_cmd(
            ['session-manage', '--path', session_path, '--disconnect']
        )

    def _disconnect_all_sessions(self, config_name: str) -> None:
        """Disconnect all sessions for a config name (handles duplicates)."""
        sessions = self._get_sessions_for_config(config_name)
        for s in sessions:
            path = s.get('path')
            if path:
                logger.debug(f"Disconnecting session {path}")
                self._disconnect_by_path(path)


    def is_vpn_active(self, vpn_name: str) -> bool:
        if not self._available:
            return False

        status = self._get_session_status(vpn_name)
        if status and 'Client connected' in status:
            return True
        return False

    def get_vpn_status(self, vpn_name: str) -> VPNStatus:
        is_active = self.is_vpn_active(vpn_name)

        if is_active:
            return VPNStatus(
                connected=True,
                ip_address=None,  # openvpn3 doesn't easily expose tunnel IP via CLI
                connection_time=datetime.now()
            )
        else:
            return VPNStatus(connected=False)

    def connect_vpn(self, vpn_name: str, **kwargs) -> Tuple[bool, str]:
        auth_timeout = kwargs.get('auth_timeout', DEFAULT_AUTH_TIMEOUT)

        logger.info(f"Connecting to OpenVPN3 config: {vpn_name}")

        # Clean up any existing sessions for this config first
        existing = self._get_sessions_for_config(vpn_name)
        if existing:
            logger.info(f"Cleaning up {len(existing)} existing session(s) for {vpn_name}")
            self._disconnect_all_sessions(vpn_name)
            time.sleep(1)

        # Start the session (returns quickly, auth happens asynchronously)
        success, output = self._run_cmd(
            ['session-start', '--config', vpn_name],
            timeout=30
        )

        if not success:
            message = f"Failed to start OpenVPN3 session: {output}"
            logger.error(message)
            return False, message

        # Raise the browser window so the user can complete OIDC auth
        self._raise_browser()

        # Poll for "Client connected" status
        elapsed = 0
        poll_interval = 2
        while elapsed < auth_timeout:
            status = self._get_session_status(vpn_name)

            if status and 'Client connected' in status:
                message = f"Connected to {vpn_name} (OpenVPN3)"
                logger.info(message)
                return True, message

            # "Web authentication required" is expected — keep polling
            if status:
                logger.debug(f"{vpn_name}: status = {status} ({elapsed}s/{auth_timeout}s)")

            time.sleep(poll_interval)
            elapsed += poll_interval

        # Timeout — clean up the pending session by path
        logger.warning(f"Auth timeout after {auth_timeout}s for {vpn_name}")
        self._disconnect_all_sessions(vpn_name)
        message = f"Authentication timed out after {auth_timeout}s for {vpn_name}"
        return False, message

    def disconnect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        logger.info(f"Disconnecting OpenVPN3 session: {vpn_name}")

        sessions = self._get_sessions_for_config(vpn_name)
        if not sessions:
            message = f"No active session found for {vpn_name} (OpenVPN3)"
            logger.info(message)
            return True, message

        # Disconnect all sessions by path (handles duplicates safely)
        all_ok = True
        for s in sessions:
            path = s.get('path')
            if path:
                ok, output = self._disconnect_by_path(path)
                if not ok:
                    logger.warning(f"Failed to disconnect session {path}: {output}")
                    all_ok = False

        if all_ok:
            message = f"Disconnected from {vpn_name} (OpenVPN3)"
            logger.info(message)
            return True, message
        else:
            message = f"Some sessions failed to disconnect for {vpn_name} (OpenVPN3)"
            logger.warning(message)
            return False, message

    def get_vpn_details(self, vpn_name: str) -> dict:
        if not self._available or not self.is_vpn_active(vpn_name):
            return {}

        sessions = self._get_sessions_for_config(vpn_name)
        if not sessions:
            return {}

        device = sessions[0].get('device', '')
        if not device:
            return {}

        # Get IP and routes from system interfaces
        ip_addr = ''
        routes = []
        try:
            result = subprocess.run(
                ['ip', 'addr', 'show', device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    inet_match = re.match(r'\s+inet\s+(\S+)', line)
                    if inet_match:
                        ip_addr = inet_match.group(1)
                        break

            result = subprocess.run(
                ['ip', 'route', 'show', 'dev', device],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line.strip():
                        routes.append(line.strip())
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return {'interface': device, 'ip': ip_addr, 'routes': routes}

    def _raise_browser(self) -> None:
        """Raise the browser window to front for OIDC auth.

        Tries common browser class names via kdotool (KDE Wayland).
        Best-effort — silently does nothing if kdotool isn't available
        or no browser window is found.
        """
        try:
            subprocess.run(
                ['which', 'kdotool'],
                capture_output=True, timeout=2
            ).check_returncode()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                FileNotFoundError):
            return

        for browser_class in ('vivaldi', 'firefox', 'chromium', 'google-chrome'):
            try:
                result = subprocess.run(
                    ['kdotool', 'search', '--class', browser_class],
                    capture_output=True, text=True, timeout=2
                )
                if result.returncode == 0 and result.stdout.strip():
                    subprocess.run(
                        ['kdotool', 'search', '--class', browser_class,
                         'windowraise', '%1'],
                        capture_output=True, timeout=2
                    )
                    logger.debug(f"Raised browser window: {browser_class}")
                    return
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

    def get_connection_timestamp(self, vpn_name: str) -> Optional[datetime]:
        # OpenVPN3 CLI doesn't expose session start time directly
        return None

    # -- Async variants (used by MonitorController) --

    def is_vpn_active_async(self, vpn_name: str, parent: Optional[QObject] = None) -> "_Ov3IsActiveOp":
        return _Ov3IsActiveOp(vpn_name, parent=parent)

    def connect_vpn_async(self, vpn_name: str, auth_timeout: int = DEFAULT_AUTH_TIMEOUT,
                          parent: Optional[QObject] = None) -> "_Ov3ConnectOp":
        return _Ov3ConnectOp(vpn_name, auth_timeout=auth_timeout, parent=parent)

    def disconnect_vpn_async(self, vpn_name: str, parent: Optional[QObject] = None) -> "_Ov3DisconnectOp":
        return _Ov3DisconnectOp(vpn_name, parent=parent)


# ---------------------------------------------------------------------------
# Async operations — each is a QObject with a `finished` signal.
# ---------------------------------------------------------------------------


def _run_ov3_async(args: List[str], parent: QObject,
                   timeout_ms: int = OV3_CMD_TIMEOUT_MS) -> "_Ov3CmdOp":
    """Convenience constructor for a single openvpn3 subcommand."""
    return _Ov3CmdOp(args, timeout_ms=timeout_ms, parent=parent)


class _Ov3CmdOp(QObject):
    """Runs a single `openvpn3 <args>` invocation and emits (success, output)."""

    finished = pyqtSignal(bool, str)

    def __init__(self, args: List[str], timeout_ms: int = OV3_CMD_TIMEOUT_MS,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._args = args
        self._timeout_ms = timeout_ms
        self._done = False
        self._proc: Optional[QProcess] = None
        self._timer: Optional[QTimer] = None

    def start(self) -> None:
        if self._done:
            return
        self._proc = QProcess(self)
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(self._timeout_ms)
        logger.debug(f"Running command: openvpn3 {' '.join(self._args)}")
        self._proc.start('openvpn3', self._args)

    def _on_finished(self, exit_code: int, _status) -> None:
        if self._done:
            return
        self._done = True
        if self._timer:
            self._timer.stop()
        stdout = bytes(self._proc.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        stderr = bytes(self._proc.readAllStandardError()).decode('utf-8', errors='replace').strip()
        ok = (exit_code == 0)
        output = stdout if ok else (stderr or stdout)
        self.finished.emit(ok, output)

    def _on_error(self, _err) -> None:
        if self._done:
            return
        self._done = True
        if self._timer:
            self._timer.stop()
        self.finished.emit(False, self._proc.errorString() if self._proc else 'unknown')

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._done = True
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        self.finished.emit(False, f"Command timed out after {self._timeout_ms // 1000}s")


def _parse_sessions_output(output: str) -> list:
    """Stand-alone copy of OpenVPN3Backend._parse_sessions for async use."""
    sessions = []
    current: dict = {}
    for line in output.split('\n'):
        path_match = re.match(r'\s*Path:\s*(.+)', line)
        if path_match:
            if current:
                sessions.append(current)
            current = {'path': path_match.group(1).strip()}
        cfg_match = re.match(r'\s*Config name:\s*(.+)', line)
        if cfg_match and current:
            current['config_name'] = cfg_match.group(1).strip()
        status_match = re.match(r'\s*Status:\s*(.+)', line)
        if status_match and current:
            current['status'] = status_match.group(1).strip()
        dev_match = re.search(r'Device:\s*(\S+)', line)
        if dev_match and current:
            current['device'] = dev_match.group(1).strip()
    if current:
        sessions.append(current)
    return sessions


class _Ov3IsActiveOp(QObject):
    """Checks whether a named config has an active 'Client connected' session."""

    finished = pyqtSignal(bool)

    def __init__(self, vpn_name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._vpn_name = vpn_name
        self._list_op: Optional[_Ov3CmdOp] = None

    def start(self) -> None:
        self._list_op = _run_ov3_async(['sessions-list'], parent=self)
        self._list_op.finished.connect(self._on_list)
        self._list_op.start()

    def _on_list(self, success: bool, output: str) -> None:
        if not success or 'No sessions available' in output:
            self.finished.emit(False)
            return
        for s in _parse_sessions_output(output):
            if (s.get('config_name') == self._vpn_name
                    and 'Client connected' in s.get('status', '')):
                self.finished.emit(True)
                return
        self.finished.emit(False)


class _Ov3DisconnectOp(QObject):
    """Disconnects all sessions for a named config.

    Sequence: list → for each matching session path, session-manage --disconnect.
    Emits finished(success, message) once all sessions have been handled.
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, vpn_name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._vpn_name = vpn_name
        self._list_op: Optional[_Ov3CmdOp] = None
        self._pending_paths: list = []
        self._any_failure = False

    def start(self) -> None:
        self._list_op = _run_ov3_async(['sessions-list'], parent=self)
        self._list_op.finished.connect(self._on_list)
        self._list_op.start()

    def _on_list(self, success: bool, output: str) -> None:
        if not success or 'No sessions available' in output:
            msg = f"No active session found for {self._vpn_name} (OpenVPN3)"
            logger.info(msg)
            self.finished.emit(True, msg)
            return

        matching = [s for s in _parse_sessions_output(output)
                    if s.get('config_name') == self._vpn_name]
        self._pending_paths = [s['path'] for s in matching if s.get('path')]
        if not self._pending_paths:
            msg = f"No active session found for {self._vpn_name} (OpenVPN3)"
            self.finished.emit(True, msg)
            return
        self._disconnect_next()

    def _disconnect_next(self) -> None:
        if not self._pending_paths:
            if self._any_failure:
                msg = f"Some sessions failed to disconnect for {self._vpn_name} (OpenVPN3)"
                logger.warning(msg)
                self.finished.emit(False, msg)
            else:
                msg = f"Disconnected from {self._vpn_name} (OpenVPN3)"
                logger.info(msg)
                self.finished.emit(True, msg)
            return

        path = self._pending_paths.pop(0)
        op = _run_ov3_async(['session-manage', '--path', path, '--disconnect'],
                            parent=self)
        op.finished.connect(self._on_one_disconnected)
        op.start()

    def _on_one_disconnected(self, success: bool, output: str) -> None:
        if not success:
            logger.warning(f"Failed to disconnect session: {output}")
            self._any_failure = True
        self._disconnect_next()


class _Ov3ConnectOp(QObject):
    """State machine: optional pre-cleanup → session-start → poll for Client connected.

    Matches the sync connect_vpn sequence: list existing → disconnect each →
    session-start --config → poll sessions-list every 2s until 'Client connected'
    or auth_timeout.
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, vpn_name: str, auth_timeout: int = DEFAULT_AUTH_TIMEOUT,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._vpn_name = vpn_name
        self._auth_timeout_s = auth_timeout
        self._elapsed_s = 0
        self._cleanup_op: Optional[_Ov3DisconnectOp] = None
        self._start_op: Optional[_Ov3CmdOp] = None
        self._poll_op: Optional[_Ov3CmdOp] = None
        self._poll_timer: Optional[QTimer] = None
        self._done = False

    def start(self) -> None:
        if self._done:
            return
        logger.info(f"Connecting to OpenVPN3 config: {self._vpn_name}")
        # 1. Clean up any pre-existing sessions first.
        self._cleanup_op = _Ov3DisconnectOp(self._vpn_name, parent=self)
        self._cleanup_op.finished.connect(self._on_cleanup_done)
        self._cleanup_op.start()

    def _on_cleanup_done(self, _success: bool, _msg: str) -> None:
        if self._done:
            return
        # Small settle delay before starting the new session.
        QTimer.singleShot(1_000, self._start_session)

    def _start_session(self) -> None:
        if self._done:
            return
        self._start_op = _run_ov3_async(
            ['session-start', '--config', self._vpn_name], parent=self)
        self._start_op.finished.connect(self._on_session_started)
        self._start_op.start()

    def _on_session_started(self, success: bool, output: str) -> None:
        if self._done:
            return
        if not success:
            self._emit(False, f"Failed to start OpenVPN3 session: {output}")
            return
        # Raise browser for OIDC (fire-and-forget, best-effort).
        _raise_browser_async(self)
        # Begin polling for "Client connected".
        self._poll_timer = QTimer(self)
        self._poll_timer.setSingleShot(False)
        self._poll_timer.timeout.connect(self._poll_status)
        self._poll_timer.start(OV3_POLL_INTERVAL_MS)
        # Fire the first poll immediately so we don't wait 2s before checking.
        QTimer.singleShot(0, self._poll_status)

    def _poll_status(self) -> None:
        if self._done:
            return
        # Avoid overlapping poll requests.
        if self._poll_op is not None:
            return
        self._poll_op = _run_ov3_async(['sessions-list'], parent=self)
        self._poll_op.finished.connect(self._on_poll_done)
        self._poll_op.start()

    def _on_poll_done(self, success: bool, output: str) -> None:
        if self._done:
            return
        self._poll_op = None
        status = None
        if success:
            for s in _parse_sessions_output(output):
                if s.get('config_name') == self._vpn_name:
                    status = s.get('status')
                    break
        if status and 'Client connected' in status:
            self._emit(True, f"Connected to {self._vpn_name} (OpenVPN3)")
            return
        if status:
            logger.debug(
                f"{self._vpn_name}: status = {status} "
                f"({self._elapsed_s}s/{self._auth_timeout_s}s)")
        self._elapsed_s += OV3_POLL_INTERVAL_MS // 1000
        if self._elapsed_s >= self._auth_timeout_s:
            # Timeout: clean up and report failure.
            logger.warning(f"Auth timeout after {self._auth_timeout_s}s for {self._vpn_name}")
            self._cleanup_op = _Ov3DisconnectOp(self._vpn_name, parent=self)
            self._cleanup_op.finished.connect(
                lambda *_: self._emit(
                    False,
                    f"Authentication timed out after {self._auth_timeout_s}s "
                    f"for {self._vpn_name}")
            )
            self._cleanup_op.start()

    def _emit(self, success: bool, message: str) -> None:
        if self._done:
            return
        self._done = True
        if self._poll_timer:
            self._poll_timer.stop()
        if success:
            logger.info(message)
        else:
            logger.error(message)
        self.finished.emit(success, message)


def _raise_browser_async(parent: QObject) -> None:
    """Fire-and-forget browser raise for OIDC auth.

    Best-effort only — if kdotool isn't installed, or no browser window is
    found, silently does nothing.
    """
    proc = QProcess(parent)
    proc.finished.connect(lambda *_: proc.deleteLater())
    proc.errorOccurred.connect(lambda *_: proc.deleteLater())
    # Try the most common browser first — vivaldi, then firefox, etc.
    # This fires ONE 'kdotool search --class X windowraise %1' — if it fails,
    # we accept the cost and move on (the user can always alt-tab).
    proc.start('kdotool', ['search', '--class', 'vivaldi', 'windowraise', '%1'])
