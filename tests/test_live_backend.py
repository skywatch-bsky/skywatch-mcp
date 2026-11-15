"""Opt-in live verification suite (V.1–V.8).

These tests run ONLY when the operator opts in:

    SKYWATCH_LIVE_CH=1 uv run pytest tests/test_live_backend.py -v

after starting the ClickHouse backend and restarting the deployed server with
this code. Ozone live checks additionally require SKYWATCH_LIVE_OZONE=1.
They are never executed by the default offline run (``uv run pytest``).

Named checks (from the approved plan):

- V.1  test_live_zero_row_query
- V.2  test_live_exact_field_lookups, test_live_zero_arg_schema_legacy_contract,
       test_live_schema_values_match_describe
- V.3  test_live_nullable_rule_counts_and_or_agreement
- V.4  test_live_bounded_hydration_and_did_sampling
- V.5  test_live_rule_summary_limits (after operator-approved catalogue population)
- V.6  test_live_ozone_aliases_and_comments (needs SKYWATCH_LIVE_OZONE=1)
- V.7  test_live_health_after_start
- V.8  test_live_recorded_effective_limits

pytest never starts, stops, or restarts services; the before-state proof for
backend failure handling is the offline closed-port protocol test in
tests/test_protocol.py.
"""

import json
import os

import pytest

from skywatch_mcp.lib.clickhouse_client import (
    OSPREY_RESULTS_TABLE,
    SCHEMA_TABLES,
    get_client,
)
from skywatch_mcp.tools.clickhouse import (
    VERIFIED_RULE_CATALOGUE,
    clickhouse_health,
    clickhouse_rule_summary,
    clickhouse_schema,
)

pytestmark = [
    pytest.mark.skipif(
        os.environ.get("SKYWATCH_LIVE_CH") != "1",
        reason="live ClickHouse checks require SKYWATCH_LIVE_CH=1 (operator opt-in)",
    ),
]

REQUIRED_FIELDS = [
    "AtUri",
    "Cid",
    "UserId",
    "Handle",
    "__timestamp",
    "PostText",
    "PostIsReply",
    "PostReplyParent",
]


def wrapped(tool):
    """Call the raw handler, bypassing the error boundary, for direct assertions."""
    return tool.__wrapped__


@pytest.fixture
def client():
    return get_client()


class TestV1ZeroRowQuery:
    @pytest.mark.asyncio
    async def test_live_zero_row_query(self, client):
        result = await client.query_trusted("SELECT 1 AS connected LIMIT 1")
        assert result.rows == [{"connected": 1}]
        assert result.query_id

        zero_rows = await client.query_trusted(
            "SELECT 1 AS x FROM system.one WHERE 0 LIMIT 5"
        )
        assert zero_rows.rows == []


class TestV2SchemaLookups:
    @pytest.mark.asyncio
    async def test_live_exact_field_lookups(self, client):
        result = json.loads(
            await wrapped(clickhouse_schema)(
                table="osprey_execution_results", fields=REQUIRED_FIELDS
            )
        )
        by_name = {column["name"]: column["type"] for column in result["columns"]}
        # Every requested name is either found (typed) or informatively missing.
        for name in REQUIRED_FIELDS:
            assert name in by_name or name in result["missing_fields"]
        assert result["missing_fields"] == [
            name for name in REQUIRED_FIELDS if name not in by_name
        ]

    @pytest.mark.asyncio
    async def test_live_zero_arg_schema_legacy_contract(self, client):
        result = json.loads(await wrapped(clickhouse_schema)())
        legacy_keys = {
            "name",
            "type",
            "default_kind",
            "default_expression",
            "comment",
            "codec_expression",
            "ttl_expression",
            "table",
        }
        assert result["rows"], "zero-arg schema must not be empty with backend up"
        for row in result["rows"]:
            assert set(row.keys()) == legacy_keys
        tables = {row["table"] for row in result["rows"]}
        assert tables == set(SCHEMA_TABLES)

    @pytest.mark.asyncio
    async def test_live_schema_values_match_describe(self, client):
        """Zero-arg output keys AND values match a direct DESCRIBE, not just key names."""
        schema = json.loads(await wrapped(clickhouse_schema)())
        direct = await client.query_trusted(f"DESCRIBE TABLE {OSPREY_RESULTS_TABLE}")
        direct_by_name = {
            row["name"]: {k: v for k, v in row.items() if k != "table"}
            for row in direct.rows
        }
        schema_rows = [
            {k: v for k, v in row.items() if k != "table"}
            for row in schema["rows"]
            if row["table"] == OSPREY_RESULTS_TABLE
        ]
        schema_by_name = {row["name"]: row for row in schema_rows}
        assert schema_by_name == direct_by_name


