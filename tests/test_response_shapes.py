import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from skywatch_mcp.tools import clickhouse, content, cosharing, domain, ip, url, whois


class TestResponseShapes:

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
        """Test clickhouse_schema returns {columns, rows, coverage, meta} for zero args."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.columns = [
                {"name": "table", "type": "String"},
                {"name": "name", "type": "String"},
                {"name": "type", "type": "String"},
            ]
            mock_result.rows = [{"table": "test_table", "name": "id", "type": "Int32"}]
            mock_result.query_id = "q-schema"
            mock_result.elapsed_ms = 5
            mock_result.coverage = {
                "tables_expected": 12,
                "tables_matched": 12,
                "tables_missing": [],
            }

            mock_client = MagicMock()
            mock_client.get_schema = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await clickhouse.clickhouse_schema()
            result = json.loads(result_json)

            assert "columns" in result
            assert "rows" in result
            assert result["coverage"]["tables_expected"] == 12
            assert result["meta"]["query_id"] == "q-schema"
            assert isinstance(result["columns"], list)
            assert isinstance(result["rows"], list)

    @pytest.mark.asyncio
    async def test_clickhouse_schema_compact_response_shape(self) -> None:
        """Table-scoped clickhouse_schema returns {table, columns, missing_fields, coverage, meta}."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.rows = [
                {"name": "AtUri", "type": "String"},
                {"name": "Cid", "type": "String"},
            ]
            mock_result.query_id = "q-c"
            mock_result.elapsed_ms = 3
            mock_result.coverage = {
                "tables_expected": 1,
                "tables_matched": 1,
                "tables_missing": [],
            }

            mock_client = MagicMock()
            mock_client.get_table_columns = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await clickhouse.clickhouse_schema(table="osprey_execution_results")
            result = json.loads(result_json)

            assert result["table"] == "default.osprey_execution_results"
            assert [c["name"] for c in result["columns"]] == ["AtUri", "Cid"]
            assert result["missing_fields"] == []
            assert result["coverage"] == {
                "tables_expected": 1,
                "tables_matched": 1,
                "tables_missing": [],
            }
            mock_client.get_table_columns.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_clickhouse_health_response_shape(self) -> None:
        """clickhouse_health returns {connected, server_version, meta}."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_client_func:
            mock_result = MagicMock()
            mock_result.rows = [{"connected": 1, "server_version": "24.8"}]
            mock_result.query_id = "q-h"
            mock_result.elapsed_ms = 1

            mock_client = MagicMock()
            mock_client.query_trusted = AsyncMock(return_value=mock_result)
            mock_client_func.return_value = mock_client

            result_json = await clickhouse.clickhouse_health()
            result = json.loads(result_json)

            assert result["connected"] is True
            assert result["server_version"] == "24.8"
            assert result["meta"]["query_id"] == "q-h"

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
    async def test_error_handling_raises_classified_backend_error(self) -> None:
        """A driver crash inside the real client is classified (the SDK masks plain text)."""
        from skywatch_mcp.config import ClickHouseSettings
        from skywatch_mcp.lib.clickhouse_client import ClickHouseClient
        from skywatch_mcp.lib.tool_errors import BackendError

        with (
            patch(
                "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
            ) as mock_get,
            patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client,
        ):
            driver = AsyncMock()
            driver.query.side_effect = RuntimeError("DB error")
            mock_get.return_value = driver
            real_client = ClickHouseClient(ClickHouseSettings())
            mock_get_client.return_value = real_client

            with pytest.raises(BackendError) as exc_info:
                await clickhouse.clickhouse_query.__wrapped__(  # type: ignore[attr-defined]
                    "SELECT * FROM test LIMIT 1"
                )

            assert exc_info.value.kind == "unknown"
            assert exc_info.value.retryable is False
            # The exception text "DB error" never appears in the payload message.
            assert "DB error" not in exc_info.value.message

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

            # asdict requires the mocked result to be dataclass-compatible.
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


class TestJsonStringWrapping:
    """Changed/new tools keep the JSON-string output convention (AC.12).

    The SDK wraps each returned string into text content plus a
    ``{"result": <string>}`` structured payload.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("tool_name", "arguments", "mock_path", "setup"),
        [
            (
                "clickhouse_query",
                {"sql": "SELECT 1 LIMIT 1"},
                "skywatch_mcp.tools.clickhouse.get_client",
                "query",
            ),
            (
                "clickhouse_health",
                {},
                "skywatch_mcp.tools.clickhouse.get_client",
                "query_trusted",
            ),
        ],
    )
    async def test_success_wraps_json_string(self, tool_name, arguments, mock_path, setup) -> None:
        from mcp import Client

        from skywatch_mcp.server import mcp

        def make_result(setup_attr: str):
            from skywatch_mcp.lib.clickhouse_client import QueryResult

            if setup_attr == "query":
                return QueryResult(
                    columns=[{"name": "v", "type": "UInt8"}],
                    rows=[{"v": 1}],
                    query_id="q-w",
                    elapsed_ms=1,
                )
            return QueryResult(
                columns=[{"name": "connected", "type": "UInt8"}],
                rows=[{"connected": 1, "server_version": "test"}],
                query_id="q-w",
                elapsed_ms=1,
            )

        with patch(mock_path) as mock_get_client:
            mock_client = MagicMock()
            setattr(mock_client, setup, AsyncMock(return_value=make_result(setup)))
            mock_get_client.return_value = mock_client

            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool(tool_name, arguments)

        assert not result.is_error
        assert result.content[0].type == "text"
        text = result.content[0].text
        parsed = json.loads(text)
        assert isinstance(parsed, dict)
        assert result.structured_content == {"result": text}

    @pytest.mark.asyncio
    async def test_schema_wraps_json_string(self) -> None:
        from mcp import Client

        from skywatch_mcp.lib.clickhouse_client import QueryResult
        from skywatch_mcp.server import mcp

        schema_result = QueryResult(
            columns=[{"name": "name", "type": "String"}],
            rows=[{"name": "AtUri", "type": "String"}],
            query_id="q-s",
            elapsed_ms=1,
            coverage={"tables_expected": 12, "tables_matched": 12, "tables_missing": []},
        )
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.get_schema = AsyncMock(return_value=schema_result)
            mock_get_client.return_value = mock_client

            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool("clickhouse_schema", {})

        assert not result.is_error
        text = result.content[0].text
        assert json.loads(text)["rows"]
        assert result.structured_content == {"result": text}


class TestInputValidation:
    """Test that FastMCP validates input types and required fields."""

    @pytest.mark.asyncio
    async def test_invalid_input_type_rejected_before_handler(self) -> None:
        """Test AC2.2: MCPServer rejects invalid input types before handler execution."""
        from skywatch_mcp.server import mcp
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError) as exc_info:
            await mcp.call_tool("domain_check", {"domain": 123})

        error_message = str(exc_info.value)
        assert "Input should be a valid string" in error_message or "type=string_type" in error_message

    @pytest.mark.asyncio
    async def test_missing_required_field_rejected_with_clear_error(self) -> None:
        """Test AC2.3: MCPServer rejects missing required fields with clear error message."""
        from skywatch_mcp.server import mcp
        from mcp.server.mcpserver.exceptions import ToolError

        with pytest.raises(ToolError) as exc_info:
            await mcp.call_tool("domain_check", {})

        error_message = str(exc_info.value)
        assert "Field required" in error_message or "missing" in error_message.lower()
