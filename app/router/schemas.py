"""Route definitions shared by the router and the orchestrator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Route(str, Enum):
    """Each route maps to exactly one agent. The list is short on purpose - a
    router with twenty classes is a router that is usually wrong."""

    GENERAL = "general"              # small talk            -> plain LLM
    RAG = "rag"                      # "What is an AHU?"     -> documents
    LIVE_DATA = "live_data"          # "Chiller-01 temp?"    -> MCP reads
    DATA_ANALYSIS = "data_analysis"  # "Today's energy"      -> MCP + maths
    ACTION = "action"                # "Create a request"    -> MCP write
    INVESTIGATE = "investigate"      # "Why is it hot?"      -> RAG + MCP + reasoning
    CONFIRMATION = "confirmation"    # "yes, go ahead"       -> execute pending action


# Rough relative cost, used for reporting and for picking the cheapest safe
# option when the router is unsure.
ROUTE_COST: dict[Route, int] = {
    Route.CONFIRMATION: 0,
    Route.GENERAL: 1,
    Route.RAG: 2,
    Route.LIVE_DATA: 3,
    Route.DATA_ANALYSIS: 4,
    Route.ACTION: 4,
    Route.INVESTIGATE: 8,
}


@dataclass
class RouteDecision:
    """Where to send this request, and how sure we are."""

    route: Route
    confidence: float                  # 0.0 - 1.0
    reason: str
    method: str                        # rule | llm | fallback | escalation
    clarification: str | None = None   # set when we must ask instead of act

    @property
    def needs_clarification(self) -> bool:
        return self.clarification is not None

    def as_dict(self) -> dict:
        return {
            "route": self.route.value,
            "confidence": self.confidence,
            "reason": self.reason,
            "method": self.method,
            "estimated_cost": ROUTE_COST[self.route],
            "clarification": self.clarification,
        }
