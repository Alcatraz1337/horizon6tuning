"""Build the configured LLM client from settings."""

from __future__ import annotations

from ..config import Settings
from .base import LLMClient
from .providers import AnthropicClient, OpenAICompatibleClient


class LLMConfigError(RuntimeError):
    pass


def build_llm_client(settings: Settings) -> LLMClient:
    provider = (settings.llm_provider or "").lower().strip()

    if provider == "openai":
        return OpenAICompatibleClient(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            base_url=settings.openai_base_url or None,
            provider="openai",
        )
    if provider == "deepseek":
        return OpenAICompatibleClient(
            api_key=settings.deepseek_api_key,
            model=settings.deepseek_model,
            base_url=settings.deepseek_base_url or "https://api.deepseek.com",
            provider="deepseek",
        )
    if provider == "anthropic":
        return AnthropicClient(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            base_url=settings.anthropic_base_url or None,
        )

    raise LLMConfigError(
        f"unknown LLM_PROVIDER {provider!r} (expected one of: openai, anthropic, deepseek)"
    )