# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult


class TestBuildSignupAnomaliesQuery:
    """Test SQL query building for signup_anomalies"""

    def test_default_includes_today_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=50)

        assert "toDate(run_timestamp) = today()" in query

    def test_default_includes_only_anomalies(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=50)

        assert "is_anomaly = 1" in query

    def test_default_no_only_anomalies_omits_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(only_anomalies=False, limit=50)

        assert "is_anomaly = 1" not in query

    def test_with_pds_host_adds_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(pds_host="pds.example.com", limit=50)

        assert "pds_host = 'pds.example.com'" in query

    def test_pds_host_sanitization_strips_invalid(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(pds_host="pds.example.com'; drop--", limit=50)

        assert "pds_host = 'pds.example.comdrop--'" in query
        assert ";" not in query
        assert "'" not in query.split("pds_host = '")[1].split("'")[0]

    def test_with_granularity_daily(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(granularity="daily", limit=50)

        assert "granularity = 'daily'" in query

    def test_with_granularity_hourly(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(granularity="hourly", limit=50)

        assert "granularity = 'hourly'" in query

    def test_invalid_granularity_raises(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        with pytest.raises(ValueError):
            _build_signup_anomalies_query(granularity="weekly", limit=50)

    def test_with_date_uses_provided_date(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(date="2024-01-15", limit=50)

        assert "toDate(run_timestamp) = '2024-01-15'" in query
        assert "today()" not in query

    def test_with_min_q_value_adds_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(min_q_value=0.05, limit=50)

        assert "q_value <= 0.05" in query

    def test_respects_limit(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=100)

        assert "LIMIT 100" in query

    def test_includes_key_columns(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=50)

        assert "q_value" in query
        assert "is_anomaly" in query
        assert "dispersion_index" in query
        assert "sample_dids" in query
        assert "rolling_mean" in query
        assert "rolling_variance" in query

    def test_from_correct_table(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=50)

        assert "FROM default.pds_signup_anomalies" in query

    def test_order_by_timestamp_desc(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        query = _build_signup_anomalies_query(limit=50)

        assert "ORDER BY run_timestamp DESC" in query


class TestBuildSignupAnomalyTrendQuery:
    """Test SQL query building for signup_anomaly_trend"""

    def test_includes_host_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=14, limit=500)

        assert "pds_host = 'pds.example.com'" in query

    def test_includes_interval(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=7, limit=500)

        assert "INTERVAL 7 DAY" in query

    def test_no_only_anomalies_filter(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=14, limit=500)

        # is_anomaly appears in SELECT but not as a WHERE filter
        where_clause = query.split("WHERE")[1].split("ORDER")[0]
        assert "is_anomaly" not in where_clause

    def test_order_by_timestamp_asc(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=14, limit=500)

        assert "ORDER BY run_timestamp ASC" in query

    def test_excludes_sample_dids(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=14, limit=500)

        select_clause = query.split("FROM")[0]
        assert "sample_dids" not in select_clause

    def test_respects_limit(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=14, limit=200)

        assert "LIMIT 200" in query

    def test_host_sanitization(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        query = _build_signup_anomaly_trend_query(pds_host="pds.example.com'; DROP--", days=14, limit=500)

        assert "pds.example.com';" not in query

    def test_negative_limit_raises(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        with pytest.raises(ValueError):
            _build_signup_anomalies_query(limit=-1)

    def test_negative_days_raises(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomaly_trend_query

        with pytest.raises(ValueError):
            _build_signup_anomaly_trend_query(pds_host="pds.example.com", days=0)

    def test_nan_q_value_raises(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        with pytest.raises(ValueError):
            _build_signup_anomalies_query(min_q_value=float("nan"))

    def test_impossible_date_raises(self):
        from skywatch_mcp.tools.signup_anomaly import _build_signup_anomalies_query

        with pytest.raises(ValueError):
            _build_signup_anomalies_query(date="2026-13-99")


class TestSignupAnomaliesTool:
    """Test signup_anomalies tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.signup_anomaly.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "q_value", "type": "Float64"}],
                rows=[{"q_value": 0.01}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.signup_anomaly import signup_anomalies

            result = await signup_anomalies(limit=50)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 1
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.signup_anomaly.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.signup_anomaly import signup_anomalies

            with pytest.raises(ValueError):
                await signup_anomalies(limit=50)


class TestSignupAnomalyTrendTool:
    """Test signup_anomaly_trend tool"""

    @pytest.mark.asyncio
    async def test_returns_json_with_query_rows_count(self):
        with patch("skywatch_mcp.tools.signup_anomaly.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[{"name": "observed_count", "type": "UInt32"}],
                rows=[{"observed_count": 42}],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.signup_anomaly import signup_anomaly_trend

            result = await signup_anomaly_trend(pds_host="pds.example.com", days=14, limit=500)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 1
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        with patch("skywatch_mcp.tools.signup_anomaly.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.signup_anomaly import signup_anomaly_trend

            with pytest.raises(ValueError):
                await signup_anomaly_trend(pds_host="pds.example.com", days=14, limit=500)


class TestServerIntegration:
    """Test MCP server integration for signup_anomaly tools"""

    def test_server_should_register_signup_anomaly_tools(self):
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "signup_anomalies" in tool_names
        assert "signup_anomaly_trend" in tool_names

    def test_signup_anomaly_tools_should_have_descriptions(self):
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["signup_anomalies"].description
        assert tools_by_name["signup_anomaly_trend"].description
