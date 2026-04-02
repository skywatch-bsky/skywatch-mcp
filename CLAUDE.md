# skywatch-mcp

Last verified: 2026-04-02

## Tech Stack
- Language: Python 3.12+, strict mypy
- Framework: FastMCP (MCP protocol server)
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

## Project Structure
- `src/skywatch_mcp/server.py` -- FastMCP app, registers all tool modules via import side-effects
- `src/skywatch_mcp/config.py` -- ClickHouseSettings and OzoneSettings (pydantic-settings, env vars)
- `src/skywatch_mcp/tools/` -- MCP tool functions (8 modules, 20 tools)
- `src/skywatch_mcp/lib/` -- Pure utilities: SQL validation, WHOIS parsing, URL shortener list, ClickHouse client
- `src/skywatch_mcp/models/` -- Empty, reserved for future Pydantic models
- `tests/` -- 242 tests, all async, no external service dependencies

## Conventions
- Functional Core / Imperative Shell pattern (annotated with `# pattern:` comments)
- All tools register on the shared `mcp` instance from `server.py`
- Tool functions return JSON strings (not dicts) -- MCP protocol requirement
- Tool errors raise `ValueError` with user-facing messages
- ClickHouse queries from user input go through `query()` (validated); internal queries use `query_trusted()`
- Ozone tools use module-level session cache with auto-refresh on ExpiredToken

## Environment Variables
- `CLICKHOUSE_HOST`, `CLICKHOUSE_PORT`, `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`, `CLICKHOUSE_DATABASE`, `CLICKHOUSE_TAILNET_IP`
- `OZONE_SERVICE_URL`, `OZONE_HANDLE`, `OZONE_ADMIN_PASSWORD`, `OZONE_DID`, `OZONE_PDS`

## Boundaries
- All ClickHouse access is read-only (SELECT/WITH only, enforced by sql_validation)
- Ozone write operations are limited to moderation events (label, comment, tag, mute, etc.)
- No direct database writes anywhere in the codebase
