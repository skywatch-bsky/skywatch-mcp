# Skywatch MCP Python Conversion Design

## Summary

Skywatch MCP is a Python port of an existing TypeScript MCP server that gives an LLM client (e.g. Claude) a set of structured tools for investigating activity on the AT Protocol / Bluesky network. The server exposes 21 tools across five domains: direct ClickHouse database access, network investigation (DNS, IP geolocation, URL expansion, WHOIS), co-sharing cluster analysis, content similarity search, and moderation actions via the Ozone API. The Python version is a functional drop-in for the TS server — same environment variables, same tool names, same wire shape — so existing plugin manifests require no changes.

The implementation uses the official MCP Python SDK's `FastMCP` layer, with tool handlers registered at import time via decorators. All I/O is async throughout: ClickHouse via `clickhouse-connect`'s `AsyncClient`, HTTP via `httpx`, DNS via `dnspython`'s async resolver, and WHOIS via an `asyncio.to_thread()` wrapper around the sync `python-whois` library. Input validation and response serialisation use Pydantic v2 models, replacing the TS version's Zod schemas. The project is managed by `uv` and targets Python 3.12+.

## Definition of Done

1. **A Python 3.12+ MCP server** managed by `uv`, exposing the same 11 tool categories (21 individual tools) as the TS version over stdio transport
2. **Pydantic models** for all tool inputs and structured responses, replacing Zod schemas
3. **Fully async** — all I/O (ClickHouse, HTTP, DNS, WHOIS) uses async/await
4. **Comprehensive tests** — pytest-based, covering SQL validation, tool handlers, and parsing logic
5. **Same env var configuration** — drop-in replacement for the TS server in the plugin manifest

## Acceptance Criteria

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.1 Success:** `clickhouse_query` executes valid SELECT and returns columns + rows
- **skywatch-mcp-py.AC1.2 Success:** `clickhouse_schema` returns column definitions for all queryable tables
- **skywatch-mcp-py.AC1.3 Success:** `domain_check` resolves A, AAAA, NS, MX, TXT, CNAME, SOA records
- **skywatch-mcp-py.AC1.4 Success:** `ip_lookup` returns geo, network, and flag data for valid IPv4/IPv6
- **skywatch-mcp-py.AC1.5 Success:** `url_expand` follows redirect chain up to 15 hops with status codes
- **skywatch-mcp-py.AC1.6 Success:** `whois_lookup` returns registrar, dates, nameservers, domain age
- **skywatch-mcp-py.AC1.7 Success:** `content_similarity` finds posts by ngramDistance within threshold
- **skywatch-mcp-py.AC1.8 Success:** `cosharing_clusters` returns cluster metadata with filtering
- **skywatch-mcp-py.AC1.9 Success:** `cosharing_pairs` returns paired accounts with edge weights
- **skywatch-mcp-py.AC1.10 Success:** `cosharing_evolution` traces cluster timeline with evolution types
- **skywatch-mcp-py.AC1.11–AC1.20 Success:** All 10 Ozone tools (label, comment, acknowledge, escalate, tag, mute, unmute, resolve_appeal, query_statuses, query_events) execute against Ozone API
- **skywatch-mcp-py.AC1.21 Success:** Server lists exactly 21 tools on startup

### skywatch-mcp-py.AC2: Pydantic models for all inputs/outputs
- **skywatch-mcp-py.AC2.1 Success:** Each tool has a Pydantic input model with field descriptions
- **skywatch-mcp-py.AC2.2 Failure:** Invalid input types rejected before handler execution
- **skywatch-mcp-py.AC2.3 Failure:** Missing required fields rejected with clear error message
- **skywatch-mcp-py.AC2.4 Success:** Response models serialise to JSON matching TS output shape

