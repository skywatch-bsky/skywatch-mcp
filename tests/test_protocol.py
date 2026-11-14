"""Raw JSON-RPC tests against the real stdio console entry point.

Covers AC.3/AC.4/AC.6: modern discovery without initialize, mandated request
metadata, unsupported-version errors, the 2025-11-25 legacy handshake, and the
bounded/cleaned-up subprocess fixture itself. Tests never touch backend
services: every scenario here is discovery, listing, or argument validation.
"""

import asyncio
import json
import os
import sys
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from tests.test_mcp_integration import EXPECTED_TOOL_NAMES

PROTO_VERSION_META = "io.modelcontextprotocol/protocolVersion"
CLIENT_CAPABILITIES_META = "io.modelcontextprotocol/clientCapabilities"
SERVER_INFO_META = "io.modelcontextprotocol/serverInfo"

MODERN_VERSION = "2026-07-28"
LEGACY_VERSION = "2025-11-25"

READ_TIMEOUT_SECONDS = 20.0
SHUTDOWN_GRACE_SECONDS = 5.0


class ProtocolError(Exception):
    """The subprocess violated the newline-delimited JSON-RPC contract."""


class StdioJsonRpcHarness:
    """Bounded subprocess JSON-RPC harness with guaranteed cleanup.

    Starts ``command``, writes newline-delimited JSON, and reads responses by
    matching id, skipping notifications. Every read is bounded; ``aclose()``
    always closes stdin, terminates, and reaps the process, including on the
    timeout and non-JSON failure paths.
    """

    def __init__(self, command: list[str], cwd: Path, env: dict[str, str]) -> None:
        self._command = command
        self._cwd = cwd
        self._env = env
        self._proc: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> "StdioJsonRpcHarness":
        self._proc = await asyncio.create_subprocess_exec(
            *self._command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=str(self._cwd),
            env=self._env,
        )
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close stdin, terminate, and reap the process. Safe to call twice."""
        proc = self._proc
        if proc is None:
            return
        self._proc = None
        if proc.stdin is not None:
            proc.stdin.close()
        if proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=SHUTDOWN_GRACE_SECONDS)
        except TimeoutError:
            proc.kill()
            await proc.wait()

    async def send(self, message: dict[str, Any]) -> None:
        proc = self._require_proc()
        if proc.stdin is None:  # pragma: no cover - PIPE guarantees a writer
            raise ProtocolError("subprocess stdin is closed")
        proc.stdin.write((json.dumps(message) + "\n").encode())
        await proc.stdin.drain()

    async def request(self, req_id: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
        await self.send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        return await self.wait_for_response(req_id)

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self.send({"jsonrpc": "2.0", "method": method, "params": params})

    async def wait_for_response(self, req_id: int) -> dict[str, Any]:
        """Read lines until the response with ``req_id`` arrives, skipping notifications."""
        proc = self._require_proc()
        if proc.stdout is None:  # pragma: no cover - PIPE guarantees a reader
            raise ProtocolError("subprocess stdout is closed")
        deadline = asyncio.get_running_loop().time() + READ_TIMEOUT_SECONDS
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"no response for id {req_id} within {READ_TIMEOUT_SECONDS}s")
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
            except TimeoutError as exc:
                raise TimeoutError(
                    f"no response for id {req_id} within {READ_TIMEOUT_SECONDS}s"
                ) from exc
            if not line:
                raise ProtocolError(f"server closed stdout while awaiting id {req_id}")
            try:
                message = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ProtocolError(f"non-JSON stdout line: {line!r}") from exc
            if isinstance(message, dict) and message.get("id") == req_id and (
                "result" in message or "error" in message
            ):
                return message

    def _require_proc(self) -> asyncio.subprocess.Process:
        if self._proc is None:  # pragma: no cover - misuse guard
            raise ProtocolError("harness is not started")
        return self._proc


def _server_command() -> list[str]:
    """The real console entry point from the worktree venv, with a module fallback."""
    console_script = Path(sys.executable).parent / "skywatch-mcp"
    if console_script.exists():
        return [str(console_script)]
    return [sys.executable, "-c", "from skywatch_mcp.server import main; main()"]


def _controlled_env() -> dict[str, str]:
    """Host env without credentials; the child runs from tmp_path so no .env is found."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("OZONE_", "CLICKHOUSE_"))
    }
    env.setdefault("PYTHONUNBUFFERED", "1")
    return env


def _modern_meta(version: str = MODERN_VERSION) -> dict[str, Any]:
    return {"_meta": {PROTO_VERSION_META: version, CLIENT_CAPABILITIES_META: {}}}


