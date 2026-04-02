# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — TS source at /Users/scarndp/dev/skywatch/claude-skills/plugins/skywatch-investigations/servers/skywatch-mcp/

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC2: Pydantic models for all inputs/outputs
- **skywatch-mcp-py.AC2.1 Success:** Each tool has a Pydantic input model with field descriptions
- **skywatch-mcp-py.AC2.2 Failure:** Invalid input types rejected before handler execution
- **skywatch-mcp-py.AC2.3 Failure:** Missing required fields rejected with clear error message
- **skywatch-mcp-py.AC2.4 Success:** Response models serialise to JSON matching TS output shape

**Note on AC2.1-AC2.3:** FastMCP automatically generates Pydantic input models from tool function parameter type annotations. Each tool uses `Annotated[type, Field(description="...")]` for rich parameter descriptions. FastMCP handles validation (AC2.2, AC2.3) automatically — invalid types and missing required fields are rejected before handler execution. This is the idiomatic FastMCP pattern and does NOT require separate Pydantic model files in `models/`. The `models/` directory from the design is not populated; instead, data structures are defined inline or as dataclasses where needed.

### skywatch-mcp-py.AC4: Comprehensive tests
- **skywatch-mcp-py.AC4.1 Success:** SQL validation has all 42 test cases ported from TS
- **skywatch-mcp-py.AC4.3 Success:** WHOIS parser and URL shortener list have unit tests

