import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from skywatch_mcp.lib.clickhouse_client import ClickHouseClient, QueryResult, SCHEMA_TABLES
from skywatch_mcp.config import ClickHouseSettings


class TestClickHouseClient:
    """Test ClickHouseClient wrapper"""

    @pytest.fixture
    def mock_settings(self):
        return ClickHouseSettings(
            host="http://localhost",
            port=8123,
            user="default",
            password="",
            database="default",
        )

    @pytest.fixture
    async def mock_client(self):
        """Mock AsyncClient"""
        mock = AsyncMock()
        return mock

    @pytest.mark.asyncio
    async def test_query_should_validate_and_execute_valid_select(self, mock_settings):
        """Validates query then executes against ClickHouse"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = MagicMock()
            mock_result.column_names = ["id", "name"]
            mock_result.column_types = ["UInt64", "String"]
            mock_result.result_rows = [[1, "test"], [2, "test2"]]
            mock_async_client.query.return_value = mock_result

            client = ClickHouseClient(mock_settings)
            result = await client.query("SELECT id, name FROM users LIMIT 10")

            assert isinstance(result, QueryResult)
            assert result.columns == [
                {"name": "id", "type": "UInt64"},
                {"name": "name", "type": "String"},
            ]
            assert result.rows == [
                {"id": 1, "name": "test"},
                {"id": 2, "name": "test2"},
            ]

    @pytest.mark.asyncio
    async def test_query_should_reject_missing_limit(self, mock_settings):
        """Query without LIMIT should raise ValueError"""
        client = ClickHouseClient(mock_settings)

        with pytest.raises(ValueError, match="Query validation failed"):
            await client.query("SELECT * FROM users")

    @pytest.mark.asyncio
    async def test_query_should_reject_non_select(self, mock_settings):
        """Query starting with non-SELECT should raise ValueError"""
        client = ClickHouseClient(mock_settings)

        with pytest.raises(ValueError, match="Query validation failed"):
            await client.query("INSERT INTO users VALUES (1) LIMIT 10")

    @pytest.mark.asyncio
    async def test_query_trusted_should_not_validate(self, mock_settings):
        """query_trusted should execute without validation"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = MagicMock()
            mock_result.column_names = ["result"]
            mock_result.column_types = ["UInt64"]
            mock_result.result_rows = [[42]]
            mock_async_client.query.return_value = mock_result

            client = ClickHouseClient(mock_settings)
            result = await client.query_trusted("SELECT 42")

            assert isinstance(result, QueryResult)
            assert result.columns == [{"name": "result", "type": "UInt64"}]
            assert result.rows == [{"result": 42}]

    @pytest.mark.asyncio
    async def test_get_schema_should_describe_all_tables(self, mock_settings):
        """get_schema should DESCRIBE all SCHEMA_TABLES and combine results"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            # Create 11 mock results (one per table in SCHEMA_TABLES)
            mock_results = []
            for i in range(11):
                mock_result = MagicMock()
                mock_result.column_names = ["name", "type"]
                mock_result.column_types = ["String", "String"]
                mock_result.result_rows = [
                    [f"col_{i}_1", "UInt64"],
                    [f"col_{i}_2", "String"],
                ]
                mock_results.append(mock_result)

            # Set up side effects to return each result in sequence
            mock_async_client.query.side_effect = mock_results

            client = ClickHouseClient(mock_settings)
            result = await client.get_schema()

            assert isinstance(result, QueryResult)
            # Should have name, type, and table columns
            assert any(col["name"] == "table" for col in result.columns)
            # Should have 22 rows total (2 from each of 11 tables)
            assert len(result.rows) == 22
            # All rows should have table field
            assert all("table" in row for row in result.rows)
            # Verify all 11 tables were queried
            assert mock_async_client.query.call_count == 11

    @pytest.mark.asyncio
    async def test_get_schema_should_handle_table_errors_gracefully(self, mock_settings):
        """get_schema should skip tables that fail to DESCRIBE"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            # Create 11 side effects with some exceptions at known positions
            mock_side_effects = []
            for i in range(11):
                if i in (2, 5, 8):  # Fail at positions 2, 5, 8
                    mock_side_effects.append(Exception(f"Table not found at position {i}"))
                else:
                    mock_result = MagicMock()
                    mock_result.column_names = ["name", "type"]
                    mock_result.column_types = ["String", "String"]
                    mock_result.result_rows = [[f"col_{i}", "String"]]
                    mock_side_effects.append(mock_result)

            mock_async_client.query.side_effect = mock_side_effects

            client = ClickHouseClient(mock_settings)
            result = await client.get_schema()

            assert isinstance(result, QueryResult)
            # Should have 8 rows (1 from each successful table: 11 - 3 exceptions = 8)
            assert len(result.rows) == 8
            # All rows should have table field
            assert all("table" in row for row in result.rows)
            # Verify all 11 tables were attempted
            assert mock_async_client.query.call_count == 11

    @pytest.mark.asyncio
    async def test_client_should_use_async_methods(self, mock_settings):
        """Client should use AsyncClient.query (async)"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = MagicMock()
            mock_result.column_names = ["test"]
            mock_result.column_types = ["String"]
            mock_result.result_rows = [["value"]]
            mock_async_client.query = AsyncMock(return_value=mock_result)

            client = ClickHouseClient(mock_settings)
            await client.query_trusted("SELECT 'test' LIMIT 1")

            # Verify async query method was called
            mock_async_client.query.assert_called_once()
            # Verify it was awaited (AsyncMock verifies this)

    @pytest.mark.asyncio
    async def test_query_should_set_60_second_timeout(self, mock_settings):
        """query() should use 60s max_execution_time"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = MagicMock()
            mock_result.column_names = ["test"]
            mock_result.column_types = ["String"]
            mock_result.result_rows = [["value"]]
            mock_async_client.query.return_value = mock_result

            client = ClickHouseClient(mock_settings)
            await client.query("SELECT 1 LIMIT 1")

            # Verify settings were passed with 60s timeout
            call_args = mock_async_client.query.call_args
            assert call_args[1]["settings"]["max_execution_time"] == 60

    @pytest.mark.asyncio
    async def test_query_trusted_should_set_120_second_timeout(self, mock_settings):
        """query_trusted() should use 120s max_execution_time"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = MagicMock()
            mock_result.column_names = ["test"]
            mock_result.column_types = ["String"]
            mock_result.result_rows = [["value"]]
            mock_async_client.query.return_value = mock_result

            client = ClickHouseClient(mock_settings)
            await client.query_trusted("SELECT 1")

            # Verify settings were passed with 120s timeout
            call_args = mock_async_client.query.call_args
            assert call_args[1]["settings"]["max_execution_time"] == 120


class TestSchemaTables:
    """Test SCHEMA_TABLES constant"""

    def test_should_have_11_tables(self):
        """SCHEMA_TABLES should contain 11 predefined tables"""
        assert len(SCHEMA_TABLES) == 11

    def test_should_have_expected_table_names(self):
        """SCHEMA_TABLES should contain all expected table names"""
        expected = {
            "default.osprey_execution_results",
            "default.pds_signup_anomalies",
            "default.url_overdispersion_results",
            "default.account_entropy_results",
            "default.url_cosharing_pairs",
            "default.url_cosharing_clusters",
            "default.url_cosharing_membership",
            "default.quote_cosharing_pairs",
            "default.quote_cosharing_clusters",
            "default.quote_cosharing_membership",
            "default.quote_overdispersion_results",
        }
        assert set(SCHEMA_TABLES) == expected
