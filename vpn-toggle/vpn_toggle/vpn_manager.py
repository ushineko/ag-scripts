"""
VPN Manager — facade that delegates to backend implementations.

Maintains backward compatibility: external code continues to use VPNManager
with the same API. The backend is selected per-VPN based on config.
"""
import logging
from datetime import datetime
from typing import List, Tuple, Optional

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from .models import VPNConnection, VPNStatus  # noqa: F401 (re-exported)
from .backends import VPNBackend
from .backends.nm import NMBackend

logger = logging.getLogger('vpn_toggle.vpn_manager')


class VPNManager:
    """
    Facade that manages VPN connections across multiple backends.

    Backends are registered at init. Each VPN is associated with a backend
    via the config's 'backend' field (defaults to 'networkmanager').
    """

    def __init__(self, config_manager=None):
        self._backends: dict[str, VPNBackend] = {}
        self._config_manager = config_manager
        # Maps vpn_name -> backend_name, populated by list_vpns() discovery
        self._discovered_backends: dict[str, str] = {}

        # Register NetworkManager backend
        nm = NMBackend()
        if nm.available:
            self._backends['networkmanager'] = nm
        else:
            logger.warning("NetworkManager backend unavailable (nmcli not found)")

        # Register OpenVPN3 backend
        from .backends.openvpn3 import OpenVPN3Backend
        ov3 = OpenVPN3Backend()
        if ov3.available:
            self._backends['openvpn3'] = ov3
        else:
            logger.debug("OpenVPN3 backend unavailable (openvpn3 not found)")

        if not self._backends:
            raise RuntimeError(
                "No VPN backends available. "
                "Please install NetworkManager (nmcli) or OpenVPN3."
            )

    def _get_backend(self, vpn_name: str) -> VPNBackend:
        """Get the backend for a VPN.

        Resolution order:
        1. Explicit 'backend' field in config (e.g., "openvpn3")
        2. Discovery map from list_vpns() (connection_type recorded at discovery)
        3. Default to 'networkmanager'
        """
        backend_name = None

        # 1. Check config for explicit backend
        if self._config_manager:
            vpn_config = self._config_manager.get_vpn_config(vpn_name)
            if vpn_config:
                backend_name = vpn_config.get('backend')

        # 2. Fall back to discovery map
        if not backend_name:
            backend_name = self._discovered_backends.get(vpn_name, 'networkmanager')

        backend = self._backends.get(backend_name)
        if not backend:
            # Fall back to first available backend
            backend = next(iter(self._backends.values()))
            logger.warning(
                f"Backend '{backend_name}' not available for {vpn_name}, "
                f"falling back to '{backend.name}'"
            )
        return backend

    def _get_backend_for_connect(self, vpn_name: str) -> Tuple[VPNBackend, dict]:
        """Get backend and any extra kwargs (like auth_timeout) for connect."""
        backend = self._get_backend(vpn_name)
        kwargs = {}
        if backend.name == 'openvpn3':
            # Check config for custom auth timeout
            if self._config_manager:
                vpn_config = self._config_manager.get_vpn_config(vpn_name)
                if vpn_config:
                    kwargs['auth_timeout'] = vpn_config.get('auth_timeout_seconds', 60)
                else:
                    kwargs['auth_timeout'] = 60
            else:
                kwargs['auth_timeout'] = 60
        return backend, kwargs

    def list_vpns(self) -> List[VPNConnection]:
        """List all VPN connections across all backends."""
        all_vpns = []
        for backend in self._backends.values():
            try:
                vpns = backend.list_vpns()
                for vpn in vpns:
                    self._discovered_backends[vpn.name] = backend.name
                all_vpns.extend(vpns)
            except Exception as e:
                logger.error(f"Error listing VPNs from {backend.name}: {e}")
        return all_vpns

    def is_vpn_active(self, vpn_name: str) -> bool:
        return self._get_backend(vpn_name).is_vpn_active(vpn_name)

    def get_vpn_status(self, vpn_name: str) -> VPNStatus:
        return self._get_backend(vpn_name).get_vpn_status(vpn_name)

    def connect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        backend, kwargs = self._get_backend_for_connect(vpn_name)
        return backend.connect_vpn(vpn_name, **kwargs)

    def disconnect_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        return self._get_backend(vpn_name).disconnect_vpn(vpn_name)

    def bounce_vpn(self, vpn_name: str) -> Tuple[bool, str]:
        backend, kwargs = self._get_backend_for_connect(vpn_name)
        return backend.bounce_vpn(vpn_name, **kwargs)

    def get_connection_timestamp(self, vpn_name: str) -> Optional[datetime]:
        return self._get_backend(vpn_name).get_connection_timestamp(vpn_name)

    def get_vpn_details(self, vpn_name: str) -> dict:
        return self._get_backend(vpn_name).get_vpn_details(vpn_name)

    # -- Async variants (used by MonitorController) --

    def is_vpn_active_async(self, vpn_name: str, parent: Optional[QObject] = None):
        """Return an async op whose `finished(bool)` signal reports activeness."""
        return self._get_backend(vpn_name).is_vpn_active_async(vpn_name, parent=parent)

    def connect_vpn_async(self, vpn_name: str, parent: Optional[QObject] = None):
        """Return an async op whose `finished(success, message)` signals connect result."""
        backend, kwargs = self._get_backend_for_connect(vpn_name)
        return backend.connect_vpn_async(vpn_name, parent=parent, **kwargs)

    def disconnect_vpn_async(self, vpn_name: str, parent: Optional[QObject] = None):
        """Return an async op whose `finished(success, message)` signals disconnect result."""
        return self._get_backend(vpn_name).disconnect_vpn_async(vpn_name, parent=parent)

    def bounce_vpn_async(self, vpn_name: str, grace_seconds: int = 2,
                         parent: Optional[QObject] = None) -> "BounceOperation":
        """Return an async op that disconnects, waits grace_seconds, then reconnects."""
        return BounceOperation(self, vpn_name, grace_seconds, parent=parent)


class BounceOperation(QObject):
    """Disconnect → grace wait → connect, emitting finished(success, message).

    Mirrors `VPNBackend.bounce_vpn` but without blocking the thread.
    """

    finished = pyqtSignal(bool, str)

    def __init__(self, manager: VPNManager, vpn_name: str, grace_seconds: int,
                 parent: Optional[QObject] = None):
        super().__init__(parent)
        self._manager = manager
        self._vpn_name = vpn_name
        self._grace_ms = max(0, int(grace_seconds * 1000))
        self._done = False

    def start(self) -> None:
        if self._done:
            return
        logger.info(f"Bouncing VPN: {self._vpn_name}")
        op = self._manager.disconnect_vpn_async(self._vpn_name, parent=self)
        op.finished.connect(self._on_disconnected)
        op.start()

    def _on_disconnected(self, success: bool, message: str) -> None:
        if self._done:
            return
        if not success:
            logger.warning(f"Disconnect failed (may not have been connected): {message}")
        QTimer.singleShot(self._grace_ms, self._reconnect)

    def _reconnect(self) -> None:
        if self._done:
            return
        op = self._manager.connect_vpn_async(self._vpn_name, parent=self)
        op.finished.connect(self._on_reconnected)
        op.start()

    def _on_reconnected(self, success: bool, message: str) -> None:
        if self._done:
            return
        self._done = True
        if success:
            msg = f"Bounced {self._vpn_name} successfully"
            logger.info(msg)
            self.finished.emit(True, msg)
        else:
            msg = f"Bounce failed (reconnect failed): {message}"
            logger.error(msg)
            self.finished.emit(False, msg)
