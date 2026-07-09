# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.lib.sanitizers import sanitize_at_uri, sanitize_date, sanitize_did
from skywatch_mcp.server import mcp

_VALID_GRANULARITIES = {"hourly", "daily"}
_VALID_SIGNALS = {"volume", "density"}


def _build_quote_overdispersion_results_query(
    quoted_uri: str | None = None,
    quoted_author_did: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    signal: str | None = None,
    only_anomalies: bool = True,
    limit: int = 50,
) -> str:
    if signal is not None and signal not in _VALID_SIGNALS:
        raise ValueError(
            f"Invalid signal. Expected one of {_VALID_SIGNALS}, got: {signal}"
        )

    filters: list[str] = []

    if quoted_uri:
        safe_uri = sanitize_at_uri(quoted_uri)
        filters.append(f"quoted_uri = '{safe_uri}'")

    if quoted_author_did:
        safe_did = sanitize_did(quoted_author_did)
        filters.append(f"quoted_author_did = '{safe_did}'")

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

    where_clause = " AND ".join(filters)

    return f"""SELECT run_timestamp, granularity, quoted_uri, quoted_author_did,
       bucket_start, total_shares, unique_sharers, sharer_density,
       expected_volume_lambda, expected_density_lambda,
       volume_p_value, volume_q_value,
       density_p_value, density_q_value,
       is_anomaly, baseline_source, baseline_days_available,
       sample_dids
FROM default.quote_overdispersion_results
WHERE {where_clause}
ORDER BY run_timestamp DESC, LEAST(volume_q_value, density_q_value) ASC
LIMIT {int(limit)}"""


def _build_quote_overdispersion_trend_query(
    quoted_uri: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    safe_uri = sanitize_at_uri(quoted_uri)

    return f"""SELECT run_timestamp, granularity, quoted_uri, quoted_author_did,
       bucket_start, total_shares, unique_sharers, sharer_density,
       expected_volume_lambda, expected_density_lambda,
       volume_p_value, volume_q_value,
       density_p_value, density_q_value,
       is_anomaly, baseline_source, baseline_days_available,
       sample_dids
FROM default.quote_overdispersion_results
WHERE quoted_uri = '{safe_uri}'
  AND run_timestamp >= today() - INTERVAL {int(days)} DAY
ORDER BY run_timestamp ASC
LIMIT {int(limit)}"""


@mcp.tool()
async def quote_overdispersion_results(
    quoted_uri: str | None = None,
    quoted_author_did: str | None = None,
    granularity: str | None = None,
    date: str | None = None,
    signal: str | None = None,
    only_anomalies: bool = True,
    limit: int = 50,
) -> str:
    """Look up anomalous quote-post concentration on a single quoted URI, detected via negative-binomial and beta-binomial testing with BH-FDR correction. Structurally similar to URL overdispersion but targets quote-post clustering instead of URL sharing. Note: population baseline dominance (50–70%+) is expected/normal for quote posts due to their short-lived nature."""
    try:
        query = _build_quote_overdispersion_results_query(
            quoted_uri, quoted_author_did, granularity, date, signal, only_anomalies, limit
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
async def quote_overdispersion_trend(
    quoted_uri: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    """Time series of quote-post overdispersion data for a single quoted URI. Shows full baseline history across both signals (volume and density)."""
    try:
        query = _build_quote_overdispersion_trend_query(quoted_uri, days, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e
