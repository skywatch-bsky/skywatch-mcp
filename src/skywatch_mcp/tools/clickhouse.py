# pattern: Imperative Shell

import json
import re
from typing import Any

from skywatch_mcp.lib.clickhouse_client import (
    OSPREY_RESULTS_TABLE,
    SCHEMA_TABLES,
    get_client,
    serialize_rows,
)
from skywatch_mcp.lib.sanitizers import sanitize_did, validate_days
from skywatch_mcp.lib.tool_errors import BackendError, ToolInputError, tool_error_boundary
from skywatch_mcp.server import mcp


def _normalize_table_name(table: str) -> str:
    """Resolve a short or fully qualified table name against SCHEMA_TABLES."""
    if table in SCHEMA_TABLES:
        return table
    if "." not in table:
        candidate = f"default.{table}"
        if candidate in SCHEMA_TABLES:
            return candidate
    raise ToolInputError(
        f"Unknown table: {table}. Valid tables: {', '.join(SCHEMA_TABLES)}"
    )


def _meta(result: Any) -> dict[str, Any]:
    """Correlation metadata carried on success payloads."""
    return {"query_id": result.query_id, "elapsed_ms": result.elapsed_ms}


@mcp.tool()
@tool_error_boundary
async def clickhouse_query(sql: str) -> str:
    """Execute a read-only SQL query against the ClickHouse database. SELECT and WITH (CTEs) are allowed. JOINs, UNIONs, subqueries, and any table are permitted. Queries must include a LIMIT clause. Results are truncated at 1 MiB of serialized output with meta.truncated/rows_returned reporting. Backend failures return structured JSON errors with kind/retryable/query_id — use query_id for server-side correlation. For pre-built co-sharing analysis, see the dedicated cosharing_clusters/cosharing_pairs/cosharing_evolution tools."""
    result = await get_client().query(sql)
    text, _meta_map = serialize_rows(
        result.columns, result.rows, extra_meta=_meta(result)
    )
    return text


@mcp.tool()
@tool_error_boundary
async def clickhouse_schema(
    table: str | None = None,
    field: str | None = None,
    fields: list[str] | None = None,
) -> str:
    """Get column definitions for queryable tables (osprey_execution_results, pds_signup_anomalies, url/quote overdispersion_results, account_entropy_results, url/quote cosharing pairs/clusters/membership, url_cosharing_runs). With no arguments, returns the full schema of all tables with coverage metadata. Pass table (short like osprey_execution_results or full like default.osprey_execution_results) to scope to one table. Pass field (single) or fields (list, mutually exclusive) together with table for exact case-sensitive lookups; absent names are reported in missing_fields rather than failing. Backend failures return structured JSON errors, never an empty schema."""
    if field is not None and fields is not None:
        raise ToolInputError(
            "Pass either field (a single name) or fields (a list), not both."
        )
    if (field is not None or fields is not None) and table is None:
        raise ToolInputError(
            "Field selection requires table. Pass table together with field or fields."
        )

    client = get_client()
    if table is None:
        result = await client.get_schema()
        return json.dumps(
            {
                "columns": result.columns,
                "rows": result.rows,
                "coverage": result.coverage,
                "meta": _meta(result),
            },
            indent=2,
            default=str,
        )

    normalized = _normalize_table_name(table)
    try:
        result = await client.get_table_columns(normalized)
    except BackendError as exc:
        if exc.kind == "invalid_sql" and exc.code == 60:
            # Confirmed table absence only. Other invalid_sql codes (47 unknown
            # identifier, 62 syntax error) keep the classified BackendError so
            # query_id and the numeric code stay available for diagnosis.
            code_text = f" (code {exc.code})" if exc.code is not None else ""
            raise ToolInputError(
                f"Table {table} does not exist{code_text}. "
                f"Valid tables: {', '.join(SCHEMA_TABLES)}"
            ) from exc
        raise

    requested = [field] if field is not None else list(fields or [])
    requested_set = set(requested)
    available = {row["name"] for row in result.rows}
    missing_fields = [name for name in requested if name not in available]
    selected_rows = (
        [row for row in result.rows if row["name"] in requested_set]
        if requested
        else result.rows
    )
    response = {
        "table": normalized,
        "columns": [
            {"name": row["name"], "type": row["type"]} for row in selected_rows
        ],
        "missing_fields": missing_fields,
        "coverage": result.coverage,
        "meta": _meta(result),
    }
    return json.dumps(response, indent=2, default=str)


@mcp.tool()
@tool_error_boundary
async def clickhouse_health() -> str:
    """Check ClickHouse connectivity: runs SELECT 1 plus version() under a 5-second budget. Returns connected, server_version, and correlation meta on success; a classified structured failure (kind backend_unavailable/auth_failed/...) otherwise. Use as the first probe when queries fail."""
    result = await get_client().query_trusted(
        "SELECT 1 AS connected, version() AS server_version LIMIT 1",
        max_execution_time=5,
    )
    row = result.rows[0] if result.rows else {}
    return json.dumps(
        {
            "connected": row.get("connected") == 1,
            "server_version": row.get("server_version"),
            "meta": _meta(result),
        },
        indent=2,
        default=str,
    )


# --- clickhouse_rule_summary -------------------------------------------------

MAX_RULES = 100

