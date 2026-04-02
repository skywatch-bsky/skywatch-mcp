# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")

import skywatch_mcp.tools.clickhouse  # noqa: E402, F401
import skywatch_mcp.tools.content  # noqa: E402, F401
import skywatch_mcp.tools.domain  # noqa: E402, F401
import skywatch_mcp.tools.ip  # noqa: E402, F401
import skywatch_mcp.tools.url  # noqa: E402, F401
import skywatch_mcp.tools.whois  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")
