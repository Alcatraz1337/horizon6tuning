"""Concrete LLM provider clients.

  * OpenAICompatibleClient — covers OpenAI and DeepSeek (DeepSeek is an
    OpenAI-compatible API; just override `base_url`).
  * AnthropicClient — the Anthropic Messages API.

Both wrap their official SDKs so streaming, retries, and auth are handled by the
SDK rather than reimplemented here.
"""

from __future__ import annotations

from .base import LLMResponse


class OpenAICompatibleClient:
    """Works for OpenAI (`base_url=None`) and DeepSeek (`base_url=https://api.deepseek.com`)."""

    def __init__(self, api_key: str, model: str, base_url: str | None = None,
                 provider: str = "openai") -> None:
        if not api_key:
            raise ValueError(f"{provider} API key is not set")
        from openai import OpenAI  # imported lazily so missing SDK only errors if used
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self.model = model
        self.provider = provider

    def complete(self, system: str, user: str, temperature: float = 0.4) -> LLMResponse:
        resp = self._client.chat.completions.create(
            model=self.model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        text = resp.choices[0].message.content or ""
        usage = None
        try:
            usage = {"prompt_tokens": resp.usage.prompt_tokens,
                     "completion_tokens": resp.usage.completion_tokens,
                     "total_tokens": resp.usage.total_tokens}
        except AttributeError:
            pass
        return LLMResponse(text=text, provider=self.provider, model=self.model,
                           usage=usage, raw=resp)


class AnthropicClient:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        if not api_key:
            raise ValueError("anthropic API key is not set")
        from anthropic import Anthropic
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = Anthropic(**kwargs)
        self.model = model
        self.provider = "anthropic"

    def complete(self, system: str, user: str, temperature: float = 0.4) -> LLMResponse:
        resp = self._client.messages.create(
            model=self.model,
            max_tokens=1024,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(block.text for block in resp.content if hasattr(block, "text"))
        usage = {"input_tokens": resp.usage.input_tokens,
                 "output_tokens": resp.usage.output_tokens}
        return LLMResponse(text=text, provider=self.provider, model=self.model,
                           usage=usage, raw=resp)