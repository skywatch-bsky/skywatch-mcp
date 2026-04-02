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
