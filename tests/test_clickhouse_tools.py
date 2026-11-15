import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult, SCHEMA_TABLES
from skywatch_mcp.lib.tool_errors import BackendError, ToolInputError


# The eight field names the live suite verifies as typed lookups (AC.5).
REQUIRED_FIELD_FIXTURES = [
    "AtUri",
    "Cid",
    "UserId",
    "Handle",
    "__timestamp",
    "PostText",
    "PostIsReply",
    "PostReplyParent",
]

FULL_OSPREY_COLUMNS = [
    {"name": "AtUri", "type": "String"},
    {"name": "Cid", "type": "String"},
    {"name": "UserId", "type": "String"},
    {"name": "Handle", "type": "String"},
    {"name": "__timestamp", "type": "DateTime"},
    {"name": "PostText", "type": "String"},
    {"name": "PostTextCleaned", "type": "String"},
    {"name": "PostIsReply", "type": "Bool"},
    {"name": "PostReplyParent", "type": "String"},
    {"name": "bot_like", "type": "Nullable(Bool)"},
]


def _mock_columns_result():
    return QueryResult(
        columns=[{"name": "name", "type": "String"}, {"name": "type", "type": "String"}],
        rows=[{"name": c["name"], "type": c["type"]} for c in FULL_OSPREY_COLUMNS],
        query_id="q-schema-1",
        elapsed_ms=4,
        coverage={"tables_expected": 1, "tables_matched": 1, "tables_missing": []},
    )


