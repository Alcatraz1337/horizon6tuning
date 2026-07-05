# Setup data model — design

**ROADMAP item 3.** Define a `Setup` as
`{id, name, car, track, fields: {…9 sections…}, notes, created_at, updated_at}`,
store setups as JSON files in `setups/`, expose CRUD over REST, and let the
current live session reference one setup. This is the per-setup metadata
foundation: the 9 tuning categories are setup data the user enters, not values
read from the live telemetry stream (per `CLAUDE.md`, only gearing is derivable
from the UDP stream; the other 8 are per-setup).

**Date:** 2026-07-04
**Scope:** backend + API + tests only. No frontend editor in v1 (that is ROADMAP
item 4). No `sessions.json` index (item 5). No LLM consumption of the attached
setup (item 11) — item 3 only stores the session→setup reference in memory.

## Decisions

- **Scope:** backend + API + tests, matching item 2's v1 pattern.
- **IDs:** `uuid.uuid4().hex` (32-char hex). Filename `setups/{id}.json`.
  Opaque, no collisions, stable across renames.
- **Validation:** permissive. All 9 sections optional, individual fields
  optional, unknown sections/fields silently dropped, numeric strings coerced
  to `float`. A setup can be just `{name, car, track, fields:
  {tire_pressure: {fl: 32.0}}}`. Best for beginners and for incremental
  editing in the item 4 editor.
- **Session link:** in-memory only. `router.state["current_setup_id"]` is set
  via API and not persisted to disk; item 5's `sessions.json` will persist it
  later. No logger changes in this item.
- **Architecture:** Approach A — one new module `app/store/setups.py`
  containing the `Setup` dataclass, a `SETUP_FIELD_SCHEMA` constant table, and
  a `SetupStore` file-CRUD class. Routes extend the existing
  `app/api/routes.py`. `SETUPS_DIR` added to `app/config.py`. This mirrors the
  codebase's flat `store/` layout and the data-driven schema pattern in
  `app/telemetry/schema.py`.

## FH6 tuning field schema

Verified against FH6-specific sources (ForzaFire FH6 Platform & Handling and
Drivetrain guides, grindout FH6 tuning guide, forzatune FH6 guide, skycoach FH6
tuning guide). Three fields deviate from the ROADMAP item 4 list and correct it
to FH6 reality:

- **Damping** uses **bump** (the FH6 slider label is "Bump Stiffness"), not
  "compression". Same physics.
- **Brake** tuning sliders are **bias** and **pressure**. Pad compound and
  rotor size are upgrade *part* choices, not tuning sliders.
- **Differential** has **accel lock** and **decel lock** per axle (front/rear)
  plus a single **center_balance** slider for AWD. **Preload does not exist in
  Forza** (it is an Assetto Corsa / iRacing concept).

ROADMAP item 4's field list will be updated to match this schema as part of
this item.

Per FH6, camber / toe / spring rate / ride height / rebound / bump are set per
axle (front/rear), not per-wheel. Tire pressure is per-wheel (FL/FR/RL/RR).
Caster is a single value. ARB, aero are front/rear. Brake bias/pressure and
diff center_balance are single values.

```python
SETUP_FIELD_SCHEMA: dict[str, list[str]] = {
    "tire_pressure":   ["fl", "fr", "rl", "rr"],                       # PSI, per-wheel
    "gearing":         ["final_drive", "gears"],                       # gears = list[float]
    "alignment":       ["camber_front", "camber_rear",
                        "toe_front", "toe_rear",
                        "caster"],
    "anti_roll_bars":  ["front", "rear"],
    "springs":         ["spring_rate_front", "spring_rate_rear",
                        "ride_height_front", "ride_height_rear"],
    "damping":         ["rebound_front", "rebound_rear",
                        "bump_front", "bump_rear"],
    "aero":            ["front_downforce", "rear_downforce"],
    "brake":           ["bias", "pressure"],
    "differential":    ["accel_lock_front", "accel_lock_rear",
                        "decel_lock_front", "decel_lock_rear",
                        "center_balance"],
}
```

`gearing.gears` is a `list[float]` (1st..top, variable length); every other
field is a scalar float (or null when unset).

