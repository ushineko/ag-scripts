"""
VPN Manager - nmcli wrapper for VPN operations
"""
import logging
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Tuple, Optional

logger = logging.getLogger('vpn_toggle.vpn_manager')


@dataclass
class VPNConnection:
    """Represents a VPN connection"""
    name: str              # nmcli connection name
    display_name: str      # User-friendly name
    active: bool           # Currently connected
    connection_type: str   # Connection type (vpn, wifi, ethernet, etc.)


@dataclass
class VPNStatus:
    """Represents the current status of a VPN connection"""
    connected: bool
    ip_address: Optional[str] = None
    connection_time: Optional[datetime] = None


class VPNManager:
    """
    Manages VPN connections using NetworkManager (nmcli).

    Provides methods to list, connect, disconnect, and manage VPN connections.
    """

    def __init__(self):
        """Initialize VPN Manager"""
        self._check_nmcli_available()

    def _check_nmcli_available(self) -> None:
        """
        Check if nmcli command is available.

        Raises:
            RuntimeError: If nmcli is not found
        """
        try:
            result = subprocess.run(
                ['which', 'nmcli'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                raise RuntimeError("nmcli command not found. Please install NetworkManager.")
            logger.debug("nmcli found and available")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Timeout checking for nmcli command")
        except FileNotFoundError:
            raise RuntimeError("which command not found")

    def _run_nmcli(self, args: List[str], timeout: int = 30) -> Tuple[bool, str]:
        """
        Run nmcli command with given arguments.

        Args:
            args: Command arguments to pass to nmcli
            timeout: Command timeout in seconds

        Returns:
            Tuple of (success, output/error_message)
        """
        cmd = ['nmcli'] + args
        logger.debug(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
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
        """
        List all VPN connections (both active and inactive).

        Returns:
            List of VPNConnection objects
        """
        logger.debug("Listing all VPN connections")

        # Get all connections
        success, output = self._run_nmcli(['-t', '-f', 'NAME,TYPE', 'connection', 'show'])
        if not success:
            logger.error("Failed to list connections")
            return []

        # Get active connections
        active_success, active_output = self._run_nmcli(['connection', 'show', '--active'])
        active_names = set()
        if active_success:
            for line in active_output.split('\n'):
                if line.strip():
                    # Extract connection name from active connections output
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

                # Filter to only VPN connections
                if 'vpn' in conn_type.lower():
                    is_active = name in active_names
                    vpns.append(VPNConnection(
                        name=name,
                        display_name=name,  # Will be overridden by config
                        active=is_active,
                        connection_type=conn_type
                    ))

        logger.info(f"Found {len(vpns)} VPN connections")
        return vpns

    def get_vpn_status(self, vpn_name: str) -> VPNStatus:
        """
        Get the current status of a VPN connection.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            VPNStatus object
        """
        logger.debug(f"Getting status for VPN: {vpn_name}")

        is_active = self.is_vpn_active(vpn_name)

        if is_active:
            # Try to get IP address
            success, output = self._run_nmcli(['-t', '-f', 'IP4.ADDRESS', 'connection', 'show', vpn_name])
            ip_address = None
            if success and output:
                # Extract IP from output like "IP4.ADDRESS[1]:10.8.0.2/24"
                for line in output.split('\n'):
                    if 'IP4.ADDRESS' in line:
                        parts = line.split(':')
                        if len(parts) >= 2:
                            ip_address = parts[1].split('/')[0]  # Remove netmask
                            break

            return VPNStatus(connected=True, ip_address=ip_address, connection_time=datetime.now())
        else:
            return VPNStatus(connected=False)

    def is_vpn_active(self, vpn_name: str) -> bool:
        """
        Check if a VPN connection is currently active.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            True if VPN is active, False otherwise
        """
        success, output = self._run_nmcli(['connection', 'show', '--active'])
        if not success:
            return False

        # Check if vpn_name appears in active connections
        for line in output.split('\n'):
            if vpn_name in line:
                return True

        return False

    def connect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        """
        Connect to a VPN.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            Tuple of (success, message)
        """
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
        """
        Disconnect from a VPN.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            Tuple of (success, message)
        """
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

    def bounce_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        """
        Bounce (restart) a VPN connection.

        Disconnects and then reconnects the VPN. Useful for resetting stuck connections.

        Args:
            vpn_name: Name of the VPN connection

        Returns:
            Tuple of (success, message)
        """
        logger.info(f"Bouncing VPN: {vpn_name}")

        # Disconnect
        disconnect_success, disconnect_msg = self.disconnect_vpn(vpn_name)
        if not disconnect_success:
            # If disconnect fails, it might not be connected - proceed anyway
            logger.warning(f"Disconnect failed (may not have been connected): {disconnect_msg}")

        # Wait a moment for the connection to fully close
        time.sleep(2)

        # Reconnect
        connect_success, connect_msg = self.connect_vpn(vpn_name)

        if connect_success:
            message = f"Bounced {vpn_name} successfully"
            logger.info(message)
            return True, message
        else:
            message = f"Bounce failed (reconnect failed): {connect_msg}"
            logger.error(message)
            return False, message
