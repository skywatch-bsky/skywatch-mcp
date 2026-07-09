# pattern: Imperative Shell

import json
import pytest
from unittest.mock import AsyncMock, patch

from skywatch_mcp.lib.clickhouse_client import QueryResult


class TestBuildClustersQuery:
    """Test SQL query building for cosharing_clusters"""

    def test_build_clusters_query_by_did_should_include_join(self):
        """_build_clusters_query with did should join membership and clusters tables"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(did="did:plc:test", limit=20)

        assert "url_cosharing_membership m" in query
        assert "url_cosharing_clusters c" in query
        assert "JOIN" in query
        assert "m.did = 'did:plc:test'" in query

    def test_build_clusters_query_by_did_without_date_uses_yesterday(self):
        """_build_clusters_query without date should use yesterday() function"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(did="did:plc:test", limit=20)

        assert "AND m.run_date = yesterday()" in query
        assert "AND m.run_date = '2024-01-01'" not in query

    def test_build_clusters_query_by_did_with_date_uses_provided_date(self):
        """_build_clusters_query with date should filter to that date"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(did="did:plc:test", date="2024-01-15", limit=20)

        assert "AND m.run_date = '2024-01-15'" in query
        assert "yesterday()" not in query

    def test_build_clusters_query_by_cluster_id_should_not_join(self):
        """_build_clusters_query with cluster_id should query clusters table only"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(cluster_id="2024-01-15-0042", limit=20)

        assert "FROM url_cosharing_clusters" in query
        assert "JOIN" not in query
        assert "WHERE cluster_id = '2024-01-15-0042'" in query

    def test_build_clusters_query_by_cluster_id_with_date_includes_date_filter(self):
        """_build_clusters_query with cluster_id and date should include date filter"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(cluster_id="2024-01-15-0042", date="2024-01-15", limit=20)

        assert "AND run_date = '2024-01-15'" in query

    def test_build_clusters_query_by_cluster_id_without_date_omits_date_filter(self):
        """_build_clusters_query with cluster_id, no date should omit date filter"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(cluster_id="2024-01-15-0042", limit=20)

        assert "AND run_date = " not in query
        assert "WHERE cluster_id = '2024-01-15-0042'" in query

    def test_build_clusters_query_without_filters_uses_yesterday(self):
        """_build_clusters_query without filters should query all clusters from yesterday"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(limit=20)

        assert "WHERE run_date = yesterday()" in query
        assert "FROM url_cosharing_clusters" in query

    def test_build_clusters_query_with_min_members_adds_filter(self):
        """_build_clusters_query with min_members should add member_count filter"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(min_members=5, limit=20)

        assert "AND member_count >= 5" in query

    def test_build_clusters_query_without_min_members_omits_filter(self):
        """_build_clusters_query without min_members should not include member filter"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(limit=20)

        assert "member_count >=" not in query

    def test_build_clusters_query_sanitizes_did(self):
        """_build_clusters_query should sanitize DID parameter"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(did="did:plc:TEST!@#", limit=20)

        assert "m.did = 'did:plc:'" in query
        assert "TEST" not in query
        assert "!@#" not in query

    def test_build_clusters_query_respects_limit(self):
        """_build_clusters_query should use provided limit"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(limit=100)

        assert "LIMIT 100" in query

    def test_build_clusters_query_includes_new_density_columns(self):
        """_build_clusters_query should include mean_edge_similarity and subgraph_density"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(limit=20)

        assert "mean_edge_similarity" in query
        assert "subgraph_density" in query

    def test_build_clusters_query_by_did_includes_new_density_columns(self):
        """_build_clusters_query with did should include mean_edge_similarity and subgraph_density"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(did="did:plc:test", limit=20)

        assert "c.mean_edge_similarity" in query
        assert "c.subgraph_density" in query

    def test_build_clusters_query_by_cluster_id_includes_new_density_columns(self):
        """_build_clusters_query with cluster_id should include mean_edge_similarity and subgraph_density"""
        from skywatch_mcp.tools.cosharing import _build_clusters_query

        query = _build_clusters_query(cluster_id="2024-01-15-0042", limit=20)

        assert "mean_edge_similarity" in query
        assert "subgraph_density" in query


class TestBuildPairsQuery:
    """Test SQL query building for cosharing_pairs"""

    def test_build_pairs_query_should_check_both_accounts(self):
        """_build_pairs_query should check account_a OR account_b"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", limit=50)

        assert "account_a = 'did:plc:test' OR account_b = 'did:plc:test'" in query

    def test_build_pairs_query_without_date_uses_yesterday(self):
        """_build_pairs_query without date should use yesterday()"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", limit=50)

        assert "AND date = yesterday()" in query

    def test_build_pairs_query_with_date_uses_provided_date(self):
        """_build_pairs_query with date should filter to that date"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", date="2024-01-15", limit=50)

        assert "AND date = '2024-01-15'" in query
        assert "yesterday()" not in query

    def test_build_pairs_query_with_min_weight_adds_filter(self):
        """_build_pairs_query with min_weight should add weight filter"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", min_weight=5, limit=50)

        assert "AND weight >= 5" in query

    def test_build_pairs_query_without_min_weight_omits_filter(self):
        """_build_pairs_query without min_weight should not include weight filter"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", limit=50)

        assert "weight >=" not in query

    def test_build_pairs_query_sanitizes_did(self):
        """_build_pairs_query should sanitize DID parameter"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:TEST!@#", limit=50)

        assert "account_a = 'did:plc:'" in query
        assert "TEST" not in query
        assert "!@#" not in query

    def test_build_pairs_query_respects_limit(self):
        """_build_pairs_query should use provided limit"""
        from skywatch_mcp.tools.cosharing import _build_pairs_query

        query = _build_pairs_query(did="did:plc:test", limit=100)

        assert "LIMIT 100" in query


class TestBuildEvolutionQuery:
    """Test SQL query building for cosharing_evolution"""

    def test_build_evolution_query_should_match_cluster_id(self):
        """_build_evolution_query should include cluster_id = filter"""
        from skywatch_mcp.tools.cosharing import _build_evolution_query

        query = _build_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "WHERE cluster_id = '2024-01-15-0042'" in query

    def test_build_evolution_query_should_match_predecessors(self):
        """_build_evolution_query should include has(predecessor_cluster_ids) check"""
        from skywatch_mcp.tools.cosharing import _build_evolution_query

        query = _build_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "OR has(predecessor_cluster_ids, '2024-01-15-0042')" in query

    def test_build_evolution_query_sanitizes_cluster_id(self):
        """_build_evolution_query should sanitize cluster_id parameter"""
        from skywatch_mcp.tools.cosharing import _build_evolution_query

        query = _build_evolution_query(cluster_id="2024-01-15-0042!@#", limit=30)

        assert "cluster_id = '2024-01-15-0042'" in query
        assert "!@#" not in query

    def test_build_evolution_query_respects_limit(self):
        """_build_evolution_query should use provided limit"""
        from skywatch_mcp.tools.cosharing import _build_evolution_query

        query = _build_evolution_query(cluster_id="2024-01-15-0042", limit=100)

        assert "LIMIT 100" in query

    def test_build_evolution_query_includes_new_density_columns(self):
        """_build_evolution_query should include mean_edge_similarity and subgraph_density"""
        from skywatch_mcp.tools.cosharing import _build_evolution_query

        query = _build_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "mean_edge_similarity" in query
        assert "subgraph_density" in query


class TestCosharingClustersToolAC1_8:
    """Test cosharing_clusters tool verifies AC1.8"""

    @pytest.mark.asyncio
    async def test_cosharing_clusters_should_return_cluster_metadata(self):
        """cosharing_clusters should return cluster metadata with filtering"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "cluster_id", "type": "String"},
                    {"name": "member_count", "type": "UInt32"},
                ],
                rows=[
                    {"cluster_id": "2024-01-15-0042", "member_count": 5},
                    {"cluster_id": "2024-01-15-0043", "member_count": 3},
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            result = await cosharing_clusters(limit=20)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 2
            assert len(data["rows"]) == 2
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_cosharing_clusters_with_did_filter(self):
        """cosharing_clusters should filter by DID"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            await cosharing_clusters(did="did:plc:test", limit=20)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "m.did = 'did:plc:test'" in query

    @pytest.mark.asyncio
    async def test_cosharing_clusters_with_cluster_id_filter(self):
        """cosharing_clusters should filter by cluster_id"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            await cosharing_clusters(cluster_id="2024-01-15-0042", limit=20)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "cluster_id = '2024-01-15-0042'" in query

    @pytest.mark.asyncio
    async def test_cosharing_clusters_with_date_filter(self):
        """cosharing_clusters should filter by date"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            await cosharing_clusters(date="2024-01-15", limit=20)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "run_date = '2024-01-15'" in query

    @pytest.mark.asyncio
    async def test_cosharing_clusters_with_min_members_filter(self):
        """cosharing_clusters should filter by min_members"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            await cosharing_clusters(min_members=10, limit=20)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "member_count >= 10" in query

    @pytest.mark.asyncio
    async def test_cosharing_clusters_should_raise_on_error(self):
        """cosharing_clusters should raise ValueError on error"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.cosharing import cosharing_clusters

            with pytest.raises(ValueError):
                await cosharing_clusters(limit=20)


class TestCosharingPairsToolAC1_9:
    """Test cosharing_pairs tool verifies AC1.9"""

    @pytest.mark.asyncio
    async def test_cosharing_pairs_should_return_paired_accounts_with_weights(self):
        """cosharing_pairs should return paired accounts with edge weights"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "account_a", "type": "String"},
                    {"name": "account_b", "type": "String"},
                    {"name": "weight", "type": "UInt32"},
                ],
                rows=[
                    {
                        "account_a": "did:plc:test",
                        "account_b": "did:plc:other",
                        "weight": 15,
                    },
                    {
                        "account_a": "did:plc:test",
                        "account_b": "did:plc:another",
                        "weight": 8,
                    },
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            result = await cosharing_pairs(did="did:plc:test", limit=50)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 2
            assert data["rows"][0]["weight"] == 15
            assert data["rows"][1]["weight"] == 8

    @pytest.mark.asyncio
    async def test_cosharing_pairs_did_is_required(self):
        """cosharing_pairs DID parameter is required"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            await cosharing_pairs(did="did:plc:test", limit=50)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "did:plc:test" in query

    @pytest.mark.asyncio
    async def test_cosharing_pairs_sanitizes_did_in_sql(self):
        """cosharing_pairs should sanitize DID in generated SQL"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            await cosharing_pairs(did="did:plc:TEST!@#", limit=50)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "account_a = 'did:plc:'" in query
            assert "TEST" not in query
            assert "!@#" not in query

    @pytest.mark.asyncio
    async def test_cosharing_pairs_with_date_filter(self):
        """cosharing_pairs should filter by date"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            await cosharing_pairs(did="did:plc:test", date="2024-01-15", limit=50)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "AND date = '2024-01-15'" in query

    @pytest.mark.asyncio
    async def test_cosharing_pairs_with_min_weight_filter(self):
        """cosharing_pairs should filter by min_weight"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            await cosharing_pairs(did="did:plc:test", min_weight=10, limit=50)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "AND weight >= 10" in query

    @pytest.mark.asyncio
    async def test_cosharing_pairs_should_raise_on_error(self):
        """cosharing_pairs should raise ValueError on error"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.cosharing import cosharing_pairs

            with pytest.raises(ValueError):
                await cosharing_pairs(did="did:plc:test", limit=50)


class TestCosharingEvolutionToolAC1_10:
    """Test cosharing_evolution tool verifies AC1.10"""

    @pytest.mark.asyncio
    async def test_cosharing_evolution_should_trace_cluster_timeline(self):
        """cosharing_evolution should trace cluster timeline with evolution types"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "run_date", "type": "Date"},
                    {"name": "evolution_type", "type": "String"},
                    {"name": "member_count", "type": "UInt32"},
                ],
                rows=[
                    {
                        "run_date": "2024-01-14",
                        "evolution_type": "born",
                        "member_count": 3,
                    },
                    {
                        "run_date": "2024-01-15",
                        "evolution_type": "continued",
                        "member_count": 5,
                    },
                    {
                        "run_date": "2024-01-16",
                        "evolution_type": "merged",
                        "member_count": 8,
                    },
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_evolution

            result = await cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 3
            assert data["rows"][0]["evolution_type"] == "born"
            assert data["rows"][1]["evolution_type"] == "continued"
            assert data["rows"][2]["evolution_type"] == "merged"

    @pytest.mark.asyncio
    async def test_cosharing_evolution_should_include_cluster_id_match(self):
        """cosharing_evolution query should include cluster_id match"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_evolution

            await cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "WHERE cluster_id = '2024-01-15-0042'" in query

    @pytest.mark.asyncio
    async def test_cosharing_evolution_should_include_predecessor_match_via_has(self):
        """cosharing_evolution query should include has() for predecessor_cluster_ids"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_evolution

            await cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "OR has(predecessor_cluster_ids, '2024-01-15-0042')" in query

    @pytest.mark.asyncio
    async def test_cosharing_evolution_sanitizes_cluster_id(self):
        """cosharing_evolution should sanitize cluster_id in SQL"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(columns=[], rows=[])
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_evolution

            await cosharing_evolution(cluster_id="2024-01-15-0042!@#", limit=30)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "cluster_id = '2024-01-15-0042'" in query
            assert "!@#" not in query

    @pytest.mark.asyncio
    async def test_cosharing_evolution_should_raise_on_error(self):
        """cosharing_evolution should raise ValueError on error"""
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.cosharing import cosharing_evolution

            with pytest.raises(ValueError):
                await cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)


class TestBuildCosharingRunsQuery:
    """Test SQL query building for cosharing_runs"""

    def test_build_cosharing_runs_query_default_uses_interval(self):
        from skywatch_mcp.tools.cosharing import _build_cosharing_runs_query

        query = _build_cosharing_runs_query(limit=14)

        assert "FROM url_cosharing_runs" in query
        assert "today() - INTERVAL 14 DAY" in query
        assert "ORDER BY run_date DESC" in query
        assert "LIMIT 14" in query

    def test_build_cosharing_runs_query_with_date_uses_exact_date(self):
        from skywatch_mcp.tools.cosharing import _build_cosharing_runs_query

        query = _build_cosharing_runs_query(date="2024-01-15", limit=14)

        assert "run_date = '2024-01-15'" in query
        assert "INTERVAL" not in query

    def test_build_cosharing_runs_query_respects_limit(self):
        from skywatch_mcp.tools.cosharing import _build_cosharing_runs_query

        query = _build_cosharing_runs_query(limit=30)

        assert "LIMIT 30" in query
        assert "INTERVAL 30 DAY" in query

    def test_build_cosharing_runs_query_includes_knee_and_guardrail(self):
        from skywatch_mcp.tools.cosharing import _build_cosharing_runs_query

        query = _build_cosharing_runs_query(limit=14)

        assert "knee_found" in query
        assert "guardrail_triggered" in query
        assert "flagged_accounts" in query
        assert "cluster_count" in query


class TestBuildQuoteClustersQuery:
    """Test SQL query building for quote_cosharing_clusters"""

    def test_build_quote_clusters_query_by_did_should_include_join(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:test", limit=20)

        assert "quote_cosharing_membership m" in query
        assert "quote_cosharing_clusters c" in query
        assert "JOIN" in query
        assert "m.did = 'did:plc:test'" in query

    def test_build_quote_clusters_query_by_did_without_date_uses_yesterday(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:test", limit=20)

        assert "AND m.run_date = yesterday()" in query

    def test_build_quote_clusters_query_by_did_with_date_uses_provided_date(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:test", date="2024-01-15", limit=20)

        assert "AND m.run_date = '2024-01-15'" in query

    def test_build_quote_clusters_query_by_cluster_id_should_not_join(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(cluster_id="2024-01-15-0042", limit=20)

        assert "FROM quote_cosharing_clusters" in query
        assert "JOIN" not in query
        assert "WHERE cluster_id = '2024-01-15-0042'" in query

    def test_build_quote_clusters_query_without_filters_uses_yesterday(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(limit=20)

        assert "WHERE run_date = yesterday()" in query
        assert "FROM quote_cosharing_clusters" in query

    def test_build_quote_clusters_query_with_min_members_adds_filter(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(min_members=5, limit=20)

        assert "AND member_count >= 5" in query

    def test_build_quote_clusters_query_sanitizes_did(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:TEST!@#", limit=20)

        assert "m.did = 'did:plc:'" in query
        assert "TEST" not in query
        assert "!@#" not in query

    def test_build_quote_clusters_query_uses_uris_not_urls(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:test", limit=20)

        assert "unique_uris" in query
        assert "unique_urls" not in query
        assert "sample_uris" in query
        assert "sample_urls" not in query

    def test_build_quote_clusters_query_has_no_density_columns(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(did="did:plc:test", limit=20)

        assert "mean_edge_similarity" not in query
        assert "subgraph_density" not in query

    def test_build_quote_clusters_query_default_path_no_density_columns(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(limit=20)

        assert "mean_edge_similarity" not in query
        assert "subgraph_density" not in query

    def test_build_quote_clusters_query_cluster_id_path_uses_uris_not_urls(self):
        from skywatch_mcp.tools.cosharing import _build_quote_clusters_query

        query = _build_quote_clusters_query(cluster_id="2024-01-15-0042", limit=20)

        assert "unique_uris" in query
        assert "unique_urls" not in query


class TestBuildQuotePairsQuery:
    """Test SQL query building for quote_cosharing_pairs"""

    def test_build_quote_pairs_query_should_check_both_accounts(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", limit=50)

        assert "account_a = 'did:plc:test' OR account_b = 'did:plc:test'" in query

    def test_build_quote_pairs_query_without_date_uses_yesterday(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", limit=50)

        assert "AND date = yesterday()" in query

    def test_build_quote_pairs_query_with_date_uses_provided_date(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", date="2024-01-15", limit=50)

        assert "AND date = '2024-01-15'" in query

    def test_build_quote_pairs_query_uses_shared_uris(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", limit=50)

        assert "shared_uris" in query
        assert "shared_urls" not in query

    def test_build_quote_pairs_query_from_quote_table(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", limit=50)

        assert "FROM quote_cosharing_pairs" in query

    def test_build_quote_pairs_query_with_min_weight_adds_filter(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:test", min_weight=5, limit=50)

        assert "AND weight >= 5" in query

    def test_build_quote_pairs_query_sanitizes_did(self):
        from skywatch_mcp.tools.cosharing import _build_quote_pairs_query

        query = _build_quote_pairs_query(did="did:plc:TEST!@#", limit=50)

        assert "account_a = 'did:plc:'" in query
        assert "TEST" not in query


class TestBuildQuoteEvolutionQuery:
    """Test SQL query building for quote_cosharing_evolution"""

    def test_build_quote_evolution_query_should_match_cluster_id(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "WHERE cluster_id = '2024-01-15-0042'" in query

    def test_build_quote_evolution_query_should_match_predecessors(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "OR has(predecessor_cluster_ids, '2024-01-15-0042')" in query

    def test_build_quote_evolution_query_uses_uris_not_urls(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "unique_uris" in query
        assert "unique_urls" not in query

    def test_build_quote_evolution_query_has_no_density_columns(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "mean_edge_similarity" not in query
        assert "subgraph_density" not in query

    def test_build_quote_evolution_query_uses_quote_table(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042", limit=30)

        assert "FROM quote_cosharing_clusters" in query

    def test_build_quote_evolution_query_sanitizes_cluster_id(self):
        from skywatch_mcp.tools.cosharing import _build_quote_evolution_query

        query = _build_quote_evolution_query(cluster_id="2024-01-15-0042!@#", limit=30)

        assert "cluster_id = '2024-01-15-0042'" in query
        assert "!@#" not in query


class TestCosharingRunsTool:
    """Test cosharing_runs tool"""

    @pytest.mark.asyncio
    async def test_cosharing_runs_should_return_run_metadata(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "run_date", "type": "Date"},
                    {"name": "cluster_count", "type": "UInt32"},
                ],
                rows=[
                    {"run_date": "2024-01-15", "cluster_count": 5},
                    {"run_date": "2024-01-14", "cluster_count": 0},
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import cosharing_runs

            result = await cosharing_runs(limit=14)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 2
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_cosharing_runs_default_query_uses_interval(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.return_value = QueryResult(columns=[], rows=[])

            from skywatch_mcp.tools.cosharing import cosharing_runs

            await cosharing_runs(limit=14)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "today() - INTERVAL 14 DAY" in query

    @pytest.mark.asyncio
    async def test_cosharing_runs_should_raise_on_error(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.cosharing import cosharing_runs

            with pytest.raises(ValueError):
                await cosharing_runs(limit=14)


class TestQuoteCosharingClustersTool:
    """Test quote_cosharing_clusters tool"""

    @pytest.mark.asyncio
    async def test_quote_cosharing_clusters_should_return_metadata(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "cluster_id", "type": "String"},
                    {"name": "member_count", "type": "UInt32"},
                ],
                rows=[
                    {"cluster_id": "2024-01-15-0042", "member_count": 5},
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import quote_cosharing_clusters

            result = await quote_cosharing_clusters(limit=20)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 1
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_quote_cosharing_clusters_with_did_filter(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.return_value = QueryResult(columns=[], rows=[])

            from skywatch_mcp.tools.cosharing import quote_cosharing_clusters

            await quote_cosharing_clusters(did="did:plc:test", limit=20)

            call_args = mock_client.query_trusted.call_args
            query = call_args[0][0]
            assert "m.did = 'did:plc:test'" in query

    @pytest.mark.asyncio
    async def test_quote_cosharing_clusters_should_raise_on_error(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Connection failed")

            from skywatch_mcp.tools.cosharing import quote_cosharing_clusters

            with pytest.raises(ValueError):
                await quote_cosharing_clusters(limit=20)


class TestQuoteCosharingPairsTool:
    """Test quote_cosharing_pairs tool"""

    @pytest.mark.asyncio
    async def test_quote_cosharing_pairs_should_return_pairs(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "account_a", "type": "String"},
                    {"name": "account_b", "type": "String"},
                    {"name": "weight", "type": "UInt32"},
                ],
                rows=[
                    {"account_a": "did:plc:test", "account_b": "did:plc:other", "weight": 10},
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import quote_cosharing_pairs

            result = await quote_cosharing_pairs(did="did:plc:test", limit=50)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 1
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_quote_cosharing_pairs_should_raise_on_error(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.cosharing import quote_cosharing_pairs

            with pytest.raises(ValueError):
                await quote_cosharing_pairs(did="did:plc:test", limit=50)


class TestQuoteCosharingEvolutionTool:
    """Test quote_cosharing_evolution tool"""

    @pytest.mark.asyncio
    async def test_quote_cosharing_evolution_should_trace_timeline(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_result = QueryResult(
                columns=[
                    {"name": "run_date", "type": "Date"},
                    {"name": "evolution_type", "type": "String"},
                ],
                rows=[
                    {"run_date": "2024-01-14", "evolution_type": "born"},
                    {"run_date": "2024-01-15", "evolution_type": "continued"},
                ],
            )
            mock_client.query_trusted.return_value = mock_result

            from skywatch_mcp.tools.cosharing import quote_cosharing_evolution

            result = await quote_cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)

            assert isinstance(result, str)
            data = json.loads(result)
            assert "query" in data
            assert "rows" in data
            assert "count" in data
            assert data["count"] == 2
            mock_client.query_trusted.assert_called_once()

    @pytest.mark.asyncio
    async def test_quote_cosharing_evolution_should_raise_on_error(self):
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client

            mock_client.query_trusted.side_effect = Exception("Query failed")

            from skywatch_mcp.tools.cosharing import quote_cosharing_evolution

            with pytest.raises(ValueError):
                await quote_cosharing_evolution(cluster_id="2024-01-15-0042", limit=30)


class TestServerIntegration:
    """Test MCP server integration for cosharing tools"""

    def test_server_should_register_cosharing_tools(self):
        """Server should register all seven cosharing-family tools"""
        from skywatch_mcp.server import mcp

        tool_names = [t.name for t in mcp._tool_manager._tools.values()]
        assert "cosharing_clusters" in tool_names
        assert "cosharing_pairs" in tool_names
        assert "cosharing_evolution" in tool_names
        assert "cosharing_runs" in tool_names
        assert "quote_cosharing_clusters" in tool_names
        assert "quote_cosharing_pairs" in tool_names
        assert "quote_cosharing_evolution" in tool_names

    def test_cosharing_tools_should_have_descriptions(self):
        """Cosharing tools should have descriptions"""
        from skywatch_mcp.server import mcp

        tools_by_name = {t.name: t for t in mcp._tool_manager._tools.values()}
        assert tools_by_name["cosharing_clusters"].description
        assert tools_by_name["cosharing_pairs"].description
        assert tools_by_name["cosharing_evolution"].description
        assert tools_by_name["cosharing_runs"].description
        assert tools_by_name["quote_cosharing_clusters"].description
        assert tools_by_name["quote_cosharing_pairs"].description
        assert tools_by_name["quote_cosharing_evolution"].description
