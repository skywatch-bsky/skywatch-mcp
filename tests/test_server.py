import pytest
from skywatch_mcp.server import mcp


class TestServerToolRegistration:

    @pytest.mark.asyncio
    async def test_all_tools_registered(self) -> None:
        tools = await mcp.list_tools()
        tool_names = {tool.name for tool in tools}

        assert len(tools) == 33, f"Expected 33 tools, got {len(tools)}"

        expected_tools = {
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

        assert tool_names == expected_tools, (
            f"Tool mismatch. Missing: {expected_tools - tool_names}, Extra: {tool_names - expected_tools}"
        )

    def test_console_script_entry_point_importable(self) -> None:
        from skywatch_mcp.server import main

        assert callable(main), "main should be callable"


class TestServerImports:

    def test_server_imports_all_tools(self) -> None:
        assert mcp is not None
        assert hasattr(mcp, "list_tools")
        assert hasattr(mcp, "run")


class TestToolInputSchemas:

    @pytest.mark.asyncio
    async def test_all_tools_have_input_schema_with_descriptions(self) -> None:
        tools = await mcp.list_tools()

        assert len(tools) > 0, "No tools registered"

        for tool in tools:
            assert hasattr(tool, "input_schema"), f"Tool {tool.name} missing input_schema"
            assert tool.input_schema is not None, f"Tool {tool.name} input_schema is None"

            schema = tool.input_schema

            # Check properties exist and have descriptions
            if "properties" in schema:
                properties = schema["properties"]
                for prop_name, prop_schema in properties.items():
                    assert isinstance(prop_schema, dict), (
                        f"Tool {tool.name} property {prop_name} schema is not a dict"
                    )
                    if "description" in prop_schema:
                        # Property has a description - good
                        assert isinstance(prop_schema["description"], str)
                        assert len(prop_schema["description"]) > 0
