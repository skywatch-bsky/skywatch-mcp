"""Test response JSON shapes match expected TS output structure."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skywatch_mcp.tools import clickhouse, content, cosharing, domain, ip, url, whois


class TestResponseShapes:
    """Verify response JSON structures match TS output."""

    @pytest.mark.asyncio
    async def test_clickhouse_query_response_shape(self) -> None:
        """Test clickhouse_query returns {columns: [...], rows: [...]}."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.columns = [
                {"name": "id", "type": "Int32"},
                {"name": "value", "type": "String"},
            ]
            mock_result.rows = [{"id": 1, "value": "test"}]

            mock_client = MagicMock()
            mock_client.query = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await clickhouse.clickhouse_query("SELECT * FROM test LIMIT 1")
            result = json.loads(result_json)

            assert "columns" in result
            assert "rows" in result
            assert isinstance(result["columns"], list)
            assert isinstance(result["rows"], list)

    @pytest.mark.asyncio
    async def test_clickhouse_schema_response_shape(self) -> None:
        """Test clickhouse_schema returns {columns: [...], rows: [...]}."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.columns = [
                {"name": "table", "type": "String"},
                {"name": "name", "type": "String"},
                {"name": "type", "type": "String"},
            ]
            mock_result.rows = [{"table": "test_table", "name": "id", "type": "Int32"}]

            mock_client = MagicMock()
            mock_client.get_schema = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await clickhouse.clickhouse_schema()
            result = json.loads(result_json)

            assert "columns" in result
            assert "rows" in result
            assert isinstance(result["columns"], list)
            assert isinstance(result["rows"], list)

    @pytest.mark.asyncio
    async def test_ip_lookup_response_shape(self) -> None:
        """Test ip_lookup returns {ip: ..., geo: {...}, network: {...}, flags: {...}}."""
        with patch("skywatch_mcp.tools.ip.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "query": "1.1.1.1",
                "country": "US",
                "city": "Los Angeles",
                "isp": "Cloudflare",
                "org": "Cloudflare",
            }
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            result_json = await ip.ip_lookup("1.1.1.1")
            result = json.loads(result_json)

            assert "ip" in result
            assert "geo" in result
            assert "network" in result
            assert "flags" in result
            assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_domain_check_response_shape(self) -> None:
        """Test domain_check returns {domain: ..., resolves: ..., records: {...}, http: ...}."""
        with (
            patch("skywatch_mcp.tools.domain._resolve_dns_records") as mock_resolve,
            patch("skywatch_mcp.tools.domain._check_http_status") as mock_http,
        ):
            mock_resolve.return_value = {
                "a": ["1.1.1.1"],
                "aaaa": [],
                "ns": [],
                "mx": [],
                "txt": [],
                "cname": [],
                "soa": None,
            }
            mock_http.return_value = {"status": 200, "statusText": "OK"}

            result_json = await domain.domain_check("example.com")
            result = json.loads(result_json)

            assert "domain" in result
            assert "resolves" in result
            assert "records" in result
            assert "http" in result
            assert result["domain"] == "example.com"
            assert isinstance(result["resolves"], bool)

    @pytest.mark.asyncio
    async def test_url_expand_response_shape(self) -> None:
        """Test url_expand returns {originalUrl: ..., finalUrl: ..., hops: [...], hopCount: ...}."""
        with patch("skywatch_mcp.tools.url.httpx.AsyncClient") as mock_client_class:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.url = "https://example.com"
            mock_response.history = []
            mock_client = AsyncMock()
            mock_client.head = AsyncMock(return_value=mock_response)
            mock_client.__aenter__.return_value = mock_client
            mock_client_class.return_value = mock_client

            result_json = await url.url_expand("https://example.com")
            result = json.loads(result_json)

            assert "originalUrl" in result
            assert "finalUrl" in result
            assert "hops" in result
            assert "hopCount" in result
            assert isinstance(result["hops"], list)
            assert isinstance(result["hopCount"], int)

    @pytest.mark.asyncio
    async def test_content_similarity_response_shape(self) -> None:
        """Test content_similarity returns list of {user: ..., handle: ..., text: ..., score: ..., created_at: ...}."""
        with patch("skywatch_mcp.tools.content.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.rows = [
                {
                    "user": "did:plc:abc123",
                    "handle": "user1",
                    "text": "similar text",
                    "score": 0.1,
                    "created_at": "2026-04-01",
                }
            ]

            mock_client = MagicMock()
            mock_client.query_trusted = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await content.content_similarity("test text")
            result = json.loads(result_json)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert "user" in item
            assert "handle" in item
            assert "text" in item
            assert "score" in item
            assert "created_at" in item

    @pytest.mark.asyncio
    async def test_cosharing_clusters_response_shape(self) -> None:
        """Test cosharing_clusters returns {query: ..., rows: [...], count: ...}."""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.rows = [
                {
                    "cluster_id": "cluster-1",
                    "run_date": "2026-04-01",
                    "member_count": 5,
                }
            ]

            mock_client = MagicMock()
            mock_client.query_trusted = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await cosharing.cosharing_clusters()
            result = json.loads(result_json)

            assert "query" in result
            assert "rows" in result
            assert "count" in result
            assert isinstance(result["rows"], list)
            assert isinstance(result["count"], int)

    @pytest.mark.asyncio
    async def test_error_handling_raises_value_error(self) -> None:
        """Test that tool handlers raise ValueError on error, which FastMCP converts to isError response."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client:
            mock_client.return_value.query.side_effect = Exception("DB error")

            with pytest.raises(ValueError, match="DB error"):
                await clickhouse.clickhouse_query("SELECT * FROM test LIMIT 1")

    @pytest.mark.asyncio
    async def test_whois_lookup_response_shape(self) -> None:
        """Test whois_lookup returns JSON with registrar and domain info."""
        with (
            patch("skywatch_mcp.tools.whois.whois_module.whois") as mock_whois,
            patch("skywatch_mcp.tools.whois.parse_whois_response") as mock_parse,
        ):
            mock_whois_obj = MagicMock()
            mock_whois_obj.text = "some whois text"
            mock_whois.return_value = mock_whois_obj

            mock_parsed = MagicMock()
            mock_parsed_dict = {
                "registrar": "Example Registrar",
                "creation_date": "2020-01-01T00:00:00Z",
                "expiration_date": "2025-01-01T00:00:00Z",
                "nameservers": ["ns1.example.com", "ns2.example.com"],
                "domain_age": 1826,
                "raw_text": "some whois text",
            }
            mock_parse.return_value = mock_parsed

            # Make asdict work with the mock
            with patch("skywatch_mcp.tools.whois.asdict", return_value=mock_parsed_dict):
                result_json = await whois.whois_lookup("example.com")
                result = json.loads(result_json)

                assert isinstance(result, dict)
                assert "registrar" in result
                assert "creation_date" in result
                assert "expiration_date" in result
                assert "nameservers" in result
                assert "domain_age" in result
                assert "raw_text" in result
