"""The only place a write tool is ever executed.

    turn 1: agent proposes  -> PendingAction stored on the session
    turn 2: user says yes   -> this module runs it
            user says no    -> this module discards it

Having a single execution point makes the safety property easy to audit.
"""

from __future__ import annotations

import re

from app.agents.base import AgentResult, PendingAction, ToolTrace
from app.logging_setup import get_logger
from app.mcp_client.client import get_mcp_client
from app.tracing import traced

log = get_logger(__name__)

AGENT_NAME = "confirmation_agent"

YES_PATTERN = re.compile(
    r"\b(yes|yeah|yep|yup|sure|ok|okay|go ahead|do it|please do|confirm(ed)?|"
    r"proceed|create it|raise it|approved?)\b",
    re.IGNORECASE,
)


def is_approval(message: str) -> bool:
    return bool(YES_PATTERN.search(message))


def _spoken_confirmation(result: dict) -> str:
    """Read the request number back - short and specific."""
    request = result.get("service_request", {})
    request_id = request.get("id", "the request")

    if result.get("created"):
        return (
            f"Done. I have raised {request_id} at {request.get('priority', 'medium')} "
            f"priority and assigned it to the {request.get('assigned_to', 'maintenance')}."
        )
    if result.get("updated"):
        return f"Done. {request_id} is now marked {request.get('status', 'updated')}."
    return "The action completed successfully."


@traced("agent.confirmation")
async def execute_pending_action(message: str, pending: PendingAction) -> AgentResult:
    if not is_approval(message):
        log.info("User declined the pending action: %s", pending.tool)
        return AgentResult(
            text="Understood, I have not made any changes. Let me know if you need anything else.",
            agent=AGENT_NAME,
            steps=1,
        )

    mcp = await get_mcp_client()
    result = await mcp.call(pending.tool, pending.arguments)
    trace = ToolTrace(
        pending.tool, pending.arguments, "error" not in result, "executed after confirmation"
    )

    if "error" in result:
        log.error("Confirmed action failed: %s", result["error"])
        return AgentResult(
            text=(
                f"I could not complete that action. {result['error']} "
                "Would you like me to try a different approach?"
            ),
            agent=AGENT_NAME,
            tools_used=[trace],
            steps=1,
        )

    return AgentResult(
        text=_spoken_confirmation(result), agent=AGENT_NAME, tools_used=[trace], steps=1
    )