# Identifier grammar: precondition for safe backtick quoting (backticks are
# also doubled as defense in depth, though the grammar already excludes them).
_RULE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# Known-non-rule operational columns: rejected outright, even if a
# mis-populated catalogue contained them.
_RULE_FLAG_DENYLIST = frozenset(
    {
        "AtUri",
        "Cid",
        "UserId",
        "Handle",
        "__timestamp",
        "PostText",
        "PostTextCleaned",
        "PostIsReply",
        "PostReplyParent",
    }
)

# Type eligibility for rule flag columns.
_RULE_ELIGIBLE_TYPES = frozenset(
    {"Bool", "Nullable(Bool)", "UInt8", "Nullable(UInt8)"}
)

# Authoritative provenance for the rule catalogue: the osprey rule definition
# tree (sibling skywatch-osprey-rules/rules, .sml rule files) is the designated
# source; operator-supplied exports are the alternative. The catalogue ships
# EMPTY — until the operator confirms the source (and the backend is up to
# verify column identities), every request fails closed with the structured
# rule_catalogue_unavailable error. Flag candidacy (grammar, denylist, column
# type) is a necessary filter on catalogue contents, never by itself
# verification of rule identity.
VERIFIED_RULE_CATALOGUE: frozenset[str] = frozenset()


def _verify_rule_names(rules: list[str]) -> list[str]:
    """Offline validation stages for rule names (pattern: Functional Core).

    Order: non-empty; count <= MAX_RULES; identifier grammar; denylist;
    catalogue membership (fail-closed when unpopulated); deduplication
    preserving first-occurrence order. Raises before any backend call.
    """
    if not rules:
        raise ToolInputError("rules must be a non-empty list of rule names.")
    if len(rules) > MAX_RULES:
        raise ToolInputError(
            f"rules exceeds the maximum of {MAX_RULES} rule names; got {len(rules)}."
        )
    invalid = [name for name in rules if not _RULE_NAME_RE.match(name)]
    if invalid:
        raise ToolInputError(
            "Invalid rule identifier(s): "
            + ", ".join(invalid)
            + ". Rule names must match ^[A-Za-z_][A-Za-z0-9_]*$."
        )
    denylisted = sorted({name for name in rules if name in _RULE_FLAG_DENYLIST})
    if denylisted:
        raise ToolInputError(
            "Not rule columns: "
            + ", ".join(denylisted)
            + ". These are operational osprey_execution_results columns, not rule flags."
        )
    if not VERIFIED_RULE_CATALOGUE:
        raise BackendError(kind="rule_catalogue_unavailable", retryable=True)
    unknown = sorted({name for name in rules if name not in VERIFIED_RULE_CATALOGUE})
    if unknown:
        raise ToolInputError(
            "Unknown rule name(s): "
            + ", ".join(unknown)
            + '. Verify names with clickhouse_schema(table="osprey_execution_results").'
        )
    return list(dict.fromkeys(rules))


def build_rule_summary_sql(rule_names: list[str]) -> str:
    """Build the single atomic rule-summary query (pattern: Functional Core).

    Per-rule counts via independent countIf aggregates; no cross-rule
    aggregation is ever generated. Identifiers are backticked (doubled as
    defense in depth); did/days ride as typed bound parameters, never
    interpolated.
    """
    selects = ", ".join(
        f"countIf(`{name.replace('`', '``')}`) AS m_{index}"
        for index, name in enumerate(rule_names)
    )
    return (
        f"SELECT count() AS window_rows, {selects} "
        f"FROM {OSPREY_RESULTS_TABLE} "
        "WHERE UserId = {did:String} "
        "AND __timestamp >= now() - toIntervalDay({days:UInt32})"
    )


@mcp.tool()
@tool_error_boundary
async def clickhouse_rule_summary(did: str, days: int, rules: list[str]) -> str:
    """Count per-rule flag matches for one DID over a trailing window in osprey_execution_results. rules is a list of verified rule column names (max 100); did is sanitized; days is 1-365. Rule names must be in the verified rule catalogue; execution binds did/days as typed parameters and returns one row of independent per-rule counts plus window_rows (0 means an empty window, distinct from rules that never fire) and coverage. Unknown names fail with an actionable error; the rule catalogue must be configured or the call fails closed with kind rule_catalogue_unavailable."""
    clean_did = sanitize_did(did)
    window_days = validate_days(days)
    deduped = _verify_rule_names(rules)

    client = get_client()
    columns_result = await client.get_table_columns(OSPREY_RESULTS_TABLE)
    type_by_name = {row["name"]: row["type"] for row in columns_result.rows}
    wrong_type = [
        name
        for name in deduped
        if type_by_name.get(name) not in _RULE_ELIGIBLE_TYPES
    ]
    if wrong_type:
        raise ToolInputError(
            "Rule column(s) with ineligible type(s): "
            + ", ".join(wrong_type)
            + ". Rule flags must be Bool, Nullable(Bool), UInt8, or Nullable(UInt8)."
        )

    sql = build_rule_summary_sql(deduped)
    result = await client.query_trusted(
        sql, parameters={"did": clean_did, "days": window_days}
    )
    row = result.rows[0] if result.rows else {}
    return json.dumps(
        {
            "did": clean_did,
            "window_days": window_days,
            "rules": [
                {"rule": name, "matches": row.get(f"m_{index}")}
                for index, name in enumerate(deduped)
            ],
            "window_rows": row.get("window_rows"),
            "coverage": {
                "rules_requested": len(rules),
                "rules_evaluated": len(deduped),
                "unknown_rules": [],
            },
            "meta": _meta(result),
        },
        indent=2,
        default=str,
    )
