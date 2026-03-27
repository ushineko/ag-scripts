"""
NetworkManager backend — manages VPN connections via nmcli.
"""
import logging
import subprocess
from datetime import datetime
from typing import List, Tuple, Optional

from ..models import VPNConnection, VPNStatus
from . import VPNBackend

logger = logging.getLogger('vpn_toggle.backends.nm')


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