class TestV3NullableAgreement:
    @pytest.mark.asyncio
    async def test_live_nullable_rule_counts_and_or_agreement(self, client):
        sql = (
            "SELECT countIf(a) AS count_a, countIf(b) AS count_b, "
            "countIf(a OR b) AS count_or, countIf(or(a, b)) AS count_or_fn, "
            "countIf(a AND b) AS count_and "
            "FROM values('a Nullable(UInt8), b Nullable(UInt8)', "
            "(1, 0), (0, 0), (1, 1), (NULL, 1), (NULL, 0), (NULL, NULL), (0, 1)) "
            "LIMIT 1"
        )
        result = await client.query_trusted(sql)
        row = result.rows[0]
        # Hand-computed fixture: NULL and 0 never fire; 1 fires.
        assert row["count_a"] == 2
        assert row["count_b"] == 3
        assert row["count_or"] == 4
        assert row["count_or_fn"] == 4
        assert row["count_and"] == 1
        # Independent identity agreement.
        assert row["count_a"] + row["count_b"] - row["count_and"] == row["count_or"]


class TestV4HydrationBounds:
    @pytest.mark.asyncio
    async def test_live_bounded_hydration_and_did_sampling(self, client):
        step1 = await client.query_trusted(
            f"SELECT AtUri FROM {OSPREY_RESULTS_TABLE} WHERE AtUri IS NOT NULL LIMIT 50"
        )
        assert 0 <= len(step1.rows) <= 50
        uris = [row["AtUri"] for row in step1.rows]
        if uris:
            quoted = ", ".join("'" + uri.replace("'", "\\'") + "'" for uri in uris)
            step2 = await client.query_trusted(
                f"SELECT AtUri, Handle FROM {OSPREY_RESULTS_TABLE} "
                f"WHERE AtUri IN ({quoted}) LIMIT 50"
            )
            assert 0 <= len(step2.rows) <= 50
        sampling = await client.query_trusted(
            f"SELECT DISTINCT UserId FROM {OSPREY_RESULTS_TABLE} LIMIT 25"
        )
        assert 0 <= len(sampling.rows) <= 25


class TestV5RuleSummaryLimits:
    @pytest.mark.asyncio
    async def test_live_rule_summary_over_max_rejected(self):
        rules = [f"rule_{i}" for i in range(548)]
        from skywatch_mcp.lib.tool_errors import ToolInputError

        with pytest.raises(ToolInputError, match="100"):
            await wrapped(clickhouse_rule_summary)("did:plc:example", 30, rules)

    @pytest.mark.asyncio
    async def test_live_rule_summary_complete_results(self, client):
        """Requires the operator-approved catalogue population step to have run."""
        assert len(VERIFIED_RULE_CATALOGUE) > 0, (
            "VERIFIED_RULE_CATALOGUE is unpopulated: run V.5 only after the "
            "operator confirms the authoritative rule source (skywatch-osprey-rules "
            "tree or operator-supplied export) and the catalogue constant is filled."
        )
        rules = sorted(VERIFIED_RULE_CATALOGUE)[:100]
        result = json.loads(
            await wrapped(clickhouse_rule_summary)("did:plc:example", 30, rules)
        )
        assert result["window_rows"] is not None
        assert len(result["rules"]) == len(rules)
        assert result["coverage"]["rules_evaluated"] == len(rules)


class TestV7Health:
    @pytest.mark.asyncio
    async def test_live_health_after_start(self):
        result = json.loads(await wrapped(clickhouse_health)())
        assert result["connected"] is True
        assert result["server_version"]


class TestV8EffectiveLimits:
    @pytest.mark.asyncio
    async def test_live_recorded_effective_limits(self, client):
        result = await client.query_trusted(
            "SELECT name, value FROM system.settings "
            "WHERE name IN ('max_query_size', 'max_parser_depth') LIMIT 10"
        )
        recorded = {row["name"]: row["value"] for row in result.rows}
        # Reported back to the operator; informs any future budget revision.
        print(f"EFFECTIVE SERVER LIMITS (record for budget revision): {recorded}")
        assert "max_query_size" in recorded
        assert "max_parser_depth" in recorded


@pytest.mark.skipif(
    os.environ.get("SKYWATCH_LIVE_OZONE") != "1",
    reason="live Ozone checks additionally require SKYWATCH_LIVE_OZONE=1",
)
class TestV6OzoneAliases:
    @pytest.mark.asyncio
    async def test_live_ozone_aliases_and_comments(self):
        """Real read-only Ozone calls prove both alias forms are accepted identically.

        Byte-identity of the outgoing request paths is asserted deterministically
        offline (tests/test_mcp_integration.py::TestOzoneEventTypeAliases, request
        capture — no network). This live check makes two real queryEvents calls
        (short name vs full NSID) and asserts both succeed with identical event
        id sets. Comment behavior: any returned event carrying a ``comment`` key
        must expose it verbatim as a string; the manual plan step is to inspect
        one event with and one without a reporter comment.
        """
        import json as json_module

        import skywatch_mcp.tools.ozone as ozone_module

        short_result = await ozone_module.ozone_query_events(types=["report"], limit=10)
        full_result = await ozone_module.ozone_query_events(
            types=["tools.ozone.moderation.defs#modEventReport"], limit=10
        )
        short_events = json_module.loads(short_result).get("events", [])
        full_events = json_module.loads(full_result).get("events", [])
        assert {e["id"] for e in short_events} == {e["id"] for e in full_events}
        for event in full_events:
            comment = event.get("event", {}).get("comment")
            if comment is not None:
                assert isinstance(comment, str)
