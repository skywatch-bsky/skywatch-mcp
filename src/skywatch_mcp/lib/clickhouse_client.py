# pattern: Imperative Shell

"""ClickHouse client with classified failures and bounded execution.

Error classification: every driver failure is mapped to a ``BackendError``
carrying only structured, sanitized fields (``kind``, ``retryable``,
``query_id``, numeric ``code``). Classification parses only numeric signals
(ClickHouse exception code, HTTP status) out of the driver message; all
surrounding text — which can embed raw backend response bodies — is discarded
and never forwarded or logged. The client-visible message for each kind is a
fixed allowlisted string defined in ``lib/tool_errors.py``.

Correlation: every query gets a UUID ``query_id`` passed to the driver via
``transport_settings`` and echoed in success metadata and error payloads, so
``system.query_log`` and tool output correlate.

Result budget: ``serialize_rows`` enforces ``RESULT_BYTE_BUDGET`` (1 MiB,
provisional) against the final composed output text — columns, rows, meta,
indentation, and JSON escaping — with indivisible rows. Phase 0 measurement
(recorded outcomes and limit-by-evidentiary-status table):
``docs/measurements/2026-11-15-serialization-budget.md``.

Known limitation: output truncation does not bound driver-side memory —
result rows are fully materialized by the driver before budgeting. Memory is
bounded today only by the caller's LIMIT clause and server-side limits.
"""

import asyncio
import json
import logging
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from skywatch_mcp.config import ClickHouseSettings
from skywatch_mcp.lib.sql_validation import ValidationFailure, validate_query
from skywatch_mcp.lib.tool_errors import BackendError, ToolInputError

logger = logging.getLogger(__name__)

QUERY_DEADLINE_GRACE_SECONDS = 10

# Driver socket bound (D.5): must cover the largest per-call budget (120 s)
# plus grace (10 s). The installed driver's default is 300 s; asyncio.timeout
# cancellation cannot kill the executor thread's HTTP call, so this bound is
# what actually caps a hung socket.
DRIVER_SOCKET_TIMEOUT_SECONDS = 130

SCHEMA_TABLE_BUDGET_SECONDS = 10
SCHEMA_OVERALL_DEADLINE_SECONDS = 60

# Provisional pending live verification V.8 (effective ``max_query_size``);
# revision requires recorded measurement evidence in
# docs/measurements/2026-11-15-serialization-budget.md.
RESULT_BYTE_BUDGET = 1_048_576

SCHEMA_TABLES = [
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
]

# The rule-summary subject table (also SCHEMA_TABLES[0]).
OSPREY_RESULTS_TABLE = "default.osprey_execution_results"


@dataclass(frozen=True)
class QueryResult:
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]
    query_id: str | None = None
    elapsed_ms: int | None = None
    coverage: dict[str, Any] | None = None


# Numeric signals only. The driver's message bodies embed raw server response
# text; these regexes extract integers and discard everything else.
_CH_CODE_RE = re.compile(r"Received ClickHouse exception, code:\s*(\d+)")
_BODY_CODE_RE = re.compile(r"\bCode:\s*(\d+)[.\s]")
_HTTP_STATUS_RE = re.compile(r"HTTP driver received HTTP status\s*(\d+)")

# Stable driver phrasing for connection-level failures (no numeric code).
_UNAVAILABLE_PHRASES = (
    "executing http request attempt",
    "connection refused",
    "name or service not known",
    "temporary failure in name resolution",
    "connection reset",
)


