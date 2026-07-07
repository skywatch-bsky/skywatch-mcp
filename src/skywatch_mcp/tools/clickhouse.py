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
    """Get the column definitions (names and types) for all queryable tables including osprey_execution_results, pds_signup_anomalies, url/quote overdispersion_results, account_entropy_results, url/quote cosharing pairs/clusters/membership, and url_cosharing_runs."""
    try:
        result = await get_client().get_schema()
        return json.dumps({"columns": result.columns, "rows": result.rows}, indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e
