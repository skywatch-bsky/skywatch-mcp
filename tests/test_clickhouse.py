import json
import logging

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from clickhouse_connect.driver.exceptions import (
    DatabaseError,
    OperationalError,
    ProgrammingError,
)

from skywatch_mcp.lib.clickhouse_client import (
    ClickHouseClient,
    QueryResult,
    RESULT_BYTE_BUDGET,
    SCHEMA_TABLES,
    _classify_backend_exception,
    serialize_rows,
)
from skywatch_mcp.lib.tool_errors import BackendError
from skywatch_mcp.config import ClickHouseSettings

SENTINEL = "SENTINEL-SECRET-BACKEND-BODY"


def _mock_query_result(columns, rows):
    mock = MagicMock()
    mock.column_names = columns
    mock.column_types = ["String"] * len(columns)
    mock.result_rows = rows
    return mock


class TestBackendClassification:
    """D.3 classification matrix: driver exception shapes → BackendError."""

    @pytest.mark.parametrize(
        ("exc", "kind", "retryable", "code"),
        [
            # Deadline-wrapper timeout (asyncio.timeout raises TimeoutError)
            (TimeoutError(), "timeout", True, None),
            # Connection-level failures (httpclient retry loop phrasing)
            (
                OperationalError(
                    f"Error {SENTINEL} executing HTTP request attempt 1"
                    f"(for url http://{SENTINEL}:8123/)"
                ),
                "backend_unavailable",
                True,
                None,
            ),
            (
                OperationalError("Connection refused by 10.0.0.1"),
                "backend_unavailable",
                True,
                None,
            ),
            (
                OperationalError("Code: 1000. DNS problem: name or service not known"),
                "backend_unavailable",
                True,
                None,
            ),
            # Authentication
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 516, server response: {SENTINEL}"
                ),
                "auth_failed",
                False,
                516,
            ),
            (
                DatabaseError(f"HTTP driver received HTTP status 403, server response: {SENTINEL}"),
                "auth_failed",
                False,
                403,
            ),
            # Invalid SQL: parse error 62, unknown table 60, unknown function 47
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 62, server response: "
                    f"Code: 62.\nDB::Exception: Syntax error {SENTINEL}"
                ),
                "invalid_sql",
                False,
                62,
            ),
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 60, server response: {SENTINEL}"
                ),
                "invalid_sql",
                False,
                60,
            ),
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 47, server response: {SENTINEL}"
                ),
                "invalid_sql",
                False,
                47,
            ),
            # Server-side execution timeout
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 159, server response: {SENTINEL}"
                ),
                "timeout",
                True,
                159,
            ),
            # Request too large: query size 61, memory 241, HTTP 413
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 61, server response: {SENTINEL}"
                ),
                "request_too_large",
                False,
                61,
            ),
            (
                OperationalError("Max query size exceeded: requested 999999"),
                "request_too_large",
                False,
                None,
            ),
            (
                DatabaseError(f"HTTP driver received HTTP status 413, server response: {SENTINEL}"),
                "request_too_large",
                False,
                413,
            ),
            (
                DatabaseError(
                    f"Received ClickHouse exception, code: 241, server response: {SENTINEL}"
                ),
                "request_too_large",
                True,
                241,
            ),
            # Gateway failures
            (
                DatabaseError(f"HTTP driver received HTTP status 502, server response: {SENTINEL}"),
                "backend_unavailable",
                True,
                502,
            ),
            (
                DatabaseError(f"HTTP driver received HTTP status 503, server response: {SENTINEL}"),
                "backend_unavailable",
                True,
                503,
            ),
            (
                DatabaseError(f"HTTP driver received HTTP status 504, server response: {SENTINEL}"),
                "timeout",
                True,
                504,
            ),
            # Unrecognized
            (RuntimeError("mystery failure"), "unknown", False, None),
            (
                ProgrammingError(f"totally unexpected: {SENTINEL}"),
                "unknown",
                False,
                None,
            ),
        ],
    )
    def test_classification_matrix(self, exc, kind, retryable, code):
        classified = _classify_backend_exception(exc, query_id="q-1")
        assert isinstance(classified, BackendError)
        assert classified.kind == kind
        assert classified.retryable is retryable
        assert classified.code == code
        assert classified.query_id == "q-1"

    def test_allowlisted_messages_only(self):
        """Every classification produces exactly the fixed text with only the code substituted."""
        for exc, expected_message, marker in [
            (TimeoutError(), "Query exceeded its execution budget. Narrow the query or reduce the LIMIT.", None),
            (
                OperationalError("Error x executing HTTP request attempt 1"),
                "ClickHouse backend is unreachable. Verify the service is running, then retry.",
                "executing HTTP request attempt",
            ),
            (
                DatabaseError("Received ClickHouse exception, code: 516, server response: body"),
                "ClickHouse authentication failed. Check the CLICKHOUSE_USER and "
                "CLICKHOUSE_PASSWORD configuration.",
                "body",
            ),
            (
                DatabaseError("Received ClickHouse exception, code: 62, server response: body"),
                "ClickHouse rejected the query (code 62). Check table and column names with clickhouse_schema.",
                "body",
            ),
            (
                DatabaseError("Received ClickHouse exception, code: 61, server response: body"),
                "Query exceeded a size or memory limit (code 61). Split the query or narrow columns and rows.",
                "body",
            ),
            (
                DatabaseError("Received ClickHouse exception, code: 241, server response: body"),
                "Query exceeded a size or memory limit (code 241). Split the query or narrow columns and rows.",
                "body",
            ),
            (
                DatabaseError("Received ClickHouse exception, code: 159, server response: body"),
                "Query exceeded its execution budget. Narrow the query or reduce the LIMIT.",
                "body",
            ),
            (
                DatabaseError("HTTP driver received HTTP status 504, server response: body"),
                "Query exceeded its execution budget. Narrow the query or reduce the LIMIT.",
                "server response",
            ),
            (
                RuntimeError("unrecognized-weird-text"),
                "ClickHouse returned an unrecognized error (code unknown). Use query_id for server-side correlation.",
                "unrecognized-weird-text",
            ),
        ]:
            classified = _classify_backend_exception(exc, query_id="q")
            payload = classified.to_payload()
            assert payload["message"] == expected_message
            serialized = json.dumps(payload)
            if marker is not None:
                assert marker not in serialized

    def test_adversarial_error_content_absent(self):
        """Sentinels in code header, body, multiline bodies, and unknown types never surface."""
        adversarial = [
            DatabaseError(
                f"Received ClickHouse exception, code: 62, server response: "
                f"Code: 62.\nDB::Exception: user {SENTINEL} password hunter2 "
                f"SELECT * FROM secret Table: {SENTINEL}"
            ),
            OperationalError(
                f"Error <class 'httpx.ConnectError'> executing HTTP request attempt 3 "
                f"(for url http://{SENTINEL}:8123/?user=admin)"
            ),
            RuntimeError(f"raw: {SENTINEL}"),
        ]
        for exc in adversarial:
            classified = _classify_backend_exception(exc, query_id="q-9")
            payload_json = json.dumps(classified.to_payload())
            assert SENTINEL not in payload_json
            assert "hunter2" not in payload_json
            assert "http://" not in payload_json
            assert "admin" not in payload_json
            # The exception's own text stays in-process (cause chain), not in the payload.
            assert str(classified) == classified.message

    @pytest.mark.asyncio
    async def test_client_failure_log_is_sanitized(self, caplog):
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            failing = AsyncMock()
            failing.query.side_effect = DatabaseError(
                f"Received ClickHouse exception, code: 516, server response: {SENTINEL}"
            )
            mock_get.return_value = failing
            client = ClickHouseClient(ClickHouseSettings())
            with caplog.at_level(logging.WARNING, logger="skywatch_mcp.lib.clickhouse_client"):
                with pytest.raises(BackendError):
                    await client.query_trusted("SELECT 1")

        assert "kind=auth_failed" in caplog.text
        assert "code=516" in caplog.text
        assert SENTINEL not in caplog.text
        assert "516, server response" not in caplog.text

    @pytest.mark.asyncio
    async def test_driver_error_logging_redacted(self, caplog, capsys):
        """The driver's own WARNING body-read path is suppressed by configuration."""
        from clickhouse_connect.driver import httpclient as hc_module

        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_get.return_value = AsyncMock()
            client = ClickHouseClient(ClickHouseSettings())
            await client._get_client()  # applies the logging redaction

        assert logging.getLogger("clickhouse_connect").level == logging.ERROR

        fake_self = MagicMock()
        fake_self.show_clickhouse_errors = True
        fake_self.url = f"http://driver-host/{SENTINEL}-url"
        fake_response = MagicMock()
        fake_response.headers = {"X-ClickHouse-Exception-Code": "62"}
        fake_response.status = 500

        with caplog.at_level(logging.DEBUG, logger=""):
            with patch.object(
                hc_module,
                "get_response_data",
                side_effect=RuntimeError(f"body read failed: {SENTINEL}"),
            ):
                with pytest.raises(DatabaseError) as exc_info:
                    hc_module.HttpClient._error_handler(fake_self, fake_response)

        raised = str(exc_info.value)
        assert "code: 62" in raised  # numeric signal preserved
        assert SENTINEL not in caplog.text
        assert SENTINEL not in capsys.readouterr().err

    @pytest.mark.asyncio
    async def test_query_id_is_generated_and_passed(self):
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(["v"], [[1]])
            mock_get.return_value = driver
            client = ClickHouseClient(ClickHouseSettings())
            result = await client.query_trusted("SELECT 1")

            call_kwargs = driver.query.call_args[1]
            passed_id = call_kwargs["transport_settings"]["query_id"]
            assert passed_id == result.query_id
            assert len(passed_id) == 36  # uuid4 string

    @pytest.mark.asyncio
    async def test_error_includes_query_id(self):
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.side_effect = DatabaseError(
                f"Received ClickHouse exception, code: 62, server response: {SENTINEL}"
            )
            mock_get.return_value = driver
            client = ClickHouseClient(ClickHouseSettings())
            with pytest.raises(BackendError) as exc_info:
                await client.query_trusted("SELECT 1")

            passed_id = driver.query.call_args[1]["transport_settings"]["query_id"]
            assert exc_info.value.query_id == passed_id
            assert exc_info.value.to_payload()["query_id"] == passed_id

    @pytest.mark.asyncio
    async def test_send_receive_timeout_bounded(self):
        """Client construction bounds the driver socket at 130 s (D.5)."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_get.return_value = AsyncMock()
            client = ClickHouseClient(ClickHouseSettings())
            await client._get_client()

            assert mock_get.call_args[1]["send_receive_timeout"] == 130

    @pytest.mark.asyncio
    async def test_timeout_settings_retained(self):
        """Per-call max_execution_time settings retained for query/query_trusted."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(["v"], [[1]])
            mock_get.return_value = driver
            client = ClickHouseClient(ClickHouseSettings())

            await client.query("SELECT 1 LIMIT 1")
            assert driver.query.call_args[1]["settings"]["max_execution_time"] == 60

            await client.query_trusted("SELECT 1")
            assert driver.query.call_args[1]["settings"]["max_execution_time"] == 120

            await client.query_trusted("SELECT 1", max_execution_time=5)
            assert driver.query.call_args[1]["settings"]["max_execution_time"] == 5


