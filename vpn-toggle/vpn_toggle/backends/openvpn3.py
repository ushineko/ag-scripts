"""
OpenVPN3 backend — manages VPN connections via openvpn3 CLI.
"""
import logging
import re
import subprocess
import time
from datetime import datetime
from typing import List, Tuple, Optional

from ..models import VPNConnection, VPNStatus
from . import VPNBackend

logger = logging.getLogger('vpn_toggle.backends.openvpn3')

DEFAULT_AUTH_TIMEOUT = 60


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

        Each dict has keys: path, config_name, status
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