## Data model (`app/store/setups.py`)

```python
@dataclass
class Setup:
    id: str                   # uuid4 hex, e.g. "a3f1b2c4..."
    name: str                 # user label, e.g. "R32 Fuji balanced"
    car: str                  # free text, e.g. "Nissan Skyline GT-R R32"
    track: str                # free text, e.g. "Fuji Speedway"
    fields: dict              # {"tire_pressure": {"fl": 32.0, ...}, ...}
    notes: str                # free text, default ""
    created_at: float         # time.time() at create
    updated_at: float         # time.time() at create/update

    def as_dict(self) -> dict: ...   # JSON-serializable form for API + disk
```

`id` / `name` / `car` / `track` are strings; `fields` defaults to `{}`;
`notes` defaults to `""`; `created_at` and `updated_at` are `time.time()`
floats (set on create, `updated_at` refreshed on update, `created_at`
preserved on update).

## `SetupStore` (`app/store/setups.py`)

```python
class SetupStore:
    def __init__(self, setups_dir: str | Path) -> None: ...

    def list(self) -> list[dict]: ...
        # summaries: [{id, name, car, track, notes, updated_at}, ...]
        # scans setups_dir, sorted by updated_at desc. No `fields` payload.

    def get(self, setup_id: str) -> dict | None: ...
        # full setup dict (with fields), or None if file missing / id invalid

    def create(self, data: dict) -> dict: ...
        # generates uuid4 hex id + created_at/updated_at, normalizes fields,
        # saves atomically, returns the saved full setup dict.
        # Raises ValueError if `name` missing/empty.

    def update(self, setup_id: str, data: dict) -> dict | None: ...
        # None if not found / id invalid. Replaces any provided top-level key
        # (name/car/track/notes/fields); preserves id + created_at, refreshes
        # updated_at. fields, if given, is re-normalized.
        # Raises ValueError if a provided name is empty.

    def delete(self, setup_id: str) -> bool: ...
        # True if deleted, False if not found / id invalid
```

Key behaviors:

- **ID generation & safety:** `create` generates `uuid.uuid4().hex`. On
  `get` / `update` / `delete`, `setup_id` is validated against `^[a-f0-9]{32}$`
  before any filesystem path is constructed — this blocks path traversal
  (`../`) and weird filenames cold. No file operation ever uses an unvalidated
  user-supplied ID; an invalid id returns `None` / `False` rather than raising.
- **Permissive normalization:** a `_normalize_fields(fields)` helper keeps
  only sections in `SETUP_FIELD_SCHEMA` and only field names listed under each
  section; unknown sections/fields are silently dropped; numeric strings
  coerced to `float`; everything else passes through; missing keys are omitted
  (treated as null on read). Runs on both `create` and `update`.
- **`list()` returns summaries, not full fields** — keeps the list payload
  small; the item 4 editor calls `get()` for the full document.
- **No caching:** setups are few and small; each call reads from disk. External
  edits (a user hand-editing a JSON file) are picked up immediately.
- **Atomic writes:** write to `{setups_dir}/{id}.json.tmp` then `os.replace`
  to `{setups_dir}/{id}.json`. A crash mid-write leaves the previous file
  intact (or no file for a brand-new setup), never a half-written one.
- **Required field:** `name` is required on create and on update-if-provided
  (a nameless setup is useless); `car` / `track` default to `""`, `notes` to
  `""`, `fields` to `{}`. The store raises `ValueError`; routes map that to
  HTTP 400.
- **Directory creation:** `SetupStore.__init__` does
  `os.makedirs(setups_dir, exist_ok=True)` so a fresh clone (with `setups/`
  gitignored) works without manual setup.

## API (`app/api/routes.py`)

Seven new routes, all reading `router.state["setups"]` (the `SetupStore`) and
`router.state["current_setup_id"]`:

