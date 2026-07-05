"""Application configuration, loaded from environment / .env via pydantic-settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    # Telemetry UDP listener
    udp_host: str = "0.0.0.0"
    udp_port: int = 9999

    # File logging
    log_dir: str = "./logs"
    log_stride: int = 5          # log every Nth packet
    log_format: str = "csv"      # csv | jsonl | both

    # Setup library (one JSON file per setup)
    setups_dir: str = "./setups"

    # Rolling buffer
    buffer_frames: int = 600

    # LLM provider selection: openai | anthropic | deepseek
    llm_provider: str = "openai"

    # OpenAI / OpenAI-compatible
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str = ""

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    anthropic_base_url: str = ""

    # DeepSeek (OpenAI-compatible)
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"

    # Web server
    web_host: str = "127.0.0.1"
    web_port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()