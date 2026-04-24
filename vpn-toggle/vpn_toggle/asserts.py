"""
Assert system for VPN health checking
"""
import logging
import re
import socket
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger('vpn_toggle.asserts')


@dataclass
class AssertResult:
    """Result of an assert check"""
    success: bool
    message: str
    details: Dict[str, Any]  # Additional details for logging


class VPNAssert(ABC):
    """
    Base class for VPN asserts.

    An assert is a health check that verifies the VPN connection is working correctly.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize assert with configuration.

        Args:
            config: Assert configuration dictionary
        """
        self.config = config

    @abstractmethod
    def check(self) -> AssertResult:
        """
        Perform the assert check.

        Returns:
            AssertResult indicating success or failure
        """
        pass

    def get_description(self) -> str:
        """
        Get human-readable description of this assert.

        Returns:
            Description string
        """
        return self.config.get('description', self.__class__.__name__)


class DNSLookupAssert(VPNAssert):
    """
    DNS Lookup Assert - Verifies DNS resolution matches expected IP prefix.

    Resolves a hostname and checks if the returned IP address starts with
    the expected prefix (supports partial matching).
    """

    def check(self) -> AssertResult:
        """
        Perform DNS lookup and check against expected IP prefix.

        Returns:
            AssertResult with success status and details
        """
        hostname = self.config.get('hostname')
        expected_prefix = self.config.get('expected_prefix')

        if not hostname or not expected_prefix:
            return AssertResult(
                success=False,
                message="DNS assert configuration missing hostname or expected_prefix",
                details={'hostname': hostname, 'expected_prefix': expected_prefix}
            )

        try:
            # Resolve hostname to IP
            ip_address = socket.gethostbyname(hostname)
            logger.debug(f"DNS lookup for {hostname}: {ip_address}")

            # Check if IP starts with expected prefix
            if ip_address.startswith(expected_prefix):
                message = f"DNS check PASSED: {hostname} resolves to {ip_address} (matches prefix {expected_prefix})"
                logger.info(message)
                return AssertResult(
                    success=True,
                    message=message,
                    details={'hostname': hostname, 'ip': ip_address, 'expected_prefix': expected_prefix}
                )
            else:
                message = f"DNS check FAILED: {hostname} resolves to {ip_address} (expected prefix {expected_prefix})"
                logger.warning(message)
                return AssertResult(
                    success=False,
                    message=message,
                    details={'hostname': hostname, 'ip': ip_address, 'expected_prefix': expected_prefix}
                )

        except socket.gaierror as e:
            message = f"DNS check FAILED: Could not resolve {hostname}: {e}"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'hostname': hostname, 'error': str(e)}
            )
        except Exception as e:
            message = f"DNS check FAILED: Unexpected error: {e}"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'hostname': hostname, 'error': str(e)}
            )


