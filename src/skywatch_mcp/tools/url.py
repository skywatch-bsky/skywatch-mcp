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
