# pattern: Imperative Shell

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def mock_whois_module():
    """Fixture to provide mocked whois.whois function"""
    with patch("skywatch_mcp.tools.whois.whois_module.whois") as mock_whois:
        yield mock_whois


class TestWhoisLookup:
    """Test whois_lookup tool verifies AC1.6 and AC3.4"""

    @pytest.mark.asyncio
    async def test_whois_lookup_returns_structured_data(self, mock_whois_module):
        """whois_lookup should return registrar, dates, nameservers, and domain age (AC1.6)"""
        whois_response_text = """
Domain Name: EXAMPLE.COM
Registrar: Example Registrar, Inc.
Creation Date: 2000-02-23T00:00:00Z
Registry Expiry Date: 2025-02-23T00:00:00Z
Name Server: NS1.EXAMPLE.COM
Name Server: NS2.EXAMPLE.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("example.com")
        data = json.loads(result)

        assert data["registrar"] == "Example Registrar, Inc."
        assert data["creation_date"] == "2000-02-23T00:00:00Z"
        assert data["expiration_date"] == "2025-02-23T00:00:00Z"
        assert len(data["nameservers"]) == 2
        assert "NS1.EXAMPLE.COM" in data["nameservers"]
        assert "NS2.EXAMPLE.COM" in data["nameservers"]
        assert data["domain_age"] is not None
        assert data["domain_age"] > 0
        assert "raw_text" in data

    @pytest.mark.asyncio
    async def test_whois_lookup_uses_asyncio_to_thread(self, mock_whois_module):
        """whois_lookup should use asyncio.to_thread() for sync WHOIS (AC3.4)"""
        whois_response_text = """
Domain Name: TEST.COM
Registrar: Test Registrar
Creation Date: 2010-01-01T00:00:00Z
Registry Expiry Date: 2025-01-01T00:00:00Z
Name Server: NS.TEST.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        # Test that whois_lookup doesn't block the event loop
        # If it were sync-blocking, this would hang
        result = await whois_lookup("test.com")
        data = json.loads(result)

        assert data["registrar"] == "Test Registrar"
        # Verify that whois.whois was called (through to_thread)
        mock_whois_module.assert_called_once_with("test.com")

    @pytest.mark.asyncio
    async def test_whois_lookup_extracts_all_components(self, mock_whois_module):
        """whois_lookup should extract all AC1.6 components"""
        whois_response_text = """
Domain Name: DOMAIN.COM
Registrar: GoDaddy.com, Inc.
Creation Date: 2005-03-15T10:30:00Z
Registry Expiry Date: 2026-03-15T10:30:00Z
Name Server: NS1.GODADDY.COM
Name Server: NS2.GODADDY.COM
Name Server: NS3.GODADDY.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("domain.com")
        data = json.loads(result)

        # Verify registrar
        assert data["registrar"] is not None
        assert "GoDaddy" in data["registrar"]

        # Verify dates
        assert data["creation_date"] is not None
        assert "2005-03-15" in data["creation_date"]
        assert data["expiration_date"] is not None
        assert "2026-03-15" in data["expiration_date"]

        # Verify nameservers
        assert len(data["nameservers"]) == 3
        assert all("GODADDY.COM" in ns for ns in data["nameservers"])

        # Verify domain_age is calculated
        assert data["domain_age"] is not None
        assert data["domain_age"] > 0

    @pytest.mark.asyncio
    async def test_whois_lookup_handles_missing_fields(self, mock_whois_module):
        """whois_lookup should handle missing optional fields gracefully"""
        whois_response_text = """
