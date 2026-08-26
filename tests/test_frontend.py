from __future__ import annotations

import asyncio

import pytest
from mcp import types

from mcp_frontend import server


def _tool(name: str = "x") -> types.Tool:
    return types.Tool(
        name=name,
        description="",
        inputSchema={"type": "object", "properties": {}},
        outputSchema=None,
    )


def test_schema_hash_is_order_independent():
    a = _tool("a")
    b = _tool("b")
    assert server.tool_schema_hash([a, b]) == server.tool_schema_hash([b, a])


def test_surface_drift_fails_closed(monkeypatch):
    monkeypatch.setattr(server, "EXPECTED_TOOL_COUNT", 2)
    monkeypatch.setattr(server, "EXPECTED_SCHEMA_SHA256", "wrong")
    with pytest.raises(RuntimeError, match="surface drifted"):
        server._assert_expected_surface([_tool("a")])


def test_system_info_identity_is_nested_without_schema_change(monkeypatch):
    monkeypatch.setattr(server, "RELEASE_ID", "candidate-1")
    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="ok")],
        structuredContent={"result": {"system": "Linux"}},
    )
    updated = server._with_identity(result)
    assert updated.structuredContent["result"]["evolution"]["evolvable_mcp_release_id"] == "candidate-1"


def test_list_tools_forwards_exact_surface(monkeypatch):
    tools = [_tool("a"), _tool("b")]
    expected_hash = server.tool_schema_hash(tools)
    monkeypatch.setattr(server, "EXPECTED_TOOL_COUNT", 2)
    monkeypatch.setattr(server, "EXPECTED_SCHEMA_SHA256", expected_hash)

    async def fake_tools():
        return tools

    monkeypatch.setattr(server, "_upstream_tools", fake_tools)
    assert [t.name for t in asyncio.run(server.list_tools())] == ["a", "b"]
