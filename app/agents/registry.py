"""Route -> agent.

Each agent is ToolLoopAgent with a different prompt, model tier and tool
allow-list. The allow-list is a security boundary: the live-data agent cannot
create a service request because those schemas are never in its context.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol

from app.agents.base import AgentResult
from app.agents.prompts import (
    ACTION_AGENT_PROMPT,
    DATA_AGENT_PROMPT,
    INVESTIGATION_AGENT_PROMPT,
    LIVE_DATA_AGENT_PROMPT,
)
from app.agents.simple_agents import GeneralAgent, RagAgent
from app.agents.tool_agent import ToolLoopAgent
from app.llm.models import ModelTier
from app.router.schemas import Route

READ_TOOLS = [
    "find_assets",
    "get_asset_details",
    "get_asset_status",
    "get_sensor_data",
    "get_active_alerts",
    "get_asset_relationships",
    "get_zone_conditions",
]


class Agent(Protocol):
    name: str

    async def run(self, message: str, history: list[dict] | None = None) -> AgentResult: ...


@lru_cache(maxsize=1)
def get_agents() -> dict[Route, Agent]:
    return {
        Route.GENERAL: GeneralAgent(),
        Route.RAG: RagAgent(),

        # Simple lookups - the fast model is enough.
        Route.LIVE_DATA: ToolLoopAgent(
            name="live_data_agent",
            system_prompt=LIVE_DATA_AGENT_PROMPT,
            tier=ModelTier.FAST,
            tool_names=READ_TOOLS,
            include_rag_tool=False,
            max_steps=3,
        ),
        Route.DATA_ANALYSIS: ToolLoopAgent(
            name="data_agent",
            system_prompt=DATA_AGENT_PROMPT,
            tier=ModelTier.FAST,
            tool_names=[*READ_TOOLS, "get_energy_consumption"],
            include_rag_tool=False,
            max_steps=4,
        ),

        # Sees the write tools, but ToolLoopAgent holds them for confirmation.
        Route.ACTION: ToolLoopAgent(
            name="action_agent",
            system_prompt=ACTION_AGENT_PROMPT,
            tier=ModelTier.SMART,
            allow_writes=True,
            max_steps=5,
        ),

        # Every tool, smart model, most steps. Also the escalation target.
        Route.INVESTIGATE: ToolLoopAgent(
            name="investigation_agent",
            system_prompt=INVESTIGATION_AGENT_PROMPT,
            tier=ModelTier.SMART,
            allow_writes=True,
        ),
    }


def get_agent(route: Route) -> Agent:
    """CONFIRMATION is handled by app/agents/confirmation.py, not by an agent
    object, so anything unmapped falls back to the general agent."""
    agents = get_agents()
    return agents.get(route, agents[Route.GENERAL])
