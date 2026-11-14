"""In-memory protocol integration tests against the real MCPServer dispatch.

Covers AC.2 (registration/contracts), AC.5 (success/error contracts in both
protocol eras) and the error-boundary guarantees: safe validation errors stay
actionable, backend failure details are masked. Raw-JSON-RPC stdio behavior is
covered separately in test_protocol.py.
"""

import importlib.metadata
import inspect
import tomllib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from mcp import Client

from skywatch_mcp.server import mcp
from skywatch_mcp.tools import ozone as ozone_module

EXPECTED_TOOL_NAMES: set[str] = {
    "clickhouse_query",
    "clickhouse_schema",
    "domain_check",
    "ip_lookup",
    "url_expand",
    "whois_lookup",
    "content_similarity",
    "cosharing_clusters",
    "cosharing_pairs",
    "cosharing_evolution",
    "cosharing_runs",
    "quote_cosharing_clusters",
    "quote_cosharing_pairs",
    "quote_cosharing_evolution",
    "signup_anomalies",
    "signup_anomaly_trend",
    "url_overdispersion_results",
    "url_overdispersion_trend",
    "quote_overdispersion_results",
    "quote_overdispersion_trend",
    "account_entropy_results",
    "account_entropy_trend",
    "ozone_label",
    "ozone_comment",
    "ozone_acknowledge",
    "ozone_escalate",
    "ozone_tag",
    "ozone_mute",
    "ozone_unmute",
    "ozone_resolve_appeal",
    "ozone_report",
    "ozone_query_statuses",
    "ozone_query_events",
}

SENTINEL_SECRET = "SENTINEL-SECRET-BACKEND-BODY"

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _lock_mcp_version() -> str:
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text())
    for package in lock["package"]:
        if package["name"] == "mcp":
            return package["version"]
    raise AssertionError("mcp package missing from uv.lock")


def _configured_ozone_settings() -> ozone_module.OzoneSettings:
    return ozone_module.OzoneSettings(
        handle="moderator@example",
        admin_password="not-a-real-password",
        did="did:plc:testmoderator",
        pds="ozone.example.invalid",
    )


def _fake_query_result(rows: list[dict[str, object]]) -> SimpleNamespace:
    return SimpleNamespace(rows=rows)


class TestSdkVersion:
    def test_locked_sdk_version(self) -> None:
        """The lockfile pins mcp 2.3.x and the installed distribution matches it."""
        assert _lock_mcp_version() == "2.3.0"
        assert importlib.metadata.version("mcp") == "2.3.0"


class TestRegistration:
    @pytest.mark.asyncio
    async def test_all_tools_registered(self) -> None:
        async with Client(mcp, raise_exceptions=True) as client:
            result = await client.list_tools()
            names = {tool.name for tool in result.tools}

        assert len(result.tools) == 33
        assert names == EXPECTED_TOOL_NAMES, (
            f"Tool mismatch. Missing: {EXPECTED_TOOL_NAMES - names}, Extra: {names - EXPECTED_TOOL_NAMES}"
        )


