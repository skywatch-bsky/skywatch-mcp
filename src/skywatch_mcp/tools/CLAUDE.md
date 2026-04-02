# MCP Tools

Last verified: 2026-04-02

## Purpose
Expose AT Protocol investigation and moderation capabilities as MCP tools. Each module registers tools on the shared `mcp` FastMCP instance via decorator side-effects at import time.

## Contracts
- **Exposes**: 20 MCP tools across 8 modules
- **Guarantees**: All tools return JSON strings. All errors raise `ValueError`.
- **Expects**: `server.mcp` must be instantiated before tool module imports

## Tool Inventory
| Module | Tools | External Dependency |
|--------|-------|-------------------|
| clickhouse | `clickhouse_query`, `clickhouse_schema` | ClickHouse (via lib) |
| content | `content_similarity` | ClickHouse (via lib) |
| cosharing | `cosharing_clusters`, `cosharing_pairs`, `cosharing_evolution` | ClickHouse (via lib) |
| domain | `domain_check` | DNS (dnspython), HTTP |
| ip | `ip_lookup` | ip-api.com |
| ozone | `ozone_label`, `ozone_comment`, `ozone_acknowledge`, `ozone_escalate`, `ozone_tag`, `ozone_mute`, `ozone_unmute`, `ozone_resolve_appeal`, `ozone_query_statuses`, `ozone_query_events` | Ozone API via PDS proxy |
| url | `url_expand` | HTTP (follows redirects) |
| whois | `whois_lookup` | python-whois (via lib) |

## Key Decisions
- Tool registration via import side-effects: keeps server.py minimal, tools self-contained
- `query()` vs `query_trusted()`: user-supplied SQL is validated; internal SQL (cosharing, content) uses trusted path with longer timeout
- Ozone session management: module-level cache with automatic refresh on ExpiredToken
- Cosharing queries use manual DID/cluster_id/date sanitization (regex allowlist) instead of parameterized queries
- Cosharing numeric parameters (min_members, min_weight) explicitly cast to int for defense-in-depth validation

## Invariants
- clickhouse_query only permits SELECT/WITH statements with a LIMIT clause
- Ozone tools validate configuration before any API call
- AT-URI subjects require a CID parameter; DID subjects do not
- Cosharing date parameters must be YYYY-MM-DD format (validated at query-build time)
