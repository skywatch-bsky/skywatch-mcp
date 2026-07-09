# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult


class TestBuildAccountEntropyResultsQuery:
    """Test SQL query building for account_entropy_results"""

    def test_default_includes_today_filter(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "toDate(run_timestamp) = today()" in query

    def test_default_includes_only_bot_like(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "is_bot_like = 1" in query

    def test_no_only_bot_like_omits_filter(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(only_bot_like=False, limit=50)

        assert "is_bot_like = 1" not in query

    def test_with_user_id_adds_filter(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(user_id="did:plc:abc123", limit=50)

        assert "user_id = 'did:plc:abc123'" in query

    def test_user_id_sanitization(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(user_id="did:plc:abc!@#", limit=50)

        assert "user_id = 'did:plc:abc'" in query
        assert "!@#" not in query

    def test_with_date_uses_provided_date(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(date="2024-01-15", limit=50)

        assert "toDate(run_timestamp) = '2024-01-15'" in query

    def test_includes_norm_columns(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "hourly_entropy_norm" in query
        assert "interval_entropy_norm" in query

    def test_includes_raw_entropy_columns(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "hourly_entropy" in query
        assert "interval_entropy" in query

    def test_includes_interval_cv(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "interval_cv" in query

    def test_includes_all_flag_columns(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "hourly_flag" in query
        assert "interval_flag" in query
        assert "cv_flag" in query

    def test_includes_sample_rkeys(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "sample_rkeys" in query

    def test_no_q_value_or_min_q_value(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "q_value" not in query

    def test_from_correct_table(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "FROM default.account_entropy_results" in query

    def test_order_by_timestamp_desc(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=50)

        assert "ORDER BY run_timestamp DESC" in query

    def test_respects_limit(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_results_query

        query = _build_account_entropy_results_query(limit=100)

        assert "LIMIT 100" in query


class TestBuildAccountEntropyTrendQuery:
    """Test SQL query building for account_entropy_trend"""

    def test_includes_user_id_filter(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc123", days=14, limit=500)

        assert "user_id = 'did:plc:abc123'" in query

    def test_includes_interval(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc123", days=7, limit=500)

        assert "INTERVAL 7 DAY" in query

    def test_no_bot_like_filter(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc123", days=14, limit=500)

        where_clause = query.split("WHERE")[1].split("ORDER")[0]
        assert "is_bot_like = 1" not in where_clause

    def test_order_by_timestamp_asc(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc123", days=14, limit=500)

        assert "ORDER BY run_timestamp ASC" in query

    def test_includes_sample_rkeys(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc123", days=14, limit=500)

        assert "sample_rkeys" in query

    def test_user_id_sanitization(self):
        from skywatch_mcp.tools.account_entropy import _build_account_entropy_trend_query

        query = _build_account_entropy_trend_query(user_id="did:plc:abc!@#", days=14, limit=500)

        assert "user_id = 'did:plc:abc'" in query


class TestAccountEntropyResultsTool:
    """Test account_entropy_results tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.account_entropy.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "user_id", "type": "String"}],
                rows=[{"user_id": "did:plc:abc123"}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.account_entropy import account_entropy_results

            result = await account_entropy_results(limit=50)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.account_entropy.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.account_entropy import account_entropy_results

            with pytest.raises(ValueError):
                await account_entropy_results(limit=50)


class TestAccountEntropyTrendTool:
    """Test account_entropy_trend tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.account_entropy.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "post_count", "type": "UInt32"}],
                rows=[{"post_count": 42}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.account_entropy import account_entropy_trend

            result = await account_entropy_trend(user_id="did:plc:abc123", days=14, limit=500)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.account_entropy.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.account_entropy import account_entropy_trend

            with pytest.raises(ValueError):
                await account_entropy_trend(user_id="did:plc:abc123", days=14, limit=500)


class TestServerIntegration:
    """Test MCP server integration for account_entropy tools"""

    def test_server_should_register_account_entropy_tools(self):
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "account_entropy_results" in tool_names
        assert "account_entropy_trend" in tool_names

    def test_account_entropy_tools_should_have_descriptions(self):
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["account_entropy_results"].description
        assert tools_by_name["account_entropy_trend"].description