class TestInputContracts:
    @pytest.mark.asyncio
    async def test_tool_input_contracts(self) -> None:
        """Every tool's schema mirrors its handler signature: required set, defaults, types."""
        from skywatch_mcp.tools import (
            account_entropy,
            clickhouse,
            content,
            cosharing,
            domain,
            ip,
            ozone,
            quote_overdispersion,
            signup_anomaly,
            url,
            url_overdispersion,
            whois,
        )

        handlers = {
            **{n: getattr(account_entropy, n) for n in ("account_entropy_results", "account_entropy_trend")},
            **{n: getattr(clickhouse, n) for n in ("clickhouse_query", "clickhouse_schema")},
            **{n: getattr(content, n) for n in ("content_similarity",)},
            **{n: getattr(cosharing, n) for n in (
                "cosharing_clusters",
                "cosharing_pairs",
                "cosharing_evolution",
                "cosharing_runs",
                "quote_cosharing_clusters",
                "quote_cosharing_pairs",
                "quote_cosharing_evolution",
            )},
            **{n: getattr(domain, n) for n in ("domain_check",)},
            **{n: getattr(ip, n) for n in ("ip_lookup",)},
            **{n: getattr(ozone, n) for n in (
                "ozone_label",
                "ozone_comment",
                "ozone_acknowledge",
                "ozone_escalate",
                "ozone_tag",
                "ozone_mute",
                "ozone_unmute",
                "ozone_resolve_appeal",
                "ozone_report",
                "ozone_query_statuses",
                "ozone_query_events",
            )},
            **{n: getattr(quote_overdispersion, n) for n in (
                "quote_overdispersion_results",
                "quote_overdispersion_trend",
            )},
            **{n: getattr(signup_anomaly, n) for n in ("signup_anomalies", "signup_anomaly_trend")},
            **{n: getattr(url, n) for n in ("url_expand",)},
            **{n: getattr(url_overdispersion, n) for n in (
                "url_overdispersion_results",
                "url_overdispersion_trend",
            )},
            **{n: getattr(whois, n) for n in ("whois_lookup",)},
        }

        async with Client(mcp, raise_exceptions=True) as client:
            result = await client.list_tools()
            by_name = {tool.name: tool for tool in result.tools}

        assert set(by_name) == EXPECTED_TOOL_NAMES

        for name, tool in by_name.items():
            handler = handlers[name]
            signature = inspect.signature(handler)

            schema = tool.input_schema
            assert schema.get("type") == "object", f"{name}: schema is not an object"
            properties = schema.get("properties", {})
            assert set(properties) == set(signature.parameters), (
                f"{name}: schema properties {sorted(properties)} != handler params "
                f"{sorted(signature.parameters)}"
            )

            expected_required = [
                param_name
                for param_name, param in signature.parameters.items()
                if param.default is inspect.Parameter.empty
            ]
            assert schema.get("required", []) == expected_required, (
                f"{name}: required {schema.get('required')} != {expected_required}"
            )

            for param_name, param in signature.parameters.items():
                if param.default is inspect.Parameter.empty:
                    continue
                default = properties[param_name].get("default")
                assert default == param.default, (
                    f"{name}.{param_name}: schema default {default!r} != handler default {param.default!r}"
                )


