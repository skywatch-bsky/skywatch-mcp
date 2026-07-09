# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.lib.sanitizers import (
    sanitize_date,
    sanitize_hostname,
    validate_days,
    validate_limit,
)
from skywatch_mcp.server import mcp

_VALID_GRANULARITIES = {"hourly", "daily"}
_VALID_SIGNALS = {"volume", "density"}


def _build_url_overdispersion_results_query(
    domain: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    signal: str | None = None,
    only_anomalies: bool = True,
    only_watchlist: bool = False,
    limit: int = 50,
) -> str:
    if signal is not None and signal not in _VALID_SIGNALS:
        raise ValueError(
            f"Invalid signal. Expected one of {_VALID_SIGNALS}, got: {signal}"
        )

    filters: list[str] = []

    if domain:
        safe_domain = sanitize_hostname(domain)
        filters.append(f"domain = '{safe_domain}'")

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

    if only_anomalies:
        filters.append("is_anomaly = 1")

    if signal == "volume":
        filters.append("volume_q_value <= density_q_value")
    elif signal == "density":
        filters.append("density_q_value <= volume_q_value")

    if only_watchlist:
        filters.append("on_watchlist = 1")

    where_clause = " AND ".join(filters)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, granularity, domain, bucket_start,
       total_shares, unique_sharers, sharer_density,
       expected_volume_lambda, expected_density_lambda,
       volume_p_value, volume_q_value,
       density_p_value, density_q_value,
       is_anomaly, baseline_source, baseline_days_available,
       sample_dids, sample_urls, on_watchlist
FROM default.url_overdispersion_results
WHERE {where_clause}
ORDER BY run_timestamp DESC, LEAST(volume_q_value, density_q_value) ASC
LIMIT {safe_limit}"""


def _build_url_overdispersion_trend_query(
    domain: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    safe_domain = sanitize_hostname(domain)
    safe_days = validate_days(days)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, granularity, domain, bucket_start,
       total_shares, unique_sharers, sharer_density,
       expected_volume_lambda, expected_density_lambda,
       volume_p_value, volume_q_value,
       density_p_value, density_q_value,
       is_anomaly, baseline_source, baseline_days_available,
       sample_dids, sample_urls, on_watchlist
FROM default.url_overdispersion_results
WHERE domain = '{safe_domain}'
  AND run_timestamp >= today() - INTERVAL {safe_days} DAY
ORDER BY run_timestamp ASC
LIMIT {safe_limit}"""


@mcp.tool()
async def url_overdispersion_results(
    domain: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    signal: str | None = None,
    only_anomalies: bool = True,
    only_watchlist: bool = False,
    limit: int = 50,
) -> str:
    """Look up anomalous URL/domain-sharing volume or density spikes detected via negative-binomial and beta-binomial testing with BH-FDR correction. Each row has two independent signals: volume (total shares) and density (unique sharers per share). Filter by domain, granularity, or signal type. The signal parameter filters to rows where the specified signal is the dominant (lower q-value) signal — it does not independently test whether that signal is anomalous. The on_watchlist flag reflects operator-maintained domain tracking, not a model output."""
    try:
        query = _build_url_overdispersion_results_query(
            domain, granularity, date, signal, only_anomalies, only_watchlist, limit
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
async def url_overdispersion_trend(
    domain: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    """Time series of URL overdispersion data for a single domain across both signals (volume and density). Shows full baseline history, not just flagged rows. Ordered chronologically."""
    try:
        query = _build_url_overdispersion_trend_query(domain, days, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e
