# Libraries

Last verified: 2026-11-14

## Purpose
Pure utility code with no MCP or framework dependency. These are the Functional Core modules that tools depend on. The one exception is `tool_errors.py`, which is the SDK error boundary itself and is therefore allowed to import from `mcp` and `httpx`.

## Contracts

### tool_errors
- **Exposes**: `ToolInputError(ValueError)`, `tool_error_boundary(fn)` async decorator
- **Guarantees**: The boundary translates `ToolInputError` to the SDK's `ToolError`, whose message reaches clients prefixed as `Error executing tool <name>: <message>`; `TimeoutError`, `httpx.TimeoutException`, and `httpx.ConnectError` become fixed detail-free `ToolError` messages; every other exception propagates unchanged so the SDK masks it. `functools.wraps` preserves the handler signature for schema discovery.
- **Expects**: Applied directly beneath `@mcp.tool()` on every tool

### clickhouse_client
- **Exposes**: `get_client() -> ClickHouseClient` (lazy singleton), `QueryResult` dataclass
- **Guarantees**: `query()` rejects non-SELECT, missing LIMIT, semicolons, INTO — with a `ToolInputError` naming the reason — and raises `TimeoutError` with a fixed message on deadline overrun. `query_trusted()` skips validation (60s vs 120s timeout). `get_schema()` returns columns for all known tables.
- **Expects**: `CLICKHOUSE_*` env vars for connection

### sql_validation
- **Exposes**: `validate_query(sql) -> ValidationSuccess | ValidationFailure`
- **Guarantees**: Only SELECT/WITH allowed. LIMIT clause required. No semicolons. No INTO keyword. Whitespace normalized.
- **Pure**: No side effects, no I/O

### sanitizers
- **Exposes**: `sanitize_date`, `sanitize_did`, `sanitize_hostname`, `sanitize_at_uri`, `sanitize_cluster_id`, `validate_limit`, `validate_days`, `validate_q_value`, `validate_threshold`
- **Guarantees**: Validators raise `ToolInputError` (a `ValueError` subclass) on bad input, so pure-helper callers that catch `ValueError` keep working and the tool boundary forwards the message to clients.
- **Pure**: No side effects, no I/O

### whois_parser
- **Exposes**: `parse_whois_response(raw_text) -> WhoisResult`
- **Guarantees**: Extracts registrar, dates, nameservers via regex. Calculates domain age in days. Never raises on unparseable input (fields return None).
- **Pure**: No side effects, no I/O

### url_shorteners
- **Exposes**: `is_known_shortener(hostname) -> bool`, `KNOWN_SHORTENERS` frozenset
- **Guarantees**: Case-insensitive hostname matching against known shortener domains
- **Pure**: No side effects, no I/O

## Key Decisions
- `ValidationResult` uses `TypeAlias` from `typing` for Python 3.10+ compatibility
- ClickHouse client is a lazy singleton to share connections across tools
- SCHEMA_TABLES list is hardcoded -- must be updated when new ClickHouse tables are added
- `ToolInputError` subclasses `ValueError` instead of replacing it: existing helper-level callers and tests keep their contract, and only the tool boundary decides what reaches clients
