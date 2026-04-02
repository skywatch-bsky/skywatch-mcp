# Skywatch MCP Python Implementation Plan

**Goal:** Port the existing TypeScript MCP server to Python 3.12+, exposing 21 tools across five domains via the official MCP Python SDK's FastMCP layer.

**Architecture:** Async Python MCP server using FastMCP with Pydantic v2 for input validation. Tool handlers registered via `@mcp.tool()` decorators. All I/O async throughout.

**Tech Stack:** Python 3.12+, uv, mcp SDK (FastMCP), Pydantic v2, pydantic-settings, clickhouse-connect, httpx, dnspython, python-whois, pytest, pytest-asyncio, pytest-mock

**Scope:** 8 phases from original design (phases 1-8)

**Codebase verified:** 2026-04-01 — TS source for domain.ts, ip.ts, url.ts, whois.ts read; dnspython async API researched

---

## Acceptance Criteria Coverage

This phase implements and tests:

### skywatch-mcp-py.AC1: All 21 tools exposed and functional
- **skywatch-mcp-py.AC1.3 Success:** `domain_check` resolves A, AAAA, NS, MX, TXT, CNAME, SOA records
- **skywatch-mcp-py.AC1.4 Success:** `ip_lookup` returns geo, network, and flag data for valid IPv4/IPv6
- **skywatch-mcp-py.AC1.5 Success:** `url_expand` follows redirect chain up to 15 hops with status codes
- **skywatch-mcp-py.AC1.6 Success:** `whois_lookup` returns registrar, dates, nameservers, domain age

### skywatch-mcp-py.AC3: All I/O is async
- **skywatch-mcp-py.AC3.2 Success:** DNS resolution uses dnspython async resolver
- **skywatch-mcp-py.AC3.3 Success:** HTTP requests (ip-api, URL expansion, Ozone) use httpx AsyncClient
- **skywatch-mcp-py.AC3.4 Success:** WHOIS uses asyncio.to_thread() wrapper
- **skywatch-mcp-py.AC3.5 Failure:** Network timeouts (5s for HTTP, 60s/120s for ClickHouse) return error, don't hang

---

## Phase 4: Network Tools (Domain, IP, URL, WHOIS)

**Goal:** The four network investigation tools.

**Done when:** All four tools registered, DNS resolves all record types, IP validates addresses, URL follows redirect chains, WHOIS returns structured results. All tests pass with mocked I/O.

---

<!-- START_SUBCOMPONENT_A (tasks 1-3) -->
<!-- START_TASK_1 -->
### Task 1: Create domain_check tool

**Files:**
- Create: `src/skywatch_mcp/tools/domain.py`

**Implementation:**

Port the TS `domain_check` tool. Uses dnspython's async resolver for DNS records (A, AAAA, NS, MX, TXT, CNAME, SOA) via `asyncio.gather` with `return_exceptions=True`, plus httpx HEAD request for HTTP status.

```python
# pattern: Imperative Shell

import asyncio
import json
from typing import Any

import dns.asyncresolver
import dns.resolver
import httpx

from skywatch_mcp.server import mcp


async def _resolve_dns_records(domain: str) -> dict[str, Any]:
    resolver = dns.asyncresolver.Resolver()

    results = await asyncio.gather(
        resolver.resolve(domain, "A"),
        resolver.resolve(domain, "AAAA"),
        resolver.resolve(domain, "NS"),
        resolver.resolve(domain, "MX"),
        resolver.resolve(domain, "TXT"),
        resolver.resolve(domain, "CNAME"),
        resolver.resolve(domain, "SOA"),
        return_exceptions=True,
    )

    a = [str(r) for r in results[0]] if not isinstance(results[0], BaseException) else []
    aaaa = [str(r) for r in results[1]] if not isinstance(results[1], BaseException) else []
    ns = [str(r) for r in results[2]] if not isinstance(results[2], BaseException) else []
    mx = (
        [{"exchange": str(r.exchange), "priority": r.preference} for r in results[3]]
        if not isinstance(results[3], BaseException)
        else []
    )
    txt = (
        [[s.decode() for s in r.strings] for r in results[4]]
        if not isinstance(results[4], BaseException)
        else []
    )
    cname = [str(r) for r in results[5]] if not isinstance(results[5], BaseException) else []

    soa = None
    if not isinstance(results[6], BaseException):
        for r in results[6]:
            soa = {
                "nsname": str(r.mname),
                "hostmaster": str(r.rname),
                "serial": r.serial,
                "refresh": r.refresh,
                "retry": r.retry,
                "expire": r.expire,
                "minttl": r.minimum,
            }

    return {"a": a, "aaaa": aaaa, "ns": ns, "mx": mx, "txt": txt, "cname": cname, "soa": soa}


async def _check_http_status(domain: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.head(f"https://{domain}")
            return {"status": response.status_code, "statusText": response.reason_phrase or ""}
    except Exception:
        return None


@mcp.tool()
async def domain_check(domain: str) -> str:
    """Check DNS records and HTTP status for a domain. Returns A, AAAA, NS, MX, TXT, CNAME, SOA records and whether the domain resolves."""
    try:
        records = await _resolve_dns_records(domain)
        http = await _check_http_status(domain)
        resolves = len(records["a"]) > 0 or len(records["aaaa"]) > 0

        result = {"domain": domain, "resolves": resolves, "records": records, "http": http}
        return json.dumps(result, indent=2)
    except Exception as e:
        raise ValueError(str(e)) from e
```