### skywatch-mcp-py.AC3: All I/O is async
- **skywatch-mcp-py.AC3.1 Success:** ClickHouse queries use AsyncClient (query + query_trusted)
- **skywatch-mcp-py.AC3.2 Success:** DNS resolution uses dnspython async resolver
- **skywatch-mcp-py.AC3.3 Success:** HTTP requests (ip-api, URL expansion, Ozone) use httpx AsyncClient
- **skywatch-mcp-py.AC3.4 Success:** WHOIS uses asyncio.to_thread() wrapper
- **skywatch-mcp-py.AC3.5 Failure:** Network timeouts (5s for HTTP, 60s/120s for ClickHouse) return error, don't hang
- **skywatch-mcp-py.AC3.6 Success:** Ozone session tokens cached and reused across requests
- **skywatch-mcp-py.AC3.7 Failure:** Expired Ozone token triggers auto-refresh, not auth error

### skywatch-mcp-py.AC4: Comprehensive tests
- **skywatch-mcp-py.AC4.1 Success:** SQL validation has all 42 test cases ported from TS
- **skywatch-mcp-py.AC4.2 Success:** Each tool module has handler tests with mocked I/O
- **skywatch-mcp-py.AC4.3 Success:** WHOIS parser and URL shortener list have unit tests

