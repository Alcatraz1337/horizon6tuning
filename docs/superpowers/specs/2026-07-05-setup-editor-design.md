# Setup editor — design

**ROADMAP item 4.** A single "Setups" view in the dashboard where the user
fills in a car's 9 FH6 tuning categories (tire pressure, gearing, alignment,
anti-roll bars, springs, damping, aero, brake, differential) as collapsible
sections, manages saved setups (list / create / edit / delete), attaches one
setup to the current live session so the LLM knows the current setup, and
switches between metric and English units. The 9 categories are per-setup
metadata the user enters — not values read from the live telemetry stream (per
`CLAUDE.md`, only gearing is derivable from the UDP stream; the other 8 are
per-setup). The backend (SetupStore + REST CRUD + session-attach) was
delivered by item 3; item 4 is the frontend editor plus a small schema
endpoint and a schema correction.

**Date:** 2026-07-05
**Branch:** `feature/setup-editor`
**Scope:** frontend Setups view (vanilla HTML/CSS/JS, no build step), one new
backend schema endpoint, one `Setup.units` field + server-side unit
conversion, and a tire-pressure schema correction. No `sessions.json` index
(item 5), no LLM consumption of the attached setup (item 11), no setup
library search/filter/duplicate (item 21).

## Decisions

- **Surface:** a new "Setups" view in the dashboard (editor + minimal saved-
  setups list), reached via topbar tabs with `#setups` hash routing. Item 21
  later layers search/filter/duplicate/soft-delete on top of the same list.
- **JS structure (Approach B):** split `frontend/setups.js` out of `app.js`,
  with a tiny `frontend/common.js` holding shared helpers (`$`, fetchJSON) and
  a minimal event bus for `current-setup-id` + `active-view`. `index.html`
  loads `common.js`, then `app.js` and `setups.js`.
- **Save model:** explicit Save button (POST new / PUT existing). Dirty
  indicator; warn-on-navigate-away with unsaved changes. Unit-toggle is the
  one exception — it saves immediately (see Unit model).
- **Schema source:** `GET /api/setups/schema` exposes the 9 sections, field
  keys, labels, grouping, units, and conversion factors from a new
  `SETUP_FIELD_META` table co-located with `SETUP_FIELD_SCHEMA` in
  `app/store/setups.py` — single source of truth, mirroring
  `app/telemetry/schema.py`. The frontend fetches it once and renders the form
  dynamically.
- **Attach UX:** per-row Attach/Detach in the saved-setups list + a topbar
  current-setup chip visible from both Live and Setups views, kept in sync via
  the `common.js` event bus.
- **Units:** per-setup `units` field (`"english"` (default) | `"metric"`).
  The JSON file stores values in the declared unit, so the file adapts when
  the user switches units. The backend is the single conversion authority —
  the unit-toggle PUT sends the new `units` + current fields; the backend
  converts the three convertible field families and re-saves. Non-convertible
  fields (degrees, %, ratios) are stored unchanged.
- **Visual direction:** extends the existing dashboard tokens (dark
  racing-red/amber, monospace numerics, card panels, status dots). No new
  palette or typefaces. Signature element: a 9-segment completeness strip
  under the setup name, one segment per section, filled = accent red, empty =
  muted, clickable to jump to its section.

## FH6 tuning field schema (verified)

Cross-verified against FH6-specific sources (ForzaFire Platform & Handling and
Drivetrain guides, grindout FH6 tuning guide, forzatune FH6 guide, forza.guide
cheat sheet, GAMES.GG tuning guide). The FH6 tuning menu exposes these
adjustable sliders per category:

- **Tire pressure** — front, rear (per-axle, **2 sliders**). ForzaFire's
  "Tuning Front and Rear Tire Pressure" section, grindout's Front/Rear PSI
  table, and forzatune's "front tire pressure… rear tires" all confirm
  per-axle. **This corrects item 3's merged schema**, which had per-wheel
  `fl/fr/rl/rr` — that conflated the per-wheel tire *temperature* telemetry
  (4 values, correct) with the per-axle *pressure* tuning slider (2 values).
