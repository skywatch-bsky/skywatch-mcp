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
