"""Provider-agnostic LLM client interface."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    usage: dict | None = None
    raw: object | None = None  # underlying SDK response, for debugging


class LLMClient(Protocol):
    """All providers implement this minimal interface."""

    provider: str
    model: str

    def complete(self, system: str, user: str, temperature: float = 0.4) -> LLMResponse:
        """Generate a completion for a (system, user) prompt pair."""
        ...