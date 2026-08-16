"""Plain data objects used to talk to any LLM provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModelTier(str, Enum):
    """FAST for routing and summarising, SMART for reasoning and tool planning.

    Choosing the tier per task is the main cost/latency lever in this project.
    """

    FAST = "fast"
    SMART = "smart"


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Normalised reply - identical in shape for Groq, Ollama and Gemini."""

    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = ""

    @property
    def wants_tools(self) -> bool:
        return len(self.tool_calls) > 0