### skywatch-mcp-py.AC5: Drop-in replacement
- **skywatch-mcp-py.AC5.1 Success:** Same env var names accepted (CLICKHOUSE_HOST, OZONE_SERVICE_URL, etc.)
- **skywatch-mcp-py.AC5.2 Success:** Same defaults for all env vars (http://localhost, 8123, default, etc.)

---

## Phase 2: Configuration & Core Library

**Goal:** Environment variable configuration and pure utility functions (SQL validation, URL shorteners, WHOIS parser).

**Done when:** All pure function tests pass. Config loads from env vars with correct defaults and types.

---

<!-- START_SUBCOMPONENT_A (tasks 1-2) -->
<!-- START_TASK_1 -->
### Task 1: Create configuration module

**Files:**
- Create: `src/skywatch_mcp/config.py`

**Implementation:**

`src/skywatch_mcp/config.py`:

```python
# pattern: Functional Core

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class ClickHouseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CLICKHOUSE_")

    host: str = Field(default="http://localhost")
    port: int = Field(default=8123)
    user: str = Field(default="default")
    password: str = Field(default="")
    database: str = Field(default="default")
    tailnet_ip: str | None = Field(default=None)

    @property
    def effective_host(self) -> str:
        if self.tailnet_ip:
            return f"http://{self.tailnet_ip}"
        return self.host


class OzoneSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OZONE_")

    service_url: str | None = Field(default=None)
    handle: str | None = Field(default=None)
    admin_password: str | None = Field(default=None)
    did: str | None = Field(default=None)
    pds: str | None = Field(default=None)

    @property
    def is_configured(self) -> bool:
        return all([self.handle, self.admin_password, self.did, self.pds])
```

Note: The TS server uses `OZONE_HANDLE`, `OZONE_ADMIN_PASSWORD`, `OZONE_DID`, `OZONE_PDS` (all optional). The `CLICKHOUSE_TAILNET_IP` overrides `CLICKHOUSE_HOST` when set. Both of these patterns are preserved exactly.

**Verification:**

Run: `uv run python -c "from skywatch_mcp.config import ClickHouseSettings, OzoneSettings; ch = ClickHouseSettings(); print(ch.host, ch.port, ch.user, ch.database); oz = OzoneSettings(); print(oz.is_configured)"`

Expected: `http://localhost 8123 default default` on line 1, `False` on line 2.

**Commit:** `feat: add pydantic-settings configuration for ClickHouse and Ozone`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Test configuration loading

**Verifies:** skywatch-mcp-py.AC5.1, skywatch-mcp-py.AC5.2

**Files:**
- Create: `tests/test_config.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC5.1: ClickHouseSettings reads CLICKHOUSE_HOST, CLICKHOUSE_PORT, CLICKHOUSE_USER, CLICKHOUSE_PASSWORD, CLICKHOUSE_DATABASE from env vars. OzoneSettings reads OZONE_HANDLE, OZONE_ADMIN_PASSWORD, OZONE_DID, OZONE_PDS. CLICKHOUSE_TAILNET_IP overrides host when set.
- skywatch-mcp-py.AC5.2: ClickHouseSettings defaults to host=http://localhost, port=8123, user=default, password="", database=default. OzoneSettings defaults all fields to None and is_configured returns False.

Use `monkeypatch.setenv()` to test env var loading. Do not mock pydantic-settings internals.

**Verification:**
Run: `uv run pytest tests/test_config.py -v`
Expected: All tests pass

**Commit:** `test: add configuration loading tests`
<!-- END_TASK_2 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 3-5) -->
<!-- START_TASK_3 -->
### Task 3: Create SQL validation module

**Files:**
- Create: `src/skywatch_mcp/lib/sql_validation.py`

**Implementation:**

Port the TS `validateQuery` function exactly. The logic is:

```python
# pattern: Functional Core

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationSuccess:
    normalized: str


@dataclass(frozen=True)
class ValidationFailure:
    reason: str


type ValidationResult = ValidationSuccess | ValidationFailure


def validate_query(sql: str) -> ValidationResult:
    trimmed = sql.strip()

    if len(trimmed) == 0:
        return ValidationFailure(reason="Query cannot be empty")

    normalized = re.sub(r"\s+", " ", trimmed)
    tokens = normalized.split()
    if not tokens:
        return ValidationFailure(reason="Query cannot be empty")

    first_token = tokens[0]
    upper_first = first_token.upper()

    if upper_first not in ("SELECT", "WITH"):
        return ValidationFailure(
            reason=f"Only SELECT queries are allowed. Query starts with '{first_token}'"
        )

    upper_normalized = normalized.upper()

    if not re.search(r"\bLIMIT\s+\d+\b", upper_normalized):
        return ValidationFailure(
            reason="Query must contain a LIMIT clause with a numeric value (e.g., LIMIT 10)"
        )

    if ";" in upper_normalized:
        return ValidationFailure(
            reason="Query cannot contain semicolons (multi-statement execution not allowed)"
        )

    if re.search(r"\bINTO\b", upper_normalized, re.IGNORECASE):
        return ValidationFailure(
            reason="Query cannot contain INTO keyword (data export not allowed)"
        )

    return ValidationSuccess(normalized=normalized)
```

This is a direct port of the TS logic. Same error messages, same validation order, same whitespace normalisation.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.lib.sql_validation import validate_query; print(validate_query('SELECT * FROM t LIMIT 10'))"`
Expected: `ValidationSuccess(normalized='SELECT * FROM t LIMIT 10')`

**Commit:** `feat: add SQL validation module (ported from TS)`
<!-- END_TASK_3 -->

<!-- START_TASK_4 -->
### Task 4: Port all 42 SQL validation test cases

**Verifies:** skywatch-mcp-py.AC4.1

**Files:**
- Create: `tests/test_sql_validation.py`

**Testing:**
Port all 42 test cases from the TS file at `/Users/scarndp/dev/skywatch/claude-skills/plugins/skywatch-investigations/servers/skywatch-mcp/src/lib/sql-validation.test.ts`.

The test groups are:
1. **Reject non-SELECT statements** (7 tests): INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE — all must return ValidationFailure with "Only SELECT queries are allowed"
2. **Require LIMIT clause** (5 tests): missing LIMIT, LIMIT without number, valid LIMIT, large LIMIT value, LIMIT with non-numeric
3. **Allow JOINs and UNIONs** (4 tests): JOIN, LEFT JOIN, UNION, UNION ALL — all must return ValidationSuccess
4. **Allow any table** (4 tests): arbitrary table name, no FROM clause, subqueries, CTEs — all must return ValidationSuccess
5. **Case-insensitive handling** (2 tests): lowercase select/limit, mixed case — all must return ValidationSuccess
6. **Whitespace normalisation** (3 tests): extra spaces, tabs/newlines, normalised output verification
7. **Edge cases** (4 tests): empty query, whitespace-only, complex valid query, query with comment
8. **Data export prevention** (4 tests): semicolon mid-query, semicolon at end, INTO OUTFILE, INTO DUMPFILE

That's 33 listed above. The remaining 9 tests to reach 42 may come from the count including sub-assertions. Count the actual test functions in the TS file and port each one. Use `isinstance(result, ValidationSuccess)` and `isinstance(result, ValidationFailure)` for assertions.

**Verification:**
Run: `uv run pytest tests/test_sql_validation.py -v`
Expected: All tests pass

**Commit:** `test: port all 42 SQL validation test cases from TS`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Verify SQL validation test count matches TS

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/test_sql_validation.py -v --co | grep "test_" | wc -l`
Expected: Count should be ≥33 (the TS file has "describe" blocks with "it" blocks — count the actual `it()` calls in the TS file and ensure Python has the same number)

Run: `uv run pytest tests/test_sql_validation.py -v`
Expected: All tests pass

**Commit:** No commit needed — verification only
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-7) -->
<!-- START_TASK_6 -->
### Task 6: Create URL shorteners module

**Files:**
- Create: `src/skywatch_mcp/lib/url_shorteners.py`

**Implementation:**

```python
# pattern: Functional Core

KNOWN_SHORTENERS = frozenset({
    "bit.ly",
    "bitly.com",
    "t.co",
    "goo.gl",
    "tinyurl.com",
    "ow.ly",
    "is.gd",
    "v.gd",
    "buff.ly",
    "amzn.to",
    "youtu.be",
    "rb.gy",
    "shorturl.at",
    "tiny.cc",
    "cutt.ly",
})


def is_known_shortener(hostname: str) -> bool:
    return hostname.lower() in KNOWN_SHORTENERS
```

Direct port of the TS Set with case-insensitive lookup via `.lower()`.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.lib.url_shorteners import is_known_shortener; print(is_known_shortener('bit.ly'), is_known_shortener('example.com'))"`
Expected: `True False`

**Commit:** `feat: add URL shortener domain list`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Test URL shorteners

**Verifies:** skywatch-mcp-py.AC4.3 (partial — URL shortener list)

**Files:**
- Create: `tests/test_url_shorteners.py`

**Testing:**
- All 15 known shortener domains return True
- Case-insensitive matching (e.g., "BIT.LY" returns True)
- Unknown domains return False (e.g., "example.com", "google.com")
- Empty string returns False

**Verification:**
Run: `uv run pytest tests/test_url_shorteners.py -v`
Expected: All tests pass

**Commit:** `test: add URL shortener tests`
<!-- END_TASK_7 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_SUBCOMPONENT_D (tasks 8-10) -->
<!-- START_TASK_8 -->
### Task 8: Create WHOIS parser module

**Files:**
- Create: `src/skywatch_mcp/lib/whois_parser.py`

**Implementation:**

Port the TS `parseWhoisResponse` function:

```python
# pattern: Functional Core

import re
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class WhoisResult:
    registrar: str | None
    creation_date: str | None
    expiration_date: str | None
    nameservers: list[str]
    domain_age: int | None
    raw_text: str


def _extract_field(text: str, patterns: list[re.Pattern[str]]) -> str | None:
    for pattern in patterns:
        match = pattern.search(text)
        if match and match.group(1):
            return match.group(1).strip()
    return None


def _extract_nameservers(text: str) -> list[str]:
    pattern = re.compile(r"Name\s+Server:\s*(.+)", re.IGNORECASE)
    return [m.group(1).strip() for m in pattern.finditer(text) if m.group(1)]


def _calculate_domain_age(creation_date_str: str | None) -> int | None:
    if not creation_date_str:
        return None
    try:
        creation_date = datetime.fromisoformat(creation_date_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_days = (now - creation_date).days
        return age_days
    except (ValueError, TypeError):
        return None


_REGISTRAR_PATTERNS = [re.compile(r"Registrar:\s*(.+)", re.IGNORECASE)]

_CREATION_PATTERNS = [
    re.compile(r"Creation\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"Created:\s*(.+)", re.IGNORECASE),
]

_EXPIRATION_PATTERNS = [
    re.compile(r"Registry\s+Expiry\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"Expiration\s+Date:\s*(.+)", re.IGNORECASE),
    re.compile(r"expires:\s*(.+)", re.IGNORECASE),
]


def parse_whois_response(raw_text: str) -> WhoisResult:
    registrar = _extract_field(raw_text, _REGISTRAR_PATTERNS)
    creation_date = _extract_field(raw_text, _CREATION_PATTERNS)
    expiration_date = _extract_field(raw_text, _EXPIRATION_PATTERNS)
    nameservers = _extract_nameservers(raw_text)
    domain_age = _calculate_domain_age(creation_date)

    return WhoisResult(
        registrar=registrar,
        creation_date=creation_date,
        expiration_date=expiration_date,
        nameservers=nameservers,
        domain_age=domain_age,
        raw_text=raw_text,
    )
```

Same regex patterns, same extraction order, same domain age calculation as TS version.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.lib.whois_parser import parse_whois_response; r = parse_whois_response('Registrar: Example Registrar\nCreation Date: 2020-01-01T00:00:00Z\nName Server: ns1.example.com'); print(r.registrar, r.creation_date, r.nameservers)"`
Expected: `Example Registrar 2020-01-01T00:00:00Z ['ns1.example.com']`

**Commit:** `feat: add WHOIS parser module (ported from TS)`
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Test WHOIS parser

**Verifies:** skywatch-mcp-py.AC4.3 (partial — WHOIS parser)

**Files:**
- Create: `tests/test_whois_parser.py`

**Testing:**
Tests must verify:
- Registrar extraction from "Registrar: <name>" lines
- Creation date extraction from "Creation Date:" and "Created:" variants
- Expiration date extraction from "Registry Expiry Date:", "Expiration Date:", and "expires:" variants
- Nameserver extraction: multiple "Name Server:" lines collected into a list
- Domain age calculation: correct number of days from creation date to now
- Domain age returns None when creation date is missing or unparseable
- Empty/missing fields return None
- Raw text is preserved in the result

**Verification:**
Run: `uv run pytest tests/test_whois_parser.py -v`
Expected: All tests pass

**Commit:** `test: add WHOIS parser tests`
<!-- END_TASK_9 -->

<!-- START_TASK_10 -->
### Task 10: Phase 2 verification

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/ -v`
Expected: All tests pass (config, SQL validation, URL shorteners, WHOIS parser)

Run: `uv run python -c "from skywatch_mcp.config import ClickHouseSettings, OzoneSettings; from skywatch_mcp.lib.sql_validation import validate_query; from skywatch_mcp.lib.url_shorteners import is_known_shortener; from skywatch_mcp.lib.whois_parser import parse_whois_response; print('All Phase 2 modules importable')"`
Expected: `All Phase 2 modules importable`

**Commit:** No commit needed — verification only
<!-- END_TASK_10 -->
<!-- END_SUBCOMPONENT_D -->
