# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

A Python workspace for capturing **Forza Horizon 6** live telemetry during gameplay
and combining it with third-party LLM analysis (OpenAI / Anthropic / DeepSeek).
Four capabilities: live telemetry tracking, file logging, multi-provider LLM
insights, and a browser dashboard that displays both raw data and LLM coaching.

## Commands

```bash
# Setup
python -m venv .venv
. .venv/Scripts/activate            # Windows / Git Bash: source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env                # then add your LLM API key(s)

# Run the dashboard + telemetry listener (serves http://127.0.0.1:8000)
python -m app.main

# Test without the game (streams synthetic 324B packets to UDP_PORT)
python scripts/fake_sender.py

# Parser tests (no pytest needed; also works with `pytest tests/`)
python tests/test_parser.py
```

Environment is configured via `.env` (see `.env.example`): `UDP_HOST/UDP_PORT`
(telemetry listener bind — must match the in-game "Data Out" IP/port),
`LLM_PROVIDER` (`openai|anthropic|deepseek`) plus the matching `*_API_KEY` /
`*_MODEL` / `*_BASE_URL`, `LOG_DIR/LOG_STRIDE/LOG_FORMAT`, `BUFFER_FRAMES`,
`WEB_HOST/WEB_PORT`.

## Architecture

```
Forza Horizon 6  --UDP 324B-->  UDP listener (asyncio DatagramProtocol)
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                      ▼
        Rolling buffer       File logger             WebSocket broadcast
       (recent frames +     (CSV/JSONL,               (per-connection queue;
        aggregate stats)     stride-throttled)         slow clients drop, not block)
              │                                              │
              ▼                                              ▼
       Insights service ─── LLM provider ──>          browser dashboard
       (summary -> prompt)  (OpenAI-compat             (gauges, pedals, tires,
                              or Anthropic)             sparkline, insights panel)
```

Package layout under `app/`:

- **`telemetry/`** — the wire format. `schema.py` is the single source of truth:
  data-driven field tables `(name, struct_char)` for the three contiguous packet
  sections (232B sled + 12B Horizon gap + 79B dash = ~324B "Dash Horizon",
  little-endian). `parser.py` builds struct format strings from those tables and
  unpacks each section only if the packet is long enough, so 232B sled and
  323/324B dash-horizon both parse. `frame.py` is the `TelemetryFrame` dataclass
  with derived helpers (`speed_kmh`, `throttle_pct`, `gear_display`,
  `tire_temps_c`, `to_dict()`). `listener.py` is the asyncio UDP server.
- **`store/`** — `buffer.py` rolling `deque` + `summary()` (compact LLM-friendly
  aggregates over the window); `logger.py` session CSV/JSONL writer.
- **`llm/`** — `base.py` defines the `LLMClient` protocol; `providers.py`
  implements `OpenAICompatibleClient` (covers **OpenAI and DeepSeek** via
  `base_url`) and `AnthropicClient`; `factory.py` selects per `LLM_PROVIDER`;
  `prompts.py` holds the coaching system/user prompts.
- **`insights/service.py`** — buffer summary → prompt → LLM → cached insight.
- **`api/routes.py`** — FastAPI router: `/`, `/api/status`, `WS /ws/telemetry`,
  `POST|GET /api/insights`. App state is attached to the router as `router.state`
  (a dict) during `lifespan` in `main.py` — routes read `router.state[...]`.
  A `_ConnectionManager` gives each WebSocket its own `asyncio.Queue` so the
  synchronous UDP `on_frame` callback (`manager.publish`) can't block the listener.
- **`main.py`** — `lifespan` wires buffer/logger/telemetry/LLM/insights together,
  starts the UDP listener, and registers the publish callback; `create_app()`
  mounts `/static` for the frontend.

`frontend/` is vanilla HTML/CSS/JS (no build step): `app.js` opens the WebSocket,
renders frames into `index.html`'s gauges/pedals/tire/lap widgets, keeps a
Chart.js sparkline, and calls `POST /api/insights`.

## Project direction & roadmap

The product target is a **shareable open-source tuning tool, useful from
beginner to pro**. The full execution-ordered feature list (21 items) lives in
[`ROADMAP.md`](ROADMAP.md) at the repo root. Two constraints from that roadmap
affect how new features are designed and should be respected on every change:

- **Beginner → pro is one tool, not two.** Achieved via a Simple/Advanced
  mode toggle in the dashboard (currently planned as ROADMAP item 8), with
  per-widget "?" tooltips and expand affordances layered on top (item 9).
  Simple mode is a curated subset, not a parallel code path.
- **The 9 tuning categories are tire pressure, gearing, alignment (camber /
  toe / caster), anti-roll bars, springs (rate + ride height), damping
  (rebound / compression), aero (downforce), brake (bias / pad / rotor), and
  differential (accel lock / decel lock / preload). Of these, only
  **gearing is derivable from the live UDP stream**; the other 8 are setup
  metadata that the user must enter and store against each session. A
  feature that "reads" tire pressure, alignment, ARB, springs, damping,
  aero, brake, or diff out of the live telemetry is making a wrong
  assumption — that data is per-setup, not per-frame. Live telemetry can
  give us *measured* behavior (tire temp/slip, suspension travel, G-forces)
  on those dimensions, but the *intended* values come from the attached
  Setup (ROADMAP items 3–4).

**Persistence is files only** for now (CSV/JSONL logs + a `sessions.json`
index + `setups/` JSON files). SQLite is parked in `ROADMAP.md` under
"Parked ideas" — revisit when in-app queries matter.

## Key Design Decisions & Constraints

- **Telemetry → LLM cadence is decoupled.** Telemetry is ~60Hz; LLM calls are
  slow and rate-limited. The LLM is never called per-packet — only on demand via
  `POST /api/insights`, which summarizes the in-memory window (`buffer.summary()`).
  Keep it that way.
- **Provider abstraction is real.** New OpenAI-compatible providers (e.g. a local
  Ollama/LiteLLM endpoint) are a one-line addition in `factory.py` reusing
  `OpenAICompatibleClient` with a different `base_url`/key.
- **FH6 packet schema is an assumption.** The parser is built from the documented
  Forza "Dash Horizon" layout used by FH4/FH5 (sources in `app/telemetry/schema.py`).
  If FH6 changes offsets/types, edit `schema.py`'s field tables — the parser
  rebuilds its struct formats from them. The `scripts/fake_sender.py` builds
  packets from the same tables, so it stays in sync.
- **API keys live in `.env` only** (gitignored). Never hardcode. The server starts
  fine with no LLM key configured — `/api/insights` then returns a 400 with a
  helpful message rather than crashing.
- **Logging is stride-throttled** (`LOG_STRIDE`, default 5 ≈ 12 rows/sec at 60Hz)
  and `flush()`es each write so a crash doesn't lose the session.