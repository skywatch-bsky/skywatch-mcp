# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult


class TestBuildQuoteOverdispersionResultsQuery:
    """Test SQL query building for quote_overdispersion_results"""

    def test_default_includes_today_filter(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "toDate(run_timestamp) = today()" in query

    def test_default_includes_only_anomalies(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "is_anomaly = 1" in query

    def test_with_quoted_uri_adds_filter(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
        query = _build_quote_overdispersion_results_query(quoted_uri=uri, limit=50)

        assert f"quoted_uri = '{uri}'" in query

    def test_quoted_uri_sanitization(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(
            quoted_uri="at://did:plc:abc/post'; drop", limit=50
        )

        assert "at://did:plc:abc/postdrop" in query
        assert ";" not in query
        assert "'" not in query.split("quoted_uri = '")[1].split("'")[0]

    def test_with_quoted_author_did_adds_filter(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(
            quoted_author_did="did:plc:abc123", limit=50
        )

        assert "quoted_author_did = 'did:plc:abc123'" in query

    def test_quoted_author_did_sanitization(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(
            quoted_author_did="did:plc:abc!@#", limit=50
        )

        assert "quoted_author_did = 'did:plc:abc'" in query
        assert "!@#" not in query

    def test_with_granularity_daily(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(granularity="daily", limit=50)

        assert "granularity = 'daily'" in query

    def test_with_granularity_hourly(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(granularity="hourly", limit=50)

        assert "granularity = 'hourly'" in query

    def test_invalid_granularity_raises(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        with pytest.raises(ValueError):
            _build_quote_overdispersion_results_query(granularity="weekly", limit=50)

    def test_signal_volume_adds_comparison(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(signal="volume", limit=50)

        assert "volume_q_value <= density_q_value" in query

    def test_signal_density_adds_comparison(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(signal="density", limit=50)

        assert "density_q_value <= volume_q_value" in query

    def test_invalid_signal_raises(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        with pytest.raises(ValueError):
            _build_quote_overdispersion_results_query(signal="unknown", limit=50)

    def test_no_sample_urls_column(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "sample_urls" not in query
        assert "sample_dids" in query

    def test_no_on_watchlist_column(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "on_watchlist" not in query

    def test_includes_quoted_uri_and_author_did(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "quoted_uri" in query
        assert "quoted_author_did" in query

    def test_from_correct_table(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=50)

        assert "FROM default.quote_overdispersion_results" in query

    def test_respects_limit(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(limit=100)

        assert "LIMIT 100" in query


class TestBuildQuoteOverdispersionTrendQuery:
    """Test SQL query building for quote_overdispersion_trend"""

    def test_includes_quoted_uri_filter(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_trend_query

        uri = "at://did:plc:abc/app.bsky.feed.post/xyz"
        query = _build_quote_overdispersion_trend_query(quoted_uri=uri, days=14, limit=500)

        assert f"quoted_uri = '{uri}'" in query

    def test_includes_interval(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_trend_query

        query = _build_quote_overdispersion_trend_query(
            quoted_uri="at://did:plc:abc/post/xyz", days=7, limit=500
        )

        assert "INTERVAL 7 DAY" in query

    def test_no_only_anomalies_filter(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_trend_query

        query = _build_quote_overdispersion_trend_query(
            quoted_uri="at://did:plc:abc/post/xyz", days=14, limit=500
        )

        where_clause = query.split("WHERE")[1].split("ORDER")[0]
        assert "is_anomaly" not in where_clause

    def test_order_by_timestamp_asc(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_trend_query

        query = _build_quote_overdispersion_trend_query(
            quoted_uri="at://did:plc:abc/post/xyz", days=14, limit=500
        )

        assert "ORDER BY run_timestamp ASC" in query

    def test_signal_applies_independently_of_only_anomalies(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        query = _build_quote_overdispersion_results_query(
            signal="density", only_anomalies=False, limit=50
        )

        assert "density_q_value <= volume_q_value" in query
        assert "is_anomaly = 1" not in query

    def test_negative_limit_raises(self):
        from skywatch_mcp.tools.quote_overdispersion import _build_quote_overdispersion_results_query

        with pytest.raises(ValueError):
            _build_quote_overdispersion_results_query(limit=0)


class TestQuoteOverdispersionResultsTool:
    """Test quote_overdispersion_results tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.quote_overdispersion.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "quoted_uri", "type": "String"}],
                rows=[{"quoted_uri": "at://did:plc:abc/post/xyz"}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.quote_overdispersion import quote_overdispersion_results

            result = await quote_overdispersion_results(limit=50)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.quote_overdispersion.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.quote_overdispersion import quote_overdispersion_results

            with pytest.raises(ValueError):
                await quote_overdispersion_results(limit=50)


class TestQuoteOverdispersionTrendTool:
    """Test quote_overdispersion_trend tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.quote_overdispersion.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "total_shares", "type": "UInt32"}],
                rows=[{"total_shares": 50}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.quote_overdispersion import quote_overdispersion_trend

            result = await quote_overdispersion_trend(
                quoted_uri="at://did:plc:abc/post/xyz", days=14, limit=500
            )

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.quote_overdispersion.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.quote_overdispersion import quote_overdispersion_trend

            with pytest.raises(ValueError):
                await quote_overdispersion_trend(
                    quoted_uri="at://did:plc:abc/post/xyz", days=14, limit=500
                )


class TestServerIntegration:
    """Test MCP server integration for quote_overdispersion tools"""

    def test_server_should_register_quote_overdispersion_tools(self):
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "quote_overdispersion_results" in tool_names
        assert "quote_overdispersion_trend" in tool_names

    def test_quote_overdispersion_tools_should_have_descriptions(self):
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["quote_overdispersion_results"].description
        assert tools_by_name["quote_overdispersion_trend"].description
