# pattern: Imperative Shell

import json

from skywatch_mcp.lib.clickhouse_client import get_client
from skywatch_mcp.lib.sanitizers import (
    sanitize_date,
    sanitize_did,
    validate_days,
    validate_limit,
)
from skywatch_mcp.server import mcp


def _build_account_entropy_results_query(
    user_id: str | None = None,
    date: str | None = None,
    only_bot_like: bool = True,
    limit: int = 50,
) -> str:
    filters: list[str] = []

    if user_id:
        safe_did = sanitize_did(user_id)
        filters.append(f"user_id = '{safe_did}'")

    if date:
        safe_date = sanitize_date(date)
        filters.append(f"toDate(run_timestamp) = '{safe_date}'")
    else:
        filters.append("toDate(run_timestamp) = today()")

    if only_bot_like:
        filters.append("is_bot_like = 1")

    where_clause = " AND ".join(filters)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, user_id, window_start, window_end,
       post_count, hourly_entropy, interval_entropy,
       hourly_entropy_norm, interval_entropy_norm,
       mean_interval_seconds, stddev_interval_seconds, interval_cv,
       is_bot_like, hourly_flag, interval_flag, cv_flag,
       sample_rkeys
FROM default.account_entropy_results
WHERE {where_clause}
ORDER BY run_timestamp DESC, hourly_entropy_norm DESC
LIMIT {safe_limit}"""


def _build_account_entropy_trend_query(
    user_id: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    safe_did = sanitize_did(user_id)
    safe_days = validate_days(days)
    safe_limit = validate_limit(limit)

    return f"""SELECT run_timestamp, user_id, window_start, window_end,
       post_count, hourly_entropy, interval_entropy,
       hourly_entropy_norm, interval_entropy_norm,
       mean_interval_seconds, stddev_interval_seconds, interval_cv,
       is_bot_like, hourly_flag, interval_flag, cv_flag,
       sample_rkeys
FROM default.account_entropy_results
WHERE user_id = '{safe_did}'
  AND run_timestamp >= today() - INTERVAL {safe_days} DAY
ORDER BY run_timestamp ASC
LIMIT {safe_limit}"""


@mcp.tool()
async def account_entropy_results(
    user_id: str | None = None,
    date: str | None = None,
    only_bot_like: bool = True,
    limit: int = 50,
) -> str:
    """Look up bot-like posting pattern detection results based on normalized entropy (Miller–Madow corrected) and inter-post interval coefficient of variation. An account is flagged is_bot_like when hourly_entropy_norm is high AND either interval_entropy_norm is low or interval_cv is low — indicating metronomic, machine-like posting. Returns individual flag columns (hourly_flag, interval_flag, cv_flag) for diagnostic attribution. Note: user_id is a DID. Accounts with fewer than 10 posts are never scored."""
    try:
        query = _build_account_entropy_results_query(user_id, date, only_bot_like, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e


@mcp.tool()
async def account_entropy_trend(
    user_id: str,
    days: int = 14,
    limit: int = 500,
) -> str:
    """Time series of account entropy and coefficient-of-variation signals for a single account. Shows whether bot-like behavior is sustained across windows or a one-off. Returns all entropy/CV metrics including individual flag columns. Ordered chronologically."""
    try:
        query = _build_account_entropy_trend_query(user_id, days, limit)
        result = await get_client().query_trusted(query)
        return json.dumps(
            {"query": query, "rows": result.rows, "count": len(result.rows)},
            indent=2,
            default=str,
        )
    except Exception as e:
        raise ValueError(str(e)) from e