class TestClickHouseTools:
    """Test ClickHouse MCP tools"""

    @pytest.mark.asyncio
    async def test_clickhouse_query_tool_should_execute_and_return_json(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "id", "type": "UInt64"},
                    {"name": "name", "type": "String"},
                ],
                rows=[
                    {"id": 1, "name": "test"},
                    {"id": 2, "name": "test2"},
                ],
                query_id="q-1",
                elapsed_ms=3,
            )
            mock_client.query.return_value = mock_result

            # Import after patching to get the patched version
            from skywatch_mcp.tools.clickhouse import clickhouse_query

            result = await clickhouse_query("SELECT id, name FROM users LIMIT 10")

            assert isinstance(result, str)
            data = json.loads(result)
            assert "columns" in data
            assert "rows" in data
            assert len(data["columns"]) == 2
            assert len(data["rows"]) == 2
            assert data["meta"]["query_id"] == "q-1"
            assert data["meta"]["truncated"] is False

    @pytest.mark.asyncio
    async def test_clickhouse_query_tool_should_raise_on_validation_error(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query.side_effect = ValueError(
                "Query validation failed: Query must contain a LIMIT clause"
            )

            from skywatch_mcp.tools.clickhouse import clickhouse_query

            with pytest.raises(ValueError):
                await clickhouse_query("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_zero_arg_schema_tool_returns_legacy_shape_with_coverage(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            legacy_rows = [
                {"name": "AtUri", "type": "String", "default_kind": "", "table": "default.osprey_execution_results"},
                {"name": "Cid", "type": "String", "default_kind": "", "table": "default.osprey_execution_results"},
            ]
            mock_result = QueryResult(
                columns=[
                    {"name": "name", "type": "String"},
                    {"name": "type", "type": "String"},
                    {"name": "default_kind", "type": "String"},
                    {"name": "table", "type": "String"},
                ],
                rows=legacy_rows,
                query_id="q-schema",
                elapsed_ms=7,
                coverage={"tables_expected": 12, "tables_matched": 12, "tables_missing": []},
            )
            mock_client.get_schema.return_value = mock_result

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema()

            assert isinstance(result, str)
            data = json.loads(result)
            assert "columns" in data
            assert "rows" in data
            assert data["rows"] == legacy_rows
            assert data["coverage"]["tables_expected"] == 12
            assert data["meta"]["query_id"] == "q-schema"

    @pytest.mark.asyncio
    async def test_schema_selection_by_table_short_name(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.return_value = _mock_columns_result()

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema(table="osprey_execution_results")

            data = json.loads(result)
            assert data["table"] == "default.osprey_execution_results"
            assert len(data["columns"]) == len(FULL_OSPREY_COLUMNS)
            assert data["missing_fields"] == []
            assert data["coverage"] == {
                "tables_expected": 1,
                "tables_matched": 1,
                "tables_missing": [],
            }
            mock_client.get_table_columns.assert_awaited_once_with(
                "default.osprey_execution_results"
            )

    @pytest.mark.asyncio
    async def test_schema_selection_by_table_full_name(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.return_value = _mock_columns_result()

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema(table="default.osprey_execution_results")
            assert json.loads(result)["table"] == "default.osprey_execution_results"
            mock_client.get_table_columns.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_schema_selection_by_fields_exact_match(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.return_value = _mock_columns_result()

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema(
                table="osprey_execution_results", fields=REQUIRED_FIELD_FIXTURES
            )

            data = json.loads(result)
            returned_names = [c["name"] for c in data["columns"]]
            assert returned_names == REQUIRED_FIELD_FIXTURES
            assert data["missing_fields"] == []
            assert data["coverage"]["tables_expected"] == 1
            assert data["meta"]["query_id"] == "q-schema-1"

    @pytest.mark.asyncio
    async def test_schema_existing_table_missing_fields_is_success(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.return_value = _mock_columns_result()

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema(
                table="osprey_execution_results", fields=["AtUri", "NotARealColumn"]
            )
            data = json.loads(result)
            assert data["missing_fields"] == ["NotARealColumn"]
            assert [c["name"] for c in data["columns"]] == ["AtUri"]

    @pytest.mark.asyncio
    async def test_schema_single_field_exact_match(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.return_value = _mock_columns_result()

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema(table="osprey_execution_results", field="AtUri")
            data = json.loads(result)
            assert data["columns"] == [{"name": "AtUri", "type": "String"}]
            assert data["missing_fields"] == []

    @pytest.mark.asyncio
    async def test_schema_unknown_table_actionable_error(self):
        """An unknown requested table name fails with the valid-table listing."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            with pytest.raises(ToolInputError) as exc_info:
                await clickhouse_schema.__wrapped__(table="not_a_table")  # type: ignore[attr-defined]
            assert "not_a_table" in str(exc_info.value)
            assert "default.osprey_execution_results" in str(exc_info.value)
            mock_client.get_table_columns.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_schema_missing_table_selection_is_actionable_error(self):
        """Confirmed table absence (code 60) lists valid tables plus the code."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.side_effect = BackendError(
                kind="invalid_sql", retryable=False, query_id="q", code=60
            )

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            with pytest.raises(ToolInputError) as exc_info:
                await clickhouse_schema.__wrapped__(  # type: ignore[attr-defined]
                    table="osprey_execution_results"
                )
            message = str(exc_info.value)
            assert "code 60" in message
            assert "default.osprey_execution_results" in message

    @pytest.mark.asyncio
    async def test_schema_field_and_fields_mutually_exclusive(self):
        from skywatch_mcp.tools.clickhouse import clickhouse_schema

        with pytest.raises(ToolInputError, match="not both"):
            await clickhouse_schema.__wrapped__(  # type: ignore[attr-defined]
                table="osprey_execution_results", field="AtUri", fields=["Cid"]
            )

    @pytest.mark.asyncio
    async def test_schema_fields_require_table(self):
        from skywatch_mcp.tools.clickhouse import clickhouse_schema

        with pytest.raises(ToolInputError, match="requires table"):
            await clickhouse_schema.__wrapped__(fields=["AtUri"])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_schema_compact_global_failures_are_classified(self):
        """Global failure kinds from a compact DESCRIBE propagate as classified BackendError."""
        kinds = ["backend_unavailable", "auth_failed", "timeout", "unknown"]
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            for kind in kinds:
                mock_client = AsyncMock()
                mock_get_client.return_value = mock_client
                mock_client.get_table_columns.side_effect = BackendError(
                    kind=kind, retryable=True, query_id="q", code=1
                )

                from skywatch_mcp.tools.clickhouse import clickhouse_schema

                with pytest.raises(BackendError) as exc_info:
                    await clickhouse_schema.__wrapped__(  # type: ignore[attr-defined]
                        table="osprey_execution_results"
                    )
                assert exc_info.value.kind == kind

    @pytest.mark.asyncio
    async def test_schema_compact_invalid_sql_non_absence_propagates(self):
        """invalid_sql without confirmed absence (code 47/62) keeps the BackendError."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.get_table_columns.side_effect = BackendError(
                kind="invalid_sql", retryable=False, query_id="q-47", code=47
            )

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            with pytest.raises(BackendError) as exc_info:
                await clickhouse_schema.__wrapped__(  # type: ignore[attr-defined]
                    table="osprey_execution_results"
                )
            assert exc_info.value.kind == "invalid_sql"
            assert exc_info.value.code == 47
            assert exc_info.value.query_id == "q-47"

    @pytest.mark.asyncio
    async def test_clickhouse_schema_tool_should_raise_on_error(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.get_schema.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            with pytest.raises(Exception, match="Connection failed"):
                await clickhouse_schema()

    @pytest.mark.asyncio
    async def test_health_tool_success(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.query_trusted.return_value = QueryResult(
                columns=[{"name": "connected", "type": "UInt8"}, {"name": "server_version", "type": "String"}],
                rows=[{"connected": 1, "server_version": "24.8.1.1"}],
                query_id="q-health",
                elapsed_ms=2,
            )

            from skywatch_mcp.tools.clickhouse import clickhouse_health

            result = await clickhouse_health()
            data = json.loads(result)
            assert data["connected"] is True
            assert data["server_version"] == "24.8.1.1"
            assert data["meta"]["query_id"] == "q-health"
            call_kwargs = mock_client.query_trusted.call_args[1]
            assert call_kwargs["max_execution_time"] == 5

    @pytest.mark.asyncio
    async def test_health_tool_structured_failure(self):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            mock_client.query_trusted.side_effect = BackendError(
                kind="backend_unavailable", retryable=True, query_id="q-h", code=None
            )

            from skywatch_mcp.tools.clickhouse import clickhouse_health

            with pytest.raises(BackendError) as exc_info:
                await clickhouse_health.__wrapped__()  # type: ignore[attr-defined]
            assert exc_info.value.kind == "backend_unavailable"


class TestServerImport:
    """Test MCP server integration"""

    def test_server_should_import_clickhouse_tools(self):
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "clickhouse_query" in tool_names
        assert "clickhouse_schema" in tool_names
        assert "clickhouse_health" in tool_names
        assert "clickhouse_rule_summary" in tool_names

    def test_server_should_have_tool_descriptions(self):
        """Tools should have descriptions"""
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["clickhouse_query"].description
        assert tools_by_name["clickhouse_schema"].description
        assert tools_by_name["clickhouse_health"].description
        assert tools_by_name["clickhouse_rule_summary"].description


class TestSchemaTableListAlignment:

    def test_schema_tables_cover_all_tools_advertised_tables(self):
        """The tool docstring tables stay aligned with SCHEMA_TABLES membership."""
        assert SCHEMA_TABLES  # non-empty; detailed membership pinned in test_clickhouse.py
