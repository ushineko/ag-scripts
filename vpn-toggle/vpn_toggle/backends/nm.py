"""
NetworkManager backend — manages VPN connections via nmcli.

Provides both sync methods (used by GUI card buttons, tray, and tests) and
async variants (used by the event-driven MonitorController).
"""
import logging
import subprocess
from datetime import datetime
from typing import List, Tuple, Optional

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from ..models import VPNConnection, VPNStatus
from . import VPNBackend

logger = logging.getLogger('vpn_toggle.backends.nm')

NMCLI_DEFAULT_TIMEOUT_MS = 30_000
NMCLI_CONNECT_TIMEOUT_MS = 60_000


class NMBackend(VPNBackend):
    """VPN backend using NetworkManager (nmcli)."""

    def __init__(self):
        self._available = self._check_nmcli()

    @property
    def name(self) -> str:
        return "networkmanager"

    @property
    def available(self) -> bool:
        return self._available

    def _check_nmcli(self) -> bool:
        try:
            result = subprocess.run(
                ['which', 'nmcli'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                logger.debug("nmcli found and available")
                return True
            else:
                logger.warning("nmcli command not found")
                return False
        except (subprocess.TimeoutExpired, FileNotFoundError):
            logger.warning("Failed to check for nmcli")
            return False

    def _run_nmcli(self, args: List[str], timeout: int = 30) -> Tuple[bool, str]:
        cmd = ['nmcli'] + args
        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout
            )
            if result.returncode == 0:
                logger.debug(f"Command succeeded: {result.stdout.strip()}")
                return True, result.stdout.strip()
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

        success, output = self._run_nmcli(['-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if not success:
            logger.error("Failed to list connections")
            return []

        active_success, active_output = self._run_nmcli(['connection', 'show', '--active'])
        active_names = set()
        if active_success:
            for line in active_output.split('\n'):
                if line.strip():
                    parts = line.split()
                    if len(parts) > 0:
                        active_names.add(parts[0])

        vpns = []
        for line in output.split('\n'):
            if not line.strip():
                continue

            parts = line.split(':')
            if len(parts) >= 2:
                name = parts[0]
                conn_type = parts[1]

                if 'vpn' in conn_type.lower():
                    is_active = name in active_names
                    vpns.append(VPNConnection(
                        name=name,
                        display_name=name,
                        active=is_active,
                        connection_type=conn_type
                    ))

        logger.info(f"Found {len(vpns)} NM VPN connections")
        return vpns

    def is_vpn_active(self, vpn_name: str) -> bool:
        if not self._available:
            return False

        success, output = self._run_nmcli(['connection', 'show', '--active'])
        if not success:
            return False

        for line in output.split('\n'):
            if vpn_name in line:
                return True
        return False

    def get_vpn_status(self, vpn_name: str) -> VPNStatus:
        is_active = self.is_vpn_active(vpn_name)

        if is_active:
            success, output = self._run_nmcli(['-t', '-f', 'IP4.ADDRESS', 'connection', 'show', vpn_name])
            ip_address = None
            if success and output:
                for line in output.split('\n'):
                    if 'IP4.ADDRESS' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            ip_address = parts[1].split('/')[0]
                            break

            return VPNStatus(connected=True, ip_address=ip_address, connection_time=datetime.now())
        else:
            return VPNStatus(connected=False)

    def connect_vpn(self, vpn_name: str, **kwargs) -> Tuple[bool, str]:
        logger.info(f"Connecting to VPN: {vpn_name}")
        success, output = self._run_nmcli(['connection', 'up', vpn_name], timeout=60)

        if success:
            message = f"Connected to {vpn_name}"
            logger.info(message)
            return True, message
        else:
            message = f"Failed to connect to {vpn_name}: {output}"
            logger.error(message)
            return False, message

    def disconnect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        logger.info(f"Disconnecting VPN: {vpn_name}")
        success, output = self._run_nmcli(['connection', 'down', vpn_name])

        if success:
            message = f"Disconnected from {vpn_name}"
            logger.info(message)
            return True, message
        else:
            message = f"Failed to disconnect from {vpn_name}: {output}"
            logger.error(message)
            return False, message

    def get_vpn_details(self, vpn_name: str) -> dict:
        if not self._available or not self.is_vpn_active(vpn_name):
            return {}

        success, output = self._run_nmcli(
            ['-t', '-f', 'IP4.ADDRESS,IP4.ROUTE,GENERAL.DEVICES',
             'connection', 'show', vpn_name]
        )
        if not success:
            return {}

        interface = ''
        ip_addr = ''
        routes = []
        for line in output.split('\n'):
            if line.startswith('GENERAL.DEVICES:'):
                interface = line.split(':', 1)[1].strip()
            elif line.startswith('IP4.ADDRESS'):
                ip_addr = line.split(':', 1)[1].strip()
            elif line.startswith('IP4.ROUTE'):
                # Format: dst = X, nh = Y, mt = Z
                route_part = line.split(':', 1)[1].strip()
                routes.append(route_part)

        return {'interface': interface, 'ip': ip_addr, 'routes': routes}

    def get_connection_timestamp(self, vpn_name: str) -> Optional[datetime]:
        success, output = self._run_nmcli(
            ['-t', '-f', 'connection.timestamp', 'connection', 'show', vpn_name]
        )
        if not success or not output:
            return None

        for line in output.split('\n'):
            if 'connection.timestamp' in line:
                parts = line.split(':', 1)
                if len(parts) >= 2:
                    try:
                        ts = int(parts[1].strip())
                        if ts > 0:
                            return datetime.fromtimestamp(ts)
                    except (ValueError, OSError):
                        pass
        return None

    # -- Async variants (used by MonitorController) --

    def is_vpn_active_async(self, vpn_name: str, parent: Optional[QObject] = None) -> "_NmActiveCheckOp":
        return _NmActiveCheckOp(vpn_name, parent=parent)

    def connect_vpn_async(self, vpn_name: str, parent: Optional[QObject] = None) -> "_NmConnectOp":
        return _NmConnectOp(vpn_name, parent=parent)

    def disconnect_vpn_async(self, vpn_name: str, parent: Optional[QObject] = None) -> "_NmDisconnectOp":
        return _NmDisconnectOp(vpn_name, parent=parent)


# ---------------------------------------------------------------------------
# Async operations — one QObject per in-flight nmcli invocation.
# ---------------------------------------------------------------------------


class _NmCmdOp(QObject):
    """Base for a single async nmcli command. Subclasses parse stdout."""

    def __init__(self, args: List[str], timeout_ms: int = NMCLI_DEFAULT_TIMEOUT_MS,
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
        logger.debug(f"Running command: nmcli {' '.join(self._args)}")
        self._proc.start('nmcli', self._args)

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
        self._emit(ok, output)

    def _on_error(self, _err) -> None:
        if self._done:
            return
        self._done = True
        if self._timer:
            self._timer.stop()
        msg = self._proc.errorString() if self._proc else 'unknown'
        self._emit(False, msg)

    def _on_timeout(self) -> None:
        if self._done:
            return
        self._done = True
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        self._emit(False, f"Command timed out after {self._timeout_ms // 1000}s")

    def _emit(self, success: bool, output: str) -> None:
        """Subclasses override to emit their specific finished signal."""
        raise NotImplementedError


class _NmActiveCheckOp(_NmCmdOp):
    finished = pyqtSignal(bool)  # is_active

    def __init__(self, vpn_name: str, parent: Optional[QObject] = None):
        super().__init__(['connection', 'show', '--active'], parent=parent)
        self._vpn_name = vpn_name

    def _emit(self, success: bool, output: str) -> None:
        if not success:
            self.finished.emit(False)
            return
        active = any(self._vpn_name in line for line in output.split('\n'))
        self.finished.emit(active)


class _NmConnectOp(_NmCmdOp):
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, vpn_name: str, parent: Optional[QObject] = None):
        super().__init__(['connection', 'up', vpn_name],
                         timeout_ms=NMCLI_CONNECT_TIMEOUT_MS, parent=parent)
        self._vpn_name = vpn_name

    def _emit(self, success: bool, output: str) -> None:
        if success:
            msg = f"Connected to {self._vpn_name}"
            logger.info(msg)
            self.finished.emit(True, msg)
        else:
            msg = f"Failed to connect to {self._vpn_name}: {output}"
            logger.error(msg)
            self.finished.emit(False, msg)


class _NmDisconnectOp(_NmCmdOp):
    finished = pyqtSignal(bool, str)  # success, message

    def __init__(self, vpn_name: str, parent: Optional[QObject] = None):
        super().__init__(['connection', 'down', vpn_name], parent=parent)
        self._vpn_name = vpn_name

    def _emit(self, success: bool, output: str) -> None:
        if success:
            msg = f"Disconnected from {self._vpn_name}"
            logger.info(msg)
            self.finished.emit(True, msg)
        else:
            msg = f"Failed to disconnect from {self._vpn_name}: {output}"
            logger.error(msg)
            self.finished.emit(False, msg)
