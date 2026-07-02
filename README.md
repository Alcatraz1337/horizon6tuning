# horizon6tuning

Live telemetry workspace for **Forza Horizon 6**. Captures the game's UDP "Data Out"
stream, logs it to disk, and feeds rolling summaries to a third-party LLM
(OpenAI / Anthropic / DeepSeek) for driving coaching — all shown in a local web
dashboard.

![status](https://img.shields.io/badge/status-WIP-orange) ![python](https://img.shields.io/badge/python-3.12%2B-blue) ![license](https://img.shields.io/badge/license-MIT-green)

## Features

- **Live telemetry** — receives the Forza "Dash Horizon" UDP stream (~60Hz) and
  parses all 84+ fields (RPM, speed, gear, pedals, G-forces, tire slip/temp,
  suspension, lap times, fuel, boost, power, torque, …).
- **File logging** — every session is written to a timestamped CSV and/or JSONL
  file under `logs/`, stride-throttled so it doesn't drown your disk.
- **LLM coaching** — on demand, sends a compact statistical summary of the recent
  driving window to OpenAI, Anthropic, or DeepSeek and renders the coaching
  response in the dashboard.
- **Dashboard** — a dark, racing-styled web UI with RPM/speed gauges, pedal bars,
  steering indicator, color-coded tire temperatures, lap times, fuel/boost, a live
  RPM+speed sparkline, and the insights panel.

## Architecture

```
Forza Horizon 6  --UDP 324B packets-->  UDP listener (asyncio)
                                            │
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
              Rolling buffer         File logger (CSV/JSONL)   WebSocket broadcast
              (recent frames +                                  to browser dashboard
               aggregate stats)            │                        │
                    │                       │                        │
                    ▼                       │                        ▼
            Insights service ─── LLM provider ──> insights panel (browser)
            (summary -> prompt)   (OpenAI / Anthropic / DeepSeek)
```

| Package | Responsibility |
|---|---|
| `app/telemetry/` | Data-driven struct parser for the Forza packet, `asyncio` UDP listener, `TelemetryFrame` model |
| `app/store/` | Rolling ring buffer + running aggregate stats; session CSV/JSONL logger |
| `app/llm/` | Provider-agnostic `LLMClient` interface; OpenAI-compatible client (OpenAI **and** DeepSeek) + Anthropic client; prompt templates |
| `app/insights/` | Buffer summary → prompt → LLM → cached insight |
| `app/api/` | FastAPI app: static frontend, `/api/status`, `WS /ws/telemetry`, `POST /api/insights` |
| `frontend/` | Vanilla HTML/CSS/JS dashboard (gauges, pedals, tires, sparkline, insights) |
| `scripts/` | `fake_sender.py` — synthetic packet stream for game-free testing |

## Setup

```bash
python -m venv .venv
. .venv/Scripts/activate        # Windows (Git Bash: source .venv/Scripts/activate)
pip install -r requirements.txt
cp .env.example .env            # then edit .env and add your LLM API key(s)
```

Requires Python 3.12+ (uses `type X | None` syntax).

## In-game telemetry settings (Forza Horizon 6)

1. **Settings → HUD & Gameplay → Data Out**: On
2. **Data Out IP Address**: `127.0.0.1` (or this machine's LAN IP if the dashboard runs elsewhere)
3. **Data Out Port**: `9999` (must match `UDP_PORT` in `.env`)
4. **Data Out Packet Format**: `Dash` / `Car Dash` — the 324B "Dash Horizon" format
   this parser expects. The 232B "Sled" format also parses, but the dashboard uses
   dash-only fields (speed, gear, lap times, tire temps).

> **FH6 packet schema note:** The parser is built from the documented Forza
> "Dash Horizon" layout used by FH4/FH5 (see sources in `app/telemetry/schema.py`).
> If FH6 changes offsets/types, capture one real packet and adjust `schema.py`'s
> field tables — both the parser and `fake_sender.py` rebuild from them.

## Run

```bash
python -m app.main
# open http://127.0.0.1:8000
```

Launch the game; the dashboard's status dot turns green when packets arrive.
Press **Analyze** in the insights panel to send the current telemetry window to
the configured LLM.

## Test without the game

```bash
python scripts/fake_sender.py      # streams synthetic 324B packets to UDP_PORT
python tests/test_parser.py        # parser round-trip tests (no pytest needed)
```

## Configuration (`.env`)

| Variable | Default | Purpose |
|---|---|---|
| `UDP_HOST` / `UDP_PORT` | `0.0.0.0` / `9999` | Telemetry listener bind (match in-game Data Out) |
| `LOG_DIR` / `LOG_STRIDE` / `LOG_FORMAT` | `./logs` / `5` / `csv` | File logging location, every-Nth-packet throttle, `csv`/`jsonl`/`both` |
| `BUFFER_FRAMES` | `600` | Rolling window size (~10s at 60Hz) shown in UI / sent to LLM |
| `LLM_PROVIDER` | `openai` | One of `openai` / `anthropic` / `deepseek` |
| `OPENAI_API_KEY` / `OPENAI_MODEL` / `OPENAI_BASE_URL` | — | OpenAI credentials (any OpenAI-compatible endpoint via `OPENAI_BASE_URL`) |
| `ANTHROPIC_API_KEY` / `ANTHROPIC_MODEL` | — | Anthropic credentials |
| `DEEPSEEK_API_KEY` / `DEEPSEEK_MODEL` / `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | DeepSeek (OpenAI-compatible) credentials |
| `WEB_HOST` / `WEB_PORT` | `127.0.0.1` / `8000` | Dashboard server bind |

API keys live in `.env` only (gitignored). The server starts fine with no LLM key
configured — `/api/insights` then returns a helpful 400 instead of crashing.

## HTTP / WebSocket API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/` | Dashboard UI |
| `GET` | `/api/status` | Listener state, packet counts, last frame age, logger info |
| `WS` | `/ws/telemetry` | Live `TelemetryFrame` JSON stream |
| `POST` | `/api/insights` | Run LLM analysis on the current buffer (`{"extra": "optional focus"}`) |
| `GET` | `/api/insights` | Most recent insight |

## Adding a new LLM provider

Any OpenAI-compatible endpoint (e.g. a local Ollama / LiteLLM server) is a one-line
addition in `app/llm/factory.py` reusing `OpenAICompatibleClient` with a different
`base_url` and key. Non-OpenAI-compatible providers implement the `LLMClient`
protocol in `app/llm/base.py`.

## License

MIT