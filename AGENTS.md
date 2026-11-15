# skywatch-mcp

Last verified: 2026-11-15

## Tech Stack
- Language: Python 3.12+, strict mypy
- Framework: MCP Python SDK (`mcp` 2.3, `MCPServer` from `mcp.server`), stdio default with optional streamable HTTP (`SKYWATCH_TRANSPORT=http`), MCP 2026-07-28 with 2025-11-25 legacy support
- Database: ClickHouse (read-only analytics queries)
- External APIs: Ozone (AT Protocol moderation), ip-api.com, python-whois
- HTTP: httpx (async)
- Config: pydantic-settings (env vars)
- Testing: pytest + pytest-asyncio
- Linting: ruff, mypy --strict

## Commands
- `uv run pytest` -- run all tests
- `uv run pytest tests/test_foo.py` -- run single test file
- `uv run mypy src/` -- type check
- `uv run ruff check src/ tests/` -- lint
- `uv run skywatch-mcp` -- start server (stdio transport)
- `SKYWATCH_TRANSPORT=http uv run skywatch-mcp` -- start server (streamable HTTP, host/port via `SKYWATCH_HOST`/`SKYWATCH_PORT`)

## Project Structure
- `src/skywatch_mcp/server.py` -- MCPServer app, registers all tool modules via import side-effects
- `src/skywatch_mcp/config.py` -- ClickHouseSettings and OzoneSettings (pydantic-settings, env vars)
- `src/skywatch_mcp/tools/` -- MCP tool functions (12 modules, 35 tools): ClickHouse analytics (query, schema selection, health, rule summary), reputation lookups (domain, IP, URL, WHOIS, content similarity), Ozone moderation, statistical anomaly detection (account_entropy, signup_anomaly, cosharing, quote_overdispersion, url_overdispersion)
- `src/skywatch_mcp/lib/` -- Reusable helpers: SQL validation, WHOIS parsing, URL shortener list, ClickHouse client (classification, query_id correlation, bounded DESCRIBE schema fetch, 1 MiB result budget), Ozone API client (`OzoneClient` in `ozone_api.py`: cached sessions, auto-refresh on ExpiredToken), error boundary (`tool_errors.py`: `ToolInputError`, `BackendError`, `tool_error_boundary`)
- `src/skywatch_mcp/models/` -- Empty, reserved for future Pydantic models
- `tests/` -- Offline suite, no external service dependencies (protocol tests spawn the real stdio server in a temporary directory); `tests/test_live_backend.py` is opt-in gated (`SKYWATCH_LIVE_CH=1`, Ozone live checks additionally `SKYWATCH_LIVE_OZONE=1`) and skipped by default
- `docs/measurements/` -- Recorded measurement artifacts backing provisional limits

## Conventions
- Functional Core / Imperative Shell pattern (annotated with `# pattern:` comments)
- All tools register on the shared `mcp` instance from `server.py`
- Tool functions return JSON strings. This is a compatibility convention, not a protocol requirement: the SDK wraps each string into text content plus a `{"result": <string>}` structured payload. Changing a tool to return a dict changes its output shape and its clients.
- Error boundary (`src/skywatch_mcp/lib/tool_errors.py`): every tool sits under `@tool_error_boundary` (below `@mcp.tool()`). Three distinct channels: (1) `ToolInputError` for safe validation/configuration failures — reaches clients as SDK `ToolError` with an actionable message; (2) `BackendError` for classified ClickHouse backend failures — reaches clients as `ToolError` whose message is the SDK prefix plus parseable JSON (`kind`, `retryable`, `query_id`, numeric `code`, fixed allowlisted `message`), never raw backend text, hosts, URLs, or SQL; (3) everything else, including plain `ValueError`, stays masked as `Error executing tool <name>`. Logging from backend-failure paths carries only `kind`, `code`, `query_id`.
- Pure helpers (`lib/sanitizers.py`, query builders, `_build_subject_ref`) raise `ToolInputError` for user-facing input problems. A plain `ValueError` is masked by the SDK like any backend failure, so never raise plain `ValueError` for messages clients need to read.
- ClickHouse queries from user input go through `query()` (validated); internal queries use `query_trusted()` (optional keyword-only typed bound `parameters`, `max_execution_time` override). Every query carries a UUID `query_id` for `system.query_log` correlation, echoed in success `meta` and error payloads.
- Measured limits: 60 s user-query budget / 120 s trusted budget / 10 s deadline grace / 130 s driver socket bound (code-measured); 10 s per-table DESCRIBE + 60 s overall schema deadline; 1 MiB `RESULT_BYTE_BUDGET` on the final serialized output (provisional — see `docs/measurements/2026-11-15-serialization-budget.md`; effective server `max_query_size` unknown until the gated live check reads `system.settings`). Result truncation does not bound driver-side memory; memory is bounded by the caller's LIMIT and server limits.
- Ozone tools use module-level session cache with auto-refresh on ExpiredToken; event-type filters accept short names and full `tools.ozone.moderation.defs#modEvent*` NSIDs interchangeably via `normalize_event_types`.
- `clickhouse_rule_summary` requires `VERIFIED_RULE_CATALOGUE` (authoritative provenance; ships EMPTY, failing closed with structured `rule_catalogue_unavailable`) — flag candidacy alone never verifies rule identity.

## Environment Variables
- `SKYWATCH_TRANSPORT` (`stdio`|`http`, default `stdio`), `SKYWATCH_HOST` (default `127.0.0.1`), `SKYWATCH_PORT` (default `8000`) -- server process settings (`ServerSettings`)
- `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_TAILNET_IP`
- `OZONE_HANDLE`, `OZONE_ADMIN_PASSWORD`, `OZONE_DID`, `OZONE_PDS` -- required for Ozone tools (`OzoneSettings.is_configured`)
- `OZONE_SERVICE_URL` -- defined in `OzoneSettings` but currently unused; Ozone requests go to `https://<OZONE_PDS>/xrpc/...`

## Boundaries
- All ClickHouse access is read-only (SELECT/WITH only, enforced by sql_validation)
- Ozone write operations are limited to moderation events (label, comment, tag, mute, report, etc.)
- No direct database writes anywhere in the codebase
