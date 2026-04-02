# Test Requirements: skywatch-mcp-py Acceptance Criteria

Maps every acceptance criterion from the design to either an automated test or a documented human verification step.

---

## Automated Tests

| AC ID | Description | Test Type | Test File | Automated? | Notes |
|-------|-------------|-----------|-----------|------------|-------|
| AC1.1 | `clickhouse_query` executes valid SELECT and returns columns + rows | Unit | `tests/test_clickhouse.py` | Yes | Mock AsyncClient; verify JSON has `columns` and `rows` keys |
| AC1.2 | `clickhouse_schema` returns column definitions for all queryable tables | Unit | `tests/test_clickhouse.py` | Yes | Mock DESCRIBE TABLE for 11 tables; verify `table` field appended to rows |
| AC1.3 | `domain_check` resolves A, AAAA, NS, MX, TXT, CNAME, SOA records | Unit | `tests/test_domain.py` | Yes | Mock `dns.asyncresolver.Resolver().resolve()` for each record type |
| AC1.4 | `ip_lookup` returns geo, network, and flag data for valid IPv4/IPv6 | Unit | `tests/test_ip.py` | Yes | Mock httpx GET to ip-api.com; test `_validate_ip_address` directly |
| AC1.5 | `url_expand` follows redirect chain up to 15 hops with status codes | Unit | `tests/test_url.py` | Yes | Mock httpx HEAD with chained 301/302/200 responses; verify hop list and max-hop error |
| AC1.6 | `whois_lookup` returns registrar, dates, nameservers, domain age | Unit | `tests/test_whois_tool.py` | Yes | Mock `whois.whois()` returning sample `.text`; verify parsed fields |
| AC1.7 | `content_similarity` finds posts by ngramDistance within threshold | Unit | `tests/test_content.py` | Yes | Test `_escape_clickhouse_sql` and `_build_similarity_query` directly; mock ClickHouseClient for handler |
| AC1.8 | `cosharing_clusters` returns cluster metadata with filtering | Unit | `tests/test_cosharing.py` | Yes | Test `_build_clusters_query` for each filter combination (DID, cluster_id, date, min_members, default) |
| AC1.9 | `cosharing_pairs` returns paired accounts with edge weights | Unit | `tests/test_cosharing.py` | Yes | Test `_build_pairs_query`; verify DID sanitisation in generated SQL |
| AC1.10 | `cosharing_evolution` traces cluster timeline with evolution types | Unit | `tests/test_cosharing.py` | Yes | Test `_build_evolution_query` includes `has()` for predecessor lookup |
| AC1.11 | `ozone_label` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify event body has correct `$type`, `createLabelVals`/`negateLabelVals` |
| AC1.12 | `ozone_comment` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify calls `_emit_ozone_event` with correct `$type` |
| AC1.13 | `ozone_acknowledge` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify event `$type` and `acknowledgeAccountSubjects` field |
| AC1.14 | `ozone_escalate` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify event `$type` |
| AC1.15 | `ozone_tag` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify `add`/`remove` arrays in event body |
| AC1.16 | `ozone_mute` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify `durationInHours` in event body |
| AC1.17 | `ozone_unmute` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify event `$type` |
| AC1.18 | `ozone_resolve_appeal` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx; verify comment is required |
| AC1.19 | `ozone_query_statuses` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx GET; verify review_state shorthand mapped to full `tools.ozone.moderation.defs#*` type |
| AC1.20 | `ozone_query_events` executes against Ozone API | Unit | `tests/test_ozone.py` | Yes | Mock httpx GET; verify event type shorthand mapping and query string construction |
| AC1.21 | Server lists exactly 21 tools on startup | Integration | `tests/test_server.py` | Yes | Import `mcp` instance; assert tool count == 21 and verify all 21 tool names |
| AC2.1 | Each tool has a Pydantic input model with field descriptions | Integration | `tests/test_server.py` | Yes | FastMCP auto-generates input models from `Annotated[type, Field(description=...)]`; verify each registered tool has an input schema with descriptions |
| AC2.2 | Invalid input types rejected before handler execution | Unit | `tests/test_response_shapes.py` | Yes | Call tool with wrong type (e.g. int where str expected); verify rejection before handler runs |
| AC2.3 | Missing required fields rejected with clear error message | Unit | `tests/test_response_shapes.py` | Yes | Call tool omitting required param; verify error message names the missing field |
| AC2.4 | Response models serialise to JSON matching TS output shape | Unit | `tests/test_response_shapes.py` | Yes | Verify key shapes: `clickhouse_query` has `{columns, rows}`, `ip_lookup` has `{ip, geo, network, flags}`, `domain_check` has `{domain, resolves, records, http}`, `url_expand` has `{originalUrl, finalUrl, hops, hopCount}`, `content_similarity` returns list of `{user, handle, text, score, created_at}`, `cosharing_*` returns `{query, rows, count}` |
| AC3.1 | ClickHouse queries use AsyncClient (query + query_trusted) | Unit | `tests/test_clickhouse.py` | Yes | Tests use `async def` with `await`; mock verifies `clickhouse_connect.get_async_client` called |
| AC3.2 | DNS resolution uses dnspython async resolver | Unit | `tests/test_domain.py` | Yes | Mock `dns.asyncresolver.Resolver`; verify async resolve calls |
| AC3.3 | HTTP requests use httpx AsyncClient | Unit | `tests/test_ip.py`, `tests/test_url.py`, `tests/test_ozone.py` | Yes | Mock `httpx.AsyncClient`; verify async request methods called |
| AC3.4 | WHOIS uses asyncio.to_thread() wrapper | Unit | `tests/test_whois_tool.py` | Yes | Mock `whois.whois()`; verify sync function runs via `asyncio.to_thread` |
| AC3.5 | Network timeouts return error, don't hang | Unit | `tests/test_url.py`, `tests/test_ip.py` | Yes | Mock httpx to raise `TimeoutException`; verify error returned (not hang). URL expand: timeout records `statusCode: 0`. IP lookup: raises ValueError with timeout message |
| AC3.6 | Ozone session tokens cached and reused across requests | Unit | `tests/test_ozone.py` | Yes | Call `_get_access_token` twice; verify `_create_session` called only once (second call returns cached) |
| AC3.7 | Expired Ozone token triggers auto-refresh, not auth error | Unit | `tests/test_ozone.py` | Yes | Mock first response with "ExpiredToken" body; verify `_refresh_session` called and request retried |
| AC4.1 | SQL validation has all 42 test cases ported from TS | Unit | `tests/test_sql_validation.py` | Yes | Port all test groups: reject non-SELECT (7), require LIMIT (5), allow JOINs/UNIONs (4), allow any table (4), case-insensitive (2), whitespace normalisation (3), edge cases (4), data export prevention (4), plus remaining sub-assertions |
| AC4.2 | Each tool module has handler tests with mocked I/O | Unit | `tests/test_clickhouse.py`, `tests/test_domain.py`, `tests/test_ip.py`, `tests/test_url.py`, `tests/test_whois_tool.py`, `tests/test_content.py`, `tests/test_cosharing.py`, `tests/test_ozone.py` | Yes | One test file per tool module; all I/O mocked |
| AC4.3 | WHOIS parser and URL shortener list have unit tests | Unit | `tests/test_whois_parser.py`, `tests/test_url_shorteners.py` | Yes | WHOIS: registrar, dates, nameservers, domain age, empty fields, raw text. URL shorteners: all 15 domains, case-insensitive, unknown domains, empty string |
| AC5.1 | Same env var names accepted | Unit | `tests/test_config.py` | Yes | Use `monkeypatch.setenv()` to set CLICKHOUSE_HOST, CLICKHOUSE_PORT, etc.; verify settings load correctly. Verify CLICKHOUSE_TAILNET_IP overrides host |
| AC5.2 | Same defaults for all env vars | Unit | `tests/test_config.py` | Yes | Instantiate settings with no env vars; verify host=http://localhost, port=8123, user=default, password="", database=default, Ozone fields=None |