Note: `asyncio` is imported at module level since `_resolve_dns_records` uses `asyncio.gather`. The `httpx.AsyncClient` is created per-request (via `async with`) which is acceptable for investigation tools with low request volume. For high-throughput scenarios (like Ozone batch operations), a shared client could be considered as an optimisation.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.domain import domain_check; print('imported')"`
Expected: `imported`

**Commit:** `feat: add domain_check tool with async DNS and HTTP status`
<!-- END_TASK_1 -->

<!-- START_TASK_2 -->
### Task 2: Create ip_lookup tool

**Files:**
- Create: `src/skywatch_mcp/tools/ip.py`

**Implementation:**

Port the TS `ip_lookup` tool. Custom IP validation (same regex logic as TS) followed by httpx GET to ip-api.com with the fields query parameter.

```python
# pattern: Imperative Shell

import json
import re

import httpx

from skywatch_mcp.server import mcp


def _validate_ip_address(ip: str) -> bool:
    ipv4_match = re.match(r"^(\d+)\.(\d+)\.(\d+)\.(\d+)$", ip)
    if ipv4_match:
        for i in range(1, 5):
            if not (0 <= int(ipv4_match.group(i)) <= 255):
                return False
        return True

    if ":" not in ip:
        return False
    if ip.count(":") < 2:
        return False
    if ":::" in ip:
        return False
    if not re.match(r"^[0-9a-fA-F:.]+$", ip):
        return False
    return True


@mcp.tool()
async def ip_lookup(ip: str) -> str:
    """Look up geographic location and network information for an IP address using ip-api.com."""
    if not _validate_ip_address(ip):
        raise ValueError(f"Invalid IP address format: {ip}")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={
                    "fields": "status,message,query,country,countryCode,region,regionName,city,zip,lat,lon,timezone,isp,org,as,asname,mobile,proxy,hosting"
                },
            )
            data = response.json()

        if data.get("status") == "fail":
            raise ValueError(data.get("message", "Unknown API error"))

        result = {
            "ip": data.get("query", ip),
            "geo": {
                "country": str(data.get("country", "")),
                "countryCode": str(data.get("countryCode", "")),
                "region": str(data.get("region", "")),
                "city": str(data.get("city", "")),
                "zip": str(data.get("zip", "")),
                "lat": float(data.get("lat", 0)),
                "lon": float(data.get("lon", 0)),
                "timezone": str(data.get("timezone", "")),
            },
            "network": {
                "isp": str(data.get("isp", "")),
                "org": str(data.get("org", "")),
                "asn": str(data.get("as", "")),
                "asname": str(data.get("asname", "")),
            },
            "flags": {
                "mobile": bool(data.get("mobile")),
                "proxy": bool(data.get("proxy")),
                "hosting": bool(data.get("hosting")),
            },
        }
        return json.dumps(result, indent=2)
    except httpx.TimeoutException as e:
        raise ValueError(f"Request timed out: {e}") from e
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(str(e)) from e
```

Note: The `_validate_ip_address` function is a direct port of the TS `validateIpAddress` regex logic.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.ip import _validate_ip_address; print(_validate_ip_address('192.168.1.1'), _validate_ip_address('::1'), _validate_ip_address('invalid'))"`
Expected: `True True False`

**Commit:** `feat: add ip_lookup tool with ip-api.com integration`
<!-- END_TASK_2 -->

<!-- START_TASK_3 -->
### Task 3: Create url_expand tool

**Files:**
- Create: `src/skywatch_mcp/tools/url.py`

**Implementation:**

Port the TS `url_expand` tool. Manually follows redirect chain up to 15 hops using httpx with `follow_redirects=False`, identifies known URL shorteners at each hop.

