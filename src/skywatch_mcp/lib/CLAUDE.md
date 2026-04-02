# Libraries

Last verified: 2026-04-02

## Purpose
Pure utility code with no MCP or framework dependency. These are the Functional Core modules that tools depend on.

## Contracts

### clickhouse_client
- **Exposes**: `get_client() -> ClickHouseClient` (lazy singleton), `QueryResult` dataclass
- **Guarantees**: `query()` rejects non-SELECT, missing LIMIT, semicolons, INTO. `query_trusted()` skips validation (60s vs 120s timeout). `get_schema()` returns columns for all known tables.
- **Expects**: `CLICKHOUSE_*` env vars for connection

### sql_validation
- **Exposes**: `validate_query(sql) -> ValidationSuccess | ValidationFailure`
- **Guarantees**: Only SELECT/WITH allowed. LIMIT clause required. No semicolons. No INTO keyword. Whitespace normalized.
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
- `ValidationResult` uses Python 3.12 type alias (`type X = A | B`) instead of inheritance
- ClickHouse client is a lazy singleton to share connections across tools
- SCHEMA_TABLES list is hardcoded -- must be updated when new ClickHouse tables are added