class TestSuccessContracts:
    @staticmethod
    async def _run_analytics(mode: str) -> tuple[object, str]:
        rows = [{"run_date": "2026-04-01", "cluster_count": 3}]
        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.query_trusted.return_value = _fake_query_result(rows)
            mock_get_client.return_value = mock_client
            async with Client(mcp, mode=mode) as client:
                session = client.session
                if mode == "legacy":
                    await session.initialize()
                result = await session.call_tool("cosharing_runs", {"limit": 5})
                # The exact handler JSON string, computed from the same patched backend.
                from skywatch_mcp.tools.cosharing import cosharing_runs as handler

                expected = await handler.__wrapped__(limit=5)
        return result, expected

    @staticmethod
    async def _run_moderation(mode: str) -> tuple[object, str]:
        settings = _configured_ozone_settings()
        api_response = {"event": {}, "subject": {}}
        with (
            patch.object(ozone_module, "_settings", settings),
            patch.object(ozone_module, "_ozone_request", AsyncMock(return_value=api_response)),
        ):
            async with Client(mcp, mode=mode) as client:
                session = client.session
                if mode == "legacy":
                    await session.initialize()
                result = await session.call_tool(
                    "ozone_tag",
                    {"subject": "did:plc:testsubject", "add": ["spam"]},
                )
                from skywatch_mcp.tools.ozone import ozone_tag as handler

                expected = await handler.__wrapped__(
                    subject="did:plc:testsubject", add=["spam"]
                )
        return result, expected

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["auto", "legacy"])
    async def test_tool_success_contracts_by_protocol(self, mode: str) -> None:
        """Text content equals the handler JSON string; the structured wrapper wraps that exact string."""
        for runner in (self._run_analytics, self._run_moderation):
            result, expected_json = await runner(mode)

            assert not result.is_error
            assert len(result.content) == 1
            assert result.content[0].text == expected_json
            assert result.structured_content == {"result": expected_json}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["auto", "legacy"])
    async def test_expected_tool_errors_by_protocol(self, mode: str) -> None:
        """Safe validation failures come back as is_error results whose message stays readable."""
        async with Client(mcp, mode=mode) as client:
            session = client.session
            if mode == "legacy":
                await session.initialize()

            bad_sql = await session.call_tool("clickhouse_query", {"sql": "SELECT 1"})
            assert bad_sql.is_error
            assert "Query validation failed" in bad_sql.content[0].text
            assert "LIMIT" in bad_sql.content[0].text

            bad_enum = await session.call_tool(
                "signup_anomalies", {"granularity": "weekly"}
            )
            assert bad_enum.is_error
            assert "Invalid granularity" in bad_enum.content[0].text
            assert "weekly" in bad_enum.content[0].text

            with patch.object(ozone_module, "_settings", _configured_ozone_settings()):
                bad_subject = await session.call_tool(
                    "ozone_comment", {"subject": "not-a-did", "comment": "hi"}
                )
            assert bad_subject.is_error
            assert "Subject must be a DID" in bad_subject.content[0].text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode", ["auto", "legacy"])
    async def test_unexpected_error_details_are_masked(self, mode: str) -> None:
        """A crash inside a backend client surfaces a generic message, never the exception text."""
        async def crash(*args: object, **kwargs: object) -> object:
            raise ValueError(f"backend said: {SENTINEL_SECRET}")

        with patch("skywatch_mcp.tools.cosharing.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.query_trusted.side_effect = crash
            mock_get_client.return_value = mock_client

            async with Client(mcp, mode=mode) as client:
                session = client.session
                if mode == "legacy":
                    await session.initialize()
                result = await session.call_tool("cosharing_runs", {"limit": 5})

        assert result.is_error
        assert result.content[0].text == "Error executing tool cosharing_runs"
        wire = str(result)
        assert SENTINEL_SECRET not in wire
        assert "backend said" not in wire


class TestErrorBoundary:
    @pytest.mark.asyncio
    async def test_safe_error_type_is_preserved(self) -> None:
        """ToolInputError reaches clients as ToolError with its message intact, prefix included."""
        async with Client(mcp, raise_exceptions=True) as client:
            result = await client.call_tool("ip_lookup", {"ip": "999.999.999.999"})
        assert result.is_error
        assert "Error executing tool ip_lookup:" in result.content[0].text
        assert "Invalid IP address format" in result.content[0].text

    @pytest.mark.asyncio
    async def test_backend_value_error_is_masked(self) -> None:
        """A ValueError carrying a backend response body is not forwarded to the client."""

        async def fail(*args: object, **kwargs: object) -> object:
            raise ValueError(SENTINEL_SECRET)

        with patch("skywatch_mcp.tools.clickhouse.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.query.side_effect = fail
            mock_get_client.return_value = mock_client

            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool(
                    "clickhouse_query", {"sql": "SELECT 1 LIMIT 1"}
                )

        assert result.is_error
        assert result.content[0].text == "Error executing tool clickhouse_query"
        assert SENTINEL_SECRET not in str(result)

    def test_boundary_preserves_tool_signature(self) -> None:
        """functools.wraps keeps the handler signature visible for SDK schema discovery."""
        from skywatch_mcp.tools.ozone import ozone_report

        wrapped = inspect.signature(ozone_report)
        original = inspect.signature(ozone_report.__wrapped__)

        assert list(wrapped.parameters) == list(original.parameters)
        for name, original_param in original.parameters.items():
            wrapped_param = wrapped.parameters[name]
            assert wrapped_param.default == original_param.default
            assert wrapped_param.annotation == original_param.annotation
