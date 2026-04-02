# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — TS source and clickhouse-connect async API researched

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.1 Success:** `clickhouse_query` executes valid SELECT and returns columns + rows
- **skywatch-mcp-py.AC1.2 Success:** `clickhouse_schema` returns column definitions for all queryable tables

### skywatch-mcp-py.AC3: All I/O is async
- **skywatch-mcp-py.AC3.1 Success:** ClickHouse queries use AsyncClient (query + query_trusted)

---

## Phase 3: ClickHouse Client & Tools

**Goal:** Async ClickHouse client wrapper and the two ClickHouse tools (clickhouse_query, clickhouse_schema).

**Done when:** Both tools registered, validated queries execute against mocked client, schema returns column definitions, invalid SQL rejected before execution.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create ClickHouse client wrapper

**Files:**
- Create: `src/skywatch_mcp/lib/clickhouse_client.py`

**Implementation:**

The TS version has a lazy singleton client with two query paths: `query()` (validated, 60s timeout) and `queryTrusted()` (no validation, 120s timeout), plus a `getSchema()` method that iterates over 11 predefined tables.

```python
# pattern: Imperative Shell

from dataclasses import dataclass
from typing import Any

import clickhouse_connect
from clickhouse_connect.driver.asyncclient import AsyncClient

from skywatch_mcp.config import ClickHouseSettings
from skywatch_mcp.lib.sql_validation import ValidationFailure, validate_query


@dataclass(frozen=True)
class QueryResult:
    columns: list[dict[str, str]]
    rows: list[dict[str, Any]]


SCHEMA_TABLES = [
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
]


class ClickHouseClient:
    def __init__(self, settings: ClickHouseSettings) -> None:
        self._settings = settings
        self._client: AsyncClient | None = None

    async def _get_client(self) -> AsyncClient:
        if self._client is None:
            self._client = await clickhouse_connect.get_async_client(
                host=self._settings.effective_host.replace("http://", "").replace("https://", ""),
                port=self._settings.port,
                username=self._settings.user,
                password=self._settings.password,
                database=self._settings.database,
            )
        return self._client

    async def _execute_query(
        self, sql: str, max_execution_time: int
    ) -> QueryResult:
        client = await self._get_client()
        result = await client.query(
            query=sql,
            settings={"max_execution_time": max_execution_time},
        )
        columns = [
            {"name": name, "type": col_type}
            for name, col_type in zip(result.column_names, result.column_types, strict=True)
        ]
        rows = [
            dict(zip(result.column_names, row, strict=True))
            for row in result.result_rows
        ]
        return QueryResult(columns=columns, rows=rows)

    async def query(self, sql: str) -> QueryResult:
        validation = validate_query(sql)
        if isinstance(validation, ValidationFailure):
            raise ValueError(f"Query validation failed: {validation.reason}")
        return await self._execute_query(validation.normalized, 60)

    async def query_trusted(self, sql: str) -> QueryResult:
        return await self._execute_query(sql, 120)

    async def get_schema(self) -> QueryResult:
        all_rows: list[dict[str, Any]] = []
        schema_columns: list[dict[str, str]] = []

        for table in SCHEMA_TABLES:
            try:
                result = await self._execute_query(f"DESCRIBE TABLE {table}", 60)
                tagged_rows = [{**row, "table": table} for row in result.rows]
                all_rows.extend(tagged_rows)
                if not schema_columns:
                    schema_columns = [*result.columns, {"name": "table", "type": "String"}]
            except Exception:
                pass

        return QueryResult(columns=schema_columns, rows=all_rows)


# Lazy singleton — shared across all tool modules
_client: ClickHouseClient | None = None


def get_client() -> ClickHouseClient:
    global _client
    if _client is None:
        _client = ClickHouseClient(ClickHouseSettings())
    return _client
```

Note: `column_types` from clickhouse-connect's QueryResult gives type names. The `host` parameter to `get_async_client` should be the hostname without protocol prefix — the library handles HTTP internally. The `get_client()` function provides a lazy singleton shared by all tool modules (clickhouse, content, cosharing).

**Verification:**
Run: `uv run python -c "from skywatch_mcp.lib.clickhouse_client import ClickHouseClient, SCHEMA_TABLES; print(len(SCHEMA_TABLES), 'tables')"`
Expected: `11 tables`

**Commit:** `feat: add async ClickHouse client wrapper with query validation`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create ClickHouse tool handlers

**Files:**
- Create: `src/skywatch_mcp/tools/clickhouse.py`

**Implementation:**

Register `clickhouse_query` and `clickhouse_schema` tools with the FastMCP server. The TS version passes the client as a parameter; in the Python version, we import the lazy singleton from the client module.

```python
# pattern: Imperative Shell

import json

from skywatch_mcp.server import mcp
from skywatch_mcp.lib.clickhouse_client import get_client


@mcp.tool()
async def clickhouse_query(sql: str) -> str:
    """Execute a read-only SQL query against the ClickHouse database. SELECT and WITH (CTEs) are allowed. JOINs, UNIONs, subqueries, and any table are permitted. Queries must include a LIMIT clause. For pre-built co-sharing analysis, see the dedicated cosharing_clusters/cosharing_pairs/cosharing_evolution tools."""
    try:
        result = await get_client().query(sql)
        return json.dumps({"columns": result.columns, "rows": result.rows}, indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e


@mcp.tool()
async def clickhouse_schema() -> str:
    """Get the column definitions (names and types) for all queryable tables including osprey_execution_results, pds_signup_anomalies, url/quote overdispersion_results, account_entropy_results, url/quote cosharing pairs/clusters/membership."""
    try:
        result = await get_client().get_schema()
        return json.dumps({"columns": result.columns, "rows": result.rows}, indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e
```

Update `src/skywatch_mcp/server.py` to import the tools module:

```python
# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")

import skywatch_mcp.tools.clickhouse  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")
```

Tool registration happens at import time via decorators. The `noqa` comments suppress linting for the import-for-side-effect pattern.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.server import mcp; print([t.name for t in mcp._tool_manager._tools.values()])"`
Expected: List containing `clickhouse_query` and `clickhouse_schema`

**Commit:** `feat: add clickhouse_query and clickhouse_schema tools`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Test ClickHouse client and tools

**Verifies:** skywatch-mcp-py.AC1.1, skywatch-mcp-py.AC1.2, skywatch-mcp-py.AC3.1

**Files:**
- Create: `tests/test_clickhouse.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.1: `clickhouse_query` with a valid SELECT+LIMIT returns columns and rows from the mocked client. Invalid SQL (missing LIMIT, non-SELECT) raises ValueError before reaching the client.
- skywatch-mcp-py.AC1.2: `clickhouse_schema` calls DESCRIBE TABLE for each of the 11 schema tables and returns combined column definitions with a `table` field appended.
- skywatch-mcp-py.AC3.1: Verify the client uses async methods (the test itself uses `async def` with `await`).

Mock `clickhouse_connect.get_async_client` to return a mock AsyncClient whose `query()` method returns a mock result with `column_names`, `column_types`, and `result_rows`.

Test the ClickHouseClient class directly (not through FastMCP), to avoid needing to wire up the full MCP server in tests.

**Verification:**
Run: `uv run pytest tests/test_clickhouse.py -v`
Expected: All tests pass

**Commit:** `test: add ClickHouse client and tool tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 3 verification

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/ -v`
Expected: All tests pass (Phase 2 + Phase 3)

Run: `uv run python -c "from skywatch_mcp.server import mcp"`
Expected: No import errors

**Commit:** No commit needed — verification only
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
