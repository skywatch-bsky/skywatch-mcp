# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — TS source for content.ts read

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.7 Success:** `content_similarity` finds posts by ngramDistance within threshold

### skywatch-mcp-py.AC3: All I/O is async
- **skywatch-mcp-py.AC3.1 Success:** ClickHouse queries use AsyncClient (query + query_trusted)

---

## Phase 5: Content Similarity Tool

**Goal:** ClickHouse ngramDistance-based text similarity search.

**Done when:** Tool builds correct ngramDistance queries with proper escaping, uses `query_trusted()`, returns similarity scores. Tests pass.

Note: The TS version uses `client.query()` (validated) for this tool, but since the query is internally constructed (not user input), `query_trusted()` with no SQL validation is more appropriate and matches the design plan.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create content_similarity tool

**Files:**
- Create: `src/skywatch_mcp/tools/content.py`

**Implementation:**

Port the TS `content_similarity` tool. Builds an ngramDistance query against `default.osprey_execution_results`, escaping single quotes and backslashes in user-provided text.

```python
# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.server import mcp


def _escape_clickhouse_sql(text: str) -> str:
    return text.replace("\\", "\\\\").replace("'", "\\'")


def _build_similarity_query(escaped_text: str, threshold: float, limit: int) -> str:
    return f"""SELECT
    did as user,
    handle,
    content as text,
    ngramDistance(content, '{escaped_text}') as score,
    created_at
  FROM default.osprey_execution_results
  WHERE ngramDistance(content, '{escaped_text}') < {threshold}
  ORDER BY score ASC
  LIMIT {limit}"""


@mcp.tool()
async def content_similarity(
    text: str,
    threshold: float = 0.4,
    limit: int = 20,
) -> str:
    """Find posts with similar text content using ClickHouse ngramDistance. Useful for detecting copypasta and coordinated posting.

    Args:
        text: Text to search for similar content
        threshold: Distance threshold (0=identical, 1=completely different). Lower values find more similar content. Default 0.4
        limit: Maximum number of results. Default 20
    """
    try:
        escaped_text = _escape_clickhouse_sql(text)
        query = _build_similarity_query(escaped_text, threshold, limit)
        result = await get_client().query_trusted(query)

        results = [
            {
                "user": str(row.get("user", "")),
                "handle": str(row.get("handle", "")),
                "text": str(row.get("text", "")),
                "score": float(row.get("score", 0)),
                "created_at": str(row.get("created_at", "")),
            }
            for row in result.rows
        ]

        return json.dumps(results, indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e
```

The `_escape_clickhouse_sql` and `_build_similarity_query` functions are extracted as pure functions (Functional Core) for testability.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.content import _escape_clickhouse_sql, _build_similarity_query; print(_build_similarity_query(_escape_clickhouse_sql(\"hello world\"), 0.4, 20)[:50])"`
Expected: First 50 chars of the generated SQL query

**Commit:** `feat: add content_similarity tool with ngramDistance`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update server.py to import content tool

**Files:**
- Modify: `src/skywatch_mcp/server.py`

**Implementation:**

Add import for content tool module:

```python
import skywatch_mcp.tools.content  # noqa: E402, F401
```

Add this line after the existing tool imports in server.py.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.server import mcp; print('content_similarity' in [t.name for t in mcp._tool_manager._tools.values()])"`
Expected: `True`

**Commit:** `feat: register content_similarity tool in server`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Test content_similarity tool

**Verifies:** skywatch-mcp-py.AC1.7, skywatch-mcp-py.AC3.1

**Files:**
- Create: `tests/test_content.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.7: content_similarity builds correct ngramDistance query with proper escaping (single quotes and backslashes), passes threshold and limit parameters correctly, returns structured results with user/handle/text/score/created_at fields.
- skywatch-mcp-py.AC3.1: Uses the async ClickHouse client's `query_trusted()` method.

Test the pure functions directly:
- `_escape_clickhouse_sql("it's a test")` → `"it\\'s a test"`
- `_escape_clickhouse_sql("back\\slash")` → `"back\\\\slash"`
- `_build_similarity_query("hello", 0.3, 10)` contains correct SQL with ngramDistance

Mock the ClickHouseClient to test the tool handler returns correct JSON structure.

**Verification:**
Run: `uv run pytest tests/test_content.py -v`
Expected: All tests pass

**Commit:** `test: add content_similarity tool tests`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->