- **Gearing** — final drive + individual gear ratios (1st..top, variable
  list). 2 fields, one a `list[float]`.
- **Alignment** — front camber, rear camber, front toe, rear toe, caster
  (single). 5 sliders (ForzaFire: "front camber, rear camber, front toe, rear
  toe, and front caster").
- **Anti-roll bars** — front, rear. 2 sliders.
- **Springs** — spring rate front/rear, ride height front/rear. 4 sliders
  (ForzaFire: "spring rate (front and rear), ride height (front and rear)").
- **Damping** — rebound front/rear, bump front/rear. 4 sliders (ForzaFire:
  "damping (bump and rebound, front and rear)"). FH6 labels compression
  "bump".
- **Aero** — front downforce, rear downforce. 2 sliders.
- **Brake** — bias, pressure. 2 sliders (grindout: "Brake Bias and
  Pressure"). Pad compound / rotor size are upgrade parts, not tuning
  sliders.
- **Differential** — accel lock front/rear, decel lock front/rear,
  center_balance (AWD only). 5 sliders (ForzaFire: "Acceleration AND
  Deceleration on both axles, plus the AWD Center Balance slider"). FH6 has no
  diff preload.

Per-section slider counts: **2 / 2 / 5 / 2 / 4 / 4 / 2 / 2 / 5** (28 scalar
sliders + 1 variable gears list). The editor's per-section fill count shows
`k/N` against these Ns.

### Schema correction (item 3 fix)

`SETUP_FIELD_SCHEMA["tire_pressure"]` changes from `["fl", "fr", "rl", "rr"]`
to `["front", "rear"]`. `_normalize_fields` is data-driven over
`SETUP_FIELD_SCHEMA`, so it picks up the change with no logic edit. One
assertion in `tests/test_setups.py` updates. A note is appended to the item 3
spec. Any setup file created with the old per-wheel keys has them dropped by
normalization on next read (permissive normalization already drops unknown
field names).

```python
SETUP_FIELD_SCHEMA: dict[str, list[str]] = {
    "tire_pressure":   ["front", "rear"],                  # PSI/bar, per-axle  ← corrected
    "gearing":         ["final_drive", "gears"],           # gears = list[float]
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

### Presentation metadata (`SETUP_FIELD_META`)

A new table in `app/store/setups.py`, keyed by `(section, field)`, holding
`label`, `group` (`per_axle | single | list`), `unit` (canonical for the
field family), `unit_metric`, `unit_english`, and `conversion` (factor to
apply to the English value to get the metric value; `null` for
non-convertible fields). `gearing.gears` is `group: "list"`. The schema
endpoint serializes this. The frontend uses `group` to pick the field layout
and the unit fields to label inputs.

## Unit model

**Per-setup unit storage; files adapt.** The `Setup` dataclass gains a
`units: str = "english"` field, included in `_SETUP_KEYS`. The JSON file
stores values in the declared unit. A metric setup's file reads
`"tire_pressure": {"front": 2.21}, "units": "metric"`; an English one reads
`"tire_pressure": {"front": 32.0}, "units": "english"`. A user hand-editing
the JSON sees values in the declared unit.

**Convertible field families** (everything else — camber/toe/caster °, ARB,
aero, brake bias/pressure %, diff locks/center_balance %, gear ratios — is
unitless and stored unchanged):

| Field family | Fields | English unit | Metric unit | English→Metric | Metric→English |
|---|---|---|---|---|---|
| Tire pressure | `tire_pressure.*` | PSI | bar | ×0.0689476 | ×14.503773 |
| Spring rate | `springs.spring_rate_*` | lb/in | kgf/mm | ×0.017857 | ×56.020 |
| Ride height | `springs.ride_height_*` | in | cm | ×2.54 | ×0.393701 |

**Unit toggle = immediate save + server-side conversion.** When the user
clicks the toggle on an existing setup, the frontend sends
`PUT /api/setups/{id}` with `{units: <new>, fields: <current formState
fields>}`. The backend:

1. Reads the stored `units` (the *old* unit).
2. Normalizes the sent `fields` (interpreted as being in the old unit).
3. Converts the three convertible field families from old → new unit.
4. Sets `units = new`, refreshes `updated_at`, saves atomically.
5. Returns the converted full setup.

The frontend reloads the returned setup; dirty clears; toast "Saved in
metric" (or "Saved in English"). Non-convertible fields pass through
untouched. For a brand-new (unsaved) setup, the toggle applies the same
factors in-memory to convert the values being typed and flips the displayed
unit; the file is created on Save with the selected unit (no immediate save
— nothing exists yet). A new setup starts in English; the user can toggle
before saving.

**Conversion factors are single-source.** The factor table lives in
`SETUP_FIELD_META` in `app/store/setups.py` and is serialized by the schema
endpoint, so the frontend reads the same factors the backend uses. The
backend applies them for saved-setup conversion (the tested path); the
frontend applies them only for the in-memory new-setup case (manual
verification). The saved value is always what the backend wrote, so storage
and display never diverge. The item 11 LLM path reads `setup.units` to
interpret values.

**Backward compatibility:** existing item-3 setup files (no `units` field)
read back as `"english"` (default). `create`/`update` validate `units` to
`"english" | "metric"`, defaulting to `"english"` if missing/invalid
(permissive, matching the store's existing validation posture).

**Rounding:** display to 1 decimal for pressure (bar) and ride height (cm),
0 decimals for spring rate (lb/in, community convention). Storage keeps full
float precision; the round-trip metric→english test asserts values return
within 0.01.

## `Setup` model change (`app/store/setups.py`)

```python
@dataclass
class Setup:
    id: str
    name: str
    car: str = ""
    track: str = ""
    fields: dict = field(default_factory=dict)
    notes: str = ""
    units: str = "english"      # "english" | "metric"  ← new
    created_at: float = 0.0
    updated_at: float = 0.0
```

`_SETUP_KEYS` becomes `("id", "name", "car", "track", "fields", "notes",
"units", "created_at", "updated_at")`. `SetupStore.create` and `update`
accept `units`; an invalid/missing value defaults to `"english"`. `update`
with a `units` that differs from the stored value triggers conversion of the
merged fields before save. A new `_convert_units(fields, old, new)` helper
performs the three family conversions; it is a no-op when `old == new`.

## Schema endpoint (`app/api/routes.py`)

```
GET /api/setups/schema →
{
  "sections": [
    {"key": "tire_pressure", "label": "Tire pressure", "fields": [
      {"key": "front", "label": "Front", "group": "per_axle",
       "unit": "psi", "unit_metric": "bar", "unit_english": "psi",
       "conversion": 0.0689476},
      {"key": "rear", "label": "Rear", "group": "per_axle", ...}
    ]},
    {"key": "gearing", "label": "Gearing", "fields": [
      {"key": "final_drive", "label": "Final drive", "group": "single",
       "unit": "ratio", "unit_metric": null, "unit_english": null,
       "conversion": null},
      {"key": "gears", "label": "Gears", "group": "list",
       "unit": "ratio", ...}
    ]},
    ...9 sections, field counts 2/2/5/2/4/4/2/2/5...
  ]
}
```

`group` ∈ `per_axle | single | list`. The frontend pairs `per_axle` fields
into Front|Rear rows. The endpoint reads `SETUP_FIELD_SCHEMA` +
`SETUP_FIELD_META` (module-level constants) and serializes them — it does
not touch the store or `router.state`, so it works even before the store is
initialized (no 503 path).

## Frontend

### Files

```
frontend/
  index.html        # +topbar tabs + current-setup chip + Setups view container; +<script> tags
  styles.css        # +Setups view styles (extends existing tokens)
  common.js   (new) # $, fetchJSON, event bus (current-setup-id, active-view)
  app.js            # live dashboard; reads bus for the topbar chip
  setups.js   (new) # Setups view: list, editor, 9 sections, attach, unit toggle, hash routing
```

### Topbar

Two new elements in `topbar-right`, before the existing status + logging
toggle:

1. **View tabs** — `[Live]` `[Setups]` segmented control. Active = accent
   border + text color; inactive = muted. Click sets `location.hash` to
   `#setups` (Setups) or `#`/empty (Live). `hashchange` swaps main content.
   `role="tab"`, `aria-selected`.
2. **Current-setup chip** — `▸ {setup name}` or `▸ no setup attached`.
   Clicking jumps to the Setups view. Subscribes to the bus `setup:change`
   event. Muted when nothing attached.

The live WebSocket stays connected while the Setups view is shown (the live
grid is hidden, not torn down), so returning to Live is instant and the
buffer keeps filling.

### Setups view layout

Two-pane on wide screens: list pane (~320px, left) + editor pane (fills,
right). Narrow screens (≤980px) collapse to a single pane with a back-button
swap between list and editor.

**List pane** — `+ New setup` button, then saved setups sorted by
`updated_at` desc (backend already sorts). Each row: name (bold), `car ·
track` (muted one line), `updated {relative}` (muted small). The
currently-attached row shows a red `●` "Current" badge + "Detach" on hover;
other rows show "Attach" + "Edit" + "Delete" (trash) on hover. Clicking a row
opens it in the editor pane.

**Editor pane** — top: Name (required), Car, Track (free text). Below: the
9-segment completeness strip + the `Metric | English` unit toggle. Then 9
collapsible sections (`<details>`; first section open, rest collapsed). Then
Notes textarea. Footer: "● Unsaved changes" dot + `Cancel` + `Save changes`.

### 9-section form

Each section is a collapsible card. Header: section label + `k/N` fill count
+ chevron. Field layouts derive from the schema's `group`:

- **per_axle** (tire_pressure, anti_roll_bars, aero, and the per-axle pairs
  inside springs/damping/alignment/differential) — Front|Rear two-column
  rows.
- **single** (caster, brake.bias, brake.pressure, differential.center_balance,
  gearing.final_drive) — single input + unit.
- **list** (gearing.gears) — final_drive single input, then a dynamic gears
  list: rows labeled 1st/2nd/…/top, each a number input, with `+ gear` /
  `− gear` add/remove buttons. `gears` is `list[float]`; empty list allowed.

`alignment` mixes per-axle (camber_f/r, toe_f/r) + single (caster): two
Front|Rear rows then one single row. `differential`: two Front|Rear rows
(accel_lock_f/r, decel_lock_f/r) + center_balance single row, with a small
"center_balance is AWD-only" helper note. `springs`: two Front|Rear rows
(spring_rate, ride_height). `damping`: two Front|Rear rows (rebound, bump).

Units (from schema metadata, shown next to inputs): pressure PSI/bar, gear
ratios ratio, camber/toe/caster °, ARB stiffness, spring rate lb/in or
kgf/mm, ride height in or cm, aero downforce, brake bias %, brake pressure %,
diff locks %, center_balance %. The displayed unit follows the setup's
`units` field.

### Save / dirty model

Every input writes to an in-memory `formState` object. Comparing `formState`
against the loaded setup determines dirty. The "● Unsaved changes" dot + Save
button enable on dirty, or on name-non-empty for a new setup. **Save** POSTs
(new) or PUTs (existing) the whole `{name, car, track, fields, notes, units}`
(no unit conversion — fields are already in the setup's unit). On success:
toast "Saved", dirty clears, list pane refreshes, form reloads the saved
setup. **Cancel** on a dirty form confirms "Discard unsaved changes?" and
reloads from disk; on a clean form it deselects.

### Light client-side validation

Numeric inputs reject non-numeric input; empty = null (sent as omitted). No
min/max gating in v1 (item 18 may add guided ranges). Backend 400 (e.g. empty
name on save) renders inline under Name. Backend 404 on PUT/DELETE (setup
deleted in another tab) → toast "This setup was deleted elsewhere" + list
reload. Network failure → toast "Couldn't reach the server" with retry; form
state preserved.

## Wiring, config

No new config fields. `SETUPS_DIR` (item 3) already points at `setups/`. The
schema endpoint and unit conversion are pure code additions to
`app/store/setups.py` and `app/api/routes.py`. `app/main.py` lifespan is
unchanged — the `SetupStore` is already created and attached to
`router.state["setups"]`. `frontend/index.html` gains three `<script>` tags
(`common.js`, `app.js`, `setups.js` — `app.js` already loaded; we add
`common.js` before it and `setups.js` after).

`ROADMAP.md` — append status marker `[in progress]` to item 4 for the
duration of the work, then `[done · branch feature/setup-editor]` on
completion. Item 4's field list is already FH6-correct (item 3's spec updated
it); this spec only corrects tire_pressure to per-axle and adds the
`units` field.

## Tests (`tests/test_setups.py`, extended)

Follows `tests/test_setups.py` style: `from __future__ import annotations`,
`sys.path` insert, runnable via `python tests/test_setups.py` and
`python -m pytest tests/test_setups.py -q`. Uses pytest `tmp_path` for the
setups dir. Route tests call route functions directly via `asyncio.run(...)`
and set `routes.router.state` by hand.

New / changed cases:

1. **Schema endpoint shape** — `GET /api/setups/schema` returns 9 sections
   in schema order, with field counts 2/2/5/2/4/4/2/2/5; `tire_pressure`
   fields are `front`/`rear` (not `fl`/`fr`/`rl`/`rr`); each field has
   `label`, `group`, `unit`; convertible fields have non-null `unit_metric`/
   `unit_english`/`conversion`, non-convertible fields have nulls.
2. **Schema correction round-trips** — `create({name, fields:
   {tire_pressure: {front: 32.0, rear: 30.0}}})`; `get(id)` returns the same
   two values; the old per-wheel keys (`fl`/`fr`/`rl`/`rr`) are dropped by
   normalization if supplied.
3. **Unit round-trip** — create in english with `tire_pressure.front = 32.0`
   (PSI), `springs.spring_rate_front = 500.0` (lb/in),
   `springs.ride_height_front = 5.0` (in), `alignment.camber_front = -1.5`.
   PUT with `units: "metric"` + same fields → backend converts:
   `tire_pressure.front ≈ 2.21` bar, `springs.spring_rate_front ≈ 8.93`
   kgf/mm, `springs.ride_height_front = 12.7` cm; `units == "metric"`;
   `alignment.camber_front` still `-1.5` (degrees don't convert). PUT back
   with `units: "english"` + the metric fields → values return to 32.0 /
   500.0 / 5.0 within 0.01; `-1.5` unchanged.
4. **File adapts on disk** — after the metric switch in case 3, read
   `{setups_dir}/{id}.json` directly and assert the JSON contains the
   converted metric values and `"units": "metric"` (proves the file adapts,
   not just the API response).
5. **Default + backward-compat unit** — a setup created without `units`
   reads back as `"english"`; a hand-written item-3 file with no `units`
   field reads back as `"english"`.
6. **Invalid unit defaults** — `create({name: "x", units: "klingon"})`
   defaults to `"english"` (permissive).
7. **Non-convertible fields untouched across unit switch** — asserted within
   case 3 (camber) and separately for `brake.bias`, `differential.center_balance`,
   `gearing.final_drive`, `gearing.gears`.
8. **Existing item-3 cases still pass** — create/get round-trip, permissive
   normalization, list summaries sorted by updated_at desc, update preserves
   id + created_at, delete, bad-id rejection, create requires name, API
   routes, atomic write leaves no temp. The permissive-normalization test
   updates if it previously asserted `fl`/`fr`/`rl`/`rr`.

A `__main__` block runs all test functions and prints
`"setup editor tests passed"`, matching `test_setups.py`/`test_laps.py`.

### Manual verification checklist (frontend, no JS harness)

Committed alongside the spec. Launch `python -m app.main` +
`python scripts/fake_sender.py`, open `http://127.0.0.1:8000`:

- Topbar shows Live/Setups tabs + current-setup chip ("no setup attached").
- Click Setups → URL becomes `#setups`, Setups view shown, live grid hidden;
  Live WS stays connected (verify by returning to Live and seeing fresh
  telemetry).
- Empty list: "No setups yet — create your first tuning sheet." + New setup.
- New setup: Name placeholder; Tire pressure open, other 8 collapsed; Save
  disabled until Name non-empty.
- Fill fields → 9-segment strip + per-section `k/N` counts update live.
- Save → toast "Saved"; list pane shows the new row; chip unchanged.
- Edit an existing setup → dirty dot appears on first edit; Save writes;
  Cancel-on-dirty confirms.
- Attach a row → chip shows `▸ {name}`; Current badge on the row; Detach
  returns chip to "no setup attached".
- Delete → confirm dialog → row removed; if deleted setup was current, chip
  reverts to "no setup attached".
- Unit toggle on an existing setup → values convert (32 PSI → 2.2 bar),
  toast "Saved in metric"; reopen the setup → still metric; toggle back →
  32 PSI returns. Inspect `setups/{id}.json` on disk → shows metric values +
  `"units": "metric"` after the switch.
- Narrow the window to ≤980px → single-pane list/editor swap with back
  button.
- Hash on load: `http://127.0.0.1:8000/#setups` opens directly to Setups.

## Out of scope (deferred)

- `sessions.json` index and persisting the session→setup link to disk (item 5).
- LLM consumption of the attached setup / setup-aware analysis (item 11).
- Setup library page: search/filter, duplicate-as-template, soft-delete
  (item 21).
- Beginner tooltips and guided min/max ranges on sliders (items 9, 18).
- Simple/Advanced mode toggle (item 8) — the Setups view is the same in both
  modes for v1.

## Risks / assumptions

- **FH6 tuning UI is verified** for the 9 sections, field names, and
  per-section slider counts via FH6-specific guides (see sources). The
  tire_pressure correction is the one deviation from item 3's merged schema.
  If a future FH6 patch changes a slider, only `SETUP_FIELD_SCHEMA` +
  `SETUP_FIELD_META` need editing — the model, store, API, editor, and tests
  are data-driven.
- **Per-setup unit storage means two setups can have different units.** A
  list with mixed units is fine (the editor displays each in its own unit),
  but cross-setup comparison (item 13) will need to normalize to one unit
  before diffing. Noted for item 13, not handled here.
- **Unit conversion is lossy within rounding.** The round-trip test asserts
  values return within 0.01. Repeated toggling could drift by floating-point
  dust; acceptable for a tuning tool where the user re-enters values from the
  game anyway.
- **Backend-as-conversion-authority** keeps one tested conversion path. If
  the frontend also needs to convert for live display while editing before
  save, it reads the schema's `conversion` factor — but the saved value is
  always what the backend wrote, so storage and display never diverge.
- **Vanilla JS with no build step and no test harness** — frontend is
  verified manually per the checklist. The schema endpoint and unit
  conversion are unit-tested in Python. If the frontend grows, a JS test
  harness is a future addition (not item 4).

## Sources

- ForzaFire — FH6 Platform & Handling Tuning Guide:
  https://www.forzafire.com/guides/forza-horizon-6-platform-and-handling-tuning-guide
- ForzaFire — FH6 Drivetrain Tuning Guide:
  https://www.forzafire.com/guides/forza-horizon-6-drivetrain-tuning-guide
- ForzaFire — FH6 Tires & Rims Tuning Guide (Tuning Front and Rear Tire
  Pressure): https://www.forzafire.com/guides/forza-horizon-6-tires-and-rims-tuning-guide
- grindout — FH6 Tuning Guide: https://grindout.com/forza-6/guides/tuning
- forzatune — The Fully Updated Forza Tuning Guide (FH6 + Motorsport):
  https://forzatune.com/guide/the-fully-updated-forza-tuning-guide
- forza.guide — FH6 Tuning Cheat Sheet: https://forza.guide
- GAMES.GG — FH6 Tuning Guide:
  https://games.gg/forza-horizon-6/guides/forza-horizon-6-tuning-guide