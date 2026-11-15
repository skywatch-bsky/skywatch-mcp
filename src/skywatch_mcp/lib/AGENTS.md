# Libraries

Last verified: 2026-11-15

## Purpose
Reusable library modules. Most are Functional Core (pure, no I/O); `clickhouse_client.py` is a narrowly-scoped Imperative Shell adapter (driver I/O behind the client class), and `tool_errors.py` is the SDK error boundary itself, the only module allowed to import from `mcp` and `httpx`.

## Contracts

### tool_errors
- **Exposes**: `ToolInputError(ValueError)`, `BackendError(Exception)`, `tool_error_boundary(fn)` async decorator
- **Guarantees**: The boundary translates `ToolInputError` to the SDK's `ToolError`, whose message reaches clients prefixed as `Error executing tool <name>: <message>`; `BackendError` is translated to `ToolError(json.dumps(payload))` carrying `kind`, `retryable`, `query_id`, numeric `code`, and a fixed allowlisted `message` — never raw backend text; `TimeoutError`, `httpx.TimeoutException`, and `httpx.ConnectError` become fixed detail-free `ToolError` messages; every other exception (including plain `ValueError`) propagates unchanged so the SDK masks it. `functools.wraps` preserves the handler signature for schema discovery, so the raw handler stays reachable as `tool.__wrapped__` in tests.
- **Error-channel discipline**: `BackendError` = classified backend failure (structured, safe-to-forward). `ToolInputError` = validation/configuration failure with actionable text. These channels are distinct and never conflated.
- **Logging discipline**: the boundary logs only `kind`, `code`, and `query_id` from a `BackendError` — never the original exception text.
- **Expects**: Applied directly beneath `@mcp.tool()` on every tool

### clickhouse_client
- **Exposes**: `get_client() -> ClickHouseClient` (lazy singleton), `QueryResult` dataclass (`columns`, `rows`, `query_id`, `elapsed_ms`, `coverage`), `serialize_rows(columns, rows, extra_meta) -> (text, meta)`, constants `SCHEMA_TABLES`, `OSPREY_RESULTS_TABLE`, `RESULT_BYTE_BUDGET`, `DRIVER_SOCKET_TIMEOUT_SECONDS`
- **Guarantees**: Every query carries a generated UUID `query_id` passed via `transport_settings` and echoed in `QueryResult.query_id`; per-call budgets go through `settings={"max_execution_time": budget}` plus an `asyncio.timeout(budget + 10s grace)` deadline; the driver socket itself is bounded at 130 s (`send_receive_timeout`), since executor-thread cancellation is best-effort. Driver failures are classified by `_classify_backend_exception` (numeric ClickHouse exception codes, HTTP status, and stable connection phrases only — surrounding text is discarded) into `BackendError` kinds: `backend_unavailable`, `auth_failed`, `invalid_sql`, `request_too_large`, `timeout`, `unknown`. `query()` rejects non-SELECT, missing LIMIT, semicolons, INTO with a `ToolInputError` naming the reason (60 s budget); `query_trusted()` skips validation (120 s default, keyword-only `max_execution_time`, optional typed bound `parameters`). `get_table_columns(table)` = one bounded `DESCRIBE` (10 s) with scope-relative coverage. `get_schema()` reproduces the legacy per-table `DESCRIBE` contract byte-exactly (row keys + fully qualified `table` tagging) with fail-fast on global failure classes, per-table `invalid_sql` recorded in `coverage.tables_missing` with numeric codes, an overall 60 s deadline, and a classified error when every table fails — never an empty success. The `clickhouse_connect` logging namespace is pinned to ERROR at client construction so the driver's own WARNING-level raw-body logging is redacted.
- **Budget**: `serialize_rows` enforces `RESULT_BYTE_BUDGET` (1 MiB, provisional pending live verification of effective `max_query_size`) against the final composed output text in UTF-8 bytes — columns, rows, meta, escaping, indentation. Rows are indivisible; truncated responses are compact JSON with `meta.truncated`/`meta.rows_returned` (plus a `note` when the first row alone exceeds the budget). Fully-fitting responses keep `indent=2`, except when pretty-printing alone overflows the budget and the compact complete form fits — that returns compact with `truncated: false`. Truncation-path admission is linear (pre-encoded rows, conservative meta bound without the note). Known limitation: truncation does not bound driver-side memory — rows are materialized before budgeting; memory is bounded only by the caller's LIMIT and server limits. Measurement record: `docs/measurements/2026-11-15-serialization-budget.md`; budget revisions require recorded evidence.
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
- `BackendError` deliberately does NOT subclass `ValueError`: plain `ValueError` keeps the masked SDK path, and only explicitly classified failures reach clients
- Error classification parses only numeric signals out of driver messages, so clickhouse-connect format drift degrades to kind `unknown` instead of leaking text
- Schema fetching stays on per-table `DESCRIBE` (not `system.columns`): the published `system.columns` contract lacks `codec_expression`/`ttl_expression` fidelity, and DESCRIBE is the legacy byte-exact source