```
GET    /api/setups                  → {"setups": [<summary>, ...]}
GET    /api/setups/{setup_id}       → full setup dict  (404 if not found)
POST   /api/setups                  → created full setup dict
       body: {name (required), car?, track?, fields?, notes?}
PUT    /api/setups/{setup_id}       → updated full setup dict  (404 if not found)
       body: any subset of {name, car, track, fields, notes}
DELETE /api/setups/{setup_id}       → {"deleted": setup_id}  (404 if not found)
POST   /api/session/setup           → {"setup_id": "...", "setup": <full setup or null>}
       body: {setup_id}   (setup_id=null/omitted detaches)
GET    /api/session/setup           → {"setup_id": "...", "setup": <full setup or null>}
```

Error handling, matching existing `routes.py` style
(`JSONResponse({"error": ...}, status_code=...)`):

- **400** — `POST /api/setups` with missing/empty `name` (store raised
  `ValueError`); `POST /api/session/setup` with a `setup_id` that is not a
  32-char hex string (the store would never have produced it).
- **404** — `GET` / `PUT` / `DELETE /api/setups/{id}` when the store returns
  `None` / `False`; `POST /api/session/setup` when `setup_id` is valid-format
  but no setup file exists.
- **503** — `router.state["setups"]` missing (mirrors the logging routes'
  "not initialized" guard).

Session-link behavior:

- `POST /api/session/setup` with `{"setup_id": "a3f1..."}` validates the id
  format itself (32-char hex) — *before* calling the store — so a bad-format
  id returns 400 distinct from a valid-format-but-missing id's 404. It then
  looks the id up, sets `router.state["current_setup_id"]`, and returns the full
  setup so the caller can render it immediately. With `{"setup_id": null}` or
  `{}` it detaches (sets to `None`) and returns `{"setup_id": null,
  "setup": null}`.
- `GET /api/session/setup` returns `{"setup_id": null, "setup": null}` when
  nothing is attached. When attached, it re-reads the setup from the store so a
  since-deleted setup is reported as `{"setup_id": "...", "setup": null}` —
  the dangling id stays so item 5 can record it, but the frontend sees the
  setup is gone.
- `DELETE /api/setups/{id}` does **not** auto-detach the current session link —
  it leaves a dangling id (reported as `setup: null` above). The user detaches
  explicitly. This keeps delete side-effects simple and predictable.

## Wiring, config, gitignore

**`app/config.py`** — one new field:
```python
setups_dir: str = "./setups"
```

**`.env.example`** — append:
```
# ---- Setup library ----
# Where setup JSON files are stored (one file per setup).
SETUPS_DIR=./setups
```

**`.gitignore`** — add `setups/` (user data, same treatment as `logs/`).
Add `setups/.gitkeep` so the directory exists in a fresh clone.

**`app/store/__init__.py`** — export the new types:
```python
from .setups import Setup, SetupStore
__all__ = ["TelemetryBuffer", "TelemetryLogger", "Setup", "SetupStore"]
```

**`app/main.py` `lifespan`** — create the store alongside buffer/logger/laps
and attach to router state:
```python
from .store.setups import SetupStore
...
setups = SetupStore(setups_dir=settings.setups_dir)
...
router.state = {
    ...existing keys...,
    "setups": setups,
    "current_setup_id": None,
}
```

No change to the UDP `on_frame` callback — setups are not derived from
telemetry. The store is created on startup and lives for the app lifetime; no
per-frame work.

**`ROADMAP.md`** — update item 4's field list to match the FH6 schema above
(camber/toe per axle front/rear, caster single, springs/damping per axle
front/rear, damping `bump` not "compression", brake `bias`+`pressure` not
pad/rotor, diff `accel_lock`/`decel_lock` per axle + `center_balance`, no
preload). Append status marker `[done · branch feature/setup-data-model]` to
item 3.

## Tests (`tests/test_setups.py`, TDD)

Follows `tests/test_laps.py` style: `from __future__ import annotations`,
`sys.path` insert, runnable via `python tests/test_setups.py` and
`python -m pytest tests/test_setups.py -q`. Uses pytest's `tmp_path` fixture
for the setups dir so tests never touch the real `setups/`. Route tests call
the route functions directly via `asyncio.run(...)` and set
`routes.router.state` by hand — same pattern as `test_laps.py`.

Cases:

1. **create + get round-trip** — `create({name, car, track,
   fields: {tire_pressure: {fl: 32}}})` returns a setup with a 32-hex id,
   `created_at == updated_at`, normalized fields; `get(id)` returns the same.
