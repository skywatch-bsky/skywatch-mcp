# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_http_client():
    """Fixture to provide a properly mocked httpx AsyncClient"""
    with patch("skywatch_mcp.tools.domain.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None
        yield mock_client, mock_client_class


@pytest.fixture
def mock_dns_resolver():
    """Fixture to provide a properly mocked dns async resolver"""
    with patch("skywatch_mcp.tools.domain.dns.asyncresolver.Resolver") as mock_resolver_class:
        mock_resolver = AsyncMock()
        mock_resolver_class.return_value = mock_resolver
        yield mock_resolver, mock_resolver_class


class TestDomainCheck:
    """Test domain_check tool verifies all 7 DNS record types (AC1.3) and uses async resolver (AC3.2)"""

    @pytest.mark.asyncio
    async def test_domain_check_resolves_all_record_types(
        self, mock_dns_resolver, mock_http_client
    ):
        """domain_check should resolve A, AAAA, NS, MX, TXT, CNAME, SOA records"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_client.head.return_value = mock_response

        class MockARecord:
            def __str__(self):
                return "192.0.2.1"

        class MockAAAARecord:
            def __str__(self):
                return "2001:db8::1"

        class MockNSRecord:
            def __str__(self):
                return "ns1.example.com."

        class MockMXRecord:
            def __init__(self):
                self.exchange = "mail.example.com."
                self.preference = 10

        class MockTXTRecord:
            strings = [b"v=spf1 include:_spf.example.com ~all"]

        class MockCNAMERecord:
            def __str__(self):
                return "alias.example.com."

        class MockSOARecord:
            def __init__(self):
                self.mname = "ns1.example.com."
                self.rname = "hostmaster.example.com."
                self.serial = 2024010101
                self.refresh = 10800
                self.retry = 3600
                self.expire = 604800
                self.minimum = 86400

        mock_resolver.resolve.side_effect = [
            [MockARecord()],
            [MockAAAARecord()],
            [MockNSRecord()],
            [MockMXRecord()],
            [MockTXTRecord()],
            [MockCNAMERecord()],
            [MockSOARecord()],
        ]

        from skywatch_mcp.tools.domain import domain_check

        result = await domain_check("example.com")

        data = json.loads(result)
        assert data["domain"] == "example.com"
        assert data["resolves"] is True
        assert "192.0.2.1" in data["records"]["a"]
        assert "2001:db8::1" in data["records"]["aaaa"]
        assert "ns1.example.com." in data["records"]["ns"]
        assert len(data["records"]["mx"]) == 1
        assert data["records"]["mx"][0]["exchange"] == "mail.example.com."
        assert data["records"]["mx"][0]["priority"] == 10
        assert len(data["records"]["txt"]) == 1
        assert "v=spf1 include:_spf.example.com ~all" in data["records"]["txt"][0]
        assert "alias.example.com." in data["records"]["cname"]
        assert data["records"]["soa"] is not None
        assert data["records"]["soa"]["serial"] == 2024010101

    @pytest.mark.asyncio
    async def test_domain_check_resolves_false_when_no_a_records(
        self, mock_dns_resolver, mock_http_client
    ):
        """domain_check should return resolves=false when no A or AAAA records"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_client.head.return_value = mock_response

        mock_resolver.resolve.side_effect = [
            Exception("no A records"),
            Exception("no AAAA records"),
            [],
            [],
            [],
            [],
            [],
        ]

        from skywatch_mcp.tools.domain import domain_check

        result = await domain_check("nxdomain.example.com")

        data = json.loads(result)
        assert data["resolves"] is False

    @pytest.mark.asyncio
    async def test_domain_check_http_status_included(self, mock_dns_resolver, mock_http_client):
        """domain_check should include HTTP status if available"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        class MockARecord:
            def __str__(self):
                return "192.0.2.1"

        mock_resolver.resolve.side_effect = [
            [MockARecord()],
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_client.head.return_value = mock_response

        from skywatch_mcp.tools.domain import domain_check

        result = await domain_check("example.com")

        data = json.loads(result)
        assert data["http"] is not None
        assert data["http"]["status"] == 200
        assert data["http"]["statusText"] == "OK"

    @pytest.mark.asyncio
    async def test_domain_check_http_status_none_on_error(
        self, mock_dns_resolver, mock_http_client
    ):
        """domain_check should set http=None if HTTP check fails"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        class MockARecord:
            def __str__(self):
                return "192.0.2.1"

        mock_resolver.resolve.side_effect = [
            [MockARecord()],
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        mock_client.head.side_effect = Exception("Connection refused")

        from skywatch_mcp.tools.domain import domain_check

        result = await domain_check("example.com")

        data = json.loads(result)
        assert data["http"] is None

    @pytest.mark.asyncio
    async def test_domain_check_uses_async_resolver(self, mock_dns_resolver, mock_http_client):
        """domain_check should use dnspython's async resolver (AC3.2)"""
        mock_resolver, mock_resolver_class = mock_dns_resolver
        mock_client, _ = mock_http_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_client.head.return_value = mock_response

        mock_resolver.resolve.side_effect = [
            [],
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        from skywatch_mcp.tools.domain import domain_check

        await domain_check("example.com")

        # Verify async resolver was instantiated and used
        mock_resolver_class.assert_called_once()
        # Verify resolve was called 7 times (once per record type)
        assert mock_resolver.resolve.call_count == 7

    @pytest.mark.asyncio
    async def test_domain_check_handles_dns_resolution_exception(
        self, mock_dns_resolver, mock_http_client
    ):
        """domain_check should handle DNS resolution errors gracefully"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        # Simulate DNS error on first resolve
        mock_resolver.resolve.side_effect = Exception("DNS resolution failed")

        from skywatch_mcp.tools.domain import domain_check

        with pytest.raises(ValueError):
            await domain_check("example.com")

    @pytest.mark.asyncio
    async def test_domain_check_empty_results_handled_correctly(
        self, mock_dns_resolver, mock_http_client
    ):
        """domain_check should handle empty DNS results for missing record types"""
        mock_resolver, _ = mock_dns_resolver
        mock_client, _ = mock_http_client

        class MockARecord:
            def __str__(self):
                return "192.0.2.1"

        # Only A record exists, all others return empty
        mock_resolver.resolve.side_effect = [
            [MockARecord()],
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.reason_phrase = "OK"
        mock_client.head.return_value = mock_response

        from skywatch_mcp.tools.domain import domain_check

        result = await domain_check("example.com")

        data = json.loads(result)
        assert len(data["records"]["a"]) == 1
        assert len(data["records"]["aaaa"]) == 0
        assert len(data["records"]["ns"]) == 0
        assert len(data["records"]["mx"]) == 0
        assert len(data["records"]["txt"]) == 0
        assert len(data["records"]["cname"]) == 0
        assert data["records"]["soa"] is None
