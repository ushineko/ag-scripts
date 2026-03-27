"""
Data models for VPN Toggle
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class VPNConnection:
    """Represents a VPN connection"""
    name: str              # Connection/config name
    display_name: str      # User-friendly name
    active: bool           # Currently connected
    connection_type: str   # Connection type (vpn, openvpn3, etc.)


@dataclass
class VPNStatus:
    """Represents the current status of a VPN connection"""
    connected: bool
    ip_address: Optional[str] = None
    connection_time: Optional[datetime] = None