### skywatch-mcp-py.AC5: Drop-in replacement
- **skywatch-mcp-py.AC5.1 Success:** Same env var names accepted (CLICKHOUSE_HOST, OZONE_SERVICE_URL, etc.)
- **skywatch-mcp-py.AC5.2 Success:** Same defaults for all env vars (http://localhost, 8123, default, etc.)
- **skywatch-mcp-py.AC5.3 Success:** Server runs via `uv run skywatch-mcp` over stdio transport

## Glossary

- **MCP (Model Context Protocol)**: An open protocol for connecting LLM clients to external tool servers. The server exposes tools that a model can call during inference.
- **FastMCP**: The high-level layer in the official MCP Python SDK that handles tool registration, input validation dispatch, and stdio transport wiring via `@mcp.tool()` decorators.
- **stdio transport**: The communication channel between the MCP client and server — JSON-RPC messages over standard input/output rather than HTTP.
- **AT Protocol**: The open, federated social networking protocol underlying Bluesky. Accounts are identified by DIDs; content is addressed by AT-URIs.
- **Ozone**: The AT Protocol moderation service. Operators run their own Ozone instances to label, mute, escalate, and manage appeals for content and accounts.
- **DID (Decentralised Identifier)**: A globally unique, persistent identifier for an AT Protocol account (e.g. `did:plc:abc123`). Used as the canonical subject reference in moderation actions.
- **AT-URI**: A URI scheme for AT Protocol records, of the form `at://did/collection/rkey`. Used to reference specific posts or records.
- **ClickHouse**: A columnar OLAP database used here to store Skywatch's derived datasets (co-sharing clusters, post content, etc.).
- **ngramDistance**: A ClickHouse function that measures string similarity using n-gram overlap. Used by `content_similarity` to find posts with similar text.
- **Co-sharing**: A behavioural analysis technique that identifies accounts sharing the same URLs in close temporal proximity, used to detect coordinated inauthentic behaviour.
- **Pydantic v2**: A Python data validation library. Used here to define input models for each tool (replacing Zod) and to serialise structured responses.
- **pydantic-settings**: A Pydantic extension for loading and validating configuration from environment variables. Used for `ClickHouseSettings` and `OzoneSettings`.
- **uv**: A fast Python package and project manager (Astral). Replaces pip/poetry for dependency management and running the server entry point.
- **AsyncClient (clickhouse-connect)**: The async interface to ClickHouse provided by the `clickhouse-connect` library.
- **dnspython**: A Python DNS library with a native async resolver, used for all DNS record lookups in `domain_check`.
- **httpx**: A Python HTTP client with first-class async support. Used for IP geolocation, URL expansion, and all Ozone API calls.
- **asyncio.to_thread()**: A Python standard library function that runs a synchronous callable in a thread pool, making it awaitable. Used to wrap the sync `python-whois` library.
- **JWT session token**: A signed token used to authenticate requests to the Ozone API. The server caches and auto-refreshes these to avoid re-authenticating on every call.
- **XRPC**: The HTTP-based RPC protocol used by AT Protocol services, including Ozone.
- **ip-api.com**: A third-party geolocation API used by `ip_lookup` to return geographic and network metadata for IPv4/IPv6 addresses.
- **isError**: An MCP response field. When `True`, signals to the client that the tool call failed and the response content is an error message.
- **query_trusted()**: An internal ClickHouse query path that bypasses SQL validation. Used for internally constructed queries (co-sharing, content similarity) that don't need the user-input whitelist check.
- **Lazy singleton**: A pattern where a client instance is created on first use rather than at startup. Used for the ClickHouse `AsyncClient` to avoid connection overhead before any tool is called.

## Architecture

Python 3.12+ MCP server using the official `mcp` SDK's FastMCP layer over stdio transport. Tool registration via `@mcp.tool()` decorators with Pydantic model parameters for automatic input validation.

### Components

**Entry point** (`src/skywatch_mcp/server.py`): Creates `FastMCP("skywatch-mcp")` instance. Imports tool modules for registration at import time. Exposes `main()` for the `skywatch-mcp` console script entry point.

**Configuration** (`src/skywatch_mcp/config.py`): Two `pydantic-settings` classes — `ClickHouseSettings` and `OzoneSettings` — loading from environment variables with the same names as the TS version. Singleton instances created at module level.

**Models** (`src/skywatch_mcp/models/`): Pydantic v2 models for tool inputs and structured responses:
- `clickhouse.py` — `QueryResult`, `SchemaResult`, column/row types
- `domain.py` — `DnsResult`, `DnsRecord`, `HttpStatus`
- `ozone.py` — `SubjectRef`, `OzoneConfig`, session token types, event/status query params
- `whois.py` — `WhoisResult` (registrar, dates, nameservers, domain age)

**Library** (`src/skywatch_mcp/lib/`): Pure functions and client wrappers:
- `clickhouse_client.py` — async wrapper around `clickhouse-connect` `AsyncClient`. Lazy singleton. Two query paths: `query()` (validated, 60s timeout) and `query_trusted()` (no validation, 120s timeout). `get_schema()` for table metadata.
- `sql_validation.py` — pure function. Whitelist approach: only `SELECT`/`WITH`, mandatory `LIMIT`, no semicolons, no `INTO`. Returns normalised SQL on success.
- `url_shorteners.py` — set of known URL shortener domains (t.co, bit.ly, tinyurl.com, etc.)
- `whois_parser.py` — pure function. Extracts registrar, dates, nameservers, domain age from raw WHOIS text.

**Tools** (`src/skywatch_mcp/tools/`): Each module imports `mcp` from `server.py` and decorates async handler functions:
- `clickhouse.py` — `clickhouse_query`, `clickhouse_schema`
- `domain.py` — `domain_check` (dnspython async for all record types + httpx HEAD for HTTP status)
- `ip.py` — `ip_lookup` (httpx async to ip-api.com, IPv4/IPv6 validation)
- `url.py` — `url_expand` (httpx async with `follow_redirects=False`, max 15 hops, 5s per hop)
- `whois.py` — `whois_lookup` (python-whois via `asyncio.to_thread()`)
- `content.py` — `content_similarity` (builds ngramDistance query, uses `query_trusted()`)
- `cosharing.py` — `cosharing_clusters`, `cosharing_pairs`, `cosharing_evolution` (all build SQL internally, use `query_trusted()`)
- `ozone.py` — 10 tools: `ozone_label`, `ozone_comment`, `ozone_acknowledge`, `ozone_escalate`, `ozone_tag`, `ozone_mute`, `ozone_unmute`, `ozone_resolve_appeal`, `ozone_query_statuses`, `ozone_query_events`. Shared session management with cached JWT tokens and auto-refresh.

### Data Flow

```
Client (stdio) → FastMCP → @mcp.tool() handler
  → Pydantic validates input
  → Handler calls lib/ (clickhouse_client, dns, httpx, whois)
  → Returns JSON string or isError response
```

### External Integrations

| Service | Client | Transport | Auth |
|---------|--------|-----------|------|
| ClickHouse | clickhouse-connect AsyncClient | HTTP | User/password |
| ip-api.com | httpx | HTTP | None (free tier) |
| Bluesky PDS / Ozone | httpx | XRPC over HTTP | JWT session tokens |
| DNS | dnspython async resolver | UDP | None |
| WHOIS | python-whois (sync, wrapped) | TCP | None |

## Existing Patterns

This is a greenfield Python project — no existing Python codebase to follow. The design mirrors the TypeScript server's architecture:

- Tool modules register handlers with a central server instance (same pattern as TS `register*Tools()` functions, adapted to Python import-time decoration)
- Lazy singleton ClickHouse client (same as TS)
- Pure validation/parsing functions separated from I/O (same as TS `sql-validation.ts`, `whois-parser.ts`)
- Cached Ozone session tokens at module level with auto-refresh (same as TS)

**Divergences from TS patterns:**
- Pydantic models replace ad-hoc Zod schemas — richer validation, serialisation, and type safety
- `pydantic-settings` replaces manual `process.env` reads — validation on startup, type coercion
- `dnspython` replaces Node.js `dns.promises` — dedicated DNS library with caching
- `asyncio.to_thread()` for WHOIS instead of native async — python-whois is sync-only

## Implementation Phases

<!-- START_PHASE_1 -->
### Phase 1: Project Scaffolding
**Goal:** Initialise the uv-managed Python project with all dependencies and a minimal running MCP server.

**Components:**
- `pyproject.toml` — project metadata, dependencies, console script entry point
- `src/skywatch_mcp/__init__.py` — package marker
- `src/skywatch_mcp/server.py` — FastMCP instance, `main()` function
- `tests/` directory with `conftest.py`

**Dependencies:** None (first phase)

**Done when:** `uv sync` installs all deps, `uv run skywatch-mcp` starts and connects via stdio without errors, `uv run pytest` runs (even with no tests yet)
<!-- END_PHASE_1 -->

<!-- START_PHASE_2 -->
### Phase 2: Configuration & Core Library
**Goal:** Environment variable configuration and pure utility functions.

**Components:**
- `src/skywatch_mcp/config.py` — `ClickHouseSettings`, `OzoneSettings` via pydantic-settings
- `src/skywatch_mcp/lib/sql_validation.py` — SQL validation pure function
- `src/skywatch_mcp/lib/url_shorteners.py` — known shortener domain set
- `src/skywatch_mcp/lib/whois_parser.py` — WHOIS text parsing pure function
- `tests/test_sql_validation.py` — port all 42 TS test cases
- `tests/test_whois_parser.py` — WHOIS parsing tests

**Dependencies:** Phase 1

**Covers:** skywatch-mcp-py.AC2.1–AC2.4, skywatch-mcp-py.AC5.1–AC5.2

**Done when:** All pure function tests pass. Config loads from env vars with correct defaults and types.
<!-- END_PHASE_2 -->

<!-- START_PHASE_3 -->
### Phase 3: ClickHouse Client & Tools
**Goal:** Async ClickHouse client wrapper and the two ClickHouse tools.

**Components:**
- `src/skywatch_mcp/lib/clickhouse_client.py` — lazy async client, `query()`, `query_trusted()`, `get_schema()`
- `src/skywatch_mcp/models/clickhouse.py` — `QueryResult`, `SchemaResult` Pydantic models
- `src/skywatch_mcp/tools/clickhouse.py` — `clickhouse_query`, `clickhouse_schema` tool handlers
- `tests/test_clickhouse.py` — handler tests with mocked client

**Dependencies:** Phase 2

**Covers:** skywatch-mcp-py.AC1.1, skywatch-mcp-py.AC1.2, skywatch-mcp-py.AC3.1

**Done when:** Both tools registered, validated queries execute against mocked client, schema returns column definitions, invalid SQL rejected before execution.
<!-- END_PHASE_3 -->

<!-- START_PHASE_4 -->
### Phase 4: Network Tools (Domain, IP, URL, WHOIS)
**Goal:** The four network investigation tools.

**Components:**
- `src/skywatch_mcp/models/domain.py` — `DnsResult`, `DnsRecord`, `HttpStatus`
- `src/skywatch_mcp/models/whois.py` — `WhoisResult`
- `src/skywatch_mcp/tools/domain.py` — `domain_check` (dnspython async + httpx HEAD)
- `src/skywatch_mcp/tools/ip.py` — `ip_lookup` (httpx to ip-api.com)
- `src/skywatch_mcp/tools/url.py` — `url_expand` (manual redirect chain)
- `src/skywatch_mcp/tools/whois.py` — `whois_lookup` (python-whois via to_thread)
- `tests/test_domain.py`, `tests/test_ip.py`, `tests/test_url.py`, `tests/test_whois.py`

**Dependencies:** Phase 2

**Covers:** skywatch-mcp-py.AC1.3–AC1.6, skywatch-mcp-py.AC3.2–AC3.5

**Done when:** All four tools registered, DNS resolves all record types, IP validates addresses, URL follows redirect chains, WHOIS returns structured results. All tests pass with mocked I/O.
<!-- END_PHASE_4 -->

<!-- START_PHASE_5 -->
### Phase 5: Content Similarity Tool
**Goal:** ClickHouse ngramDistance-based text similarity search.

**Components:**
- `src/skywatch_mcp/tools/content.py` — `content_similarity` tool
- `tests/test_content.py` — query generation and handler tests

**Dependencies:** Phase 3 (ClickHouse client)

**Covers:** skywatch-mcp-py.AC1.7, skywatch-mcp-py.AC3.1

**Done when:** Tool builds correct ngramDistance queries with proper escaping, uses `query_trusted()`, returns similarity scores. Tests pass.
<!-- END_PHASE_5 -->

<!-- START_PHASE_6 -->
### Phase 6: Co-Sharing Analysis Tools
**Goal:** The three co-sharing cluster analysis tools.

**Components:**
- `src/skywatch_mcp/tools/cosharing.py` — `cosharing_clusters`, `cosharing_pairs`, `cosharing_evolution`
- `tests/test_cosharing.py` — query generation and handler tests

**Dependencies:** Phase 3 (ClickHouse client)

**Covers:** skywatch-mcp-py.AC1.8–AC1.10, skywatch-mcp-py.AC3.1

**Done when:** All three tools build correct SQL with proper input sanitisation (DID, cluster_id), use `query_trusted()` with 120s timeout, return structured results. Tests pass.
<!-- END_PHASE_6 -->

<!-- START_PHASE_7 -->
### Phase 7: Ozone Moderation Tools
**Goal:** All 10 Ozone moderation tools with shared session management.

**Components:**
- `src/skywatch_mcp/models/ozone.py` — `SubjectRef`, session types, query parameter models
- `src/skywatch_mcp/tools/ozone.py` — 10 tool handlers + session management (create, refresh, cache)
- `tests/test_ozone.py` — session management, request building, handler tests

**Dependencies:** Phase 2 (config)

**Covers:** skywatch-mcp-py.AC1.11–AC1.20, skywatch-mcp-py.AC3.6–AC3.7, skywatch-mcp-py.AC4.1–AC4.3

**Done when:** All 10 tools registered, session tokens cached and auto-refreshed, config validation rejects missing env vars, subject refs built correctly for DIDs and AT-URIs. Tests pass.
<!-- END_PHASE_7 -->

<!-- START_PHASE_8 -->
### Phase 8: Integration Verification & Cleanup
**Goal:** Verify all 21 tools are registered and the server is a drop-in replacement.

**Components:**
- `src/skywatch_mcp/server.py` — verify all tool module imports
- `tests/test_server.py` — tool registration count, tool name verification
- Verify `uv run skywatch-mcp` starts cleanly

**Dependencies:** Phases 3–7

**Covers:** skywatch-mcp-py.AC1.21, skywatch-mcp-py.AC5.3

**Done when:** Server starts, all 21 tools are listed, full test suite passes, no import errors.
<!-- END_PHASE_8 -->

## Additional Considerations

**Error handling:** All tools return `isError=True` with LLM-friendly messages on failure. Operational errors (network timeouts, ClickHouse errors) are caught per-tool, not globally. Config validation errors for Ozone tools include which env vars are missing.

**ClickHouse query safety:** The SQL validation whitelist approach is ported exactly from the TS version. This is a security boundary — the validation logic must be identical in behaviour, verified by porting all 42 test cases.

**WHOIS sync wrapping:** `asyncio.to_thread()` runs WHOIS lookups in the default thread pool executor. This is acceptable because WHOIS lookups are infrequent and short-lived. No thread pool sizing needed.
