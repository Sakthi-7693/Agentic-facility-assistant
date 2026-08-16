"""The autonomous tool-calling loop.

Every tool-using agent is this class with a different prompt, model tier and
tool allow-list. See app/agents/registry.py.

    repeat up to max_steps:
        ask the LLM, offering it the tools
        replied with text  -> done
        asked for tools    -> run them, feed results back, loop
    out of steps           -> force a final answer with no tools

Write tools are never executed here. They are captured as a PendingAction and
the model is told to ask the user first.
"""

from __future__ import annotations

import json
from typing import Any

from app.agents.base import AgentResult, PendingAction, ToolTrace
from app.config import settings
from app.llm.client import get_llm
from app.llm.models import LLMResponse, ModelTier, ToolCall
from app.logging_setup import get_logger
from app.mcp_client.client import get_mcp_client
from app.rag.pipeline import get_rag
from app.tracing import traced, update_span

log = get_logger(__name__)

# The knowledge base is offered as just another tool, so the agent can freely
# mix documentation lookups with live data reads.
RAG_TOOL_NAME = "search_knowledge_base"
RAG_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": RAG_TOOL_NAME,
        "description": (
            "Search the facility documentation (HVAC procedures, chiller and AHU "
            "manuals, maintenance, safety, policies, specifications). Use this for "
            "procedures, thresholds, definitions and troubleshooting steps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look up."}
            },
            "required": ["query"],
        },
    },
}

NO_DATA_REPLY = (
    "I could not retrieve the building data for that request. "
    "Please try again, or ask me about a specific asset such as AHU-02 or Chiller-01."
)

HELD_ACTION = {
    "status": "awaiting_user_confirmation",
    "executed": False,
    "instruction": (
        "This action was NOT executed. Briefly summarise what you found and then "
        "ask the user one short yes/no question to confirm the action."
    ),
}


def _assistant_message(response: LLMResponse) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": response.content or None,
        "tool_calls": [
            {
                "id": c.id,
                "type": "function",
                "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
            }
            for c in response.tool_calls
        ],
    }


def _tool_message(call_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": call_id,
        # Cap the payload. Every step re-sends the whole history, so one verbose
        # tool result is paid for on every remaining step of the loop.
        "content": json.dumps(payload, default=str)[:3000],
    }


def _describe(call: ToolCall) -> str:
    """Plain-English description of a held action, shown to the user."""
    args = call.arguments
    if call.name == "create_service_request":
        return (
            f"Create a {args.get('priority', 'medium')} priority maintenance request "
            f"for {args.get('asset', 'the asset')}"
        )
    if call.name == "update_service_request":
        return (
            f"Update {args.get('request_id', 'the request')} to status "
            f"'{args.get('status', 'unchanged')}'"
        )
    return f"Run {call.name}"


class ToolLoopAgent:
    def __init__(
        self,
        name: str,
        system_prompt: str,
        tier: ModelTier = ModelTier.SMART,
        tool_names: list[str] | None = None,
        allow_writes: bool = False,
        include_rag_tool: bool = True,
        max_steps: int | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tier = tier
        self.tool_names = tool_names       # None = every MCP tool
        self.allow_writes = allow_writes   # False = write schemas never shown
        self.include_rag_tool = include_rag_tool
        self.max_steps = max_steps or settings.max_agent_steps

    @traced("agent.run")
    async def run(self, message: str, history: list[dict] | None = None) -> AgentResult:
        mcp = await get_mcp_client()
        tools = mcp.openai_tools(include=self.tool_names, exclude_writes=not self.allow_writes)
        if self.include_rag_tool:
            tools.append(RAG_TOOL_SCHEMA)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            *(history or []),
            {"role": "user", "content": message},
        ]
        traces: list[ToolTrace] = []
        sources: list[str] = []
        pending: PendingAction | None = None

        # Results of tools already run this turn. Smaller models often re-request
        # the same data instead of using what they were given, which burns
        # latency and tokens without adding information.
        cache: dict[str, dict[str, Any]] = {}

        for step in range(1, self.max_steps + 1):
            try:
                response = await get_llm().chat(messages, tier=self.tier, tools=tools)
            except Exception as exc:  # noqa: BLE001
                # Usually a malformed tool call the provider rejected.
                log.warning("[%s] step %d failed (%s)", self.name, step, exc)

                # If no tool has run yet there is nothing to answer FROM, and
                # asking the model anyway produces confident invention. Say so
                # instead. Never let a failure path become a hallucination.
                if not traces:
                    return AgentResult(
                        text=NO_DATA_REPLY,
                        agent=self.name,
                        tools_used=traces,
                        steps=step,
                    )

                return await self._force_answer(messages, traces, sources, pending)

            if not response.wants_tools:
                return self._finish(response.content, traces, sources, pending, step)

            messages.append(_assistant_message(response))

            for call in response.tool_calls:
                if mcp.is_write_tool(call.name):
                    pending = PendingAction(call.name, call.arguments, _describe(call))
                    traces.append(
                        ToolTrace(call.name, call.arguments, True, "held for confirmation")
                    )
                    messages.append(_tool_message(call.id, HELD_ACTION))

                elif call.name == RAG_TOOL_NAME:
                    answer = await get_rag().answer(call.arguments.get("query", message))
                    sources.extend(answer.sources)
                    traces.append(
                        ToolTrace(
                            call.name,
                            call.arguments,
                            answer.found,
                            f"{len(answer.sources)} source(s), score {answer.top_score:.2f}",
                        )
                    )
                    messages.append(_tool_message(call.id, answer.as_dict()))

                else:
                    key = f"{call.name}:{json.dumps(call.arguments, sort_keys=True)}"

                    if key in cache:
                        result = {
                            **cache[key],
                            "note": (
                                "You already called this tool with these arguments. "
                                "Use the result you have and move on."
                            ),
                        }
                        summary = "repeat call, served from cache"
                    else:
                        result = await mcp.call(call.name, call.arguments)
                        cache[key] = result
                        summary = str(result.get("error", ""))[:120]

                    traces.append(
                        ToolTrace(call.name, call.arguments, "error" not in result, summary)
                    )
                    messages.append(_tool_message(call.id, result))

            log.info("[%s] step %d - ran %d tool(s)", self.name, step, len(response.tool_calls))

        return await self._force_answer(messages, traces, sources, pending)

    async def _force_answer(
        self,
        messages: list[dict[str, Any]],
        traces: list[ToolTrace],
        sources: list[str],
        pending: PendingAction | None,
    ) -> AgentResult:
        """Safety valve: the loop can never hang or return nothing."""
        log.warning("[%s] hit the %d step limit - forcing an answer", self.name, self.max_steps)
        messages.append(
            {
                "role": "user",
                "content": (
                    "Stop investigating and answer now, under 70 words. "
                    "Use ONLY figures that appear in the tool results above. "
                    "Do not estimate, round or invent any number. If you do not "
                    "have a figure, say you could not retrieve it."
                ),
            }
        )
        response = await get_llm().chat(messages, tier=self.tier)
        return self._finish(response.content, traces, sources, pending, self.max_steps)

    def _finish(
        self,
        text: str,
        traces: list[ToolTrace],
        sources: list[str],
        pending: PendingAction | None,
        steps: int,
    ) -> AgentResult:
        update_span(output={"answer": text, "tools": [t.name for t in traces]})
        seen: set[str] = set()
        return AgentResult(
            text=text.strip(),
            agent=self.name,
            sources=[s for s in sources if not (s in seen or seen.add(s))],
            tools_used=traces,
            pending_action=pending,
            steps=steps,
        )
