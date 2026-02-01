"""
Tests for Assert system
"""
import pytest
from unittest.mock import patch, MagicMock
import socket

from vpn_toggle.asserts import (
    VPNAssert,
    DNSLookupAssert,
    GeolocationAssert,
    AssertResult,
    create_assert
)


class TestDNSLookupAssert:
    """Test suite for DNSLookupAssert"""

    @patch('socket.gethostbyname')
    def test_dns_lookup_success_exact_match(self, mock_gethostbyname):
        """Test successful DNS lookup with exact IP match"""
        mock_gethostbyname.return_value = "100.64.1.1"

        assert_config = {
            'type': 'dns_lookup',
            'hostname': 'test.example.com',
            'expected_prefix': '100.64.1.1'
        }
        assert_obj = DNSLookupAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert '100.64.1.1' in result.message
        assert result.details['ip'] == '100.64.1.1'

    @patch('socket.gethostbyname')
    def test_dns_lookup_success_prefix_match(self, mock_gethostbyname):
        """Test successful DNS lookup with prefix match"""
        mock_gethostbyname.return_value = "100.64.5.27"

        assert_config = {
            'type': 'dns_lookup',
            'hostname': 'test.example.com',
            'expected_prefix': '100.'
        }
        assert_obj = DNSLookupAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert result.details['ip'] == '100.64.5.27'
        assert result.details['expected_prefix'] == '100.'

    @patch('socket.gethostbyname')
    def test_dns_lookup_failure_no_match(self, mock_gethostbyname):
        """Test DNS lookup failure when IP doesn't match prefix"""
        mock_gethostbyname.return_value = "192.168.1.1"

        assert_config = {
            'type': 'dns_lookup',
            'hostname': 'test.example.com',
            'expected_prefix': '100.'
        }
        assert_obj = DNSLookupAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'FAILED' in result.message
        assert result.details['ip'] == '192.168.1.1'

    @patch('socket.gethostbyname')
    def test_dns_lookup_failure_hostname_not_found(self, mock_gethostbyname):
        """Test DNS lookup failure when hostname doesn't resolve"""
        mock_gethostbyname.side_effect = socket.gaierror("Name or service not known")

        assert_config = {
            'type': 'dns_lookup',
            'hostname': 'nonexistent.example.com',
            'expected_prefix': '100.'
        }
        assert_obj = DNSLookupAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'Could not resolve' in result.message
        assert 'error' in result.details

    def test_dns_lookup_missing_configuration(self):
        """Test DNS lookup with missing configuration"""
        assert_config = {
            'type': 'dns_lookup',
            # Missing hostname and expected_prefix
        }
        assert_obj = DNSLookupAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'missing' in result.message.lower()

    @patch('socket.gethostbyname')
    def test_dns_lookup_partial_prefix(self, mock_gethostbyname):
        """Test DNS lookup with various partial prefix matches"""
        test_cases = [
            ("100.64.1.5", "100.", True),
            ("100.64.1.5", "100.64.", True),
            ("100.64.1.5", "100.64.1.", True),
            ("192.168.1.1", "10.", False),
            ("10.8.0.2", "10.8", True),
        ]

        for ip, prefix, should_succeed in test_cases:
            mock_gethostbyname.return_value = ip
            assert_config = {
                'type': 'dns_lookup',
                'hostname': 'test.example.com',
                'expected_prefix': prefix
            }
            assert_obj = DNSLookupAssert(assert_config)
            result = assert_obj.check()

            assert result.success == should_succeed, \
                f"Expected {should_succeed} for IP {ip} with prefix {prefix}"


