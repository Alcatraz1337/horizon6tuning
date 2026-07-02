"""Prompt templates for telemetry analysis."""

from __future__ import annotations

import json

SYSTEM_PROMPT = (
    "You are a precise motorsport driving coach analyzing live Forza Horizon 6 "
    "telemetry. You receive a compact statistical summary of a recent ~10-second "
    "driving window. Give concise, actionable insights: cornering technique, "
    "throttle/brake smoothness, gear/RPM usage, tire slip & temperature, lap-time "
    "trends, and concrete things the driver should change. Use bullet points. "
    "Be specific and quantitative where possible. Do not invent fields not present "
    "in the summary. Keep it under ~180 words."
)


def build_user_prompt(summary: dict, extra: str | None = None) -> str:
    """Render the telemetry summary into a prompt string for the LLM."""
    payload = json.dumps(summary, indent=2, default=str)
    parts = [
        "Here is the latest telemetry window summary (JSON):",
        "```json",
        payload,
        "```",
        "Analyze this window and give the driver coaching insights.",
    ]
    if extra:
        parts.append(f"\nAdditional context from the driver: {extra}")
    return "\n".join(parts)