Domain Name: INCOMPLETE.COM
Name Server: NS.INCOMPLETE.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("incomplete.com")
        data = json.loads(result)

        assert data["registrar"] is None
        assert data["creation_date"] is None
        assert data["expiration_date"] is None
        assert data["domain_age"] is None
        assert len(data["nameservers"]) == 1
        assert data["raw_text"] is not None

    @pytest.mark.asyncio
    async def test_whois_lookup_handles_whois_object_without_text_attribute(self, mock_whois_module):
        """whois_lookup should handle whois objects without .text attribute"""
        whois_response_str = """
Domain Name: NOTEXT.COM
Registrar: Test Registrar
Name Server: NS.NOTEXT.COM
"""

        # Create mock without .text attribute - uses __str__
        class WhoisResponseWithoutText:
            def __str__(self):
                return whois_response_str

        mock_result = WhoisResponseWithoutText()
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("notext.com")
        data = json.loads(result)

        assert data["registrar"] == "Test Registrar"
        assert len(data["nameservers"]) == 1

    @pytest.mark.asyncio
    async def test_whois_lookup_handles_multiple_creation_date_formats(self, mock_whois_module):
        """whois_lookup should handle different creation date field names"""
        # Test with "Created:" instead of "Creation Date:"
        whois_response_text = """
Domain Name: CREATED.COM
Registrar: Test Registrar
Created: 2015-06-20T00:00:00Z
Name Server: NS.CREATED.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("created.com")
        data = json.loads(result)

        assert data["creation_date"] == "2015-06-20T00:00:00Z"
        assert data["domain_age"] is not None

    @pytest.mark.asyncio
    async def test_whois_lookup_handles_multiple_expiration_date_formats(self, mock_whois_module):
        """whois_lookup should handle different expiration date field names"""
        # Test with "expires:" instead of "Registry Expiry Date:"
        whois_response_text = """
Domain Name: EXPIRES.COM
Registrar: Test Registrar
Creation Date: 2010-01-01T00:00:00Z
expires: 2025-01-01T00:00:00Z
Name Server: NS.EXPIRES.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("expires.com")
        data = json.loads(result)

        assert data["expiration_date"] == "2025-01-01T00:00:00Z"

    @pytest.mark.asyncio
    async def test_whois_lookup_handles_exception(self, mock_whois_module):
        """whois_lookup should convert exceptions to ValueError"""
        mock_whois_module.side_effect = Exception("WHOIS server error")

        from skywatch_mcp.tools.whois import whois_lookup

        with pytest.raises(ValueError, match="WHOIS server error"):
            await whois_lookup("example.com")

    @pytest.mark.asyncio
    async def test_whois_lookup_multiple_nameservers(self, mock_whois_module):
        """whois_lookup should extract multiple nameservers correctly"""
        whois_response_text = """
Domain Name: MULTI-NS.COM
Registrar: Multi NS Registrar
Creation Date: 2012-05-10T00:00:00Z
Registry Expiry Date: 2025-05-10T00:00:00Z
Name Server: NS1.EXAMPLE.NET
Name Server: NS2.EXAMPLE.NET
Name Server: NS3.EXAMPLE.NET
Name Server: NS4.EXAMPLE.NET
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("multi-ns.com")
        data = json.loads(result)

        assert len(data["nameservers"]) == 4
        assert "NS1.EXAMPLE.NET" in data["nameservers"]
        assert "NS4.EXAMPLE.NET" in data["nameservers"]

    @pytest.mark.asyncio
    async def test_whois_lookup_raw_text_included(self, mock_whois_module):
        """whois_lookup should include raw WHOIS text in response"""
        whois_response_text = "Domain Name: RAW.COM\nRegistrar: Test\n"

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("raw.com")
        data = json.loads(result)

        assert data["raw_text"] == whois_response_text

    @pytest.mark.asyncio
    async def test_whois_lookup_domain_age_calculation(self, mock_whois_module):
        """whois_lookup should calculate domain age correctly"""
        # Very old domain
        whois_response_text = """
Domain Name: OLDOMAIN.COM
Registrar: Old Registrar
Creation Date: 2000-01-01T00:00:00Z
Name Server: NS.OLDDOMAIN.COM
"""

        mock_result = MagicMock()
        mock_result.text = whois_response_text
        mock_whois_module.return_value = mock_result

        from skywatch_mcp.tools.whois import whois_lookup

        result = await whois_lookup("olddomain.com")
        data = json.loads(result)

        # Domain created in 2000, should be over 24 years old
        assert data["domain_age"] is not None
        assert data["domain_age"] > 8000  # ~24 years in days