## Human Verification

| AC ID | Description | Automated? | Justification | Verification Approach |
|-------|-------------|------------|---------------|----------------------|
| AC5.3 | Server runs via `uv run skywatch-mcp` over stdio transport | No | Requires a running process with stdio I/O; cannot be fully verified in pytest without subprocess management and JSON-RPC protocol handshake | Run `echo '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1.0"}},"id":1}' \| uv run skywatch-mcp` and verify a JSON-RPC response is returned. Also verify `uv run skywatch-mcp` starts without import errors (Ctrl+C to stop). Partially automated in `tests/test_server.py` by verifying `skywatch_mcp.server:main` is importable and callable |

## Coverage Summary

| Category | Total ACs | Automated | Human Only |
|----------|-----------|-----------|------------|
| AC1: Tools exposed and functional | 21 | 21 | 0 |
| AC2: Pydantic models | 4 | 4 | 0 |
| AC3: All I/O async | 7 | 7 | 0 |
| AC4: Comprehensive tests | 3 | 3 | 0 |
| AC5: Drop-in replacement | 3 | 2 | 1 |
| **Total** | **38** | **37** | **1** |

## Test File Index

| Test File | Phase | ACs Covered |
|-----------|-------|-------------|
| `tests/test_config.py` | 2 | AC5.1, AC5.2 |
| `tests/test_sql_validation.py` | 2 | AC4.1 |
| `tests/test_url_shorteners.py` | 2 | AC4.3 (partial) |
| `tests/test_whois_parser.py` | 2 | AC4.3 (partial) |
| `tests/test_clickhouse.py` | 3 | AC1.1, AC1.2, AC3.1, AC4.2 (partial) |
| `tests/test_domain.py` | 4 | AC1.3, AC3.2, AC4.2 (partial) |
| `tests/test_ip.py` | 4 | AC1.4, AC3.3, AC3.5 (partial), AC4.2 (partial) |
| `tests/test_url.py` | 4 | AC1.5, AC3.3, AC3.5 (partial), AC4.2 (partial) |
| `tests/test_whois_tool.py` | 4 | AC1.6, AC3.4, AC4.2 (partial) |
| `tests/test_content.py` | 5 | AC1.7, AC3.1, AC4.2 (partial) |
| `tests/test_cosharing.py` | 6 | AC1.8, AC1.9, AC1.10, AC4.2 (partial) |
| `tests/test_ozone.py` | 7 | AC1.11-AC1.20, AC3.3, AC3.6, AC3.7, AC4.2 (partial) |
| `tests/test_server.py` | 8 | AC1.21, AC2.1, AC5.3 (partial) |
| `tests/test_response_shapes.py` | 8 | AC2.2, AC2.3, AC2.4 |