class TestGeolocationAssert:
    """Test suite for GeolocationAssert"""

    @patch('requests.get')
    def test_geolocation_success_city_match(self, mock_get):
        """Test successful geolocation check with city match"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'Las Vegas',
            'regionName': 'Nevada',
            'country': 'United States',
            'query': '1.2.3.4'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Las Vegas'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert 'PASSED' in result.message
        assert result.details['actual'] == 'Las Vegas'
        assert result.details['ip'] == '1.2.3.4'

    @patch('requests.get')
    def test_geolocation_success_partial_match(self, mock_get):
        """Test geolocation with partial/case-insensitive match"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'Las Vegas',
            'regionName': 'Nevada',
            'country': 'United States',
            'query': '1.2.3.4'
        }
        mock_get.return_value = mock_response

        # Test case-insensitive match
        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'las vegas'  # lowercase
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True

        # Test partial match
        assert_config['expected_value'] = 'Vegas'
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True

    @patch('requests.get')
    def test_geolocation_success_region_match(self, mock_get):
        """Test geolocation check with region field"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'Los Angeles',
            'regionName': 'California',
            'country': 'United States',
            'query': '5.6.7.8'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'regionName',
            'expected_value': 'California'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert result.details['actual'] == 'California'

    @patch('requests.get')
    def test_geolocation_success_country_match(self, mock_get):
        """Test geolocation check with country field"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'London',
            'regionName': 'England',
            'country': 'United Kingdom',
            'query': '9.10.11.12'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'country',
            'expected_value': 'United Kingdom'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert result.details['actual'] == 'United Kingdom'

    @patch('requests.get')
    def test_geolocation_failure_no_match(self, mock_get):
        """Test geolocation failure when location doesn't match"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'New York',
            'regionName': 'New York',
            'country': 'United States',
            'query': '13.14.15.16'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Las Vegas'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'FAILED' in result.message
        assert result.details['actual'] == 'New York'
        assert result.details['expected'] == 'Las Vegas'

    @patch('requests.get')
    def test_geolocation_api_error(self, mock_get):
        """Test geolocation when API returns an error"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'fail',
            'message': 'invalid query'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Las Vegas'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'API error' in result.message

    @patch('requests.get')
    def test_geolocation_network_error(self, mock_get):
        """Test geolocation when network request fails"""
        import requests
        mock_get.side_effect = requests.RequestException("Connection timeout")

        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Las Vegas'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'Network error' in result.message

    def test_geolocation_missing_configuration(self):
        """Test geolocation with missing configuration"""
        assert_config = {
            'type': 'geolocation',
            'field': 'city'
            # Missing expected_value
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is False
        assert 'missing' in result.message.lower()

    @patch('requests.get')
    def test_geolocation_default_field(self, mock_get):
        """Test that geolocation defaults to 'city' field"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'Paris',
            'regionName': 'Île-de-France',
            'country': 'France',
            'query': '17.18.19.20'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            # No 'field' specified, should default to 'city'
            'expected_value': 'Paris'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        assert result.success is True
        assert result.details['field'] == 'city'

    @patch('requests.get')
    @patch('builtins.print')  # Mock print to verify location is printed
    def test_geolocation_prints_detected_location(self, mock_print, mock_get):
        """Test that geolocation prints detected location for user debugging"""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'success',
            'city': 'Tokyo',
            'regionName': 'Tokyo',
            'country': 'Japan',
            'query': '21.22.23.24'
        }
        mock_get.return_value = mock_response

        assert_config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Tokyo'
        }
        assert_obj = GeolocationAssert(assert_config)
        result = assert_obj.check()

        # Verify print was called with location info
        print_calls = [str(call) for call in mock_print.call_args_list]
        assert any('Tokyo' in call and 'Detected' in call for call in print_calls)


class TestAssertFactory:
    """Test suite for create_assert factory function"""

    def test_create_dns_lookup_assert(self):
        """Test creating DNS lookup assert via factory"""
        config = {
            'type': 'dns_lookup',
            'hostname': 'test.com',
            'expected_prefix': '10.'
        }
        assert_obj = create_assert(config)

        assert isinstance(assert_obj, DNSLookupAssert)
        assert assert_obj.config == config

    def test_create_geolocation_assert(self):
        """Test creating geolocation assert via factory"""
        config = {
            'type': 'geolocation',
            'field': 'city',
            'expected_value': 'Berlin'
        }
        assert_obj = create_assert(config)

        assert isinstance(assert_obj, GeolocationAssert)
        assert assert_obj.config == config

    def test_create_unknown_assert_type(self):
        """Test creating assert with unknown type raises ValueError"""
        config = {
            'type': 'unknown_type'
        }

        with pytest.raises(ValueError, match="Unknown assert type"):
            create_assert(config)

    def test_assert_get_description(self):
        """Test getting description from assert"""
        config = {
            'type': 'dns_lookup',
            'hostname': 'test.com',
            'expected_prefix': '10.',
            'description': 'Test DNS check'
        }
        assert_obj = create_assert(config)

        assert assert_obj.get_description() == 'Test DNS check'

    def test_assert_get_description_default(self):
        """Test getting default description when not provided"""
        config = {
            'type': 'dns_lookup',
            'hostname': 'test.com',
            'expected_prefix': '10.'
        }
        assert_obj = create_assert(config)

        description = assert_obj.get_description()
        assert 'DNSLookupAssert' in description