class GeolocationAssert(VPNAssert):
    """
    Geolocation Assert - Verifies public IP originates from expected location.

    Uses ip-api.com (free, no API key required) to check the geolocation
    of the public IP address.
    """

    API_URL = 'http://ip-api.com/json'
    REQUEST_TIMEOUT = 10  # seconds

    def check(self) -> AssertResult:
        """
        Perform geolocation check against expected location.

        Returns:
            AssertResult with success status and details
        """
        field = self.config.get('field', 'city')  # Default to city
        expected_value = self.config.get('expected_value')

        if not expected_value:
            return AssertResult(
                success=False,
                message="Geolocation assert configuration missing expected_value",
                details={'field': field, 'expected_value': expected_value}
            )

        try:
            # Query ip-api.com for geolocation
            logger.debug(f"Querying {self.API_URL} for geolocation")
            response = requests.get(self.API_URL, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()

            data = response.json()

            # Check if API query was successful
            if data.get('status') != 'success':
                error_message = data.get('message', 'Unknown error')
                message = f"Geolocation check FAILED: API error: {error_message}"
                logger.error(message)
                return AssertResult(
                    success=False,
                    message=message,
                    details={'error': error_message}
                )

            # Extract the requested field
            actual_value = data.get(field, '')
            public_ip = data.get('query', 'unknown')

            # IMPORTANT: Print detected location for user debugging
            logger.info(f"Detected location: {field}='{actual_value}' (IP: {public_ip})")
            print(f"[Geolocation] Detected {field}: '{actual_value}' (IP: {public_ip})")

            # Check if actual value contains expected value (case-insensitive)
            if expected_value.lower() in actual_value.lower():
                message = f"Geolocation check PASSED: {field}='{actual_value}' matches expected '{expected_value}'"
                logger.info(message)
                return AssertResult(
                    success=True,
                    message=message,
                    details={
                        'field': field,
                        'expected': expected_value,
                        'actual': actual_value,
                        'ip': public_ip,
                        'full_location': {
                            'city': data.get('city'),
                            'region': data.get('regionName'),
                            'country': data.get('country')
                        }
                    }
                )
            else:
                message = f"Geolocation check FAILED: {field}='{actual_value}' does not match expected '{expected_value}'"
                logger.warning(message)
                return AssertResult(
                    success=False,
                    message=message,
                    details={
                        'field': field,
                        'expected': expected_value,
                        'actual': actual_value,
                        'ip': public_ip,
                        'full_location': {
                            'city': data.get('city'),
                            'region': data.get('regionName'),
                            'country': data.get('country')
                        }
                    }
                )

        except requests.RequestException as e:
            message = f"Geolocation check FAILED: Network error: {e}"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'error': str(e)}
            )
        except Exception as e:
            message = f"Geolocation check FAILED: Unexpected error: {e}"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'error': str(e)}
            )


class PingAssert(VPNAssert):
    """
    Ping Assert - Verifies a host is reachable via ICMP ping.

    Useful for checking that internal hosts behind a VPN tunnel are accessible.
    """

    def check(self) -> AssertResult:
        host = self.config.get('host')
        timeout = self.config.get('timeout_seconds', 5)

        if not host:
            return AssertResult(
                success=False,
                message="Ping assert configuration missing 'host'",
                details={'host': host}
            )

        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), host],
                capture_output=True, text=True, timeout=timeout + 2
            )

            if result.returncode == 0:
                # Extract RTT from output (e.g., "time=13.5 ms")
                rtt_match = re.search(r'time[=<]([\d.]+)\s*ms', result.stdout)
                rtt = rtt_match.group(1) if rtt_match else "?"
                message = f"Ping check PASSED: {host} reachable ({rtt}ms)"
                logger.info(message)
                return AssertResult(
                    success=True,
                    message=message,
                    details={'host': host, 'rtt_ms': rtt}
                )
            else:
                message = f"Ping check FAILED: {host} unreachable"
                logger.warning(message)
                return AssertResult(
                    success=False,
                    message=message,
                    details={'host': host}
                )

        except subprocess.TimeoutExpired:
            message = f"Ping check FAILED: {host} timed out after {timeout}s"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'host': host, 'timeout': timeout}
            )
        except Exception as e:
            message = f"Ping check FAILED: {e}"
            logger.error(message)
            return AssertResult(
                success=False,
                message=message,
                details={'host': host, 'error': str(e)}
            )


def create_assert(assert_config: Dict[str, Any]) -> VPNAssert:
    """
    Factory function to create assert instances from configuration.

    Args:
        assert_config: Assert configuration dictionary with 'type' key

    Returns:
        VPNAssert instance

    Raises:
        ValueError: If assert type is unknown
    """
    assert_type = assert_config.get('type')

    if assert_type == 'dns_lookup':
        return DNSLookupAssert(assert_config)
    elif assert_type == 'geolocation':
        return GeolocationAssert(assert_config)
    elif assert_type == 'ping':
        return PingAssert(assert_config)
    else:
        raise ValueError(f"Unknown assert type: {assert_type}")


