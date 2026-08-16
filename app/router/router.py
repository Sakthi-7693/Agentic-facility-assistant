"""The routing layer.

    1. Rules     - regex, 0 ms, 0 tokens. Handles the obvious traffic.
    2. LLM       - the fast model classifies and reports a confidence.
    3. Fallback  - low confidence: ask a clarifying question, or escalate to
                   INVESTIGATE, the route that has every tool.
"""

from __future__ import annotations

from app.llm.client import get_llm
from app.llm.models import ModelTier
from app.logging_setup import get_logger
from app.router.rules import apply_rules
from app.router.schemas import Route, RouteDecision
from app.tracing import traced, update_span

log = get_logger(__name__)

LOW_CONFIDENCE = 0.45
VAGUE_WORD_COUNT = 4  # below this, ask rather than guess

CLASSIFIER_PROMPT = """You are the routing layer of a facility operations assistant.
Choose exactly ONE route for the user's message.

ROUTES
- general        : greetings, small talk, questions about your own capabilities.
- rag            : definitions, procedures, manuals, policies, safety, specifications.
- live_data      : a current reading or status of a specific asset, zone or alarm.
- data_analysis  : energy or consumption figures that must be totalled or compared.
- action         : the user explicitly asks to create or update a service request.
- investigate    : a cause/diagnosis question, or anything needing BOTH live data
                   and documentation plus reasoning ("why is it hot").

RULES
- Prefer "investigate" when the user asks WHY something is happening.
- Prefer "rag" for "what is" / "what should I check" questions.
- Only choose "action" if the user asks to change something, not merely to look.
- confidence is your honest probability (0.0-1.0) that this route is correct.

CONVERSATION SO FAR
{history}

USER MESSAGE
{message}

Reply with JSON only:
{{"route": "...", "confidence": 0.0, "reason": "one short sentence"}}"""


def _parse_route(value: object) -> Route | None:
    try:
        return Route(str(value).strip().lower())
    except ValueError:
        return None


def _clamp(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.5


class Router:
    @traced("router.decide")
    async def decide(
        self,
        message: str,
        history: list[dict] | None = None,
        has_pending_action: bool = False,
    ) -> RouteDecision:
        decision = apply_rules(message, has_pending_action)

        if decision is None:
            decision = await self._classify(message, history or [])
            if decision.confidence < LOW_CONFIDENCE:
                decision = self._handle_low_confidence(message, decision)

        log.info(
            "Route %s (%s, %.2f) - %s",
            decision.route.value,
            decision.method,
            decision.confidence,
            decision.reason,
        )
        update_span(output=decision.as_dict())
        return decision

    async def _classify(self, message: str, history: list[dict]) -> RouteDecision:
        transcript = (
            "\n".join(f"{t['role']}: {t['content']}" for t in history[-4:]) or "(no history)"
        )
        prompt = CLASSIFIER_PROMPT.format(history=transcript, message=message)

        result = await get_llm().chat_json(
            [{"role": "user", "content": prompt}],
            tier=ModelTier.FAST,
            fallback={},
        )

        route = _parse_route(result.get("route"))
        if route is None:
            return RouteDecision(
                route=Route.INVESTIGATE,
                confidence=0.3,
                reason="Classifier returned an unusable route; escalating.",
                method="fallback",
            )

        return RouteDecision(
            route=route,
            confidence=_clamp(result.get("confidence", 0.5)),
            reason=str(result.get("reason", "Classified by the LLM router."))[:200],
            method="llm",
        )

    @staticmethod
    def _handle_low_confidence(message: str, decision: RouteDecision) -> RouteDecision:
        """Short and vague -> ask. Long but unclear -> escalate."""
        if len(message.split()) <= VAGUE_WORD_COUNT:
            return RouteDecision(
                route=Route.GENERAL,
                confidence=decision.confidence,
                reason="Message too vague to route confidently.",
                method="fallback",
                clarification=(
                    "I want to make sure I check the right thing. "
                    "Which building or piece of equipment do you mean?"
                ),
            )

        return RouteDecision(
            route=Route.INVESTIGATE,
            confidence=decision.confidence,
            reason=(
                f"Low confidence ({decision.confidence:.2f}) on '{decision.route.value}' "
                "- escalated to the full agent."
            ),
            method="fallback",
        )


_router: Router | None = None


def get_router() -> Router:
    global _router
    if _router is None:
        _router = Router()
    return _router
