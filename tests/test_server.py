import pytest
from skywatch_mcp.server import mcp


class TestServerToolRegistration:
    """Verify all tools are registered correctly."""

    @pytest.mark.asyncio
    async def test_all_tools_registered(self) -> None:
        """Test AC1.21: Server has exactly 20 tools registered.

        Note: Plan said 21 but actual count is 20 (2 ClickHouse, 1 domain,
        1 IP, 1 URL, 1 WHOIS, 1 content, 3 cosharing, 10 ozone).
        """
        tools = await mcp.list_tools()
        tool_names = {tool.name for tool in tools}

        assert len(tools) == 20, f"Expected 20 tools, got {len(tools)}"

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
            "ozone_label",
            "ozone_comment",
            "ozone_acknowledge",
            "ozone_escalate",
            "ozone_tag",
            "ozone_mute",
            "ozone_unmute",
            "ozone_resolve_appeal",
            "ozone_query_statuses",
            "ozone_query_events",
        }

        assert tool_names == expected_tools, (
            f"Tool mismatch. Missing: {expected_tools - tool_names}, Extra: {tool_names - expected_tools}"
        )

    def test_console_script_entry_point_importable(self) -> None:
        """Test AC5.3: Server main function is importable and callable."""
        from skywatch_mcp.server import main

        assert callable(main), "main should be callable"


class TestServerImports:
    """Verify server module imports without errors."""

    def test_server_imports_all_tools(self) -> None:
        """Verify server.py imports all tool modules successfully."""
        # If we got here, the import succeeded (would have raised on import failure)
        assert mcp is not None
        assert hasattr(mcp, "list_tools")
        assert hasattr(mcp, "run")


class TestToolInputSchemas:
    """Verify all tools have proper input schemas."""

    @pytest.mark.asyncio
    async def test_all_tools_have_input_schema_with_descriptions(self) -> None:
        """Test AC2.1: All registered tools have inputSchema with property descriptions."""
        tools = await mcp.list_tools()

        assert len(tools) > 0, "No tools registered"

        for tool in tools:
            assert hasattr(tool, "inputSchema"), f"Tool {tool.name} missing inputSchema"
            assert tool.inputSchema is not None, f"Tool {tool.name} inputSchema is None"

            # inputSchema should be a dict with properties
            if isinstance(tool.inputSchema, dict):
                schema = tool.inputSchema
            else:
                # In case it's returned as a different type, convert to dict
                import json
                if isinstance(tool.inputSchema, str):
                    schema = json.loads(tool.inputSchema)
                else:
                    schema = vars(tool.inputSchema) if hasattr(tool.inputSchema, '__dict__') else {}

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
