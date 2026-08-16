"""MCP client - the agent's connection to the facility tool server.

Starts the server as a child process, translates its tool list into the OpenAI
tool format, and runs tool calls.

If the subprocess cannot start (sandbox, antivirus, broken interpreter path) it
falls back to calling the same functions in-process. /health reports which mode
is live.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import AsyncExitStack
from typing import Any

from app.config import BASE_DIR
from app.logging_setup import get_logger
from app.mcp_server.registry import TOOL_SPECS, TOOLS_BY_NAME
from app.mcp_server.tools import WRITE_TOOLS
from app.tracing import span, update_span

log = get_logger(__name__)


class MCPToolClient:
    def __init__(self) -> None:
        self._session: Any = None
        self._stack: AsyncExitStack | None = None
        self._tools: list[dict[str, Any]] = []
        self.mode = "not_connected"  # mcp_stdio | in_process

    async def connect(self) -> None:
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_server.server"],
                cwd=str(BASE_DIR),
                env={**os.environ, "PYTHONPATH": str(BASE_DIR)},
            )
            self._stack = AsyncExitStack()
            streams = await self._stack.enter_async_context(stdio_client(params))
            self._session = await self._stack.enter_async_context(ClientSession(*streams))
            await self._session.initialize()

            listed = await self._session.list_tools()
            self._tools = [
                {
                    "name": t.name,
                    "description": t.description or "",
                    "input_schema": t.inputSchema,
                }
                for t in listed.tools
            ]
            self.mode = "mcp_stdio"
            log.info("Connected to MCP server - %d tools available.", len(self._tools))

        except Exception as exc:  # noqa: BLE001
            log.warning("MCP subprocess unavailable (%s) - using in-process tools.", exc)
            await self._close_stack()
            self._session = None
            self._tools = [
                {
                    "name": s["name"],
                    "description": s["description"],
                    "input_schema": s["input_schema"],
                }
                for s in TOOL_SPECS
            ]
            self.mode = "in_process"

    async def close(self) -> None:
        await self._close_stack()
        self._session = None
        self.mode = "not_connected"

    async def _close_stack(self) -> None:
        if self._stack is None:
            return
        try:
            await self._stack.aclose()
        except Exception as exc:  # noqa: BLE001
            log.debug("Ignoring MCP shutdown error: %s", exc)
        finally:
            self._stack = None

    def openai_tools(
        self, include: list[str] | None = None, exclude_writes: bool = False
    ) -> list[dict[str, Any]]:
        """Tool schemas for the LLM.

        `exclude_writes` is a capability boundary: a read-only agent never sees
        the write tools, so it cannot call them even if it wanted to.
        """
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t["description"],
                    "parameters": t["input_schema"],
                },
            }
            for t in self._tools
            if (include is None or t["name"] in include)
            and not (exclude_writes and t["name"] in WRITE_TOOLS)
        ]

    @property
    def tool_names(self) -> list[str]:
        return [t["name"] for t in self._tools]

    @staticmethod
    def is_write_tool(name: str) -> bool:
        return name in WRITE_TOOLS

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Run a tool. Failures return {"error"} so the agent can recover."""
        with span("mcp.tool_call", input={"tool": name, "arguments": arguments}):
            try:
                if self._session is not None:
                    result = await self._session.call_tool(name, arguments)
                    text = "".join(b.text for b in result.content if hasattr(b, "text"))
                    payload = json.loads(text) if text else {}
                else:
                    payload = self._call_in_process(name, arguments)
            except Exception as exc:  # noqa: BLE001
                log.error("Tool '%s' failed: %s", name, exc)
                payload = {
                    "error": f"Tool '{name}' could not be executed: {exc}",
                    "hint": "Try a different tool or tell the user the data is unavailable.",
                }

            update_span(output=payload)
            return payload

    @staticmethod
    def _call_in_process(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        spec = TOOLS_BY_NAME.get(name)
        if spec is None:
            return {
                "error": f"Unknown tool '{name}'.",
                "hint": f"Available tools: {', '.join(TOOLS_BY_NAME)}",
            }
        return spec["handler"](**arguments)


_client: MCPToolClient | None = None


async def get_mcp_client() -> MCPToolClient:
    global _client
    if _client is None:
        _client = MCPToolClient()
        await _client.connect()
    return _client


async def close_mcp_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None
