# pattern: Imperative Shell

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")

import skywatch_mcp.tools.clickhouse  # noqa: E402, F401


def main() -> None:
    mcp.run(transport="stdio")
