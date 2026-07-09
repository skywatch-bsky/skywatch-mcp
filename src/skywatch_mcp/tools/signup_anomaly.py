# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.lib.sanitizers import (
    sanitize_date,
    sanitize_hostname,
    validate_days,
    validate_limit,
    validate_q_value,
)
from skywatch_mcp.server import mcp

_VALID_GRANULARITIES = {"daily", "hourly"}


def _build_signup_anomalies_query(
    pds_host: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    min_q_value: float | None = None,
    only_anomalies: bool = True,
    limit: int = 50,
) -> str:
    filters: list[str] = []

    if pds_host:
        safe_host = sanitize_hostname(pds_host)
        filters.append(f"pds_host = '{safe_host}'")

    if granularity:
        if granularity not in _VALID_GRANULARITIES:
            raise ValueError(
                f"Invalid granularity. Expected one of {_VALID_GRANULARITIES}, got: {granularity}"
            )
        filters.append(f"granularity = '{granularity}'")

    if date:
        safe_date = sanitize_date(date)
        filters.append(f"toDate(run_timestamp) = '{safe_date}'")
    else:
        filters.append("toDate(run_timestamp) = today()")

    if min_q_value is not None:
        safe_q = validate_q_value(min_q_value)
        filters.append(f"q_value <= {safe_q}")

    if only_anomalies:
        filters.append("is_anomaly = 1")

    where_clause = " AND ".join(filters)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, granularity, pds_host,
       observed_count, distinct_accounts, expected_lambda,
       p_value, q_value, is_anomaly,
       baseline_source, baseline_days_available,
       sample_dids, rolling_mean, rolling_variance, dispersion_index
FROM default.pds_signup_anomalies
WHERE {where_clause}
ORDER BY run_timestamp DESC, q_value ASC
LIMIT {safe_limit}"""


def _build_signup_anomaly_trend_query(
    pds_host: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    safe_host = sanitize_hostname(pds_host)
    safe_days = validate_days(days)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, granularity, pds_host,
       observed_count, distinct_accounts, expected_lambda,
       p_value, q_value, is_anomaly,
       baseline_source, baseline_days_available,
       rolling_mean, rolling_variance, dispersion_index
FROM default.pds_signup_anomalies
WHERE pds_host = '{safe_host}'
  AND run_timestamp >= today() - INTERVAL {safe_days} DAY
ORDER BY run_timestamp ASC
LIMIT {safe_limit}"""


@mcp.tool()
async def signup_anomalies(
    pds_host: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    min_q_value: float | None = None,
    only_anomalies: bool = True,
    limit: int = 50,
) -> str:
    """Look up anomalous PDS signup spikes detected via negative-binomial/Poisson testing with Benjamini–Hochberg FDR correction. Filter by PDS host, granularity (daily/hourly), or date. Returns observed vs expected counts, q-values, baseline source, dispersion diagnostics, and sample account DIDs. Excluded hosts (bsky.network, bridgy-fed, mostr.pub) are never scored and will return zero rows."""
    try:
        query = _build_signup_anomalies_query(
            pds_host, granularity, date, min_q_value, only_anomalies, limit
        )
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e


@mcp.tool()
async def signup_anomaly_trend(
    pds_host: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    """Time series of signup anomaly data for a single PDS host across both granularities (daily and hourly). Shows the full baseline/observed history, not just flagged rows — useful for understanding whether a spike is sustained or a one-off. Ordered chronologically."""
    try:
        query = _build_signup_anomaly_trend_query(pds_host, days, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e
