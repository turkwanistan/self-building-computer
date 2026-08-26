#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://192.168.127.10:8890/mcp"
EXPECTED = {"shell", "read_file", "write_file", "list_files", "job", "service", "reboot"}


def _tool_payload(result: Any) -> dict[str, Any]:
    """Extract a FastMCP dict result from structured or JSON-text tool output."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP may expose the dict directly or under a single result wrapper.
        wrapped = structured.get("result")
        if isinstance(wrapped, dict):
            return wrapped
        if {"exit_code", "stdout", "stderr"}.issubset(structured):
            return structured

    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(decoded, dict):
            wrapped = decoded.get("result")
            if isinstance(wrapped, dict):
                return wrapped
            if {"exit_code", "stdout", "stderr"}.issubset(decoded):
                return decoded

    raise RuntimeError("could not decode structured shell result")


async def main() -> None:
    async with streamable_http_client(URL) as streams:
        read, write, *_ = streams
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            if names != EXPECTED:
                raise SystemExit(f"tool mismatch: expected={sorted(EXPECTED)} actual={sorted(names)}")

            root_result = await session.call_tool(
                "shell", {"command": "id -u && test -w /root && echo ROOT_WRITE_OK"}
            )
            root = _tool_payload(root_result)
            if root_result.isError or root.get("exit_code") != 0 or "0\nROOT_WRITE_OK" not in str(root.get("stdout", "")):
                raise SystemExit(f"root shell validation failed: {root!r}")

            internet_result = await session.call_tool(
                "shell",
                {"command": "curl -fsS --max-time 10 https://example.com >/dev/null && echo PUBLIC_INTERNET_OK"},
            )
            internet = _tool_payload(internet_result)
            if (
                internet_result.isError
                or internet.get("exit_code") != 0
                or "PUBLIC_INTERNET_OK" not in str(internet.get("stdout", ""))
            ):
                raise SystemExit(f"public internet validation through lab MCP failed: {internet!r}")

            print(
                json.dumps(
                    {
                        "endpoint": URL,
                        "tool_count": len(names),
                        "tools": sorted(names),
                        "root": "PASS",
                        "public_internet": "PASS",
                    },
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
