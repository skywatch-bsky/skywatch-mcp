# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — TS source for cosharing.ts read

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.8 Success:** `cosharing_clusters` returns cluster metadata with filtering
- **skywatch-mcp-py.AC1.9 Success:** `cosharing_pairs` returns paired accounts with edge weights
- **skywatch-mcp-py.AC1.10 Success:** `cosharing_evolution` traces cluster timeline with evolution types

### skywatch-mcp-py.AC3: All I/O is async
- **skywatch-mcp-py.AC3.1 Success:** ClickHouse queries use AsyncClient (query + query_trusted)

---

## Phase 6: Co-Sharing Analysis Tools

**Goal:** The three co-sharing cluster analysis tools.

**Done when:** All three tools build correct SQL with proper input sanitisation (DID, cluster_id), use `query_trusted()` with 120s timeout, return structured results. Tests pass.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create co-sharing tools

**Files:**
- Create: `src/skywatch_mcp/tools/cosharing.py`

**Implementation:**

Port the TS `cosharing_clusters`, `cosharing_pairs`, and `cosharing_evolution` tools. Includes DID and cluster_id sanitisation functions.

```python
# pattern: Imperative Shell

import json
import re

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.server import mcp


def _sanitize_did(did: str) -> str:
    return re.sub(r"[^a-z0-9:.]", "", did)


def _sanitize_cluster_id(cluster_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", cluster_id)


def _build_clusters_query(
    did: str | None = None,
    cluster_id: str | None = None,
    date: str | None = None,
    min_members: int | None = None,
    limit: int = 20,
) -> str:
    if did:
        safe_did = _sanitize_did(did)
        date_filter = f"AND m.run_date = '{date}'" if date else "AND m.run_date = yesterday()"
        return f"""SELECT m.cluster_id, m.run_date, c.member_count, c.total_edges,
       c.total_weight, c.unique_urls, c.temporal_spread_hours,
       c.mean_posting_interval_seconds, c.evolution_type,
       c.predecessor_cluster_ids, c.jaccard_score,
       c.sample_dids, c.sample_urls
FROM url_cosharing_membership m
JOIN url_cosharing_clusters c
  ON m.cluster_id = c.cluster_id AND m.run_date = c.run_date
WHERE m.did = '{safe_did}' {date_filter}
ORDER BY m.run_date DESC
LIMIT {limit}"""

    if cluster_id:
        safe_id = _sanitize_cluster_id(cluster_id)
        date_filter = f"AND run_date = '{date}'" if date else ""
        return f"""SELECT cluster_id, run_date, member_count, total_edges,
       total_weight, unique_urls, temporal_spread_hours,
       mean_posting_interval_seconds, evolution_type,
       predecessor_cluster_ids, jaccard_score,
       sample_dids, sample_urls
FROM url_cosharing_clusters
WHERE cluster_id = '{safe_id}' {date_filter}
ORDER BY run_date DESC
LIMIT {limit}"""

    date_filter = f"run_date = '{date}'" if date else "run_date = yesterday()"
    member_filter = f"AND member_count >= {min_members}" if min_members else ""
    return f"""SELECT cluster_id, run_date, member_count, total_edges,
       total_weight, unique_urls, temporal_spread_hours,
       mean_posting_interval_seconds, evolution_type,
       predecessor_cluster_ids, jaccard_score,
       sample_dids, sample_urls
FROM url_cosharing_clusters
WHERE {date_filter} {member_filter}
ORDER BY member_count DESC
LIMIT {limit}"""


def _build_pairs_query(
    did: str,
    date: str | None = None,
    min_weight: int | None = None,
    limit: int = 50,
) -> str:
    safe_did = _sanitize_did(did)
    date_filter = f"AND date = '{date}'" if date else "AND date = yesterday()"
    weight_filter = f"AND weight >= {min_weight}" if min_weight else ""

    return f"""SELECT date, account_a, account_b, weight, shared_urls
FROM url_cosharing_pairs
WHERE (account_a = '{safe_did}' OR account_b = '{safe_did}')
  {date_filter} {weight_filter}
ORDER BY weight DESC
LIMIT {limit}"""


def _build_evolution_query(cluster_id: str, limit: int = 30) -> str:
    safe_id = _sanitize_cluster_id(cluster_id)

    return f"""SELECT run_date, cluster_id, member_count, total_edges,
       total_weight, unique_urls, evolution_type,
       predecessor_cluster_ids, jaccard_score,
       sample_dids
FROM url_cosharing_clusters
WHERE cluster_id = '{safe_id}'
   OR has(predecessor_cluster_ids, '{safe_id}')
ORDER BY run_date
LIMIT {limit}"""


@mcp.tool()
async def cosharing_clusters(
    did: str | None = None,
    cluster_id: str | None = None,
    date: str | None = None,
    min_members: int | None = None,
    limit: int = 20,
) -> str:
    """Find URL co-sharing clusters — groups of accounts that repeatedly share the same URLs on the same day. Filter by DID (find clusters containing an account), cluster_id (look up a specific cluster), date, or minimum member count. Returns cluster metadata, coordination metrics, evolution info, and sample members/URLs."""
    try:
        query = _build_clusters_query(did, cluster_id, date, min_members, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e


@mcp.tool()
async def cosharing_pairs(
    did: str,
    date: str | None = None,
    min_weight: int | None = None,
    limit: int = 50,
) -> str:
    """Get raw co-sharing pairs for a specific account — which other accounts share the same URLs on the same day. Returns paired accounts, edge weights (number of co-shared URLs), and the actual shared URLs."""
    try:
        query = _build_pairs_query(did, date, min_weight, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e


@mcp.tool()
async def cosharing_evolution(
    cluster_id: str,
    limit: int = 30,
) -> str:
    """Trace the evolution history of a URL co-sharing cluster over time. Shows how a cluster was born, continued, merged, split, or died across days."""
    try:
        query = _build_evolution_query(cluster_id, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e
```

