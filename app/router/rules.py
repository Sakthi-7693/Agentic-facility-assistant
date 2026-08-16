"""Stage 1 of the router: fast deterministic rules.

About 40% of traffic is trivially classifiable. A regex handles those for zero
tokens and is more reliable than a model. Anything a rule is unsure about
returns None and falls through to the LLM classifier.
"""

from __future__ import annotations

import re

from app.router.schemas import Route, RouteDecision


def _any(patterns: list[str]) -> re.Pattern:
    return re.compile("|".join(patterns), re.IGNORECASE)


GREETING = _any([
    r"^\s*(hi|hello|hey|good (morning|afternoon|evening))\b",
    r"^\s*(thanks|thank you|thankyou|bye|goodbye)\b",
    r"\bwho are you\b", r"\bwhat can you do\b", r"\bhelp me\b$",
])

AFFIRMATIVE = _any([
    r"^\s*(yes|yeah|yep|yup|sure|ok|okay|please do|go ahead|do it|confirm(ed)?|"
    r"proceed|affirmative|create it|raise it)\b",
])

NEGATIVE = _any([
    r"^\s*(no|nope|nah|cancel|stop|don'?t|do not|negative|not now|leave it)\b",
])

ACTION = _any([
    r"\b(create|raise|open|log|submit|file)\s+(a\s+)?"
    r"(maintenance|service|work)\s*(request|order|ticket)\b",
    r"\b(update|close|assign|escalate)\s+(the\s+)?(service\s*request|ticket|sr-\d+)\b",
])

ENERGY = _any([r"\b(energy|consumption|kwh|power usage|electricity|cost)\b"])

LIVE_DATA = _any([
    r"\b(current|right now|at the moment|live|latest|today'?s)\b.*\b"
    r"(temperature|status|power|airflow|reading|alert|alarm)\b",
    r"\bwhat is\b.*\b(status|temperature|power|airflow|health)\b",
    r"\b(show|list|any)\b.*\b(alerts?|alarms?)\b",
])

# The lookahead separates "what is a chiller" (definition) from
# "what is Chiller-01's temperature" (live reading).
DEFINITION = _any([
    r"\bwhat (is|are) (a|an|the)?\s*(ahu|air handling unit|chiller|vav|"
    r"cooling tower|bms|hvac|loto|lock ?out)\b(?![\s\-]*\d)",
    r"\bexplain (what|how)\b", r"\bdefine\b",
])

DOCUMENTATION = _any([
    r"\b(procedure|policy|manual|documentation|guideline|specification|"
    r"safety|ppe|checklist|standard|sop)\b",
    r"\bwhat should i (check|do)\b",
    r"\bhow (do|should) i\b",
])

INVESTIGATE = _any([
    r"\bwhy\b.*\b(high|low|hot|cold|warm|fail|failed|failing|down|wrong|"
    r"increase|increasing|drop)\b",
    r"\b(investigate|diagnose|troubleshoot|root cause|what'?s (happening|wrong|going on))\b",
    r"\b(too )?(hot|warm|cold|stuffy)\b.*\b(check|look|find out|investigate)\b",
    r"\bfind (the |likely )?cause\b",
])

# Order matters. Investigation is checked before live data because "why is X
# high" matches both, and investigation is the safer superset. Live data is
# checked before definitions for the same reason.
ORDERED_RULES: list[tuple[re.Pattern, Route, float, str]] = [
    (GREETING, Route.GENERAL, 0.95, "Greeting or capability question - no data needed."),
    (INVESTIGATE, Route.INVESTIGATE, 0.90, "Causal question - needs live data, docs and reasoning."),
    (ACTION, Route.ACTION, 0.92, "Explicit request to create or update a service request."),
    (ENERGY, Route.DATA_ANALYSIS, 0.85, "Energy question - needs aggregated live data."),
    (LIVE_DATA, Route.LIVE_DATA, 0.85, "Asks for a current reading - needs live MCP data."),
    (DEFINITION, Route.RAG, 0.90, "Definition question - answered from the documentation."),
    (DOCUMENTATION, Route.RAG, 0.80, "Asks about a procedure or policy - answered from docs."),
]


def apply_rules(text: str, has_pending_action: bool) -> RouteDecision | None:
    message = text.strip()
    if not message:
        return None

    # A pending confirmation beats everything: the user is answering us.
    if has_pending_action and (AFFIRMATIVE.search(message) or NEGATIVE.search(message)):
        return RouteDecision(
            route=Route.CONFIRMATION,
            confidence=0.99,
            reason="User replied to a pending confirmation request.",
            method="rule",
        )

    for pattern, route, confidence, reason in ORDERED_RULES:
        if pattern.search(message):
            return RouteDecision(route, confidence, reason, method="rule")

    return None  # not confident -> let the LLM decide
