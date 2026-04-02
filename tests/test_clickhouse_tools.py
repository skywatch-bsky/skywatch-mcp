import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult


class TestClickHouseTools:
    """Test ClickHouse MCP tools"""

    @pytest.mark.asyncio
    async def test_clickhouse_query_tool_should_execute_and_return_json(self):
        """clickhouse_query tool should return JSON with columns and rows"""
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

    @pytest.mark.asyncio
    async def test_clickhouse_query_tool_should_raise_on_validation_error(self):
        """clickhouse_query tool should raise ValueError on validation error"""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            # Setup mock to raise validation error
            mock_client.query.side_effect = ValueError("Query validation failed: Query must contain a LIMIT clause")

            from skywatch_mcp.tools.clickhouse import clickhouse_query

            with pytest.raises(ValueError):
                await clickhouse_query("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_clickhouse_schema_tool_should_return_json_with_schema(self):
        """clickhouse_schema tool should return JSON with column definitions"""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "name", "type": "String"},
                    {"name": "type", "type": "String"},
                    {"name": "table", "type": "String"},
                ],
                rows=[
                    {"name": "id", "type": "UInt64", "table": "default.users"},
                    {"name": "name", "type": "String", "table": "default.users"},
                ],
            )
            mock_client.get_schema.return_value = mock_result

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            result = await clickhouse_schema()

            assert isinstance(result, str)
            data = json.loads(result)
            assert "columns" in data
            assert "rows" in data
            assert len(data["columns"]) == 3
            assert len(data["rows"]) == 2

    @pytest.mark.asyncio
    async def test_clickhouse_schema_tool_should_raise_on_error(self):
        """clickhouse_schema tool should raise ValueError on error"""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.get_schema.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.clickhouse import clickhouse_schema

            with pytest.raises(ValueError):
                await clickhouse_schema()


class TestServerImport:
    """Test MCP server integration"""

    def test_server_should_import_clickhouse_tools(self):
        """Server should import clickhouse tools module"""
        # This will fail if tools aren't properly registered
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "clickhouse_query" in tool_names
        assert "clickhouse_schema" in tool_names

    def test_server_should_have_tool_descriptions(self):
        """Tools should have descriptions"""
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["clickhouse_query"].description
        assert tools_by_name["clickhouse_schema"].description