class TestClickHouseClient:

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

            mock_async_client.query.return_value = _mock_query_result(
                ["id", "name"], [[1, "test"], [2, "test2"]]
            )

            client = ClickHouseClient(mock_settings)
            result = await client.query("SELECT id, name FROM users LIMIT 10")

            assert isinstance(result, QueryResult)
            assert result.columns == [
                {"name": "id", "type": "String"},
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

            mock_async_client.query.return_value = _mock_query_result(["result"], [[42]])

            client = ClickHouseClient(mock_settings)
            result = await client.query_trusted("SELECT 42")

            assert isinstance(result, QueryResult)
            assert result.columns == [{"name": "result", "type": "String"}]
            assert result.rows == [{"result": 42}]

    @pytest.mark.asyncio
    async def test_query_trusted_forwards_bound_parameters(self, mock_settings):
        """query_trusted(parameters=...) forwards the mapping to the driver (D.12)."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(["result"], [[42]])
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            await client.query_trusted(
                "SELECT {v:UInt8}", parameters={"v": 1}
            )

            call_kwargs = driver.query.call_args[1]
            assert call_kwargs["parameters"] == {"v": 1}

    @pytest.mark.asyncio
    async def test_query_without_parameters_passes_none(self, mock_settings):
        """Plain query() forwards parameters=None — no interpolation path."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(["v"], [[1]])
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            await client.query("SELECT 1 LIMIT 1")

            assert driver.query.call_args[1]["parameters"] is None

    @pytest.mark.asyncio
    async def test_client_should_use_async_methods(self, mock_settings):
        """Client should use AsyncClient.query (async)"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_result = _mock_query_result(["test"], [["value"]])
            mock_async_client.query = AsyncMock(return_value=mock_result)

            client = ClickHouseClient(mock_settings)
            await client.query_trusted("SELECT 'test' LIMIT 1")

            mock_async_client.query.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_failure_should_classify_and_discard_cached_client(self, mock_settings):
        """A driver failure raises a classified BackendError and resets the cache."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            failed_client = AsyncMock()
            failed_client.query.side_effect = RuntimeError("connection lost")
            recovered_client = AsyncMock()
            recovered_client.query.return_value = _mock_query_result(["value"], [[1]])
            mock_get.side_effect = [failed_client, recovered_client]

            client = ClickHouseClient(mock_settings)
            with pytest.raises(BackendError) as exc_info:
                await client.query_trusted("SELECT 1")

            assert exc_info.value.kind == "unknown"
            assert client._client is None

            result = await client.query_trusted("SELECT 1")

            assert result.rows == [{"value": 1}]
            assert mock_get.await_count == 2

    @pytest.mark.asyncio
    async def test_query_timeout_should_be_bounded_and_classified(self, mock_settings):
        """Deadline expiry raises BackendError(kind=timeout) and resets the cache."""
        timeout_context = AsyncMock()
        timeout_context.__aenter__.side_effect = TimeoutError

        with (
            patch("skywatch_mcp.lib.clickhouse_client.asyncio.timeout", return_value=timeout_context),
            patch(
                "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
            ) as mock_get,
        ):
            client = ClickHouseClient(mock_settings)

            with pytest.raises(BackendError) as exc_info:
                await client.query_trusted("SELECT 1")

            assert exc_info.value.kind == "timeout"
            assert exc_info.value.retryable is True
            assert client._client is None
            mock_get.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_query_should_set_60_second_timeout(self, mock_settings):
        """query() should use 60s max_execution_time"""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            mock_async_client = AsyncMock()
            mock_get.return_value = mock_async_client

            mock_async_client.query.return_value = _mock_query_result(["test"], [["value"]])

            client = ClickHouseClient(mock_settings)
            await client.query("SELECT 1 LIMIT 1")

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

            mock_async_client.query.return_value = _mock_query_result(["test"], [["value"]])

            client = ClickHouseClient(mock_settings)
            await client.query_trusted("SELECT 1")

            call_args = mock_async_client.query.call_args
            assert call_args[1]["settings"]["max_execution_time"] == 120


class TestSchemaFetch:
    """D.6/D.7: explicit bounded per-table DESCRIBE with coverage metadata."""

    LEGACY_KEYS = [
        "name",
        "type",
        "default_kind",
        "default_expression",
        "comment",
        "codec_expression",
        "ttl_expression",
    ]

    @pytest.fixture
    def mock_settings(self):
        return ClickHouseSettings(
            host="http://localhost",
            port=8123,
            user="default",
            password="",
            database="default",
        )

    @pytest.mark.asyncio
    async def test_zero_arg_schema_matches_legacy_describe_contract(self, mock_settings):
        """Legacy passthrough: DESCRIBE row keys + fully qualified table tagging."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            described_rows = [
                ["col_a", "UInt64", "", "", "", "", ""],
                ["col_b", "String", "", "", "a comment", "LZ4", ""],
            ]
            driver.query.side_effect = [
                _mock_query_result(self.LEGACY_KEYS, described_rows)
                for _ in SCHEMA_TABLES
            ]
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            result = await client.get_schema()

            expected_keys = set(self.LEGACY_KEYS) | {"table"}
            assert result.rows, "legacy schema must never be empty on success"
            for row in result.rows:
                assert set(row.keys()) == expected_keys
            tagged_tables = {row["table"] for row in result.rows}
            assert tagged_tables == set(SCHEMA_TABLES)
            for row in result.rows:
                assert row["table"].startswith("default.")
            assert result.columns[:-1] == [
                {"name": key, "type": "String"} for key in self.LEGACY_KEYS
            ]
            assert result.columns[-1] == {"name": "table", "type": "String"}
            assert driver.query.call_count == len(SCHEMA_TABLES)
            assert result.coverage == {
                "tables_expected": len(SCHEMA_TABLES),
                "tables_matched": len(SCHEMA_TABLES),
                "tables_missing": [],
            }

    @pytest.mark.asyncio
    async def test_schema_per_table_missing_metadata_recorded(self, mock_settings):
        """One unknown table among valid ones: loop continues, code recorded."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            effects = []
            missing_table = SCHEMA_TABLES[3]
            for table in SCHEMA_TABLES:
                if table == missing_table:
                    effects.append(
                        DatabaseError(
                            f"Received ClickHouse exception, code: 60, server response: "
                            f"Code: 60.\nDB::Exception: Table {table} does not exist"
                        )
                    )
                else:
                    effects.append(_mock_query_result(["name", "type"], [["col", "UInt64"]]))
            driver.query.side_effect = effects
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            result = await client.get_schema()

            assert driver.query.call_count == len(SCHEMA_TABLES)  # loop continued
            assert result.coverage is not None
            assert result.coverage["tables_matched"] == len(SCHEMA_TABLES) - 1
            assert result.coverage["tables_missing"] == [
                {"table": missing_table, "code": 60}
            ]
            assert len(result.rows) == len(SCHEMA_TABLES) - 1

    @pytest.mark.asyncio
    async def test_schema_global_failure_fails_fast(self, mock_settings):
        """backend_unavailable on the first table aborts the loop immediately."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.side_effect = OperationalError(
                "Error <class 'httpx.ConnectError'> executing HTTP request attempt 1"
            )
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            with pytest.raises(BackendError) as exc_info:
                await client.get_schema()

            assert exc_info.value.kind == "backend_unavailable"
            assert exc_info.value.retryable is True
            assert driver.query.call_count == 1  # remaining tables never called

    @pytest.mark.asyncio
    async def test_schema_backend_down_is_explicit_failure(self, mock_settings):
        """A stopped backend never yields {'columns': [], 'rows': []} as success."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.side_effect = OperationalError(
                "Connection refused by 127.0.0.1"
            )
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            with pytest.raises(BackendError) as exc_info:
                await client.get_schema()

            failure_json = json.dumps(exc_info.value.to_payload())
            assert '"kind": "backend_unavailable"' in failure_json
            assert '"rows": []' not in failure_json  # it is an error, not a payload

    @pytest.mark.asyncio
    async def test_schema_partial_table_coverage_metadata(self, mock_settings):
        """Several per-table failures: success with explicit numeric codes."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            effects = []
            missing = [SCHEMA_TABLES[1], SCHEMA_TABLES[6]]
            for table in SCHEMA_TABLES:
                if table in missing:
                    effects.append(
                        DatabaseError(
                            "Received ClickHouse exception, code: 60, server response: x"
                        )
                    )
                else:
                    effects.append(_mock_query_result(["name", "type"], [["col", "UInt8"]]))
            driver.query.side_effect = effects
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            result = await client.get_schema()

            assert result.coverage == {
                "tables_expected": len(SCHEMA_TABLES),
                "tables_matched": len(SCHEMA_TABLES) - 2,
                "tables_missing": [
                    {"table": missing[0], "code": 60},
                    {"table": missing[1], "code": 60},
                ],
            }

    @pytest.mark.asyncio
    async def test_schema_overall_deadline_enforced(self, mock_settings, monkeypatch):
        """The 60 s overall schema deadline bounds the all-failure loop."""
        import skywatch_mcp.lib.clickhouse_client as ch_module

        monkeypatch.setattr(ch_module, "SCHEMA_OVERALL_DEADLINE_SECONDS", 0.05)

        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(["name", "type"], [["c", "UInt8"]])
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)

            async def slow_describe(table):
                import asyncio

                await asyncio.sleep(0.5)
                return await client._execute_query(f"DESCRIBE TABLE {table}", 10)

            monkeypatch.setattr(client, "get_table_columns", slow_describe)
            with pytest.raises(BackendError) as exc_info:
                await client.get_schema()

            assert exc_info.value.kind == "timeout"
            assert driver.query.call_count < len(SCHEMA_TABLES)

    @pytest.mark.asyncio
    async def test_schema_selection_by_table_single_describe(self, mock_settings):
        """get_table_columns issues exactly one DESCRIBE with scope-relative coverage."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.return_value = _mock_query_result(
                ["name", "type"], [["AtUri", "String"]]
            )
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            result = await client.get_table_columns("default.osprey_execution_results")

            assert driver.query.call_count == 1
            assert driver.query.call_args[1]["query"] == "DESCRIBE TABLE default.osprey_execution_results"
            assert result.coverage == {
                "tables_expected": 1,
                "tables_matched": 1,
                "tables_missing": [],
            }

    @pytest.mark.asyncio
    async def test_compact_unknown_table_classified_invalid_sql(self, mock_settings):
        """A missing table's DESCRIBE classifies as invalid_sql with code 60."""
        with patch(
            "skywatch_mcp.lib.clickhouse_client.clickhouse_connect.get_async_client"
        ) as mock_get:
            driver = AsyncMock()
            driver.query.side_effect = DatabaseError(
                "Received ClickHouse exception, code: 60, server response: missing"
            )
            mock_get.return_value = driver

            client = ClickHouseClient(mock_settings)
            with pytest.raises(BackendError) as exc_info:
                await client.get_table_columns("default.does_not_exist")

            assert exc_info.value.kind == "invalid_sql"
            assert exc_info.value.code == 60


