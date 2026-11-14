# pattern: Imperative Shell

from mcp.server import MCPServer

from skywatch_mcp.config import ServerSettings

mcp = MCPServer("skywatch-mcp")

import skywatch_mcp.tools.account_entropy  # noqa: E402, F401
import skywatch_mcp.tools.clickhouse  # noqa: E402, F401
import skywatch_mcp.tools.content  # noqa: E402, F401
import skywatch_mcp.tools.cosharing  # noqa: E402, F401
import skywatch_mcp.tools.domain  # noqa: E402, F401
import skywatch_mcp.tools.ip  # noqa: E402, F401
import skywatch_mcp.tools.ozone  # noqa: E402, F401
import skywatch_mcp.tools.quote_overdispersion  # noqa: E402, F401
import skywatch_mcp.tools.signup_anomaly  # noqa: E402, F401
import skywatch_mcp.tools.url  # noqa: E402, F401
import skywatch_mcp.tools.url_overdispersion  # noqa: E402, F401
import skywatch_mcp.tools.whois  # noqa: E402, F401


def main() -> None:
    settings = ServerSettings()
    if settings.transport == "http":
        mcp.run(transport="streamable-http", host=settings.host, port=settings.port)
        return
    mcp.run(transport="stdio")