2. **permissive normalization** — create with an unknown section
   (`"foo": {...}`) and an unknown field in a known section
   (`tire_pressure: {fl: 30, bogus: 1}`) → unknown section and `bogus` dropped,
   `fl` kept; numeric string `"30"` coerced to `30.0`.
3. **list returns summaries, sorted by updated_at desc** — create 3 setups,
   assert `list()` returns `{id, name, car, track, notes, updated_at}` (no
   `fields`), newest first.
4. **update preserves id + created_at, refreshes updated_at** — create, update
   name + a fields section; assert id/created_at unchanged, `updated_at`
   advanced (`>= created_at`), fields replaced.
5. **delete** — create then delete → `delete` returns True, subsequent `get`
   returns None, second `delete` returns False.
6. **bad-id rejection** — `get("../etc/passwd")`, `get("not-a-uuid")`,
   `get("deadbeef")` (too short) → all return None without reading a file;
   `delete` with the same → False.
7. **create requires name** — `create({car: "x"})` raises `ValueError`; the
   route maps it to 400.
8. **API routes** — via direct `asyncio.run` calls:
   - `POST /api/setups` happy path + 400 on missing name.
   - `GET /api/setups/{id}` 200 + 404 on missing.
   - `PUT /api/setups/{id}` 200 + 404 on missing.
   - `DELETE /api/setups/{id}` 200 + 404 on missing.
   - `POST /api/session/setup` attaches and returns full setup;
     valid-format-but-missing id → 404; bad-format id → 400; `null` detaches.
   - `GET /api/session/setup` returns `{setup_id: null, setup: null}`
     initially, and the full setup after attach.
   - Dangling id after delete: attach a setup, delete it,
     `GET /api/session/setup` returns `{setup_id: <id>, setup: null}`.
9. **atomic write leaves no temp** — after a successful create, assert no
   `*.tmp` files remain in the setups dir and the `{id}.json` file parses as
   valid JSON.

A `__main__` block runs all the test functions and prints
`"setup data model tests passed"`, matching `test_laps.py`.

## Out of scope (deferred)

- Frontend setup editor UI (item 4).
- `sessions.json` index and persisting the session→setup link to disk (item 5).
- LLM consumption of the attached setup / setup-aware analysis (item 11).
- Setup library page (search/filter, duplicate-as-template, soft-delete)
  (item 21).

## Risks / assumptions

- **FH6 tuning UI is verified** for the 9 sections and field names via
  FH6-specific guides (see sources). If a future FH6 patch adds a slider, only
  `SETUP_FIELD_SCHEMA` needs editing — the `Setup` model, store, API, and
  wiring stay the same (the data-driven table is the single source of truth,
  mirroring `app/telemetry/schema.py`).
- **Permissive validation trades safety for flexibility.** Unknown fields are
  dropped silently, which could hide a typo from a hand-editing user. Accepted
  because the item 4 editor will only ever submit known field names, and a
  hand-edited file is the user's own responsibility. The `list`/`get` shape is
  stable regardless.
- **No caching means a directory scan per `list()` call.** Fine for the
  expected scale (dozens of setups, not thousands). If the library grows,
  caching is a small later addition behind the same API.
- **In-memory session link is lost on restart.** Intentional — persistence is
  item 5's job. The attached setup is recoverable by re-attaching via the API.

## Sources

- ForzaFire — FH6 Platform & Handling Tuning Guide:
  https://www.forzafire.com/guides/forza-horizon-6-platform-and-handling-tuning-guide
- ForzaFire — FH6 Drivetrain Tuning Guide:
  https://www.forzafire.com/guides/forza-horizon-6-drivetrain-tuning-guide
- grindout — FH6 Tuning Guide:
  https://grindout.com/forza-6/guides/tuning
- forzatune — The Fully Updated Forza Tuning Guide (FH6 + Motorsport):
  https://forzatune.com/guide/the-fully-updated-forza-tuning-guide
- skycoach — Complete FH6 Tuning Guide:
  https://skycoach.gg/blog/forza-horizon-6/articles/complete-tuning-guide