"""The two agents that do not need a tool loop."""

from __future__ import annotations

from app.agents.base import AgentResult, ToolTrace
from app.agents.prompts import GENERAL_AGENT_PROMPT
from app.llm.client import get_llm
from app.llm.models import ModelTier
from app.rag.pipeline import get_rag
from app.tracing import traced


class GeneralAgent:
    """Small talk. One LLM call, no tools, fast model - the cheapest path."""

    name = "general_agent"

    @traced("agent.general")
    async def run(self, message: str, history: list[dict] | None = None) -> AgentResult:
        response = await get_llm().chat(
            [
                {"role": "system", "content": GENERAL_AGENT_PROMPT},
                *(history or []),
                {"role": "user", "content": message},
            ],
            tier=ModelTier.FAST,
            temperature=0.4,
        )
        return AgentResult(text=response.content, agent=self.name, steps=1)


class RagAgent:
    """Answers strictly from the documentation.

    If the knowledge base does not cover the question it sets escalate=True
    rather than guessing, and the orchestrator re-routes to the investigation
    agent, which can also read live data.
    """

    name = "rag_agent"

    @traced("agent.rag")
    async def run(self, message: str, history: list[dict] | None = None) -> AgentResult:
        answer = await get_rag().answer(message)

        return AgentResult(
            text=answer.answer,
            agent=self.name,
            sources=answer.sources,
            tools_used=[
                ToolTrace(
                    "search_knowledge_base",
                    {"query": message},
                    answer.found,
                    f"top score {answer.top_score:.2f}",
                )
            ],
            escalate=not answer.found,
            escalate_reason="" if answer.found else "Knowledge base did not cover the question.",
            steps=1,
        )
