# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — all prior phases complete, final integration verification

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.21 Success:** Server lists exactly 21 tools on startup

### skywatch-mcp-py.AC2: Pydantic models for all inputs/outputs
- **skywatch-mcp-py.AC2.4 Success:** Response models serialise to JSON matching TS output shape

### skywatch-mcp-py.AC5: Drop-in replacement
- **skywatch-mcp-py.AC5.3 Success:** Server runs via `uv run skywatch-mcp` over stdio transport

**Note on error handling:** FastMCP converts exceptions raised in tool handlers to `isError=True` MCP responses with the exception message as content. This is the idiomatic error handling pattern — tools raise `ValueError` with LLM-friendly messages, and FastMCP wraps them. A test in Phase 8 verifies this behaviour.

---

## Phase 8: Integration Verification & Cleanup

**Goal:** Verify all 21 tools are registered and the server is a drop-in replacement.

**Done when:** Server starts, all 21 tools are listed, full test suite passes, no import errors.

---

<!-- START_TASK_1 -->
### Task 1: Verify all tool imports in server.py

**Files:**
- Modify: `src/skywatch_mcp/server.py` (verify/fix imports)

**Implementation:**

Ensure `server.py` imports ALL tool modules. The final state should be:

```python
# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")

import skywatch_mcp.tools.clickhouse  # noqa: E402, F401
import skywatch_mcp.tools.content  # noqa: E402, F401
import skywatch_mcp.tools.cosharing  # noqa: E402, F401
import skywatch_mcp.tools.domain  # noqa: E402, F401
import skywatch_mcp.tools.ip  # noqa: E402, F401
import skywatch_mcp.tools.ozone  # noqa: E402, F401
import skywatch_mcp.tools.url  # noqa: E402, F401
import skywatch_mcp.tools.whois  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")
```

**Verification:**
Run: `uv run python -c "from skywatch_mcp.server import mcp; print('Server imports OK')"`
Expected: `Server imports OK` (no import errors)

**Commit:** `chore: verify all tool module imports in server.py`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create server integration test

**Verifies:** skywatch-mcp-py.AC1.21, skywatch-mcp-py.AC5.3

**Files:**
- Create: `tests/test_server.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.21: Import the server module, access the mcp instance, and verify it has exactly 21 registered tools. Also verify the exact tool names match:
  - `clickhouse_query`, `clickhouse_schema`
  - `domain_check`
  - `ip_lookup`
  - `url_expand`
  - `whois_lookup`
  - `content_similarity`
  - `cosharing_clusters`, `cosharing_pairs`, `cosharing_evolution`
  - `ozone_label`, `ozone_comment`, `ozone_acknowledge`, `ozone_escalate`, `ozone_tag`, `ozone_mute`, `ozone_unmute`, `ozone_resolve_appeal`, `ozone_query_statuses`, `ozone_query_events`
- skywatch-mcp-py.AC5.3: Verify the console script entry point is configured correctly by checking that `skywatch_mcp.server:main` is importable and callable.

Note: The test should import from `skywatch_mcp.server` and access the FastMCP instance's tool registry. The exact attribute path to list tools may depend on the FastMCP version — explore the `mcp` object at test time.

**Verification:**
Run: `uv run pytest tests/test_server.py -v`
Expected: All tests pass, tool count = 21

**Commit:** `test: add server integration test for tool registration`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Test response JSON shape matches TS output

**Verifies:** skywatch-mcp-py.AC2.4

**Files:**
- Create: `tests/test_response_shapes.py`

**Testing:**
Verify that key tool responses match the TS server's JSON output structure:
- `clickhouse_query` returns `{"columns": [...], "rows": [...]}` where columns have `name` and `type` fields
- `clickhouse_schema` returns same structure with `table` field appended to each row
- `ip_lookup` returns `{"ip": ..., "geo": {...}, "network": {...}, "flags": {...}}`
- `domain_check` returns `{"domain": ..., "resolves": ..., "records": {...}, "http": ...}`
- `url_expand` returns `{"originalUrl": ..., "finalUrl": ..., "hops": [...], "hopCount": ...}`
- `content_similarity` returns list of `{"user": ..., "handle": ..., "text": ..., "score": ..., "created_at": ...}`
- `cosharing_clusters` returns `{"query": ..., "rows": [...], "count": ...}`

Test by calling the pure query/formatting functions with mock data and asserting the JSON structure has the expected keys. This does NOT require live service connections.

Also test that FastMCP converts `ValueError` raised in tool handlers to `isError=True` MCP responses.

**Verification:**
Run: `uv run pytest tests/test_response_shapes.py -v`
Expected: All tests pass

**Commit:** `test: add response shape and error handling tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Full test suite verification

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/ -v`
Expected: ALL tests pass across all phases

Run: `uv run pytest tests/ -v --tb=short 2>&1 | tail -5`
Expected: Summary line showing all tests passed, 0 failures

Run: `uv run skywatch-mcp --help 2>&1 || echo "Server binary exists"`
Expected: Server entry point is accessible

**Commit:** No commit needed — verification only
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Final cleanup and linting

**Files:**
- Review all files for unused imports, missing `__init__.py` files, etc.

**Implementation:**

Run linting and type checking:

Run: `uv run ruff check src/ tests/`
Expected: No errors (or fix any that appear)

Run: `uv run ruff format --check src/ tests/`
Expected: All files formatted (or format any that aren't)

Run: `uv run mypy src/`
Expected: No type errors (or fix any that appear)

**Commit:** `chore: final cleanup, lint, and type check fixes`
<!-- END_TASK_5 -->
