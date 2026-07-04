# Per-lap segmentation — design

**ROADMAP item 2.** Detect lap boundaries from the live UDP telemetry stream
and compute per-lap summaries alongside the existing rolling buffer. This is
the foundation for later analysis features (trace view, lap comparison, tire
analytics, per-lap LLM analysis).

**Date:** 2026-07-04
**Scope:** backend + API + tests only. No frontend UI in v1 (UI consumers are
ROADMAP items 7 and 10). No on-disk persistence of lap summaries (session
index is item 5).

## Signals available in the packet

From `app/telemetry/schema.py`:

- `lap_number` (`H`) — monotonic lap counter
- `current_lap` (`f`) — running clock of the current lap, in seconds; resets
  toward 0 at the start of a new lap
- `distance_traveled` (`f`) — meters; wraps/decreases on a new lap
- `best_lap` / `last_lap` (`f`) — seconds
- `is_race_on` (`i`) — 1 while a race/session is active
- `current_race_time` (`f`) — total elapsed race time

## Lap-boundary detection rule

A lap boundary fires when **either**:

1. `lap_number` increases while `is_race_on` is true (primary signal), **or**
2. `current_lap` resets (drops below the previous frame's `current_lap` by a
   meaningful margin — i.e. the running lap clock wrapped) while `is_race_on`
   is true and `lap_number` did **not** increase (backup signal for cases where
   `lap_number` doesn't bump reliably).

Additional rules:

- **Session edges:** `is_race_on` off→on starts a fresh lap (any in-progress
  lap is finalized first); `is_race_on` on→off finalizes the in-progress lap
  without starting a new one.
- **Debounce:** a boundary is only registered after **2 consecutive
  confirming frames** so a single glitched packet cannot spawn a phantom lap.
  The first frame that looks like a boundary marks a *pending* boundary; the
  next frame must confirm it (still a new lap) before the previous lap is
  finalized.
- `distance_traveled` rollover is **not** a standalone trigger in v1; it is
  logged as extra confirmation when present but does not fire a boundary on
  its own (avoids false positives from packet jitter).

## Data model

```python
@dataclass
class Lap:
    lap_number: int            # from the packet's lap_number at lap start
    started_at_ns: int         # wall-clock ns of first frame in the lap
    ended_at_ns: int | None    # wall-clock ns of the boundary frame (None if in progress)
    duration_s: float | None   # ended_at - started_at, seconds; None while in progress
    frame_count: int
    best_lap: float | None     # seconds, snapshot at lap finalize
    last_lap: float | None     # seconds, snapshot at lap finalize
    summary: dict              # same shape as TelemetryBuffer.summary() over the lap window
```

The `summary` dict reuses the aggregate shape from
`app/store/buffer.py::TelemetryBuffer.summary()` (speed/rpm/throttle/brake/
combined tire slip / lateral-g / longitudinal-g / tire temps / fuel / boost /
gear) **plus** `lap_time` (= `duration_s`) and `fuel_used` (first-frame fuel
minus last-frame fuel in the lap). Keeping the shape consistent means the
insights service and future lap-LLM mode can reuse the same consumer code.

## `LapTracker` (`app/store/laps.py`)

```python
class LapTracker:
    def __init__(self, maxlen: int = 200) -> None: ...
    def on_frame(self, frame: TelemetryFrame) -> None: ...
    def current(self) -> dict | None: ...        # in-progress lap summary, or None
    def completed(self) -> list[dict]: ...       # list of finalized Lap.as_dict()
    def lap(self, lap_number: int) -> dict | None: ...
    def reset(self) -> None: ...                 # clear everything (new session)
```

Internals:

- A `deque[Lap]` (maxlen) of completed laps.
- A running accumulator for the in-progress lap: per-metric min/max/sum/count
  so we can compute avg/min/max at finalize without storing every frame.
  Mirrors the math in `TelemetryBuffer.summary()` but accumulated incrementally.
- `_pending_boundary: bool` and `_prev_frame` for debounce + reset detection.
- `on_frame` is synchronous and cheap (it runs inside the UDP `on_frame`
  callback, same path as the WebSocket publisher) — no I/O, no allocations
  beyond the accumulator updates.

`Lap.as_dict()` returns the JSON-serializable form for the API.

## API (`app/api/routes.py`)

Three new routes, all reading `router.state["laps"]`:

- `GET /api/laps` → `{"current": <in-progress summary or null>,
   "completed": [<Lap.as_dict>, ...]}`
- `GET /api/laps/{lap_number}` → single `Lap.as_dict()` (404 if not found in
  completed laps or current)
- Existing `GET /api/status` is **not** changed (lap data has its own endpoint
  to keep status payload small).

404 follows the existing `JSONResponse({"error": ...}, status_code=404)` style
used elsewhere in `routes.py`.

## Wiring (`app/main.py` `lifespan`)

- Create `laps = LapTracker(maxlen=200)` alongside `buffer` / `logger`.
- Extend the existing `on_frame` lambda to also call `laps.on_frame(frame)`:
  ```python
  telemetry.set_on_frame(lambda frame: (manager.publish(frame), laps.on_frame(frame)))
  ```
- Add `"laps": laps` to the `router.state` dict.

No change to `TelemetryBuffer`, `TelemetryLogger`, the listener, or the parser.

## Tests (`tests/test_laps.py`, TDD)

Follow the existing `tests/test_parser.py` style: runnable directly via
`python tests/test_laps.py` and also under `pytest tests/`. Build
`TelemetryFrame` instances directly (no UDP socket).

Cases:

1. `lap_number` increment → one completed lap, one new in-progress lap.
2. `current_lap` reset (lap_number unchanged) → boundary detected via backup
   signal.
3. `is_race_on` off→on → in-progress lap finalized, new lap started.
4. `is_race_on` on→off → in-progress lap finalized, no new lap.
5. Glitch debounce → a single frame that looks like a boundary but the next
   frame reverts does **not** finalize a lap.
6. Summary math → avg/min/max speed, lap time, fuel_used computed correctly
   over a known synthetic lap.
7. `GET /api/laps` and `GET /api/laps/{n}` return the expected shape via
   FastAPI `TestClient` (or by calling the route functions directly if
   TestClient isn't already a dependency — prefer direct call to avoid adding
   a test-only dependency; match whatever `tests/` already does).
8. Bounded memory → appending > `maxlen` laps drops the oldest.

## Out of scope (deferred)

- Frontend lap UI (items 7, 10).
- Persisting lap summaries to disk / `sessions.json` (item 5).
- Per-lap LLM analysis (item 11).
- Sector analysis (item 14).

## Risks / assumptions

- **FH6 packet quirks:** the rule is conservative (debounced, lap_number
  primary) because the schema is an FH4/FH5 assumption per `CLAUDE.md`. If FH6
  behaves differently, only `LapTracker`'s boundary rule needs editing — the
  `Lap` model, API, and wiring stay the same.
- **No raw frame storage per lap:** per-lap summaries are aggregates only; raw
  per-lap frames are already in the CSV/JSONL logs and can be reconstructed
  from there for the trace view (item 7).
- `on_frame` is synchronous and runs in the UDP callback; `LapTracker.on_frame`
  must stay O(1) per frame and never block.