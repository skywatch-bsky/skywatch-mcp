# MCP Tools

Last verified: 2026-11-14

## Purpose
Expose AT Protocol investigation and moderation capabilities as MCP tools. Each module registers tools on the shared `mcp` MCPServer instance (official MCP Python SDK) via decorator side-effects at import time.

## Contracts
- **Exposes**: 33 MCP tools across 12 modules
- **Guarantees**: All tools return JSON strings wrapped by the SDK into text content plus `{"result": <string>}` structured content. Safe validation/configuration errors surface as SDK `ToolError` messages; backend failure details are masked.
- **Expects**: Every tool is decorated `@mcp.tool()` over `@tool_error_boundary` (boundary directly beneath the registration decorator). `server.mcp` must be instantiated before tool module imports

## Tool Inventory
| Module | Tools | External Dependency |
|--------|-------|-------------------|
| account_entropy | `account_entropy_results`, `account_entropy_trend` | ClickHouse (via lib) |
| clickhouse | `clickhouse_query`, `clickhouse_schema` | ClickHouse (via lib) |
| content | `content_similarity` | ClickHouse (via lib) |
| cosharing | `cosharing_clusters`, `cosharing_pairs`, `cosharing_evolution`, `cosharing_runs`, `quote_cosharing_clusters`, `quote_cosharing_pairs`, `quote_cosharing_evolution` | ClickHouse (via lib) |
| domain | `domain_check` | DNS (dnspython), HTTP |
| ip | `ip_lookup` | ip-api.com |
| ozone | `ozone_label`, `ozone_comment`, `ozone_acknowledge`, `ozone_escalate`, `ozone_tag`, `ozone_mute`, `ozone_unmute`, `ozone_resolve_appeal`, `ozone_report`, `ozone_query_statuses`, `ozone_query_events` | Ozone API via PDS proxy |
| quote_overdispersion | `quote_overdispersion_results`, `quote_overdispersion_trend` | ClickHouse (via lib) |
| signup_anomaly | `signup_anomalies`, `signup_anomaly_trend` | ClickHouse (via lib) |
| url | `url_expand` | HTTP (follows redirects) |
| url_overdispersion | `url_overdispersion_results`, `url_overdispersion_trend` | ClickHouse (via lib) |
| whois | `whois_lookup` | python-whois (via lib) |

## Key Decisions
- Tool registration via import side-effects: keeps server.py minimal, tools self-contained
- Error boundary in `lib/tool_errors.py`: handlers stay free of try/except rewrapping; `ToolInputError` (safe input/config problems) is translated to SDK `ToolError` with its message intact, `TimeoutError`/`httpx.TimeoutException`/`httpx.ConnectError` get fixed detail-free messages, and everything else propagates for SDK masking. `functools.wraps` keeps handler signatures visible so schema discovery is unchanged
- `query()` vs `query_trusted()`: user-supplied SQL is validated; internal SQL (cosharing, content, sidecar tools) uses trusted path with longer timeout
- Ozone session management: module-level cache with automatic refresh on ExpiredToken
- Sanitizers promoted to `lib/sanitizers.py` — shared across all tool modules
- Cosharing queries use manual DID/cluster_id/date sanitization (regex allowlist) instead of parameterized queries
- Cosharing numeric parameters (min_members, min_weight) explicitly cast to int for defense-in-depth validation
- `ozone_report` report_type: friendly names resolve via `REPORT_TYPE_MAP`; any `#`-containing reason NSID passes through verbatim; anything else raises `ToolInputError`

## Invariants
- clickhouse_query only permits SELECT/WITH statements with a LIMIT clause
- Ozone tools validate configuration before any API call
- AT-URI subjects require a CID parameter; DID subjects do not
- Cosharing date parameters must be YYYY-MM-DD format (validated at query-build time)
- Overdispersion tools expose two independent signals (volume, density); `signal` parameter filters which signal drives the anomaly
- Account entropy uses fixed normalized thresholds, not BH-FDR q-values
