# pattern: Imperative Shell

"""Error boundary between tool handlers and the MCP SDK (v2, mcp 2.3+).

Three error classes reach clients differently:

- ``ToolInputError`` marks *safe* validation/configuration failures raised by
  this codebase (bad dates, out-of-range limits, unknown enum values, missing
  Ozone configuration, malformed subjects). ``tool_error_boundary`` translates
  them into the SDK's ``ToolError``, whose message is carried to the client
  prefixed as ``Error executing tool <name>: <message>``.
- ``BackendError`` marks *classified* backend failures raised by the
  ClickHouse path. The boundary forwards their structured JSON payload
  (``kind``, ``retryable``, ``query_id``, numeric ``code``, allowlisted
  ``message``) through the same SDK prefix format, so agents can parse the
  failure instead of seeing a generic mask.
- Every other exception is *unexpected*: the SDK masks its message on the wire
  and returns a generic ``Error executing tool <name>`` result. Backend
  response bodies (which may embed tokens, credentials, or subject data) must
  stay on that masked path, so the boundary deliberately does not rewrap them.
  A plain ``ValueError`` raised anywhere keeps the masked path.

Known timeout/connectivity failures are translated to fixed, detail-free
messages because their class alone is actionable; exception text is never
forwarded from those paths.
"""

import functools
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

import httpx
from mcp.server.mcpserver.exceptions import ToolError

__all__ = ["BackendError", "ToolInputError", "tool_error_boundary"]

logger = logging.getLogger(__name__)


class ToolInputError(ValueError):
    """Safe validation/configuration failure whose message may reach clients.

    Subclasses ``ValueError`` so callers and pure-helper tests that expect
    ``ValueError`` keep working unchanged.
    """


class BackendError(Exception):
    """Classified backend failure whose payload is safe to forward to clients.

    Carries only structured, sanitized fields: ``kind`` (fixed vocabulary),
    ``retryable``, ``query_id``, and a numeric ``code`` when the backend
    exposed one. The client-visible ``message`` is a fixed allowlisted string
    per ``kind`` — raw backend response text, SQL, hosts, URLs, and
    credentials never ride on this exception. Raise it ``from`` the original
    exception so the in-process cause chain stays available for diagnosis.
    """

    def __init__(
        self,
        kind: str,
        retryable: bool,
        query_id: str | None = None,
        code: int | None = None,
    ) -> None:
        if kind not in _KIND_MESSAGES:
            raise ValueError(f"Unknown BackendError kind: {kind}")
        self.kind = kind
        self.retryable = retryable
        self.query_id = query_id
        self.code = code
        super().__init__(self.message)

    @property
    def message(self) -> str:
        """Allowlisted client-visible text for this kind (code as number when known)."""
        template = _KIND_MESSAGES[self.kind]
        if "{code}" in template:
            return template.replace("{code}", str(self.code) if self.code is not None else "unknown")
        return template

    def to_payload(self) -> dict[str, Any]:
        """Structured JSON payload forwarded on the wire."""
        return {
            "kind": self.kind,
            "retryable": self.retryable,
            "query_id": self.query_id,
            "code": self.code,
            "message": self.message,
        }


# Fixed allowlisted messages per kind. Never include exception text, backend
# response bodies, hosts, URLs, SQL, or credentials here — only the numeric
# code (substituted when known) rides alongside the fixed text.
_KIND_MESSAGES: dict[str, str] = {
    "backend_unavailable": (
        "ClickHouse backend is unreachable. Verify the service is running, then retry."
    ),
    "auth_failed": (
        "ClickHouse authentication failed. Check the CLICKHOUSE_USER and "
        "CLICKHOUSE_PASSWORD configuration."
    ),
    "invalid_sql": (
        "ClickHouse rejected the query (code {code}). Check table and column "
        "names with clickhouse_schema."
    ),
    "request_too_large": (
        "Query exceeded a size or memory limit (code {code}). Split the query "
        "or narrow columns and rows."
    ),
    "timeout": (
        "Query exceeded its execution budget. Narrow the query or reduce the LIMIT."
    ),
    "unknown": (
        "ClickHouse returned an unrecognized error (code {code}). Use query_id "
        "for server-side correlation."
    ),
    "rule_catalogue_unavailable": (
        "No verified rule catalogue is configured. Establish the authoritative "
        "rule source, then retry."
    ),
}

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
    """Translate safe input errors and known backend failures into ToolErrors.

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
        except BackendError as exc:
            # Structured, sanitized payload only. The original exception (with
            # any raw backend text) stays in-process via the cause chain.
            logger.warning(
                "backend error: kind=%s code=%s query_id=%s",
                exc.kind,
                exc.code,
                exc.query_id,
            )
            raise ToolError(json.dumps(exc.to_payload())) from exc
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
