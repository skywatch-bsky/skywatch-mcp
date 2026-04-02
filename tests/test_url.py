# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


@pytest.fixture
def mock_http_client():
    """Fixture to provide a properly mocked httpx AsyncClient"""
    with patch("skywatch_mcp.tools.url.httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client_class.return_value.__aexit__.return_value = None
        yield mock_client, mock_client_class


class TestURLExpand:
    """Test url_expand tool verifies AC1.5, AC3.3, and AC3.5"""

    @pytest.mark.asyncio
    async def test_url_expand_single_hop_no_redirect(self, mock_http_client):
        """url_expand should handle URL with no redirect (200 status)"""
        mock_client, _ = mock_http_client

        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        mock_client.head.return_value = response

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["originalUrl"] == "https://example.com"
        assert data["finalUrl"] == "https://example.com"
        assert data["hopCount"] == 1
        assert len(data["hops"]) == 1
        assert data["hops"][0]["url"] == "https://example.com"
        assert data["hops"][0]["statusCode"] == 200
        assert data["hops"][0]["location"] is None
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_url_expand_follow_redirect_chain(self, mock_http_client):
        """url_expand should follow redirect chain (301 → 302 → 200)"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 301
        response1.headers = {"location": "https://redirect1.example.com/path"}

        response2 = MagicMock()
        response2.status_code = 302
        response2.headers = {"location": "https://final.example.com"}

        response3 = MagicMock()
        response3.status_code = 200
        response3.headers = {}

        mock_client.head.side_effect = [response1, response2, response3]

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://short.example.com")
        data = json.loads(result)

        assert data["originalUrl"] == "https://short.example.com"
        assert data["finalUrl"] == "https://final.example.com"
        assert data["hopCount"] == 3
        assert len(data["hops"]) == 3
        assert data["hops"][0]["statusCode"] == 301
        assert data["hops"][1]["statusCode"] == 302
        assert data["hops"][2]["statusCode"] == 200
        assert "error" not in data

    @pytest.mark.asyncio
    async def test_url_expand_identifies_shortener(self, mock_http_client):
        """url_expand should identify known URL shorteners"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 301
        response1.headers = {"location": "https://example.com/page"}

        response2 = MagicMock()
        response2.status_code = 200
        response2.headers = {}

        mock_client.head.side_effect = [response1, response2]

        from skywatch_mcp.tools.url import url_expand

        # Use a known shortener domain
        result = await url_expand("https://bit.ly/abc123")
        data = json.loads(result)

        # Verify first hop is marked as shortener
        assert data["hops"][0]["isShortener"] is True

    @pytest.mark.asyncio
    async def test_url_expand_max_redirects_exceeded(self, mock_http_client):
        """url_expand should return error when max 15 hops exceeded"""
        mock_client, _ = mock_http_client

        # Create 15 redirect responses (all 301)
        responses = []
        for i in range(15):
            response = MagicMock()
            response.status_code = 301
            response.headers = {"location": f"https://example.com/hop{i + 1}"}
            responses.append(response)

        mock_client.head.side_effect = responses

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["hopCount"] == 15
        assert "error" in data
        assert data["error"] == "Max redirects exceeded"

    @pytest.mark.asyncio
    async def test_url_expand_timeout_stops_chain(self, mock_http_client):
        """url_expand should record statusCode=0 on timeout and stop (AC3.5)"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 301
        response1.headers = {"location": "https://example.com/page"}

        mock_client.head.side_effect = [
            response1,
            httpx.TimeoutException("Request timed out"),
        ]

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["hopCount"] == 2
        assert data["hops"][0]["statusCode"] == 301
        assert data["hops"][1]["statusCode"] == 0
        assert data["hops"][1]["location"] is None

    @pytest.mark.asyncio
    async def test_url_expand_uses_async_client_with_no_follow(self, mock_http_client):
        """url_expand should use httpx AsyncClient with follow_redirects=False (AC3.3)"""
        mock_client, mock_client_class = mock_http_client

        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        mock_client.head.return_value = response

        from skywatch_mcp.tools.url import url_expand

        await url_expand("https://example.com")

        # Verify AsyncClient was instantiated with correct parameters
        mock_client_class.assert_called_once_with(timeout=5.0, follow_redirects=False)

    @pytest.mark.asyncio
    async def test_url_expand_handles_client_exception(self, mock_http_client):
        """url_expand should handle exception when client.head() raises"""
        mock_client, _ = mock_http_client

        # Simulate a general exception (not timeout) during head request
        mock_client.head.side_effect = [
            Exception("Connection reset"),
        ]

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        # Should have recorded the error with statusCode=0
        assert data["hopCount"] == 1
        assert data["hops"][0]["statusCode"] == 0
        assert data["hops"][0]["location"] is None

    @pytest.mark.asyncio
    async def test_url_expand_stops_on_non_redirect_status(self, mock_http_client):
        """url_expand should stop following when receiving non-3xx status"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 404
        response1.headers = {}

        mock_client.head.return_value = response1

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["hopCount"] == 1
        assert data["finalUrl"] == "https://example.com"
        assert data["hops"][0]["statusCode"] == 404

    @pytest.mark.asyncio
    async def test_url_expand_relative_redirect(self, mock_http_client):
        """url_expand should resolve relative redirects with urljoin"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 301
        # Relative redirect
        response1.headers = {"location": "/final-page"}

        response2 = MagicMock()
        response2.status_code = 200
        response2.headers = {}

        mock_client.head.side_effect = [response1, response2]

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com/original")
        data = json.loads(result)

        # urljoin should resolve /final-page relative to https://example.com/original
        assert data["hops"][0]["location"] == "https://example.com/final-page"
        assert data["hopCount"] == 2

    @pytest.mark.asyncio
    async def test_url_expand_300_status_redirects(self, mock_http_client):
        """url_expand should follow 3xx status codes (300-399)"""
        mock_client, _ = mock_http_client

        response1 = MagicMock()
        response1.status_code = 300  # Multiple choices
        response1.headers = {"location": "https://example.com/choice1"}

        response2 = MagicMock()
        response2.status_code = 307  # Temporary redirect
        response2.headers = {"location": "https://example.com/final"}

        response3 = MagicMock()
        response3.status_code = 200
        response3.headers = {}

        mock_client.head.side_effect = [response1, response2, response3]

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["hopCount"] == 3
        assert data["hops"][0]["statusCode"] == 300
        assert data["hops"][1]["statusCode"] == 307

    @pytest.mark.asyncio
    async def test_url_expand_non_shortener_identified_correctly(self, mock_http_client):
        """url_expand should not mark regular domains as shorteners"""
        mock_client, _ = mock_http_client

        response = MagicMock()
        response.status_code = 200
        response.headers = {}
        mock_client.head.return_value = response

        from skywatch_mcp.tools.url import url_expand

        result = await url_expand("https://example.com")
        data = json.loads(result)

        assert data["hops"][0]["isShortener"] is False
