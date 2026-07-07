# pattern: Imperative Shell

import json
import re

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.server import mcp


def _sanitize_did(did: str) -> str:
    return re.sub(r"[^a-z0-9:.]", "", did)


def _sanitize_cluster_id(cluster_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", cluster_id)


def _sanitize_date(date: str) -> str:
    """Validate and return date in YYYY-MM-DD format.

    Raises ValueError if the date does not match the expected format.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise ValueError(f"Invalid date format. Expected YYYY-MM-DD, got: {date}")
    return date


def _build_clusters_query(
    did: str | None = None,
    cluster_id: str | None = None,
    date: str | None = None,
    min_members: int | None = None,
    limit: int = 20,
) -> str:
    if did:
        safe_did = _sanitize_did(did)
        date_filter = f"AND m.run_date = '{_sanitize_date(date)}'" if date else "AND m.run_date = yesterday()"
        return f"""SELECT m.cluster_id, m.run_date, c.member_count, c.total_edges,
       c.total_weight, c.mean_edge_similarity, c.subgraph_density,
       c.unique_urls, c.temporal_spread_hours,
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
        date_filter = f"AND run_date = '{_sanitize_date(date)}'" if date else ""
        return f"""SELECT cluster_id, run_date, member_count, total_edges,
       total_weight, mean_edge_similarity, subgraph_density,
       unique_urls, temporal_spread_hours,
       mean_posting_interval_seconds, evolution_type,
       predecessor_cluster_ids, jaccard_score,
       sample_dids, sample_urls
FROM url_cosharing_clusters
WHERE cluster_id = '{safe_id}' {date_filter}
ORDER BY run_date DESC
LIMIT {limit}"""

    date_filter = f"run_date = '{_sanitize_date(date)}'" if date else "run_date = yesterday()"
    member_filter = f"AND member_count >= {int(min_members)}" if min_members else ""
    return f"""SELECT cluster_id, run_date, member_count, total_edges,
       total_weight, mean_edge_similarity, subgraph_density,
       unique_urls, temporal_spread_hours,
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
    date_filter = f"AND date = '{_sanitize_date(date)}'" if date else "AND date = yesterday()"
    weight_filter = f"AND weight >= {int(min_weight)}" if min_weight else ""

    return f"""SELECT date, account_a, account_b, weight, shared_urls
FROM url_cosharing_pairs
WHERE (account_a = '{safe_did}' OR account_b = '{safe_did}')
  {date_filter} {weight_filter}
ORDER BY weight DESC
LIMIT {limit}"""


def _build_evolution_query(cluster_id: str, limit: int = 30) -> str:
    safe_id = _sanitize_cluster_id(cluster_id)

    return f"""SELECT run_date, cluster_id, member_count, total_edges,
       total_weight, mean_edge_similarity, subgraph_density,
       unique_urls, evolution_type,
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
    """Find URL co-sharing clusters — groups of accounts identified as coordinated via TF-IDF cosine-similarity network and density-based dismantling (Cinus et al., WWW '25). Filter by DID (find clusters containing an account), cluster_id (look up a specific cluster), date, or minimum member count. Returns cluster metadata including mean_edge_similarity and subgraph_density (high values = tight coordination), evolution info, and sample members/URLs."""
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
    """Get raw co-sharing pairs for a specific account — which other accounts share the same URLs on the same day. Returns paired accounts, edge weights (number of co-shared URLs), and the actual shared URLs. Note: this materialized view is investigation tooling only; the URL co-sharing sidecar no longer consumes it (reads osprey_execution_results directly via TF-IDF)."""
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
