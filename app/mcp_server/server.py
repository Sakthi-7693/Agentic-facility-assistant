"""MCP server - exposes the facility tools over stdio.

Run standalone with:  python -m app.mcp_server.server
It will sit silently waiting for MCP messages; that is correct.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import mcp.types as types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from app.mcp_server.registry import TOOL_SPECS, TOOLS_BY_NAME

server = Server("nectar-facility-mcp")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name=spec["name"],
            description=spec["description"],
            inputSchema=spec["input_schema"],
        )
        for spec in TOOL_SPECS
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> list[types.TextContent]:
    """Run a tool. Errors come back as JSON, never as an exception."""
    spec = TOOLS_BY_NAME.get(name)

    if spec is None:
        payload = {
            "error": f"Unknown tool '{name}'.",
            "hint": f"Available tools: {', '.join(TOOLS_BY_NAME)}",
        }
    else:
        try:
            payload = spec["handler"](**(arguments or {}))
        except TypeError as exc:
            payload = {
                "error": f"Invalid arguments for '{name}': {exc}",
                "hint": f"Expected schema: {json.dumps(spec['input_schema'])}",
            }
        except Exception as exc:  # noqa: BLE001 - a tool must never kill the server
            payload = {"error": f"Tool '{name}' failed: {exc}"}

    return [types.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]


async def main() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
