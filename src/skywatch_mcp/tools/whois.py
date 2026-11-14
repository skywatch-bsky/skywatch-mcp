# pattern: Imperative Shell

import asyncio
import json
from dataclasses import asdict

import whois as whois_module

from skywatch_mcp.lib.tool_errors import tool_error_boundary
from skywatch_mcp.lib.whois_parser import parse_whois_response
from skywatch_mcp.server import mcp


def _sync_whois_lookup(domain: str) -> str:
    result = whois_module.whois(domain)
    if hasattr(result, "text"):
        return str(result.text)
    return str(result)


@mcp.tool()
@tool_error_boundary
async def whois_lookup(domain: str) -> str:
    """Look up WHOIS registration data for a domain. Returns registrar, creation/expiration dates, nameservers, and domain age."""
    raw_text = await asyncio.to_thread(_sync_whois_lookup, domain)
    result = parse_whois_response(raw_text)
    return json.dumps(asdict(result), indent=2, default=str)
