"""Offline tests for clickhouse_rule_summary (task D / AC.8).

All tests run without a backend: the rule catalogue is monkeypatched with an
explicit fixture, schema verification and execution are mocked, and the
validation order (count → grammar → denylist → catalogue → types → execute)
is asserted stage by stage.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from skywatch_mcp.lib.clickhouse_client import QueryResult
from skywatch_mcp.lib.tool_errors import BackendError, ToolInputError
from skywatch_mcp.tools.clickhouse import (
    MAX_RULES,
    VERIFIED_RULE_CATALOGUE,
    build_rule_summary_sql,
    clickhouse_rule_summary,
)

FIXTURE_CATALOGUE = frozenset(
    {
        "bot_like",
        "spam_signal",
        "inauthentic_engagement",
        "url_cosharing_flag",
        "account_entropy_flag",
        "nullable_rule_flag",
    }
)


@pytest.fixture
def fixture_catalogue(monkeypatch):
    import skywatch_mcp.tools.clickhouse as clickhouse_module

    monkeypatch.setattr(clickhouse_module, "VERIFIED_RULE_CATALOGUE", FIXTURE_CATALOGUE)


def _columns_result():
    rows = [
        {"name": "bot_like", "type": "Bool"},
        {"name": "spam_signal", "type": "Nullable(Bool)"},
        {"name": "inauthentic_engagement", "type": "UInt8"},
        {"name": "url_cosharing_flag", "type": "Nullable(UInt8)"},
        {"name": "account_entropy_flag", "type": "Bool"},
        {"name": "nullable_rule_flag", "type": "Nullable(Bool)"},
        {"name": "AtUri", "type": "String"},
        {"name": "PostText", "type": "String"},
        {"name": "wrong_type_flag", "type": "String"},
    ]
    return QueryResult(
        columns=[{"name": "name", "type": "String"}, {"name": "type", "type": "String"}],
        rows=rows,
        query_id="q-cols",
        elapsed_ms=1,
        coverage={"tables_expected": 1, "tables_matched": 1, "tables_missing": []},
    )


def _execution_result():
    return QueryResult(
        columns=[
            {"name": "window_rows", "type": "UInt64"},
            {"name": "m_0", "type": "UInt64"},
            {"name": "m_1", "type": "UInt64"},
        ],
        rows=[{"window_rows": 42, "m_0": 7, "m_1": 3}],
        query_id="q-exec",
        elapsed_ms=6,
    )


class TestSqlBuild:
    def test_rule_summary_sql_build(self):
        sql = build_rule_summary_sql(["bot_like", "spam_signal"])
        # Backticked verified identifiers with positional aliases.
        assert "countIf(`bot_like`) AS m_0" in sql
        assert "countIf(`spam_signal`) AS m_1" in sql
        # Typed bound-parameter placeholders: no interpolated did/days.
        assert "{did:String}" in sql
        assert "toIntervalDay({days:UInt32})" in sql
        assert "FROM default.osprey_execution_results" in sql
        # No cross-rule aggregation in the generated query text.
        lowered = sql.lower()
        assert "sum(" not in lowered
        assert "countif(" in lowered

    def test_sql_build_never_interpolates_parameters(self):
        sql = build_rule_summary_sql(["bot_like"])
        assert "did:plc" not in sql
        assert "365" not in sql

    def test_no_cross_rule_aggregation_for_many_rules(self):
        sql = build_rule_summary_sql(["bot_like", "spam_signal", "account_entropy_flag"])
        # One countIf per rule, nothing combining them.
        assert sql.count("countIf(") == 3
        assert "AND" not in sql or "__timestamp" in sql.split("WHERE")[1]


class TestValidationOrder:
    @pytest.mark.asyncio
    async def test_rule_summary_rejects_empty_list(self):
        with pytest.raises(ToolInputError, match="non-empty"):
            await clickhouse_rule_summary.__wrapped__("did:plc:x", 7, [])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_rule_summary_rejects_over_max(self):
        """A 548-name request fails before any backend call, naming the maximum."""
        rules = [f"rule_{i}" for i in range(548)]
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            with pytest.raises(ToolInputError) as exc_info:
                await clickhouse_rule_summary.__wrapped__("did:plc:x", 7, rules)  # type: ignore[attr-defined]
            assert str(MAX_RULES) in str(exc_info.value)
            mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_rule_summary_rejects_invalid_grammar(self):
        with pytest.raises(ToolInputError, match="Invalid rule identifier"):
            await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:x", 7, ["bad-name; DROP TABLE x"]
            )

    @pytest.mark.asyncio
    async def test_rule_summary_rejects_denylisted_rules(self):
        """UserId/PostText-style operational columns are rejected outright."""
        for denylisted in ("UserId", "PostText", "AtUri", "__timestamp"):
            with pytest.raises(ToolInputError, match="Not rule columns"):
                await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                    "did:plc:x", 7, [denylisted]
                )

    @pytest.mark.asyncio
    async def test_rule_summary_rejects_unknown_rules_against_catalogue(self, fixture_catalogue):
        with pytest.raises(ToolInputError) as exc_info:
            await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:x", 7, ["bot_like", "no_such_rule"]
            )
        assert "no_such_rule" in str(exc_info.value)
        assert 'clickhouse_schema(table="osprey_execution_results")' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_rule_summary_catalogue_unavailable_fails_closed(self):
        """Unpopulated catalogue: structured error before any backend call."""
        assert len(VERIFIED_RULE_CATALOGUE) == 0  # ships empty
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            with pytest.raises(BackendError) as exc_info:
                await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                    "did:plc:x", 7, ["bot_like"]
                )
            assert exc_info.value.kind == "rule_catalogue_unavailable"
            assert exc_info.value.retryable is True
            mock_get_client.assert_not_called()

    @pytest.mark.asyncio
    async def test_rule_summary_requires_catalogue_for_eligible_column(
        self, fixture_catalogue, monkeypatch
    ):
        """An eligible, non-denylisted Boolean column absent from the catalogue is rejected."""
        with pytest.raises(ToolInputError, match="Unknown rule name"):
            await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:x", 7, ["wrong_type_flag"]
            )

        # The same name IS accepted once the catalogue confirms it — but then
        # rejected at the type check because its live column type is String.
        import skywatch_mcp.tools.clickhouse as clickhouse_module

        monkeypatch.setattr(
            clickhouse_module,
            "VERIFIED_RULE_CATALOGUE",
            FIXTURE_CATALOGUE | {"wrong_type_flag"},
        )
        with (
            patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client,
            pytest.raises(ToolInputError, match="ineligible type"),
        ):
            mock_client = AsyncMock()
            mock_client.get_table_columns.return_value = _columns_result()
            mock_get_client.return_value = mock_client
            await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:x", 7, ["wrong_type_flag"]
            )

    @pytest.mark.asyncio
    async def test_rule_summary_dedupes_rules(self, fixture_catalogue):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.return_value = _columns_result()
            mock_client.query_trusted.return_value = _execution_result()
            mock_get_client.return_value = mock_client

            result = await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:example", 30, ["bot_like", "spam_signal", "bot_like"]
            )

        data = json.loads(result)
        assert data["coverage"]["rules_requested"] == 3
        assert data["coverage"]["rules_evaluated"] == 2
        assert [r["rule"] for r in data["rules"]] == ["bot_like", "spam_signal"]


class TestExecution:
    @pytest.mark.asyncio
    async def test_rule_summary_happy_path(self, fixture_catalogue):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.return_value = _columns_result()
            mock_client.query_trusted.return_value = _execution_result()
            mock_get_client.return_value = mock_client

            result = await clickhouse_rule_summary(
                "did:plc:example", 30, ["bot_like", "spam_signal"]
            )

        data = json.loads(result)
        assert data["did"] == "did:plc:example"
        assert data["window_days"] == 30
        assert data["rules"] == [
            {"rule": "bot_like", "matches": 7},
            {"rule": "spam_signal", "matches": 3},
        ]
        assert data["window_rows"] == 42
        assert data["coverage"] == {
            "rules_requested": 2,
            "rules_evaluated": 2,
            "unknown_rules": [],
        }
        assert data["meta"]["query_id"] == "q-exec"

        # Typed bound parameters forwarded; did/days never in the SQL text.
        sql, kwargs = mock_client.query_trusted.call_args[0][0], mock_client.query_trusted.call_args[1]
        assert kwargs["parameters"] == {"did": "did:plc:example", "days": 30}
        assert "did:plc:example" not in sql
        assert "countIf(`bot_like`) AS m_0" in sql
        assert "countIf(`spam_signal`) AS m_1" in sql

    @pytest.mark.asyncio
    async def test_rule_summary_did_is_sanitized_and_days_validated(self, fixture_catalogue):
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.return_value = _columns_result()
            mock_client.query_trusted.return_value = _execution_result()
            mock_get_client.return_value = mock_client

            result = await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                "did:plc:example; DROP TABLE x", 30, ["bot_like"]
            )
            data = json.loads(result)
            # sanitize_did strips everything outside [A-Za-z0-9:.-].
            assert data["did"] == "did:plc:exampleDROPTABLEx"
            kwargs = mock_client.query_trusted.call_args[1]
            assert kwargs["parameters"]["did"] == "did:plc:exampleDROPTABLEx"
            # The raw (unsanitized) DID never appears in the SQL text.
            assert "DROPTABLEx" not in mock_client.query_trusted.call_args[0][0]

        with pytest.raises(ToolInputError, match="days"):
            await clickhouse_rule_summary.__wrapped__("did:plc:example", 0, ["bot_like"])  # type: ignore[attr-defined]
        with pytest.raises(ToolInputError, match="days"):
            await clickhouse_rule_summary.__wrapped__("did:plc:example", 366, ["bot_like"])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_rule_summary_backend_failure(self, fixture_catalogue):
        """Both the verify and execute stages surface classified BackendError."""
        # Execute stage: schema verification fails.
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.side_effect = BackendError(
                kind="backend_unavailable", retryable=True, query_id="q-1"
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(BackendError) as exc_info:
                await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                    "did:plc:x", 7, ["bot_like"]
                )
            assert exc_info.value.kind == "backend_unavailable"
            assert exc_info.value.query_id == "q-1"

        # Execute stage: the rule query itself fails.
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.return_value = _columns_result()
            mock_client.query_trusted.side_effect = BackendError(
                kind="timeout", retryable=True, query_id="q-2", code=159
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(BackendError) as exc_info:
                await clickhouse_rule_summary.__wrapped__(  # type: ignore[attr-defined]
                    "did:plc:x", 7, ["bot_like"]
                )
            assert exc_info.value.kind == "timeout"
            assert exc_info.value.code == 159

    @pytest.mark.asyncio
    async def test_boundary_converts_backend_error_to_tool_error(self, fixture_catalogue):
        """Under the boundary, BackendError reaches clients as ToolError with JSON payload."""
        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_table_columns.side_effect = BackendError(
                kind="backend_unavailable", retryable=True, query_id="q-1"
            )
            mock_get_client.return_value = mock_client

            with pytest.raises(ToolError) as exc_info:
                await clickhouse_rule_summary("did:plc:x", 7, ["bot_like"])

        payload = json.loads(str(exc_info.value))
        assert payload["kind"] == "backend_unavailable"
        assert payload["query_id"] == "q-1"
        assert "unreachable" in payload["message"]
