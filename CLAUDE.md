# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is a greenfield repository (no code yet). The goals below describe what is to be built; do not assume any structure, build commands, or tooling exists until it is created. When starting implementation, establish the project layout first and update this file with real commands.

## Project Purpose

A workspace for capturing **Forza Horizon 6** live telemetry during gameplay and combining it with third-party LLM analysis. Three core capabilities:

1. **Live telemetry tracking** — receive real-time game telemetry data while the game is running.
2. **Logging** — persist telemetry data to file for later review/analysis.
3. **LLM integration** — connect to multiple third-party LLM providers (OpenAI, Anthropic, DeepSeek, etc.) to analyze telemetry and surface insights.
4. **Display** — visualize both the raw telemetry and the LLM-derived insights to the user.

## Domain Context

Forza Horizon telemetry is delivered over **UDP** from the game's "Data Out" setting (IP/port configured in-game, commonly `127.0.0.1` and a port like the Forza Telemetry port). The packet format is a fixed binary layout (the "Forza Motorsport/Horizon" telemetry packet) containing fields such as RPM, speed, gear, throttle/brake/clutch input, G-forces, lap/sector times, tire slip, suspension travel, etc. Forza Horizon 6's exact packet schema should be confirmed against the game's telemetry documentation or by capturing a live packet at runtime before writing the parser — do not assume it is byte-identical to prior titles.

## Implementation Notes (to be refined as code is written)

- **Telemetry source** is a UDP listener, not a file or REST API. Architecture should be built around a socket listener feeding a processing/streaming pipeline.
- **LLM provider abstraction**: multiple providers (OpenAI, Anthropic, DeepSeek) should sit behind a common interface so insights/analysis code is provider-agnostic. Keep API keys in environment variables / a config file excluded from version control — never hardcode.
- **Telemetry → LLM cadence**: telemetry arrives many times per second; LLM calls are slow and rate-limited. Design for decoupled sampling/aggregation (e.g. a rolling buffer or summary stats) rather than calling the LLM per-packet.
- When the project layout, language/framework, build/test/run commands, and module structure are established, record them in the relevant sections below and remove this notice.