```python
# pattern: Imperative Shell

import json
from urllib.parse import urljoin, urlparse

import httpx

from skywatch_mcp.lib.url_shorteners import is_known_shortener
from skywatch_mcp.server import mcp


async def _follow_redirects(start_url: str, max_hops: int = 15) -> dict:
    hops = []
    current_url = start_url
    final_url = start_url

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=False) as client:
        for _ in range(max_hops):
            try:
                hostname = urlparse(current_url).hostname or ""
                shortener = is_known_shortener(hostname)

                response = await client.head(current_url)

                location = response.headers.get("location")
                next_url = None

                if location and 300 <= response.status_code < 400:
                    try:
                        next_url = urljoin(current_url, location)
                    except Exception:
                        next_url = None

                hops.append({
                    "url": current_url,
                    "statusCode": response.status_code,
                    "location": next_url,
                    "isShortener": shortener,
                })

                if not next_url or response.status_code < 300 or response.status_code >= 400:
                    final_url = current_url
                    break

                current_url = next_url
                final_url = next_url

            except Exception:
                hostname = urlparse(current_url).hostname or ""
                shortener = is_known_shortener(hostname)
                hops.append({
                    "url": current_url,
                    "statusCode": 0,
                    "location": None,
                    "isShortener": shortener,
                })
                break

    result = {
        "originalUrl": start_url,
        "finalUrl": final_url,
        "hops": hops,
        "hopCount": len(hops),
    }

    if len(hops) >= max_hops:
        result["error"] = "Max redirects exceeded"

    return result


@mcp.tool()
async def url_expand(url: str) -> str:
    """Follow a URL's redirect chain and report each hop with status code. Identifies known URL shorteners."""
    try:
        result = await _follow_redirects(url)
        return json.dumps(result, indent=2)
    except Exception as e:
        raise ValueError(str(e)) from e
```

Note: Uses `httpx.AsyncClient(follow_redirects=False)` to manually track each redirect hop, matching the TS `redirect: "manual"` behaviour.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.url import url_expand; print('imported')"`
Expected: `imported`

**Commit:** `feat: add url_expand tool with redirect chain following`
<!-- END_TASK_3 -->
<!-- END_SUBCOMPONENT_A -->

<!-- START_SUBCOMPONENT_B (tasks 4-5) -->
<!-- START_TASK_4 -->
### Task 4: Create whois_lookup tool

**Files:**
- Create: `src/skywatch_mcp/tools/whois.py`

**Implementation:**

Port the TS `whois_lookup` tool. Uses `python-whois` via `asyncio.to_thread()` since the library is sync-only.

```python
# pattern: Imperative Shell

import asyncio
import json
from dataclasses import asdict

import whois as whois_module

from skywatch_mcp.lib.whois_parser import parse_whois_response
from skywatch_mcp.server import mcp


def _sync_whois_lookup(domain: str) -> str:
    result = whois_module.whois(domain)
    if hasattr(result, "text"):
        return result.text
    return str(result)


@mcp.tool()
async def whois_lookup(domain: str) -> str:
    """Look up WHOIS registration data for a domain. Returns registrar, creation/expiration dates, nameservers, and domain age."""
    try:
        raw_text = await asyncio.to_thread(_sync_whois_lookup, domain)
        result = parse_whois_response(raw_text)
        return json.dumps(asdict(result), indent=2, default=str)
    except Exception as e:
        raise ValueError(str(e)) from e
```

Note: The `python-whois` library's `whois()` function returns an object with a `.text` attribute containing the raw WHOIS text. We pass this to our `parse_whois_response` pure function. The `asyncio.to_thread()` wrapper runs the sync WHOIS lookup in the default thread pool executor.

**Verification:**
Run: `uv run python -c "from skywatch_mcp.tools.whois import whois_lookup; print('imported')"`
Expected: `imported`

**Commit:** `feat: add whois_lookup tool with async thread wrapper`
<!-- END_TASK_4 -->

<!-- START_TASK_5 -->
### Task 5: Update server.py to import all network tools

**Files:**
- Modify: `src/skywatch_mcp/server.py`

**Implementation:**

Add imports for all four network tool modules:

```python
# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")

import skywatch_mcp.tools.clickhouse  # noqa: E402, F401
import skywatch_mcp.tools.domain  # noqa: E402, F401
import skywatch_mcp.tools.ip  # noqa: E402, F401
import skywatch_mcp.tools.url  # noqa: E402, F401
import skywatch_mcp.tools.whois  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")
```

