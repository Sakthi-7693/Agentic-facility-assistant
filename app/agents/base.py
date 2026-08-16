"""Shared types for every agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolTrace:
    """A record of one tool the agent ran, shown in the UI and in Langfuse."""

    name: str
    arguments: dict[str, Any]
    ok: bool
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.name,
            "arguments": self.arguments,
            "ok": self.ok,
            "summary": self.summary,
        }


@dataclass
class PendingAction:
    """A write action the agent wants to perform but has NOT performed.

    Parked here until the user says yes.
    """

    tool: str
    arguments: dict[str, Any]
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": self.arguments,
            "description": self.description,
        }


@dataclass
class AgentResult:
    """Everything an agent returns. The orchestrator only ever sees this."""

    text: str
    agent: str = ""
    sources: list[str] = field(default_factory=list)
    tools_used: list[ToolTrace] = field(default_factory=list)
    pending_action: PendingAction | None = None
    # Set when the agent realises it was given the wrong job. The orchestrator
    # then re-routes - this is how a bad routing decision is caught at runtime.
    escalate: bool = False
    escalate_reason: str = ""
    steps: int = 0
