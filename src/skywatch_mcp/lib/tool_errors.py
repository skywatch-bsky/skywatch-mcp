# pattern: Imperative Shell

"""Error boundary between tool handlers and the MCP SDK (v2, mcp 2.3+).

Two error classes reach clients differently:

- ``ToolInputError`` marks *safe* validation/configuration failures raised by
  this codebase (bad dates, out-of-range limits, unknown enum values, missing
  Ozone configuration, malformed subjects). ``tool_error_boundary`` translates
  them into the SDK's ``ToolError``, whose message is carried to the client
  prefixed as ``Error executing tool <name>: <message>``.
- Every other exception is *unexpected*: the SDK masks its message on the wire
  and returns a generic ``Error executing tool <name>`` result. Backend
  response bodies (which may embed tokens, credentials, or subject data) must
  stay on that masked path, so the boundary deliberately does not rewrap them.

Known timeout/connectivity failures are translated to fixed, detail-free
messages because their class alone is actionable; exception text is never
forwarded from those paths.
"""

import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import httpx
from mcp.server.mcpserver.exceptions import ToolError

__all__ = ["ToolInputError", "tool_error_boundary"]


class ToolInputError(ValueError):
    """Safe validation/configuration failure whose message may reach clients.

    Subclasses ``ValueError`` so callers and pure-helper tests that expect
    ``ValueError`` keep working unchanged.
    """


_TIMEOUT_MESSAGE = (
    "The operation timed out before the backend service responded. "
    "Try again, or narrow the request."
)
_CONNECTIVITY_MESSAGE = (
    "A backend service is unreachable right now. Try again shortly."
)

P = ParamSpec("P")
R = TypeVar("R")


def tool_error_boundary(fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    """Translate safe input errors and known transport failures into ToolErrors.

    Must sit directly under ``@mcp.tool()``. ``functools.wraps`` preserves the
    handler's ``__wrapped__`` chain, so ``inspect.signature`` (used by the SDK
    for schema discovery) still sees the original parameters and defaults.
    """

    @functools.wraps(fn)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except TimeoutError as exc:
            # Fixed message only: a future raiser's TimeoutError text could name
            # hosts or embed request data, so no exception text is forwarded.
            raise ToolError(_TIMEOUT_MESSAGE) from exc
        except httpx.TimeoutException as exc:
            raise ToolError(_TIMEOUT_MESSAGE) from exc
        except httpx.ConnectError as exc:
            raise ToolError(_CONNECTIVITY_MESSAGE) from exc
        except ToolInputError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper
