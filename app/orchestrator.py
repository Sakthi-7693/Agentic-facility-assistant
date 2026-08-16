from __future__ import annotations
import time
from dataclasses import dataclass, field
from typing import Any

from app.agents.base import AgentResult
from app.agents.confirmation import execute_pending_action
from app.agents.registry import get_agent
from app.logging_setup import get_logger
from app.router.router import get_router
from app.router.schemas import Route, RouteDecision
from app.session import Session, session_store
from app.tracing import traced, update_trace
from app.voice.stt import transcribe_bytes
from app.voice.tts import speak

log = get_logger(__name__)

ERROR_REPLY = (
    "Sorry, I ran into a problem while handling that request. "
    "Please try again, or ask me something else."
)

RATE_LIMIT_REPLY = (
    "I have hit the model's rate limit for now. Please try again in a few "
    "minutes, or switch to a smaller model in the configuration."
)


def _error_reply(exc: Exception) -> str:
    """Rate limits are worth naming - the user can act on them."""
    text = str(exc).lower()
    if "rate limit" in text or "429" in text:
        return RATE_LIMIT_REPLY
    return ERROR_REPLY


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


@dataclass
class TurnResult:
    """Everything one turn produced. Returned to the UI as JSON."""

    session_id: str
    transcript: str
    reply: str
    audio_file: str | None = None
    route: str = ""
    route_confidence: float = 0.0
    route_reason: str = ""
    route_method: str = ""
    agent: str = ""
    sources: list[str] = field(default_factory=list)
    tools_used: list[dict] = field(default_factory=list)
    awaiting_confirmation: bool = False
    pending_action: str | None = None
    rerouted_from: str | None = None
    timings_ms: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


class Orchestrator:
    async def handle_audio(self, audio: bytes, session_id: str | None) -> TurnResult:
        started = time.perf_counter()
        transcript = await transcribe_bytes(audio)
        stt_ms = _ms(started)

        if not transcript.text:
            return TurnResult(
                session_id=session_store.get_or_create(session_id).id,
                transcript="",
                reply="I did not catch that. Could you say it again?",
                timings_ms={"stt": stt_ms},
            )

        result = await self.handle_text(transcript.text, session_id)
        result.timings_ms["stt"] = stt_ms
        return result

    @traced("turn")
    async def handle_text(self, message: str, session_id: str | None) -> TurnResult:
        started = time.perf_counter()
        session = session_store.get_or_create(session_id)

        update_trace(
            name="facility-agent-turn",
            session_id=session.id,
            input=message,
            tags=["voice-agent"],
        )

        try:
            decision, result, rerouted_from = await self._process(message, session)
        except Exception as exc:  # noqa: BLE001 - the user must always get a reply
            log.exception("Turn failed: %s", exc)
            decision = RouteDecision(Route.GENERAL, 0.0, f"Turn failed: {exc}", "error")
            result = AgentResult(text=_error_reply(exc), agent="error_handler")
            rerouted_from = None

        agent_ms = _ms(started)

        session.add_user(message)
        session.add_assistant(result.text)
        session.pending_action = result.pending_action

        tts_started = time.perf_counter()
        audio_file = await speak(result.text)

        update_trace(
            output=result.text,
            metadata={
                "route": decision.route.value,
                "confidence": decision.confidence,
                "agent": result.agent,
                "tools": [t.name for t in result.tools_used],
                "rerouted_from": rerouted_from,
            },
        )

        return TurnResult(
            session_id=session.id,
            transcript=message,
            reply=result.text,
            audio_file=audio_file,
            route=decision.route.value,
            route_confidence=round(decision.confidence, 2),
            route_reason=decision.reason,
            route_method=decision.method,
            agent=result.agent,
            sources=result.sources,
            tools_used=[t.as_dict() for t in result.tools_used],
            awaiting_confirmation=result.pending_action is not None,
            pending_action=result.pending_action.description if result.pending_action else None,
            rerouted_from=rerouted_from,
            timings_ms={"agent": agent_ms, "tts": _ms(tts_started)},
        )

    async def _process(
        self, message: str, session: Session
    ) -> tuple[RouteDecision, AgentResult, str | None]:
        decision = await get_router().decide(
            message,
            history=session.recent_history(),
            has_pending_action=session.has_pending_action,
        )

        # The user is answering a confirmation question.
        if decision.route is Route.CONFIRMATION and session.pending_action:
            pending = session.pending_action
            session.clear_pending()
            return decision, await execute_pending_action(message, pending), None

        # The router wants a clarification rather than a guess.
        if decision.needs_clarification:
            return decision, AgentResult(text=decision.clarification or "", agent="router"), None

        agent = get_agent(decision.route)
        result = await agent.run(message, history=session.recent_history())

        # Self-correction: the agent says this was the wrong route.
        if result.escalate and decision.route is not Route.INVESTIGATE:
            original = decision.route.value
            log.info("Re-routing from %s: %s", original, result.escalate_reason)
            decision = RouteDecision(
                route=Route.INVESTIGATE,
                confidence=0.6,
                reason=f"Escalated from '{original}': {result.escalate_reason}",
                method="escalation",
            )
            result = await get_agent(Route.INVESTIGATE).run(
                message, history=session.recent_history()
            )
            return decision, result, original

        return decision, result, None


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