**Verification:**
Run: `uv run python -c "from skywatch_mcp.server import mcp; print(len(mcp._tool_manager._tools), 'tools')"`
Expected: `7 tools` (2 ClickHouse + 4 network + 1 counting might vary — verify actual count)

**Commit:** `feat: register network tools in server`
<!-- END_TASK_5 -->
<!-- END_SUBCOMPONENT_B -->

<!-- START_SUBCOMPONENT_C (tasks 6-9) -->
<!-- START_TASK_6 -->
### Task 6: Test domain_check tool

**Verifies:** skywatch-mcp-py.AC1.3, skywatch-mcp-py.AC3.2

**Files:**
- Create: `tests/test_domain.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.3: domain_check resolves all 7 record types (A, AAAA, NS, MX, TXT, CNAME, SOA) and returns them in structured format. Test with a domain that has A records shows `resolves: true`. Test with empty DNS results shows `resolves: false`.
- skywatch-mcp-py.AC3.2: DNS resolution uses dnspython's async resolver (test with mocked `dns.asyncresolver.Resolver`).

Mock `dns.asyncresolver.Resolver().resolve()` to return appropriate record-like objects for each type. Mock `httpx.AsyncClient.head()` for HTTP status check.

**Verification:**
Run: `uv run pytest tests/test_domain.py -v`
Expected: All tests pass

**Commit:** `test: add domain_check tool tests`
<!-- END_TASK_6 -->

<!-- START_TASK_7 -->
### Task 7: Test ip_lookup tool

**Verifies:** skywatch-mcp-py.AC1.4, skywatch-mcp-py.AC3.3

**Files:**
- Create: `tests/test_ip.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.4: ip_lookup returns geo (country, city, lat/lon), network (isp, org, asn), and flags (mobile, proxy, hosting) for a valid IP. Invalid IPs (e.g., "999.999.999.999", "not-an-ip") raise ValueError. API failure response (status: "fail") raises ValueError.
- skywatch-mcp-py.AC3.3: HTTP requests use httpx AsyncClient (test with mocked httpx).

Test the `_validate_ip_address` function directly: valid IPv4, valid IPv6, invalid formats.

**Verification:**
Run: `uv run pytest tests/test_ip.py -v`
Expected: All tests pass

**Commit:** `test: add ip_lookup tool tests`
<!-- END_TASK_7 -->

<!-- START_TASK_8 -->
### Task 8: Test url_expand tool

**Verifies:** skywatch-mcp-py.AC1.5, skywatch-mcp-py.AC3.3, skywatch-mcp-py.AC3.5

**Files:**
- Create: `tests/test_url.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.5: url_expand follows redirect chain (301 → 302 → 200), identifies known shorteners (e.g., bit.ly), stops at max 15 hops with "Max redirects exceeded" error, handles non-redirect status codes correctly.
- skywatch-mcp-py.AC3.3: Uses httpx AsyncClient with follow_redirects=False.
- skywatch-mcp-py.AC3.5: Timeout on a hop records statusCode=0 and stops following.

Mock `httpx.AsyncClient.head()` to return different status codes and location headers for each hop.

**Verification:**
Run: `uv run pytest tests/test_url.py -v`
Expected: All tests pass

**Commit:** `test: add url_expand tool tests`
<!-- END_TASK_8 -->

<!-- START_TASK_9 -->
### Task 9: Test whois_lookup tool

**Verifies:** skywatch-mcp-py.AC1.6, skywatch-mcp-py.AC3.4

**Files:**
- Create: `tests/test_whois_tool.py`

**Testing:**
Tests must verify each AC listed above:
- skywatch-mcp-py.AC1.6: whois_lookup returns registrar, creation/expiration dates, nameservers, domain age from parsed WHOIS text.
- skywatch-mcp-py.AC3.4: WHOIS lookup uses asyncio.to_thread() wrapper (verify it doesn't block the event loop — mock `whois.whois` and verify the sync function runs in a thread).

Mock `whois_module.whois()` to return a mock object with `.text` containing sample WHOIS response text.

**Verification:**
Run: `uv run pytest tests/test_whois_tool.py -v`
Expected: All tests pass

**Commit:** `test: add whois_lookup tool tests`
<!-- END_TASK_9 -->
<!-- END_SUBCOMPONENT_C -->

<!-- START_TASK_10 -->
### Task 10: Phase 4 verification

**Files:**
- None (verification only)

**Verification:**
Run: `uv run pytest tests/ -v`
Expected: All tests pass (Phases 2-4)

**Commit:** No commit needed — verification only
<!-- END_TASK_10 -->
