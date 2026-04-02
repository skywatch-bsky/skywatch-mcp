# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


@pytest.fixture
def mock_http_client():
    """Fixture to provide a properly mocked httpx AsyncClient"""
    with patch("skywatch_mcp.tools.ip.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None
        yield mock_client, mock_client_class


class TestValidateIPAddress:
    """Test _validate_ip_address function"""

    def test_validate_valid_ipv4(self):
        """_validate_ip_address should accept valid IPv4 addresses"""
        from skywatch_mcp.tools.ip import _validate_ip_address

        assert _validate_ip_address("192.168.1.1") is True
        assert _validate_ip_address("0.0.0.0") is True
        assert _validate_ip_address("255.255.255.255") is True
        assert _validate_ip_address("8.8.8.8") is True

    def test_validate_invalid_ipv4(self):
        """_validate_ip_address should reject invalid IPv4 addresses"""
        from skywatch_mcp.tools.ip import _validate_ip_address

        assert _validate_ip_address("256.1.1.1") is False
        assert _validate_ip_address("999.999.999.999") is False
        assert _validate_ip_address("192.168.1") is False
        assert _validate_ip_address("192.168.1.1.1") is False

    def test_validate_valid_ipv6(self):
        """_validate_ip_address should accept valid IPv6 addresses"""
        from skywatch_mcp.tools.ip import _validate_ip_address

        assert _validate_ip_address("::1") is True
        assert _validate_ip_address("2001:db8::1") is True
        assert _validate_ip_address("fe80::1") is True
        assert _validate_ip_address("::") is True

    def test_validate_invalid_ipv6(self):
        """_validate_ip_address should reject invalid IPv6 addresses"""
        from skywatch_mcp.tools.ip import _validate_ip_address

        assert _validate_ip_address(":::1") is False
        assert _validate_ip_address("not-an-ip") is False
        assert _validate_ip_address("192.168.1.1") is not _validate_ip_address("192.168.1.300")


class TestIPLookup:
    """Test ip_lookup tool verifies AC1.4 and AC3.3"""

    @pytest.mark.asyncio
    async def test_ip_lookup_returns_geo_network_flags(self, mock_http_client):
        """ip_lookup should return geo, network, and flags data for valid IP"""
        mock_client, _ = mock_http_client

        api_response = {
            "status": "success",
            "query": "8.8.8.8",
            "country": "United States",
            "countryCode": "US",
            "region": "CA",
            "regionName": "California",
            "city": "Mountain View",
            "zip": "94043",
            "lat": 37.4192,
            "lon": -122.0574,
            "timezone": "America/Los_Angeles",
            "isp": "Google LLC",
            "org": "Google LLC",
            "as": "AS15169",
            "asname": "GOOGLE",
            "mobile": False,
            "proxy": False,
            "hosting": True,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_client.get.return_value = mock_response

        from skywatch_mcp.tools.ip import ip_lookup

        result = await ip_lookup("8.8.8.8")

        data = json.loads(result)
        assert data["ip"] == "8.8.8.8"
        assert data["geo"]["country"] == "United States"
        assert data["geo"]["countryCode"] == "US"
        assert data["geo"]["city"] == "Mountain View"
        assert data["geo"]["lat"] == 37.4192
        assert data["geo"]["lon"] == -122.0574
        assert data["network"]["isp"] == "Google LLC"
        assert data["network"]["asn"] == "AS15169"
        assert data["flags"]["hosting"] is True
        assert data["flags"]["mobile"] is False
        assert data["flags"]["proxy"] is False

    @pytest.mark.asyncio
    async def test_ip_lookup_valid_ipv4(self, mock_http_client):
        """ip_lookup should accept valid IPv4 addresses"""
        mock_client, _ = mock_http_client

        api_response = {
            "status": "success",
            "query": "1.1.1.1",
            "country": "Australia",
            "countryCode": "AU",
            "region": "",
            "regionName": "",
            "city": "",
            "zip": "",
            "lat": -33.494,
            "lon": 143.2104,
            "timezone": "Australia/Sydney",
            "isp": "Cloudflare",
            "org": "Cloudflare Inc",
            "as": "AS13335",
            "asname": "CLOUDFLARENET",
            "mobile": False,
            "proxy": False,
            "hosting": True,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_client.get.return_value = mock_response

        from skywatch_mcp.tools.ip import ip_lookup

        result = await ip_lookup("1.1.1.1")
        data = json.loads(result)
        assert data["ip"] == "1.1.1.1"

    @pytest.mark.asyncio
    async def test_ip_lookup_valid_ipv6(self, mock_http_client):
        """ip_lookup should accept valid IPv6 addresses"""
        mock_client, _ = mock_http_client

        api_response = {
            "status": "success",
            "query": "2001:4860:4860::8888",
            "country": "United States",
            "countryCode": "US",
            "region": "CA",
            "regionName": "California",
            "city": "Mountain View",
            "zip": "",
            "lat": 37.4192,
            "lon": -122.0574,
            "timezone": "America/Los_Angeles",
            "isp": "Google LLC",
            "org": "Google LLC",
            "as": "AS15169",
            "asname": "GOOGLE",
            "mobile": False,
            "proxy": False,
            "hosting": True,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_client.get.return_value = mock_response

        from skywatch_mcp.tools.ip import ip_lookup

        result = await ip_lookup("2001:4860:4860::8888")
        data = json.loads(result)
        assert data["ip"] == "2001:4860:4860::8888"

    @pytest.mark.asyncio
    async def test_ip_lookup_rejects_invalid_ipv4(self, mock_http_client):
        """ip_lookup should reject invalid IPv4 addresses"""
        mock_client, _ = mock_http_client

        from skywatch_mcp.tools.ip import ip_lookup

        with pytest.raises(ValueError, match="Invalid IP address format"):
            await ip_lookup("999.999.999.999")

        with pytest.raises(ValueError, match="Invalid IP address format"):
            await ip_lookup("not-an-ip")

    @pytest.mark.asyncio
    async def test_ip_lookup_rejects_invalid_ipv6(self, mock_http_client):
        """ip_lookup should reject invalid IPv6 addresses"""
        from skywatch_mcp.tools.ip import ip_lookup

        with pytest.raises(ValueError, match="Invalid IP address format"):
            await ip_lookup(":::1")

    @pytest.mark.asyncio
    async def test_ip_lookup_handles_api_failure(self, mock_http_client):
        """ip_lookup should raise ValueError on API failure"""
        mock_client, _ = mock_http_client

        api_response = {
            "status": "fail",
            "message": "invalid query",
            "query": "",
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_client.get.return_value = mock_response

        from skywatch_mcp.tools.ip import ip_lookup

        with pytest.raises(ValueError, match="invalid query"):
            await ip_lookup("192.0.2.1")

    @pytest.mark.asyncio
    async def test_ip_lookup_handles_timeout(self, mock_http_client):
        """ip_lookup should handle timeout exceptions"""
        mock_client, _ = mock_http_client

        mock_client.get.side_effect = httpx.TimeoutException("Request timed out")

        from skywatch_mcp.tools.ip import ip_lookup

        with pytest.raises(ValueError, match="Request timed out"):
            await ip_lookup("8.8.8.8")

    @pytest.mark.asyncio
    async def test_ip_lookup_uses_async_client(self, mock_http_client):
        """ip_lookup should use httpx AsyncClient (AC3.3)"""
        mock_client, mock_client_class = mock_http_client

        api_response = {
            "status": "success",
            "query": "8.8.8.8",
            "country": "United States",
            "countryCode": "US",
            "region": "",
            "regionName": "",
            "city": "",
            "zip": "",
            "lat": 0,
            "lon": 0,
            "timezone": "",
            "isp": "",
            "org": "",
            "as": "",
            "asname": "",
            "mobile": False,
            "proxy": False,
            "hosting": False,
        }

        mock_response = MagicMock()
        mock_response.json.return_value = api_response
        mock_client.get.return_value = mock_response

        from skywatch_mcp.tools.ip import ip_lookup

        await ip_lookup("8.8.8.8")

        # Verify AsyncClient was instantiated with correct timeout
        mock_client_class.assert_called_once_with(timeout=5.0)
        # Verify get was called with correct endpoint and params
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "8.8.8.8" in call_args[0][0]

    @pytest.mark.asyncio
    async def test_ip_lookup_handles_general_exception(self, mock_http_client):
        """ip_lookup should convert general exceptions to ValueError"""
        mock_client, _ = mock_http_client

        mock_client.get.side_effect = Exception("Network error")

        from skywatch_mcp.tools.ip import ip_lookup

        with pytest.raises(ValueError, match="Network error"):
            await ip_lookup("8.8.8.8")
