"""Langfuse tracing, behind a crash-proof wrapper.

The rest of the codebase writes @traced("step") and never checks whether tracing
is on. If Langfuse is missing or the keys are empty, every helper here becomes a
no-op. Observability must never take production down.

    trace  = one user turn
      span = router decision, agent run, MCP tool call, RAG retrieval
      generation = each LLM call
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator

from app.config import settings
from app.logging_setup import get_logger

log = get_logger(__name__)

_client: Any = None
_observe: Callable | None = None
_enabled = False


def init_tracing() -> bool:
    """Start Langfuse. Returns True if it is live. Idempotent."""
    global _client, _observe, _enabled

    if _enabled:
        return True

    if not settings.tracing_enabled:
        log.warning("Langfuse keys not set - tracing disabled (app still works).")
        return False

    try:
        from langfuse import Langfuse, observe

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
        _observe = observe
        _enabled = True
        log.info("Langfuse tracing enabled -> %s", settings.langfuse_host)
    except Exception as exc:  # noqa: BLE001 - never let tracing break the app
        log.warning("Langfuse could not start (%s) - continuing without tracing.", exc)

    return _enabled


def traced(name: str, as_type: str = "span") -> Callable:
    """Record a function call as a span (or a generation). Works on async too."""

    def decorator(func: Callable) -> Callable:
        if not _enabled or _observe is None:
            return func  # tracing off -> zero overhead
        try:
            # Langfuse only accepts as_type="generation"; a plain span is the
            # default and must be requested by omitting the argument.
            if as_type == "generation":
                return _observe(name=name, as_type="generation")(func)
            return _observe(name=name)(func)
        except Exception:  # noqa: BLE001
            return func

    return decorator


def update_trace(**kwargs: Any) -> None:
    """Attach session_id, input, output or tags to the current trace."""
    if _enabled:
        with contextlib.suppress(Exception):
            _client.update_current_trace(**kwargs)


def update_span(**kwargs: Any) -> None:
    """Attach input/output/metadata to the span we are currently inside."""
    if _enabled:
        with contextlib.suppress(Exception):
            _client.update_current_span(**kwargs)


@contextlib.contextmanager
def span(name: str, **kwargs: Any) -> Iterator[None]:
    """Trace a block of code rather than a whole function."""
    if not _enabled:
        yield
        return
    try:
        with _client.start_as_current_span(name=name, **kwargs):
            yield
    except Exception:  # noqa: BLE001
        yield


def score(name: str, value: float, comment: str = "") -> None:
    """Record a quality score on the current trace (used by the eval harness)."""
    if _enabled:
        with contextlib.suppress(Exception):
            _client.score_current_trace(name=name, value=value, comment=comment)


def flush() -> None:
    """Push buffered events. Call before the process exits."""
    if _enabled:
        with contextlib.suppress(Exception):
            _client.flush()


# Must run at import time. @traced decorators are applied when a module is first
# imported, so if tracing only started later (in the FastAPI lifespan) every
# decorator would already have seen _enabled = False and traced nothing.
init_tracing()
