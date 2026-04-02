# Skywatch MCP Python — Human Test Plan

**Generated:** 2026-04-01
**Implementation Plan:** docs/implementation-plans/2026-03-31-skywatch-mcp-py/
**Automated Tests:** 255 passing (all 37 acceptance criteria covered)

## Prerequisites

- Python 3.11+ with `uv` installed
- Environment variables for ClickHouse and Ozone set (or defaults accepted)
- `uv run pytest tests/ -v` passing (255/255 green)

## Phase 1: Smoke Test — Server Startup

| Step | Action | Expected |
|------|--------|----------|
| 1.1 | Run `uv run skywatch-mcp` in a terminal | Process starts without import errors, no output on stdout (stdio transport waits for JSON-RPC input) |
| 1.2 | Press Ctrl+C | Process exits cleanly with no traceback |
| 1.3 | Run `echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1.0"}},"id":1}' \| uv run skywatch-mcp` | Returns a JSON-RPC response with `"result"` containing `serverInfo` and `capabilities`. No error response. |

## Phase 2: MCP Client Integration

| Step | Action | Expected |
|------|--------|----------|
| 2.1 | Connect Claude Desktop (or `mcp-inspector`) to the server via stdio transport using `uv run skywatch-mcp` | Client successfully connects and initialises |
| 2.2 | Send `tools/list` request | Response lists exactly 20 tools with names matching the expected set |
| 2.3 | Inspect any tool's inputSchema in the response | Each tool has `inputSchema` with `properties` where each property has a `description` field |

## Phase 3: Tool Execution (with live services)

| Step | Action | Expected |
|------|--------|----------|
| 3.1 | Call `domain_check` with domain `"google.com"` | Returns JSON with `domain: "google.com"`, `resolves: true`, populated `records` (at least `a` and `ns` non-empty), `http.status: 200` |
| 3.2 | Call `ip_lookup` with ip `"8.8.8.8"` | Returns JSON with `ip: "8.8.8.8"`, `geo.country` containing "United States", `network.isp` containing "Google", `flags` object present |
| 3.3 | Call `url_expand` with a known short URL | Returns JSON with `originalUrl`, `finalUrl` different from original, `hops` array with at least 2 entries, first hop `isShortener: true` |
| 3.4 | Call `whois_lookup` with domain `"google.com"` | Returns JSON with non-null `registrar`, `creation_date`, `nameservers` (non-empty array), `domain_age` > 5000, `raw_text` present |
| 3.5 | Call `clickhouse_query` with `"SELECT 1 as test LIMIT 1"` (requires ClickHouse) | Returns `{columns: [{name: "test", type: "UInt8"}], rows: [{test: 1}]}` |
| 3.6 | Call `clickhouse_schema` (requires ClickHouse) | Returns `{columns: [...], rows: [...]}` where rows include entries for all 11 schema tables |
| 3.7 | Call `clickhouse_query` with `"DROP TABLE users LIMIT 1"` | Returns error: "Only SELECT queries are allowed" |
| 3.8 | Call `clickhouse_query` with `"SELECT * FROM users"` (no LIMIT) | Returns error mentioning "LIMIT" |

## Phase 4: Ozone Integration (requires Ozone credentials)

| Step | Action | Expected |
|------|--------|----------|
| 4.1 | Call `ozone_query_statuses` with `review_state: "open"` | Returns JSON with statuses array (may be empty). No auth errors. |
| 4.2 | Call `ozone_query_events` with `types: ["comment"]` | Returns JSON with events array. Query string contains full `tools.ozone.moderation.defs#modEventComment` type. |
| 4.3 | Call `ozone_comment` with a test subject and comment | Returns JSON with event id. Comment visible in Ozone dashboard. |
| 4.4 | Call any ozone tool, wait 2+ hours, call again | Second call succeeds (token refresh worked). No "ExpiredToken" error surfaced. |

## End-to-End: Investigation Workflow

1. Call `domain_check` with a suspicious domain — verify DNS records and HTTP status returned
2. Call `url_expand` with a URL from that domain — verify redirect chain followed and shortener detection works
3. Call `content_similarity` with text from a known suspicious post (requires ClickHouse) — verify results include `user`, `handle`, `text`, `score`, `created_at` fields
4. Call `cosharing_clusters` with the DID from step 3 — verify cluster metadata returned with `{query, rows, count}` shape
5. Call `cosharing_pairs` with same DID — verify paired accounts with edge weights
6. Call `cosharing_evolution` with a cluster_id from step 4 — verify timeline includes `evolution_type` values
7. Call `ozone_label` to apply a label to the subject — verify success response
8. Call `ozone_comment` to document findings — verify comment created

## End-to-End: Error Resilience

1. Set `CLICKHOUSE_HOST` to an unreachable IP, call `clickhouse_query` — verify error returned (not hang), within timeout
2. Unset all `OZONE_*` env vars, call `ozone_comment` — verify clear "Ozone is not configured" error
3. Call `ip_lookup` with `"not-an-ip"` — verify "Invalid IP address format" error
4. Call `url_expand` with a URL that times out — verify hop recorded with `statusCode: 0`

## Traceability

| Acceptance Criterion | Automated Test | Manual Step |
|----------------------|----------------|-------------|
| AC1.1-AC1.10 | test_clickhouse, test_domain, test_ip, test_url, test_whois_tool, test_content, test_cosharing | Phase 3: 3.1-3.8 |
| AC1.11-AC1.20 | test_ozone (handlers, query tools) | Phase 4: 4.1-4.4 |
| AC1.21 | test_server::test_all_tools_registered | Phase 2: 2.2 |
| AC2.1 | test_server::test_all_tools_have_input_schema_with_descriptions | Phase 2: 2.3 |
| AC2.2 | test_response_shapes::test_invalid_input_type_rejected | Phase 3: 3.7 |
| AC2.3 | test_response_shapes::test_missing_required_field_rejected | Phase 3: 3.8 |
| AC2.4 | test_response_shapes (7 shape tests) | Phase 3: verify live responses match shapes |
| AC3.1-AC3.7 | Various async/timeout/cache/refresh tests | Error Resilience |
| AC4.1-AC4.3 | test_sql_validation, test_whois_parser, test_url_shorteners | Fully automated |
| AC5.1-AC5.2 | test_config | Fully automated |
| AC5.3 | test_server::test_console_script_entry_point | Phase 1: 1.1-1.3 |