async def _harness(tmp_path: Path) -> AsyncIterator[StdioJsonRpcHarness]:
    harness = StdioJsonRpcHarness(_server_command(), cwd=tmp_path, env=_controlled_env())
    async with harness:
        yield harness


def modern_params(params: dict[str, Any], version: str = MODERN_VERSION) -> dict[str, Any]:
    return {**params, **_modern_meta(version)}


@pytest.fixture
async def stdio_server(tmp_path: Path) -> AsyncIterator[StdioJsonRpcHarness]:
    async for harness in _harness(tmp_path):
        yield harness


class TestModernStdioProtocol:
    @pytest.mark.asyncio
    async def test_stdio_modern_discovery_and_listing(
        self, stdio_server: StdioJsonRpcHarness
    ) -> None:
        discover = await stdio_server.request(1, "server/discover", _modern_meta())
        result = discover["result"]
        assert result["supportedVersions"] == [MODERN_VERSION]
        assert result["resultType"] == "complete"
        assert result["ttlMs"] == 0
        assert result["cacheScope"] == "private"
        assert result["_meta"][SERVER_INFO_META]["name"] == "skywatch-mcp"
        assert "tools" in result["capabilities"]

        listing = await stdio_server.request(2, "tools/list", _modern_meta())
        tools_result = listing["result"]
        assert tools_result["resultType"] == "complete"
        assert "ttlMs" in tools_result
        assert "cacheScope" in tools_result
        names = {tool["name"] for tool in tools_result["tools"]}
        assert len(tools_result["tools"]) == 33
        assert names == EXPECTED_TOOL_NAMES
        for tool in tools_result["tools"]:
            assert isinstance(tool["inputSchema"], dict)
            assert tool["inputSchema"].get("type") == "object"

        unknown = await stdio_server.request(
            3,
            "tools/call",
            modern_params({"name": "no_such_tool", "arguments": {}}),
        )
        assert "error" not in unknown
        assert unknown["result"]["isError"] is True

    @pytest.mark.asyncio
    async def test_stdio_unsupported_protocol_version(
        self, stdio_server: StdioJsonRpcHarness
    ) -> None:
        rejection = await stdio_server.request(
            1, "tools/list", _modern_meta(version="1999-01-01")
        )
        assert "result" not in rejection
        error = rejection["error"]
        assert error["code"] == -32022
        assert error["message"] == "Unsupported protocol version"
        assert error["data"] == {"supported": [MODERN_VERSION], "requested": "1999-01-01"}


class TestLegacyStdioProtocol:
    @pytest.mark.asyncio
    async def test_stdio_legacy_initialize_list_and_validation(
        self, stdio_server: StdioJsonRpcHarness
    ) -> None:
        init = await stdio_server.request(
            1,
            "initialize",
            {
                "protocolVersion": LEGACY_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "legacy-probe", "version": "0.0.0"},
            },
        )
        assert init["result"]["protocolVersion"] == LEGACY_VERSION

        await stdio_server.notify("notifications/initialized", {})

        listing = await stdio_server.request(2, "tools/list", {})
        names = {tool["name"] for tool in listing["result"]["tools"]}
        assert names == EXPECTED_TOOL_NAMES

        invalid = await stdio_server.request(
            3,
            "tools/call",
            {"name": "domain_check", "arguments": {"domain": 123}},
        )
        assert "error" not in invalid
        call_result = invalid["result"]
        assert call_result["isError"] is True
        text = call_result["content"][0]["text"]
        assert "Input should be a valid string" in text or "type=string_type" in text


class TestHarnessSelfChecks:
    @pytest.mark.asyncio
    async def test_protocol_fixture_timeout_cleans_up(self, tmp_path: Path) -> None:
        """A timed-out wait terminates and reaps the child process."""
        harness = StdioJsonRpcHarness(["sleep", "30"], cwd=tmp_path, env=_controlled_env())
        async with harness:
            proc = harness._require_proc()
            with pytest.raises(TimeoutError):
                await harness.request(1, "tools/list", {})
        assert proc.returncode is not None

    @pytest.mark.asyncio
    async def test_protocol_fixture_rejects_non_json_stdout(self, tmp_path: Path) -> None:
        """A child that writes non-JSON to stdout fails the harness, not the read loop."""
        command = [
            sys.executable,
            "-c",
            "import time; print('definitely not json', flush=True); time.sleep(30)",
        ]
        harness = StdioJsonRpcHarness(command, cwd=tmp_path, env=_controlled_env())
        async with harness:
            proc = harness._require_proc()
            with pytest.raises(ProtocolError, match="non-JSON stdout"):
                await harness.request(1, "tools/list", {})
        assert proc.returncode is not None
