"""
Assert system for VPN health checking
"""
import logging
import socket
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any

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
    else:
        raise ValueError(f"Unknown assert type: {assert_type}")
