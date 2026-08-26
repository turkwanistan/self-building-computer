from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client
from mcp.server.fastmcp import FastMCP

UPSTREAM_URL = os.environ.get("MCP_GUARDRAIL_URL", "http://127.0.0.1:8790/mcp")
EXPECTED_TOOL_COUNT = int(os.environ.get("MCP_EXPECTED_TOOL_COUNT", "51"))
EXPECTED_SCHEMA_SHA256 = os.environ.get(
    "MCP_EXPECTED_SCHEMA_SHA256",
    "195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913",
)
RELEASE_ID = os.environ.get("MCP_EVOLUTION_RELEASE_ID", "working-tree")
SOURCE_SHA256 = os.environ.get("MCP_EVOLUTION_SOURCE_SHA256", "unsealed")
GUARDRAIL_RELEASE_ID = os.environ.get("MCP_GUARDRAIL_RELEASE_ID", "gen0-optiplex-mcp-agent")
POLICY_VERSION = os.environ.get("MCP_POLICY_VERSION", "bootstrap-v1")
HOST = os.environ.get("MCP_FRONTEND_HOST", "127.0.0.1")
PORT = int(os.environ.get("MCP_FRONTEND_PORT", "8792"))

mcp = FastMCP("self-building-computer", host=HOST, port=PORT)
lowlevel = mcp._mcp_server


def canonical_schema_payload(tools: list[types.Tool]) -> list[dict[str, Any]]:
    return sorted(
        [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
                "outputSchema": tool.outputSchema,
            }
            for tool in tools
        ],
        key=lambda item: item["name"],
    )


def tool_schema_hash(tools: list[types.Tool]) -> str:
    blob = json.dumps(
        canonical_schema_payload(tools), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def release_identity(tool_count: int, schema_sha256: str) -> dict[str, Any]:
    return {
        "evolvable_mcp_release_id": RELEASE_ID,
        "evolvable_mcp_source_sha256": SOURCE_SHA256,
        "guardrail_release_id": GUARDRAIL_RELEASE_ID,
        "tool_count": tool_count,
        "tool_schema_sha256": schema_sha256,
        "policy_version": POLICY_VERSION,
    }


async def _upstream_tools() -> list[types.Tool]:
    async with streamable_http_client(UPSTREAM_URL) as streams:
        read, write, *_ = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


async def _upstream_call(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    async with streamable_http_client(UPSTREAM_URL) as streams:
        read, write, *_ = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, arguments)


def _assert_expected_surface(tools: list[types.Tool]) -> str:
    actual_count = len(tools)
    actual_hash = tool_schema_hash(tools)
    if actual_count != EXPECTED_TOOL_COUNT or actual_hash != EXPECTED_SCHEMA_SHA256:
        raise RuntimeError(
            "guardrail MCP surface drifted: "
            f"expected count/hash {EXPECTED_TOOL_COUNT}/{EXPECTED_SCHEMA_SHA256}, "
            f"got {actual_count}/{actual_hash}"
        )
    return actual_hash


@lowlevel.list_tools()
async def list_tools() -> list[types.Tool]:
    tools = await _upstream_tools()
    _assert_expected_surface(tools)
    return tools


def _with_identity(result: types.CallToolResult) -> types.CallToolResult:
    identity = release_identity(EXPECTED_TOOL_COUNT, EXPECTED_SCHEMA_SHA256)
    structured = result.structuredContent
    if isinstance(structured, dict):
        structured = dict(structured)
        nested = structured.get("result")
        if isinstance(nested, dict):
            nested = dict(nested)
            nested["evolution"] = identity
            structured["result"] = nested
        else:
            structured["evolution"] = identity
        result.structuredContent = structured
    else:
        result.content = list(result.content) + [
            types.TextContent(type="text", text=json.dumps({"evolution": identity}))
        ]
    return result


@lowlevel.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    # list_tools populates the low-level input-schema cache before normal calls.
    result = await _upstream_call(name, arguments)
    if name == "system_info":
        result = _with_identity(result)
    return result


def main() -> None:
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