The sanitisation functions strip any characters that shouldn't appear in DIDs or cluster IDs, preventing SQL injection in the internally-constructed queries.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.cosharing import _sanitize_did, _sanitize_cluster_id; print(_sanitize_did('did:plc:abc123'), _sanitize_cluster_id('2024-01-15-0042'))"`
Expected: `did:plc:abc123 2024-01-15-0042`

**Commit:** `feat: add cosharing_clusters, cosharing_pairs, cosharing_evolution tools`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Update server.py to import cosharing tools

**Files:**
- Modify: `src/skywatch_mcp/server.py`

**Implementation:**

Add import for cosharing tool module:

```python
import skywatch_mcp.tools.cosharing  # noqa: E402, F401
```

Add this line after the existing tool imports in server.py.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.server import mcp; tools = [t.name for t in mcp._tool_manager._tools.values()]; print('cosharing_clusters' in tools, 'cosharing_pairs' in tools, 'cosharing_evolution' in tools)"`
Expected: `True True True`

**Commit:** `feat: register cosharing tools in server`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-4) -->
<!-- START_TASK_3 -->
### Task 3: Test co-sharing tools

**Verifies:** skywatch-mcp-py.AC1.8, skywatch-mcp-py.AC1.9, skywatch-mcp-py.AC1.10

**Files:**
- Create: `tests/test_cosharing.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.8: `cosharing_clusters` returns cluster metadata. Test: by DID filter, by cluster_id filter, by date filter, by min_members filter, default (no filters). Verify query includes correct WHERE clauses for each case.
- skywatch-mcp-py.AC1.9: `cosharing_pairs` returns paired accounts with edge weights. Test: returns query, rows, and count. DID parameter is required and sanitised in the generated SQL.
- skywatch-mcp-py.AC1.10: `cosharing_evolution` traces cluster timeline. Test: query includes both cluster_id match and predecessor_cluster_ids match via `has()` function.

Test the pure query-building functions directly:
- `_sanitize_did` strips invalid characters
- `_sanitize_cluster_id` strips invalid characters
- `_build_clusters_query` generates correct SQL for each filter combination
- `_build_pairs_query` generates correct SQL
- `_build_evolution_query` generates correct SQL with `has()` for predecessors

**Verification:**
Run: `uv run pytest tests/test_cosharing.py -v`
Expected: All tests pass

**Commit:** `test: add co-sharing tool tests`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Phase 6 verification

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/ -v`
Expected: All tests pass (Phases 2-6)

**Commit:** No commit needed — verification only
<!-- END_TASK_4 -->
<!-- END_SUBCOMPONENT_B -->