# ---------------------------------------------------------------------------
# Async assert variants — used by the event-driven MonitorController.
#
# Each AsyncAssert is a QObject that emits `completed(AssertResult)` when the
# underlying async operation finishes (success, failure, or timeout). The
# corresponding sync classes above remain unchanged and are used by tests and
# ad-hoc callers.
#
# Key invariants:
#   - Exactly one `completed` emit per start() call (double-emit is guarded).
#   - Every in-flight Qt object is parented to `self`, so destroying the
#     assert destroys its operation.
#   - A QTimer-backed hard timeout ensures no operation wedges indefinitely.
# ---------------------------------------------------------------------------

from PyQt6.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import (
    QDnsLookup,
    QNetworkAccessManager,
    QNetworkReply,
    QNetworkRequest,
)

DNS_TIMEOUT_MS = 30_000
GEOLOCATION_TIMEOUT_MS = 12_000
PING_TIMEOUT_EXTRA_S = 2


class _AsyncAssertBase(QObject):
    """Shared completion bookkeeping for async asserts."""

    completed = pyqtSignal(object)

    def __init__(self, config: Dict[str, Any], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.config = config
        self._done = False
        self._timer: Optional[QTimer] = None

    def get_description(self) -> str:
        return self.config.get('description', self.__class__.__name__)

    def _arm_timeout(self, ms: int) -> None:
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        self._timer.start(ms)

    def _finish(self, result: "AssertResult") -> None:
        if self._done:
            return
        self._done = True
        if self._timer:
            self._timer.stop()
        self.completed.emit(result)

    def _on_timeout(self) -> None:
        """Subclasses override to abort their specific primitive."""
        if self._done:
            return
        self._finish(AssertResult(
            success=False,
            message=f"{self.__class__.__name__}: operation timed out",
            details={'timeout': True},
        ))


class AsyncDNSLookupAssert(_AsyncAssertBase):
    """Non-blocking DNS lookup using QDnsLookup."""

    def __init__(self, config: Dict[str, Any], parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._lookup: Optional[QDnsLookup] = None

    # Overridable for tests.
    def _make_lookup(self, hostname: str) -> QDnsLookup:
        lookup = QDnsLookup(self)
        lookup.setType(QDnsLookup.Type.A)
        lookup.setName(hostname)
        return lookup

    def start(self) -> None:
        if self._done:
            return
        hostname = self.config.get('hostname')
        expected_prefix = self.config.get('expected_prefix')

        if not hostname or not expected_prefix:
            self._finish(AssertResult(
                success=False,
                message="DNS assert configuration missing hostname or expected_prefix",
                details={'hostname': hostname, 'expected_prefix': expected_prefix},
            ))
            return

        self._lookup = self._make_lookup(hostname)
        self._lookup.finished.connect(self._on_finished)
        self._arm_timeout(DNS_TIMEOUT_MS)
        self._lookup.lookup()

    def _on_finished(self) -> None:
        if self._done:
            return
        hostname = self.config.get('hostname')
        expected_prefix = self.config.get('expected_prefix')

        if self._lookup is None:
            self._finish(AssertResult(
                success=False,
                message=f"DNS check FAILED: internal error (no lookup)",
                details={'hostname': hostname},
            ))
            return

        if self._lookup.error() != QDnsLookup.Error.NoError:
            msg = self._lookup.errorString()
            message = f"DNS check FAILED: Could not resolve {hostname}: {msg}"
            logger.error(message)
            self._finish(AssertResult(
                success=False,
                message=message,
                details={'hostname': hostname, 'error': msg},
            ))
            return

        records = self._lookup.hostAddressRecords()
        if not records:
            message = f"DNS check FAILED: No A records for {hostname}"
            logger.warning(message)
            self._finish(AssertResult(
                success=False,
                message=message,
                details={'hostname': hostname, 'error': 'no records'},
            ))
            return

        ip_address = records[0].value().toString()
        logger.debug(f"DNS lookup for {hostname}: {ip_address}")

        if ip_address.startswith(expected_prefix):
            message = (f"DNS check PASSED: {hostname} resolves to {ip_address} "
                       f"(matches prefix {expected_prefix})")
            logger.info(message)
            self._finish(AssertResult(
                success=True,
                message=message,
                details={'hostname': hostname, 'ip': ip_address,
                         'expected_prefix': expected_prefix},
            ))
        else:
            message = (f"DNS check FAILED: {hostname} resolves to {ip_address} "
                       f"(expected prefix {expected_prefix})")
            logger.warning(message)
            self._finish(AssertResult(
                success=False,
                message=message,
                details={'hostname': hostname, 'ip': ip_address,
                         'expected_prefix': expected_prefix},
            ))

    def _on_timeout(self) -> None:
        if self._done:
            return
        hostname = self.config.get('hostname')
        if self._lookup:
            self._lookup.abort()
        message = f"DNS check FAILED: Timed out resolving {hostname}"
        logger.error(message)
        self._finish(AssertResult(
            success=False,
            message=message,
            details={'hostname': hostname, 'error': 'timeout'},
        ))


class AsyncGeolocationAssert(_AsyncAssertBase):
    """Non-blocking HTTP GET to ip-api.com using QNetworkAccessManager."""

    API_URL = 'http://ip-api.com/json'

    def __init__(self, config: Dict[str, Any], nam: Optional[QNetworkAccessManager] = None,
                 parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._reply: Optional[QNetworkReply] = None
        self._nam = nam

    def _make_request(self) -> QNetworkReply:
        if self._nam is None:
            self._nam = QNetworkAccessManager(self)
        request = QNetworkRequest(QUrl(self.API_URL))
        request.setTransferTimeout(GEOLOCATION_TIMEOUT_MS)
        return self._nam.get(request)

    def start(self) -> None:
        if self._done:
            return
        expected_value = self.config.get('expected_value')
        field = self.config.get('field', 'city')

        if not expected_value:
            self._finish(AssertResult(
                success=False,
                message="Geolocation assert configuration missing expected_value",
                details={'field': field, 'expected_value': expected_value},
            ))
            return

        logger.debug(f"Querying {self.API_URL} for geolocation")
        self._reply = self._make_request()
        self._reply.finished.connect(self._on_finished)
        self._arm_timeout(GEOLOCATION_TIMEOUT_MS + 2_000)

    def _on_finished(self) -> None:
        if self._done:
            return
        reply = self._reply
        if reply is None:
            self._finish(AssertResult(
                success=False,
                message="Geolocation check FAILED: internal error (no reply)",
                details={},
            ))
            return

        field = self.config.get('field', 'city')
        expected_value = self.config.get('expected_value')

        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                err = reply.errorString()
                message = f"Geolocation check FAILED: Network error: {err}"
                logger.error(message)
                self._finish(AssertResult(
                    success=False, message=message,
                    details={'error': err},
                ))
                return

            body = bytes(reply.readAll()).decode('utf-8', errors='replace')
            try:
                import json as _json
                data = _json.loads(body)
            except ValueError as e:
                message = f"Geolocation check FAILED: Invalid JSON: {e}"
                logger.error(message)
                self._finish(AssertResult(
                    success=False, message=message,
                    details={'error': str(e)},
                ))
                return

            if data.get('status') != 'success':
                error_message = data.get('message', 'Unknown error')
                message = f"Geolocation check FAILED: API error: {error_message}"
                logger.error(message)
                self._finish(AssertResult(
                    success=False, message=message,
                    details={'error': error_message},
                ))
                return

            actual_value = data.get(field, '')
            public_ip = data.get('query', 'unknown')
            logger.info(f"Detected location: {field}='{actual_value}' (IP: {public_ip})")

            details = {
                'field': field,
                'expected': expected_value,
                'actual': actual_value,
                'ip': public_ip,
                'full_location': {
                    'city': data.get('city'),
                    'region': data.get('regionName'),
                    'country': data.get('country'),
                },
            }
            if expected_value.lower() in actual_value.lower():
                message = (f"Geolocation check PASSED: {field}='{actual_value}' "
                           f"matches expected '{expected_value}'")
                logger.info(message)
                self._finish(AssertResult(True, message, details))
            else:
                message = (f"Geolocation check FAILED: {field}='{actual_value}' "
                           f"does not match expected '{expected_value}'")
                logger.warning(message)
                self._finish(AssertResult(False, message, details))
        finally:
            reply.deleteLater()

    def _on_timeout(self) -> None:
        if self._done:
            return
        if self._reply:
            self._reply.abort()
        message = "Geolocation check FAILED: timed out"
        logger.error(message)
        self._finish(AssertResult(
            success=False, message=message,
            details={'error': 'timeout'},
        ))


class AsyncPingAssert(_AsyncAssertBase):
    """Non-blocking ping using QProcess."""

    def __init__(self, config: Dict[str, Any], parent: Optional[QObject] = None):
        super().__init__(config, parent)
        self._proc: Optional[QProcess] = None

    def _make_process(self) -> QProcess:
        return QProcess(self)

    def start(self) -> None:
        if self._done:
            return
        host = self.config.get('host')
        timeout = self.config.get('timeout_seconds', 5)

        if not host:
            self._finish(AssertResult(
                success=False,
                message="Ping assert configuration missing 'host'",
                details={'host': host},
            ))
            return

        self._proc = self._make_process()
        self._proc.finished.connect(self._on_finished)
        self._proc.errorOccurred.connect(self._on_error)
        self._arm_timeout(int((timeout + PING_TIMEOUT_EXTRA_S) * 1000))
        self._proc.start('ping', ['-c', '1', '-W', str(timeout), host])

    def _on_finished(self, exit_code: int, _exit_status) -> None:
        if self._done:
            return
        host = self.config.get('host')
        proc = self._proc
        stdout = bytes(proc.readAllStandardOutput()).decode('utf-8', errors='replace') if proc else ''

        if exit_code == 0:
            rtt_match = re.search(r'time[=<]([\d.]+)\s*ms', stdout)
            rtt = rtt_match.group(1) if rtt_match else "?"
            message = f"Ping check PASSED: {host} reachable ({rtt}ms)"
            logger.info(message)
            self._finish(AssertResult(
                success=True, message=message,
                details={'host': host, 'rtt_ms': rtt},
            ))
        else:
            message = f"Ping check FAILED: {host} unreachable"
            logger.warning(message)
            self._finish(AssertResult(
                success=False, message=message,
                details={'host': host},
            ))

    def _on_error(self, _err) -> None:
        if self._done:
            return
        host = self.config.get('host')
        msg = self._proc.errorString() if self._proc else 'unknown'
        message = f"Ping check FAILED: {msg}"
        logger.error(message)
        self._finish(AssertResult(
            success=False, message=message,
            details={'host': host, 'error': msg},
        ))

    def _on_timeout(self) -> None:
        if self._done:
            return
        host = self.config.get('host')
        timeout = self.config.get('timeout_seconds', 5)
        if self._proc and self._proc.state() != QProcess.ProcessState.NotRunning:
            self._proc.kill()
        message = f"Ping check FAILED: {host} timed out after {timeout}s"
        logger.error(message)
        self._finish(AssertResult(
            success=False, message=message,
            details={'host': host, 'timeout': timeout},
        ))


def create_async_assert(assert_config: Dict[str, Any],
                        parent: Optional[QObject] = None) -> _AsyncAssertBase:
    """Factory for AsyncAssert instances. Mirrors `create_assert`."""
    assert_type = assert_config.get('type')
    if assert_type == 'dns_lookup':
        return AsyncDNSLookupAssert(assert_config, parent=parent)
    elif assert_type == 'geolocation':
        return AsyncGeolocationAssert(assert_config, parent=parent)
    elif assert_type == 'ping':
        return AsyncPingAssert(assert_config, parent=parent)
    else:
        raise ValueError(f"Unknown assert type: {assert_type}")
