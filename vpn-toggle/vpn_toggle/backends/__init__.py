"""
VPN backend abstraction layer.

Each backend implements the VPNBackend protocol to provide a uniform
interface for different VPN management systems (NetworkManager, OpenVPN3, etc.).
"""
import logging
import time
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from datetime import datetime

from ..models import VPNConnection, VPNStatus


class VPNBackend(ABC):
    """
    Abstract base class for VPN backends.

    Each backend manages VPN connections through a specific system
    (e.g., NetworkManager via nmcli, OpenVPN3 via openvpn3 CLI).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Backend identifier (e.g., 'networkmanager', 'openvpn3')."""

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this backend's tooling is installed and usable."""

    @abstractmethod
    def list_vpns(self) -> List[VPNConnection]:
        """List all VPN connections managed by this backend."""

    @abstractmethod
    def is_vpn_active(self, vpn_name: str) -> bool:
        """Check if a VPN connection is currently active."""

    @abstractmethod
    def get_vpn_status(self, vpn_name: str) -> VPNStatus:
        """Get the current status of a VPN connection."""

    @abstractmethod
    def connect_vpn(self, vpn_name: str, **kwargs) -> Tuple[bool, str]:
        """Connect to a VPN. Returns (success, message)."""

    @abstractmethod
    def disconnect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        """Disconnect from a VPN. Returns (success, message)."""

    @abstractmethod
    def get_connection_timestamp(self, vpn_name: str) -> Optional[datetime]:
        """Get the timestamp when the VPN was last activated."""

    def bounce_vpn(self, vpn_name: str, **kwargs) -> Tuple[bool, str]:
        """
        Bounce (disconnect + reconnect) a VPN connection.

        Default implementation disconnects then reconnects with a 2s pause.
        Backends may override for custom behavior.
        """
        logger = logging.getLogger(f'vpn_toggle.backends.{self.name}')
        logger.info(f"Bouncing VPN: {vpn_name}")

        disconnect_success, disconnect_msg = self.disconnect_vpn(vpn_name)
        if not disconnect_success:
            logger.warning(f"Disconnect failed (may not have been connected): {disconnect_msg}")

        time.sleep(2)

        connect_success, connect_msg = self.connect_vpn(vpn_name, **kwargs)

        if connect_success:
            message = f"Bounced {vpn_name} successfully"
            logger.info(message)
            return True, message
        else:
            message = f"Bounce failed (reconnect failed): {connect_msg}"
            logger.error(message)
            return False, message
