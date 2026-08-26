#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from typing import Any

from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client


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


def schema_hash(tools: list[types.Tool]) -> str:
    blob = json.dumps(canonical_schema_payload(tools), sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


async def inspect(url: str) -> dict[str, Any]:
    async with streamable_http_client(url) as streams:
        read, write, *_ = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            tools = listed.tools
            result: dict[str, Any] = {
                "url": url,
                "tool_count": len(tools),
                "tool_schema_sha256": schema_hash(tools),
                "tools": sorted(t.name for t in tools),
            }
            names = {t.name for t in tools}
            if "system_info" in names:
                called = await session.call_tool("system_info", {})
                result["system_info_structured"] = called.structuredContent
                result["system_info_text"] = [getattr(x, "text", "") for x in called.content]
            return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("--expect-count", type=int)
    parser.add_argument("--expect-schema")
    args = parser.parse_args()
    payload = asyncio.run(inspect(args.url))
    if args.expect_count is not None and payload["tool_count"] != args.expect_count:
        raise SystemExit(f"tool count mismatch: {payload['tool_count']} != {args.expect_count}")
    if args.expect_schema and payload["tool_schema_sha256"] != args.expect_schema:
        raise SystemExit(
            f"schema mismatch: {payload['tool_schema_sha256']} != {args.expect_schema}"
        )
    print(json.dumps(payload, sort_keys=True))


if __name__ == "__main__":
    main()