def _extract_int(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    return int(match.group(1)) if match else None


def _classify_backend_exception(
    exc: Exception, query_id: str | None = None
) -> BackendError:
    """Map a driver exception to a classified BackendError (pattern: Functional Core).

    Verified against clickhouse-connect 0.15.1 formats: ``Received ClickHouse
    exception, code: N`` (header-based, httpclient._error_handler), ``Code: N.``
    embedded in server bodies, and ``HTTP driver received HTTP status N``.
    Unparseable signals degrade to kind ``unknown`` (retryable False) with the
    query_id for correlation — format drift never leaks text.
    """
    text = str(exc)
    if isinstance(exc, TimeoutError):
        # asyncio.timeout deadline expiry reaches the classifier directly in
        # some paths; there is no useful text to parse.
        return BackendError(kind="timeout", retryable=True, query_id=query_id)
    http_status = _extract_int(_HTTP_STATUS_RE, text)
    ch_code = _extract_int(_CH_CODE_RE, text)
    if ch_code is None:
        ch_code = _extract_int(_BODY_CODE_RE, text)

    def backend_error(kind: str, retryable: bool, code: int | None = None) -> BackendError:
        return BackendError(kind=kind, retryable=retryable, query_id=query_id, code=code)

    # HTTP status is the outermost signal; ClickHouse exception codes refine it.
    if http_status == 403:
        return backend_error("auth_failed", False, http_status)
    if http_status in (502, 503):
        return backend_error("backend_unavailable", True, http_status)
    if http_status == 504:
        return backend_error("timeout", True, http_status)
    if http_status == 413:
        return backend_error("request_too_large", False, http_status)

    if ch_code is not None:
        if ch_code == 516:
            return backend_error("auth_failed", False, ch_code)
        if ch_code in (47, 60, 62):
            return backend_error("invalid_sql", False, ch_code)
        if ch_code == 159:
            return backend_error("timeout", True, ch_code)
        if ch_code == 61:
            return backend_error("request_too_large", False, ch_code)
        if ch_code == 241:
            return backend_error("request_too_large", True, ch_code)
        # Unrecognized codes fall through to the connection-phrase checks so
        # e.g. "Code: 1000. name or service not known" still classifies as
        # backend_unavailable; anything else lands in unknown below.

    lowered = text.lower()
    if any(phrase in lowered for phrase in _UNAVAILABLE_PHRASES):
        return backend_error("backend_unavailable", True)
    if "max query size exceeded" in lowered:
        return backend_error("request_too_large", False)
    return backend_error("unknown", False, ch_code)


def _utf8_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _compose_output(
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    meta: dict[str, Any],
    indent: int | None,
) -> str:
    return json.dumps(
        {"columns": columns, "rows": rows, "meta": meta},
        indent=indent,
        default=str,
    )


def _truncation_meta(rows_returned: int, first_oversized: bool) -> dict[str, Any]:
    meta: dict[str, Any] = {"truncated": True, "rows_returned": rows_returned}
    if first_oversized:
        meta["note"] = _OVERSIZED_FIRST_ROW_NOTE
    return meta


_OVERSIZED_FIRST_ROW_NOTE = (
    "The first row alone exceeded the result byte budget; it was omitted."
)


def serialize_rows(
    columns: list[dict[str, str]],
    rows: list[dict[str, Any]],
    extra_meta: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Serialize rows under RESULT_BYTE_BUDGET (pattern: Functional Core).

    Budget is measured on the final composed text (columns + rows + meta +
    escaping + indentation) in UTF-8 bytes — measured via the Phase 0 artifact,
    not on the rows slice alone. Rows are indivisible: appended while the
    composed output fits; overflow stops inclusion. If even the first row does
    not fit, it is omitted and ``meta.note`` says so. Fully-fitting responses
    keep ``indent=2``; if pretty-printing alone overflows the budget, the
    compact complete form is returned (still ``truncated: false``); truncated
    responses are compact JSON. If a zero-row response itself exceeds the
    budget (pathological metadata only), the minimal payload is returned
    best-effort with ``truncated: true``.

    Admission on the truncation path pre-encodes each row once and accounts
    bytes incrementally against a conservative meta upper bound, so it is
    linear in total output size (not quadratic recomposition) and composes the
    final text exactly once; a safety loop drops rows only if the conservative
    margin was ever off.
    """
    extras = extra_meta or {}
    complete_meta: dict[str, Any] = {"truncated": False, "rows_returned": len(rows), **extras}
    complete = _compose_output(columns, rows, complete_meta, indent=2)
    if _utf8_len(complete) <= RESULT_BYTE_BUDGET:
        return complete, complete_meta

    # Pretty-printing alone can overflow the budget; try the compact form
    # before dropping any rows.
    compact_complete = _compose_output(columns, rows, complete_meta, indent=None)
    if _utf8_len(compact_complete) <= RESULT_BYTE_BUDGET:
        return compact_complete, complete_meta

    # Truncation path: incremental admission with pre-encoded rows.
    row_jsons = [json.dumps(row, default=str) for row in rows]
    prefix = '{"columns": ' + json.dumps(columns, default=str) + ', "rows": ['
    # Conservative meta bound WITHOUT the note: the note appears only when zero
    # rows are admitted (final text is then tiny), so admission must not pay
    # for it — otherwise a first row that fits with plain truncation metadata
    # would be falsely rejected as oversized.
    max_meta = _truncation_meta(len(rows), first_oversized=False)
    max_meta.update(extras)
    meta_overhead = (
        _utf8_len(', "meta": ') + _utf8_len(json.dumps(max_meta, default=str)) + 1
    )
    separator_len = _utf8_len(", ")

    included = 0
    used = _utf8_len(prefix) + meta_overhead
    first_row_oversized = False
    for index, row_json in enumerate(row_jsons):
        candidate = used + _utf8_len(row_json) + (separator_len if included else 0)
        if candidate > RESULT_BYTE_BUDGET:
            first_row_oversized = index == 0
            break
        used = candidate
        included += 1

    if rows and included == len(rows):
        # Unreachable here (compact complete already failed), kept as a guard.
        final_meta: dict[str, Any] = {"truncated": False, "rows_returned": len(rows), **extras}
    else:
        final_meta = _truncation_meta(included, first_oversized=first_row_oversized)
        final_meta.update(extras)
    text = _compose_output(columns, rows[:included], final_meta, indent=None)
    while included and _utf8_len(text) > RESULT_BYTE_BUDGET:
        # Safety net only: the conservative accounting guarantees fit, so this
        # loop should never admit-remove more than a row in practice.
        included -= 1
        final_meta = _truncation_meta(
            included, first_oversized=first_row_oversized and included == 0
        )
        final_meta.update(extras)
        text = _compose_output(columns, rows[:included], final_meta, indent=None)
    return text, final_meta


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            # Redact the driver's own logging namespace: httpclient._error_handler
            # logs raw error-response bodies at WARNING. ERROR level suppresses
            # that path; application logging discipline is enforced separately
            # (we log only kind/code/query_id).
            logging.getLogger("clickhouse_connect").setLevel(logging.ERROR)
            self._client = await clickhouse_connect.get_async_client(
                host=self._settings.effective_host.replace("http://", "").replace("https://", ""),
                port=self._settings.port,
                username=self._settings.user,
                password=self._settings.password,
                database=self._settings.database,
                send_receive_timeout=DRIVER_SOCKET_TIMEOUT_SECONDS,
            )
        return self._client

    async def _execute_query(
        self,
        sql: str,
        max_execution_time: int,
        parameters: dict[str, Any] | None = None,
    ) -> QueryResult:
        query_id = str(uuid.uuid4())
        deadline = max_execution_time + QUERY_DEADLINE_GRACE_SECONDS
        started = time.monotonic()
        try:
            async with asyncio.timeout(deadline):
                client = await self._get_client()
                result = await client.query(
                    query=sql,
                    parameters=parameters,
                    settings={"max_execution_time": max_execution_time},
                    transport_settings={"query_id": query_id},
                )
        except TimeoutError as exc:
            self._client = None
            failure = BackendError(kind="timeout", retryable=True, query_id=query_id)
            logger.warning(
                "clickhouse query failed: kind=%s code=%s query_id=%s",
                failure.kind,
                failure.code,
                failure.query_id,
            )
            raise failure from exc
        except Exception as exc:
            self._client = None
            failure = _classify_backend_exception(exc, query_id=query_id)
            logger.warning(
                "clickhouse query failed: kind=%s code=%s query_id=%s",
                failure.kind,
                failure.code,
                failure.query_id,
            )
            raise failure from exc

        elapsed_ms = int((time.monotonic() - started) * 1000)
        columns = [
            {"name": name, "type": col_type}
            for name, col_type in zip(result.column_names, result.column_types, strict=True)
        ]
        rows = [
            dict(zip(result.column_names, row, strict=True))
            for row in result.result_rows
        ]
        return QueryResult(
            columns=columns, rows=rows, query_id=query_id, elapsed_ms=elapsed_ms
        )

    async def query(self, sql: str) -> QueryResult:
        validation = validate_query(sql)
        if isinstance(validation, ValidationFailure):
            raise ToolInputError(f"Query validation failed: {validation.reason}")
        return await self._execute_query(validation.normalized, 60)

    async def query_trusted(
        self,
        sql: str,
        *,
        max_execution_time: int = 120,
        parameters: dict[str, Any] | None = None,
    ) -> QueryResult:
        return await self._execute_query(sql, max_execution_time, parameters=parameters)

    async def get_table_columns(self, table: str) -> QueryResult:
        """One bounded DESCRIBE of a single table, with scope-relative coverage."""
        result = await self._execute_query(
            f"DESCRIBE TABLE {table}", SCHEMA_TABLE_BUDGET_SECONDS
        )
        return QueryResult(
            columns=result.columns,
            rows=result.rows,
            query_id=result.query_id,
            elapsed_ms=result.elapsed_ms,
            coverage={"tables_expected": 1, "tables_matched": 1, "tables_missing": []},
        )

    async def get_schema(self) -> QueryResult:
        """Explicit bounded per-table DESCRIBE over SCHEMA_TABLES.

        Legacy source preserved byte-exactly: per-table ``DESCRIBE TABLE <t>``
        with rows tagged by fully qualified ``table``. Failure semantics:
        a global failure class (backend_unavailable, auth_failed, timeout,
        request_too_large, unknown) aborts the loop and raises that classified
        BackendError; a per-table invalid_sql (e.g. unknown table) is recorded
        in coverage.tables_missing with its numeric code and the loop
        continues. All tables failed → classified BackendError from the
        representative failure — never an empty success. The whole loop runs
        under a 60 s deadline so the pathological all-failure case stays
        bounded (per-table budget is 10 s + 10 s grace).
        """
        schema_query_id = str(uuid.uuid4())
        started = time.monotonic()
        all_rows: list[dict[str, Any]] = []
        schema_columns: list[dict[str, str]] = []
        tables_missing: list[dict[str, Any]] = []
        matched = 0
        try:
            async with asyncio.timeout(SCHEMA_OVERALL_DEADLINE_SECONDS):
                for table in SCHEMA_TABLES:
                    try:
                        result = await self.get_table_columns(table)
                    except BackendError as exc:
                        if exc.kind == "invalid_sql":
                            tables_missing.append({"table": table, "code": exc.code})
                            continue
                        raise
                    all_rows.extend({**row, "table": table} for row in result.rows)
                    if not schema_columns:
                        schema_columns = [
                            *result.columns,
                            {"name": "table", "type": "String"},
                        ]
                    matched += 1
        except TimeoutError as exc:
            failure = BackendError(
                kind="timeout", retryable=True, query_id=schema_query_id
            )
            logger.warning(
                "clickhouse schema fetch failed: kind=%s code=%s query_id=%s",
                failure.kind,
                failure.code,
                failure.query_id,
            )
            raise failure from exc

        if matched == 0 and tables_missing:
            representative = tables_missing[0]
            failure = BackendError(
                kind="invalid_sql",
                retryable=False,
                code=representative.get("code"),
                query_id=schema_query_id,
            )
            logger.warning(
                "clickhouse schema fetch failed: kind=%s code=%s query_id=%s",
                failure.kind,
                failure.code,
                failure.query_id,
            )
            raise failure

        elapsed_ms = int((time.monotonic() - started) * 1000)
        coverage = {
            "tables_expected": len(SCHEMA_TABLES),
            "tables_matched": matched,
            "tables_missing": tables_missing,
        }
        return QueryResult(
            columns=schema_columns,
            rows=all_rows,
            query_id=schema_query_id,
            elapsed_ms=elapsed_ms,
            coverage=coverage,
        )


# Share one client across tool modules.
_client: ClickHouseClient | None = None


def get_client() -> ClickHouseClient:
    global _client
    if _client is None:
        _client = ClickHouseClient(ClickHouseSettings())
    return _client
