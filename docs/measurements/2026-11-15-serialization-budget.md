# Serialization-boundary measurement for `RESULT_BYTE_BUDGET` (Phase 0)

Measured: 2026-11-15, before any implementation change (baseline: 502 tests green).
Environment: Python 3.12, `json.dumps(..., default=str)` composition identical to the
`clickhouse_query` output path, SDK wrapping emulated as
`json.dumps({"content": [{"type": "text", "text": text}], "structuredContent": {"result": text}})`.

## Recorded outcomes

Synthetic `QueryResult`s were pushed through the actual output path (`json.dumps` with
`indent=2` for `{columns, rows, meta}` plus the SDK's JSON-string wrapping). UTF-8 byte sizes:

| Scenario | tool output (bytes) | SDK-wrapped (bytes) |
|---|---|---|
| Representative: 50 rows x 4 short columns, `indent=2` | 8,171 | 18,356 |
| Mid: 1,000 rows x 4 short columns, `indent=2` | 157,133 | 350,480 |
| Boundary: 6,450 rows x 4 short columns, `indent=2` | 1,011,693 | n/a |
| Multibyte row (CJK + emoji content) | measured per-UTF-8-byte, see serialize_rows tests | n/a |
| Escaped-JSON row (quotes/backslashes x 5,000) | 90,260 | n/a |
| Oversized first row (1.1 MB single row) → zero-row fallback output | 212 | n/a |
| Zero-row minimal response | 328 | n/a |

Key observations:

1. **The SDK JSON-string wrapping multiplies wire size ~2.25x** (indentation newlines and
   quotes get escaped inside the embedded string). The budget applies to the tool's own
   final output text (the boundary defined by D.9), not to the SDK wrapper; the wrapper
   multiplier is recorded here as wire-size context, not as a budget input.
2. **Byte accounting must use UTF-8 byte length, not `len(str)`**: multibyte and escaped
   content diverge from character counts. `serialize_rows` measures
   `len(text.encode("utf-8"))`.
3. **Indivisible-row admission is linear**: the truncation path pre-encodes each
   row once and accounts bytes incrementally against a conservative meta bound
   (excluding the oversized-first-row note, which applies only to the zero-row
   fallback). Full-candidate recomposition per probe would have been quadratic
   in returned rows and blocked the event loop (measured 2.18 s for a 4,000-row
   synthetic input before the fix).
4. **Oversized-first-row fallback is tiny**: the zero-row compact payload with truncation
   metadata was 212 bytes in the measured scenario.

## Limit inventory by evidentiary status

| Limit | Status | Evidence |
|---|---|---|
| `clickhouse_query` budget 60 s | code-measured | `ClickHouseClient.query` → `_execute_query(..., 60)` + `settings={"max_execution_time": 60}`; pinned by `test_query_should_set_60_second_timeout` |
| `query_trusted` budget 120 s | code-measured | `ClickHouseClient.query_trusted` → `_execute_query(..., 120)`; pinned by `test_query_trusted_should_set_120_second_timeout` |
| Deadline grace | code-measured | `QUERY_DEADLINE_GRACE_SECONDS = 10`; deadline = budget + grace via `asyncio.timeout` |
| Driver socket bound | code-measured (after this change) | installed driver default `send_receive_timeout = 300` (`httpclient.py:67`, measured in installed 0.15.1) → client constructed with `130` per D.5 |
| Schema overall deadline | code-measured (new) | 60 s via `asyncio.timeout` around the per-table `DESCRIBE` loop (D.6) |
| Per-table `DESCRIBE` budget | code-measured (new) | 10 s + 10 s grace per table (D.6) |
| `RESULT_BYTE_BUDGET = 1_048_576` | **provisional** | Measured against this server's output boundary (table above); the *effective* server-side `max_query_size` value is unknown until the operator-approved live run reads `system.settings` (V.8). Revision requires recorded measurement evidence. |
| ClickHouse `max_query_size` | documented default, effective value unknown | ClickHouse documented default 262,144 bytes; the deployment's effective value is read only by gated live test V.8 |
| MCP stdio framing | checked, no documented SDK cap | mcp 2.3.0 stdio transport: newline-delimited JSON-RPC; no size cap documented in the SDK's stdio server/transport modules (checked 2026-11-15) |

`RESULT_BYTE_BUDGET` is marked provisional in `src/skywatch_mcp/lib/clickhouse_client.py`
pending V.8; any revision must cite recorded evidence in this file or its successor.
