from mcp.server.fastmcp import FastMCP

mcp = FastMCP("skywatch-mcp")


def main() -> None:
    mcp.run(transport="stdio")
