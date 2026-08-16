"""LLM client.

Groq, Ollama and Gemini all expose an OpenAI-compatible API, so one client
covers all three. Switching provider is a base URL change in .env.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.llm.models import LLMResponse, ModelTier, ToolCall
from app.logging_setup import get_logger
from app.tracing import traced, update_span

log = get_logger(__name__)

RETRY_DELAYS = [1, 3, 6]

# Retrying these is pointless - the same request will fail the same way. Only
# transient failures (429, 5xx, timeouts) are worth a second attempt.
FATAL_STATUS_CODES = {400, 401, 403, 404, 422}

# The exception. Smaller models sometimes emit a malformed tool call, which the
# provider rejects with a 400. That is a sampling failure, not a bad request -
# re-generating often produces a valid call, so this one IS worth retrying.
RETRYABLE_400 = "tool_use_failed"


def parse_json_safely(text: str, fallback: dict[str, Any]) -> dict[str, Any]:
    """Parse JSON from a model reply, tolerating fences and stray prose."""
    if not text:
        return fallback

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`").removeprefix("json").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            pass

    log.warning("Could not parse JSON from model output: %.120s", text)
    return fallback


class LLMClient:
    def __init__(self) -> None:
        self._client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            timeout=60.0,
        )
        log.info(
            "LLM provider=%s | fast=%s | smart=%s",
            settings.llm_provider,
            settings.fast_model,
            settings.smart_model,
        )

    @staticmethod
    def model_for(tier: ModelTier) -> str:
        return settings.fast_model if tier is ModelTier.FAST else settings.smart_model

    @traced("llm.chat", as_type="generation")
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tier: ModelTier = ModelTier.FAST,
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.2,
        force_json: bool = False,
    ) -> LLMResponse:
        model = self.model_for(tier)
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        if force_json:
            payload["response_format"] = {"type": "json_object"}

        response = self._normalise(await self._call_with_retry(payload), model)

        update_span(
            output=response.content or [c.name for c in response.tool_calls],
            metadata={
                "model": model,
                "tier": tier.value,
                "prompt_tokens": response.prompt_tokens,
                "completion_tokens": response.completion_tokens,
            },
        )
        return response

    async def chat_json(
        self,
        messages: list[dict[str, Any]],
        tier: ModelTier = ModelTier.FAST,
        fallback: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Ask for JSON. Returns `fallback` if the model produced junk."""
        response = await self.chat(messages, tier=tier, temperature=0.0, force_json=True)
        return parse_json_safely(response.content, fallback or {})

    async def _call_with_retry(self, payload: dict[str, Any]) -> Any:
        last_error: Exception | None = None

        for attempt, wait in enumerate(RETRY_DELAYS, start=1):
            try:
                return await self._client.chat.completions.create(**payload)
            except Exception as exc:  # noqa: BLE001 - provider SDKs raise many types
                last_error = exc

                fatal = getattr(exc, "status_code", None) in FATAL_STATUS_CODES
                if fatal and RETRYABLE_400 not in str(exc):
                    log.error("LLM call rejected (not retryable): %s", exc)
                    raise
                if fatal:
                    log.warning("Malformed tool call from the model - re-generating")

                log.warning(
                    "LLM call failed (attempt %d/%d): %s - retrying in %ss",
                    attempt,
                    len(RETRY_DELAYS),
                    exc,
                    wait,
                )
                await asyncio.sleep(wait)

        raise RuntimeError(f"LLM call failed after {len(RETRY_DELAYS)} attempts") from last_error

    @staticmethod
    def _normalise(raw: Any, model: str) -> LLMResponse:
        choice = raw.choices[0]
        message = choice.message
        usage = getattr(raw, "usage", None)

        return LLMResponse(
            content=(message.content or "").strip(),
            tool_calls=[
                ToolCall(
                    id=call.id,
                    name=call.function.name,
                    # Models occasionally emit slightly broken JSON here.
                    arguments=parse_json_safely(call.function.arguments, {}),
                )
                for call in message.tool_calls or []
            ],
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            finish_reason=choice.finish_reason or "",
        )


_llm_client: LLMClient | None = None


def get_llm() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
