"""Insights service: buffer summary -> LLM -> insight text.

Keeps the most recent insight in memory for the GET endpoint.
"""

from __future__ import annotations

import logging
import time

from ..llm.base import LLMClient
from ..llm.prompts import SYSTEM_PROMPT, build_user_prompt
from ..store.buffer import TelemetryBuffer

log = logging.getLogger(__name__)


class InsightsService:
    def __init__(self, buffer: TelemetryBuffer, llm: LLMClient | None) -> None:
        self._buffer = buffer
        self._llm = llm
        self._latest: dict | None = None

    @property
    def llm(self) -> LLMClient | None:
        return self._llm

    def set_llm(self, llm: LLMClient | None) -> None:
        self._llm = llm

    def latest(self) -> dict | None:
        return self._latest

    def analyze(self, extra: str | None = None) -> dict:
        summary = self._buffer.summary()
        if summary.get("empty"):
            raise RuntimeError("no telemetry available yet — start a race first")

        if self._llm is None:
            raise RuntimeError(
                "no LLM client configured (check LLM_PROVIDER and the matching API key in .env)"
            )

        user_prompt = build_user_prompt(summary, extra=extra)
        log.info("requesting insight from %s/%s", self._llm.provider, self._llm.model)
        resp = self._llm.complete(system=SYSTEM_PROMPT, user=user_prompt)

        self._latest = {
            "text": resp.text,
            "provider": resp.provider,
            "model": resp.model,
            "usage": resp.usage,
            "summary": summary,
            "generated_at": time.time(),
        }
        return self._latest