class TestSerializeRows:
    """D.9: budget over the final composed text, indivisible rows."""

    COLUMNS = [{"name": "id", "type": "UInt64"}, {"name": "text", "type": "String"}]

    def _row(self, size: int, filler: str = "x") -> dict:
        return {"id": 1, "text": filler * size}

    def test_complete_response_indented_and_within_budget(self):
        rows = [self._row(10), self._row(20)]
        text, meta = serialize_rows(self.COLUMNS, rows, extra_meta={"query_id": "q1", "elapsed_ms": 5})
        assert len(text.encode("utf-8")) <= RESULT_BYTE_BUDGET
        assert meta == {"truncated": False, "rows_returned": 2, "query_id": "q1", "elapsed_ms": 5}
        assert "\n" in text  # indent=2 preserved

    def test_truncation_metadata_on_oversized_results(self):
        """Multibyte + escaped content around byte boundaries; rows are indivisible."""
        multibyte_row = {"id": 1, "text": "日本語🚀" * 300_000}
        escaped_row = {"id": 2, "text": '"\\n\\t"' * 100_000}
        rows = [self._row(10), multibyte_row, escaped_row]
        text, meta = serialize_rows(self.COLUMNS, rows)

        assert meta["truncated"] is True
        assert meta["rows_returned"] == 1  # only the small row fits
        assert json.loads(text)["rows"] == [rows[0]]
        # Budget enforced on the final text in UTF-8 bytes.
        assert len(text.encode("utf-8")) <= RESULT_BYTE_BUDGET
        # Compact JSON when truncated.
        assert "\n" not in text

    def test_oversized_first_row_omitted_with_note(self):
        """A single row larger than the budget is omitted; meta states it."""
        huge_row = {"id": 1, "text": "x" * (RESULT_BYTE_BUDGET + 100_000)}
        rows = [huge_row, self._row(5)]
        text, meta = serialize_rows(self.COLUMNS, rows)

        assert meta["truncated"] is True
        assert meta["rows_returned"] == 0
        assert "first row alone exceeded" in meta["note"]
        assert json.loads(text)["rows"] == []

    def test_first_row_admitted_without_note_overhead(self, monkeypatch):
        """A first row that fits with plain truncation meta must not be rejected
        because the oversized-first-row note (which applies only to the zero-row
        fallback) was counted against it."""
        import skywatch_mcp.lib.clickhouse_client as ch_module

        row0 = self._row(40)
        row1 = self._row(200)
        plain_probe_meta = {"truncated": True, "rows_returned": 1}
        base = len(
            json.dumps(
                {"columns": self.COLUMNS, "rows": [row0], "meta": plain_probe_meta},
                default=str,
            ).encode("utf-8")
        )
        # Budget admits row 0 with plain meta but NOT if the note were counted.
        note_cost = len(
            (', "note": ' + json.dumps(ch_module._OVERSIZED_FIRST_ROW_NOTE)).encode("utf-8")
        )
        monkeypatch.setattr(ch_module, "RESULT_BYTE_BUDGET", base + note_cost - 1)
        text, meta = serialize_rows(self.COLUMNS, [row0, row1])

        assert meta["truncated"] is True
        assert meta["rows_returned"] == 1
        assert "note" not in meta
        assert json.loads(text)["rows"] == [row0]

    def test_pathological_zero_row_over_budget_is_best_effort(self, monkeypatch):
        """Metadata-only overflow still returns a minimal payload."""
        import skywatch_mcp.lib.clickhouse_client as ch_module

        monkeypatch.setattr(ch_module, "RESULT_BYTE_BUDGET", 10)
        text, meta = serialize_rows(self.COLUMNS, [])
        assert meta["truncated"] is True
        assert meta["rows_returned"] == 0
        parsed = json.loads(text)
        assert parsed["rows"] == []

    def test_zero_row_success_shape(self):
        text, meta = serialize_rows(self.COLUMNS, [], extra_meta={"query_id": "q", "elapsed_ms": 1})
        parsed = json.loads(text)
        assert parsed["rows"] == []
        assert parsed["columns"] == self.COLUMNS
        assert meta["truncated"] is False

    def test_all_rows_fit_compactly_when_indentation_overflows(self, monkeypatch):
        """Pretty-printing alone over budget but compact complete output fits."""
        import skywatch_mcp.lib.clickhouse_client as ch_module

        rows = [self._row(30) for _ in range(10)]
        compact_len = len(
            json.dumps(
                {
                    "columns": self.COLUMNS,
                    "rows": rows,
                    "meta": {"truncated": False, "rows_returned": len(rows)},
                },
                default=str,
            ).encode("utf-8")
        )
        monkeypatch.setattr(ch_module, "RESULT_BYTE_BUDGET", compact_len)
        text, meta = serialize_rows(self.COLUMNS, rows)
        assert meta["truncated"] is False
        assert meta["rows_returned"] == 10
        assert json.loads(text)["rows"] == rows


class TestSchemaTables:

    def test_should_have_11_tables(self):
        assert len(SCHEMA_TABLES) == 12

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
            "default.url_cosharing_runs",
            "default.quote_cosharing_pairs",
            "default.quote_cosharing_clusters",
            "default.quote_cosharing_membership",
            "default.quote_overdispersion_results",
        }
        assert set(SCHEMA_TABLES) == expected
