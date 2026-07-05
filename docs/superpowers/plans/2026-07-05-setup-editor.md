# Setup Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Setups" view in the dashboard where the user fills in a car's 9 FH6 tuning categories, manages saved setups (list/create/edit/delete), attaches one to the live session, and switches between metric and English units.

**Architecture:** Backend adds `SETUP_FIELD_META` (label/group/unit/conversion per field), a `units` field on `Setup` with server-side conversion, a `GET /api/setups/schema` endpoint, and fixes `tire_pressure` from per-wheel to per-axle. Frontend splits into `common.js` (helpers + event bus) + `setups.js` (Setups view), adds topbar tabs, hash routing (`#setups`), and a 9-segment completeness strip. Conversion factors live once in `SETUP_FIELD_META`; backend is the conversion authority; frontend only converts in-memory for the new-setup case.

**Tech Stack:** Python 3.10+ stdlib (dataclasses, json, re, os, pathlib, uuid), FastAPI, pydantic-settings. Vanilla HTML/CSS/JS in `frontend/` (no build step); Chart.js already loaded. Tests run via `conda run -n fh6tuning python -m pytest tests/ -q`.

**Spec:** `docs/superpowers/specs/2026-07-05-setup-editor-design.md`

## Global Constraints

- **Run Python via conda on this Mac:** `conda run -n fh6tuning ...` (not `.venv`). Run tests with `conda run -n fh6tuning python -m pytest tests/test_setups.py -q` and `conda run -n fh6tuning python tests/test_setups.py`.
- **Branch:** `feature/setup-editor` (already created and checked out). One commit per task.
- **Persistence is files only:** one JSON file per setup in `setups/`. No SQLite, no DB.
- **Permissive validation:** unknown sections/fields silently dropped; numeric strings coerced to `float`; all 9 sections optional; only `name` required; invalid `units` defaults to `"english"`.
- **IDs are `uuid.uuid4().hex`** (32 lowercase hex chars). Any user-supplied id is validated against `^[a-f0-9]{32}$` before filesystem path construction.
- **Atomic writes:** write `{id}.json.tmp` then `os.replace` to `{id}.json`.
- **FH6 field schema is data-driven.** `SETUP_FIELD_SCHEMA` + `SETUP_FIELD_META` are single source of truth. `tire_pressure` is `["front", "rear"]` (per-axle), not per-wheel. Damping uses `bump_*`, not `compression_*`. Brake is `bias` + `pressure` (no pad/rotor). Diff has no `preload`. Per-section slider counts: 2/2/5/2/4/4/2/2/5.
- **Match existing code style:** `from __future__ import annotations`, module docstrings, `JSONResponse({"error": ...}, status_code=...)` for non-200, route functions read `router.state[...]`.
- **Tests match `tests/test_setups.py` style:** `from __future__ import annotations`, `sys.path` insert, runnable standalone + under pytest, route tests call route functions directly via `asyncio.run(...)` and set `routes.router.state` by hand.
- **Frontend is vanilla JS, no build step, no test harness.** Verified manually per the spec's checklist after the frontend tasks land.
- **Match existing frontend style:** extend `frontend/styles.css` tokens (`--bg`, `--panel`, `--accent` red, `--accent-2` amber, `--mono`); do not introduce new palette or typefaces.

## File Structure

- **Modify `app/store/setups.py`** — fix `tire_pressure` to `["front","rear"]`; add `SETUP_FIELD_META` (label/group/unit/unit_metric/unit_english/conversion per (section, field)); add `units: str = "english"` to `Setup`; add `"units"` to `_SETUP_KEYS`; add `_convert_units(fields, old, new)` helper; make `SetupStore.create`/`update` accept `units` (default + invalid → "english") and trigger conversion in `update` when `units` changes.
- **Modify `app/api/routes.py`** — add `GET /api/setups/schema` that reads module-level `SETUP_FIELD_SCHEMA` + `SETUP_FIELD_META` and serializes (no store dependency).
- **Modify `tests/test_setups.py`** — fix the one tire_pressure assertion; add 8 new cases (schema shape, schema round-trip, unit round-trip, file-adapts, default+backward-compat, invalid unit, non-convertible pass-through, existing cases still pass).
- **Create `frontend/common.js`** — `$`, `fetchJSON`, `bus` (event bus for `setup:change` + `view:change`).
- **Create `frontend/setups.js`** — Setups view: list, editor, 9 sections, attach, unit toggle, hash routing.
- **Modify `frontend/index.html`** — add topbar tabs (Live/Setups) + current-setup chip; add Setups view container; add `<script src="/static/common.js">` before `app.js`; add `<script src="/static/setups.js">` after `app.js`.
- **Modify `frontend/styles.css`** — append styles for topbar tabs, current-setup chip, Setups view (list/editor panes, 9-segment strip, section cards, unit toggle, action buttons); narrow-screen single-pane swap.
- **Modify `frontend/app.js`** — render the current-setup chip in the topbar by reading from the bus.
- **No changes to `app/main.py`** (lifespan already wires `SetupStore` from item 3).
- **No changes to `app/config.py`** (no new env vars).

---

### Task 1: Fix tire_pressure schema (per-axle) and add SETUP_FIELD_META

**Files:**
- Modify: `app/store/setups.py:218-234` (replace `SETUP_FIELD_SCHEMA`)
- Append: `app/store/setups.py` (new `SETUP_FIELD_META` constant + `_convert_units` helper)
- Modify: `tests/test_setups.py` (one existing assertion for `tire_pressure` field names)

**Interfaces:**
- Produces: corrected `SETUP_FIELD_SCHEMA` with `tire_pressure: ["front", "rear"]`; new `SETUP_FIELD_META: dict[tuple[str,str], dict]` keyed by `(section, field)` with `{label, group, unit, unit_metric, unit_english, conversion}` per entry; new `_convert_units(fields: dict, old: str, new: str) -> dict` (no-op when `old == new`).

- [ ] **Step 1: Update the one failing test assertion**

In `tests/test_setups.py`, find and update the `test_normalize_drops_unknown_sections_and_fields` test so it uses per-axle keys:

```python
def test_normalize_drops_unknown_sections_and_fields() -> None:
    out = _normalize_fields({
        "tire_pressure": {"front": 30, "bogus": 99},
        "not_a_section": {"x": 1},
    })
    assert out == {"tire_pressure": {"front": 30}}
    assert "not_a_section" not in out
    assert "bogus" not in out["tire_pressure"]
```

Also update `test_normalize_coerces_numeric_strings_to_float`:

```python
def test_normalize_coerces_numeric_strings_to_float() -> None:
    out = _normalize_fields({"tire_pressure": {"front": "32", "rear": "30.5"}})
    assert out == {"tire_pressure": {"front": 32.0, "rear": 30.5}}
    assert isinstance(out["tire_pressure"]["front"], float)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — the test expects `{"front": 30}` but the schema (still per-wheel) drops `front` as unknown.

- [ ] **Step 3: Fix the schema and add SETUP_FIELD_META + _convert_units**

In `app/store/setups.py`, replace the `SETUP_FIELD_SCHEMA` block (lines 218-234) with the corrected schema and add `SETUP_FIELD_META` + `_convert_units` right after it:

```python
# The 9 FH6 tuning sections and their canonical field names — single source of
# truth that the item 4 editor UI will also read. Verified against FH6-specific
# guides (see docs/superpowers/specs/2026-07-05-setup-editor-design.md).
# Per FH6: camber/toe/spring-rate/ride-height/rebound/bump are per-axle
# (front/rear), not per-wheel; tire pressure is per-AXLE (2 sliders), not
# per-wheel; caster is single; damping uses "bump" (the FH6 slider label), not
# "compression"; brake tuning is bias+pressure (pad/rotor are upgrade parts,
# not sliders); diff has accel/decel lock per axle + a single center_balance
# for AWD, no preload.
SETUP_FIELD_SCHEMA: dict[str, list[str]] = {
    "tire_pressure":   ["front", "rear"],                  # PSI/bar, per-axle
    "gearing":         ["final_drive", "gears"],
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

# Per-field presentation metadata, keyed by (section, field). `group` is one of
# "per_axle" (Front|Rear pair in the UI), "single" (one input), or "list"
# (variable-length gears array). `unit` is the canonical unit for display;
# `unit_metric` / `unit_english` are the labels shown in the toggle;
# `conversion` is the multiplier applied to an English value to get the
# metric value (None for non-convertible fields like degrees, ratios, %).
# This is the single source of truth for both the schema endpoint and the
# server-side unit converter; the frontend never invents factors.
SETUP_FIELD_META: dict[tuple[str, str], dict] = {
    # tire pressure — PSI <-> bar
    ("tire_pressure", "front"): {
        "label": "Front", "group": "per_axle",
        "unit": "psi", "unit_metric": "bar", "unit_english": "psi",
        "conversion": 0.0689476,
    },
    ("tire_pressure", "rear"): {
        "label": "Rear", "group": "per_axle",
        "unit": "psi", "unit_metric": "bar", "unit_english": "psi",
        "conversion": 0.0689476,
    },
    # gearing — ratios, no conversion
    ("gearing", "final_drive"): {
        "label": "Final drive", "group": "single",
        "unit": "ratio", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("gearing", "gears"): {
        "label": "Gears", "group": "list",
        "unit": "ratio", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # alignment — degrees, no conversion
    ("alignment", "camber_front"): {
        "label": "Camber front", "group": "per_axle",
        "unit": "deg", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("alignment", "camber_rear"): {
        "label": "Camber rear", "group": "per_axle",
        "unit": "deg", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("alignment", "toe_front"): {
        "label": "Toe front", "group": "per_axle",
        "unit": "deg", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("alignment", "toe_rear"): {
        "label": "Toe rear", "group": "per_axle",
        "unit": "deg", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("alignment", "caster"): {
        "label": "Caster", "group": "single",
        "unit": "deg", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # anti-roll bars — unitless stiffness
    ("anti_roll_bars", "front"): {
        "label": "Front", "group": "per_axle",
        "unit": "stiffness", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("anti_roll_bars", "rear"): {
        "label": "Rear", "group": "per_axle",
        "unit": "stiffness", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # springs — spring rate lb/in <-> kgf/mm; ride height in <-> cm
    ("springs", "spring_rate_front"): {
        "label": "Spring rate front", "group": "per_axle",
        "unit": "lb/in", "unit_metric": "kgf/mm", "unit_english": "lb/in",
        "conversion": 0.017857,
    },
    ("springs", "spring_rate_rear"): {
        "label": "Spring rate rear", "group": "per_axle",
        "unit": "lb/in", "unit_metric": "kgf/mm", "unit_english": "lb/in",
        "conversion": 0.017857,
    },
    ("springs", "ride_height_front"): {
        "label": "Ride height front", "group": "per_axle",
        "unit": "in", "unit_metric": "cm", "unit_english": "in",
        "conversion": 2.54,
    },
    ("springs", "ride_height_rear"): {
        "label": "Ride height rear", "group": "per_axle",
        "unit": "in", "unit_metric": "cm", "unit_english": "in",
        "conversion": 2.54,
    },
    # damping — unitless
    ("damping", "rebound_front"): {
        "label": "Rebound front", "group": "per_axle",
        "unit": "rebound", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("damping", "rebound_rear"): {
        "label": "Rebound rear", "group": "per_axle",
        "unit": "rebound", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("damping", "bump_front"): {
        "label": "Bump front", "group": "per_axle",
        "unit": "bump", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("damping", "bump_rear"): {
        "label": "Bump rear", "group": "per_axle",
        "unit": "bump", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # aero — downforce level
    ("aero", "front_downforce"): {
        "label": "Front downforce", "group": "per_axle",
        "unit": "downforce", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("aero", "rear_downforce"): {
        "label": "Rear downforce", "group": "per_axle",
        "unit": "downforce", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # brake — bias % and pressure %
    ("brake", "bias"): {
        "label": "Brake bias", "group": "single",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("brake", "pressure"): {
        "label": "Brake pressure", "group": "single",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    # differential — accel/decel lock % per axle; center_balance %
    ("differential", "accel_lock_front"): {
        "label": "Accel lock front", "group": "per_axle",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("differential", "accel_lock_rear"): {
        "label": "Accel lock rear", "group": "per_axle",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("differential", "decel_lock_front"): {
        "label": "Decel lock front", "group": "per_axle",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("differential", "decel_lock_rear"): {
        "label": "Decel lock rear", "group": "per_axle",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
    ("differential", "center_balance"): {
        "label": "Center balance (AWD)", "group": "single",
        "unit": "%", "unit_metric": None, "unit_english": None,
        "conversion": None,
    },
}


def _convert_units(fields: dict, old: str, new: str) -> dict:
    """Convert the three convertible field families between english and metric.

    `fields` is a (normalized) sections-dict. Returns a NEW dict; the input
    is not mutated. Non-convertible fields (degrees, ratios, %) pass through
    unchanged. A no-op when old == new.
    """
    if old == new or not isinstance(fields, dict):
        return dict(fields) if isinstance(fields, dict) else {}

    def _conv(section: str, field: str, value):
        meta = SETUP_FIELD_META.get((section, field))
        if meta is None or meta["conversion"] is None:
            return value
        if old == "english" and new == "metric":
            return value * meta["conversion"]
        if old == "metric" and new == "english":
            return value / meta["conversion"]
        return value

    out: dict = {}
    for section, section_in in fields.items():
        if not isinstance(section_in, dict):
            continue
        out[section] = {
            fn: _conv(section, fn, v) for fn, v in section_in.items()
        }
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS (the existing 2 updated assertions now pass; nothing else changed yet).

- [ ] **Step 5: Commit**

```bash
git add app/store/setups.py tests/test_setups.py
git commit -m "fix(setups): tire_pressure per-axle + add SETUP_FIELD_META + _convert_units"
```

---

### Task 2: `Setup.units` field + per-setup unit storage + conversion in `SetupStore`

**Files:**
- Modify: `app/store/setups.py` (`Setup` dataclass, `_SETUP_KEYS`, `SetupStore.create`/`update`)
- Modify: `tests/test_setups.py` (add 5 new cases + update `__main__` block)

**Interfaces:**
- Produces: `Setup.units: str = "english"`; `_SETUP_KEYS` includes `"units"`; `SetupStore.create` accepts `units` (defaults + invalid → `"english"`); `SetupStore.update` triggers `_convert_units(merged_fields, stored_units, new_units)` when `units` changes.
- Consumes: `_convert_units` from Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_setups.py` (before the `if __name__ == "__main__":` block):

```python
# ---- 9. Setup.units field + SetupStore unit conversion ---------------------

_VALID_UNITS = ("english", "metric")


def test_create_default_units_is_english(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x"})
    assert created["units"] == "english"


def test_create_explicit_units_metric(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "metric"})
    assert created["units"] == "metric"


def test_create_invalid_units_defaults_to_english(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "klingon"})
    assert created["units"] == "english"


def test_get_backward_compat_no_units_field(tmp_path) -> None:
    """A hand-written item-3 file with no `units` reads back as english."""
    sid = "a3f1b2c4d5e6f7089a1b2c3d4e5f6071"
    (tmp_path / f"{sid}.json").write_text(json.dumps({
        "id": sid, "name": "old", "car": "", "track": "",
        "fields": {}, "notes": "",
        "created_at": 1000.0, "updated_at": 1000.0,
    }))
    store = SetupStore(tmp_path)
    got = store.get(sid)
    assert got is not None
    assert got["units"] == "english"


def test_update_units_change_converts_fields(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "english", "fields": {
        "tire_pressure": {"front": 32.0, "rear": 30.0},
        "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
        "alignment": {"camber_front": -1.5},
        "brake": {"bias": 55.0},
        "differential": {"center_balance": 50.0},
        "gearing": {"final_drive": 3.2, "gears": [3.5, 2.1, 1.0]},
    }})
    updated = store.update(created["id"], {
        "units": "metric",
        # fields sent are interpreted as being in the OLD (english) unit,
        # which is what the editor will do; mirror them here.
        "fields": {
            "tire_pressure": {"front": 32.0, "rear": 30.0},
            "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
            "alignment": {"camber_front": -1.5},
            "brake": {"bias": 55.0},
            "differential": {"center_balance": 50.0},
            "gearing": {"final_drive": 3.2, "gears": [3.5, 2.1, 1.0]},
        },
    })
    assert updated is not None
    assert updated["units"] == "metric"
    f = updated["fields"]
    # tire pressure: 32 PSI -> 2.21 bar; 30 PSI -> 2.07 bar
    assert abs(f["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
    assert abs(f["tire_pressure"]["rear"] - 30.0 * 0.0689476) < 0.01
    # spring rate: 500 lb/in -> 8.93 kgf/mm
    assert abs(f["springs"]["spring_rate_front"] - 500.0 * 0.017857) < 0.01
    # ride height: 5 in -> 12.7 cm
    assert abs(f["springs"]["ride_height_front"] - 5.0 * 2.54) < 0.01
    # non-convertible fields unchanged
    assert f["alignment"]["camber_front"] == -1.5
    assert f["brake"]["bias"] == 55.0
    assert f["differential"]["center_balance"] == 50.0
    assert f["gearing"]["final_drive"] == 3.2
    assert f["gearing"]["gears"] == [3.5, 2.1, 1.0]


def test_update_units_round_trip_within_tolerance(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "english", "fields": {
        "tire_pressure": {"front": 32.0},
        "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
    }})
    sid = created["id"]
    # english -> metric
    m = store.update(sid, {"units": "metric", "fields": {
        "tire_pressure": {"front": 32.0},
        "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
    }})
    assert m["units"] == "metric"
    # metric -> english (using the metric values as the new "current")
    e = store.update(sid, {"units": "english", "fields": {
        "tire_pressure": {"front": m["fields"]["tire_pressure"]["front"]},
        "springs": {"spring_rate_front": m["fields"]["springs"]["spring_rate_front"],
                    "ride_height_front": m["fields"]["springs"]["ride_height_front"]},
    }})
    assert e["units"] == "english"
    assert abs(e["fields"]["tire_pressure"]["front"] - 32.0) < 0.01
    assert abs(e["fields"]["springs"]["spring_rate_front"] - 500.0) < 0.01
    assert abs(e["fields"]["springs"]["ride_height_front"] - 5.0) < 0.01


def test_update_units_no_change_is_noop(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "english", "fields": {
        "tire_pressure": {"front": 32.0},
    }})
    updated = store.update(created["id"], {
        "units": "english",
        "fields": {"tire_pressure": {"front": 33.5}},  # just a regular edit
    })
    assert updated["fields"]["tire_pressure"]["front"] == 33.5  # plain overwrite


def test_file_adapts_on_disk_after_unit_change(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "units": "english", "fields": {
        "tire_pressure": {"front": 32.0},
    }})
    store.update(created["id"], {"units": "metric", "fields": {
        "tire_pressure": {"front": 32.0},
    }})
    raw = json.loads((tmp_path / f"{created['id']}.json").read_text())
    assert raw["units"] == "metric"
    assert abs(raw["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
```

Update the `__main__` block to print `"setup editor tests passed"` instead of `"setup data model tests passed"`:

```python
if __name__ == "__main__":
    _run_all = [v for k, v in sorted(globals().items())
                if k.startswith("test_") and callable(v)]
    for fn in _run_all:
        # tmp_path tests need a temp dir; make one per call
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(Path(d))
                continue
            except TypeError:
                pass
            fn()
    print("setup editor tests passed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — `Setup` has no `units` field; tests that read `created["units"]` raise `KeyError`.

- [ ] **Step 3: Update `Setup`, `_SETUP_KEYS`, `SetupStore.create` and `update`**

In `app/store/setups.py`:

1. Update `_SETUP_KEYS`:

```python
# Keys kept when re-reading a setup file (guards against hand-edited extras).
_SETUP_KEYS = ("id", "name", "car", "track", "fields", "notes",
               "units", "created_at", "updated_at")

_VALID_UNITS = ("english", "metric")


def _normalize_units(u) -> str:
    """Default invalid/missing unit values to 'english' (permissive)."""
    if isinstance(u, str) and u in _VALID_UNITS:
        return u
    return "english"
```

2. Update the `Setup` dataclass — add `units: str = "english"` after `notes`:

```python
@dataclass
class Setup:
    """One car tuning sheet. `fields` is a subset of SETUP_FIELD_SCHEMA."""

    id: str
    name: str
    car: str = ""
    track: str = ""
    fields: dict = field(default_factory=dict)
    notes: str = ""
    units: str = "english"
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)
```

3. Update `SetupStore.get` to default `units` to `"english"` when missing (backward compat for item-3 files):

```python
    def get(self, setup_id: str) -> Optional[dict]:
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        result = {k: data[k] for k in _SETUP_KEYS if k in data}
        result.setdefault("units", "english")
        return result
```

4. Update `SetupStore.create` — accept `units`:

```python
    def create(self, data: dict) -> dict:
        """Create a new setup. Raises ValueError if `name` is missing/blank."""
        name = data.get("name")
        if not name or not str(name).strip():
            raise ValueError("setup 'name' is required")
        now = time.time()
        setup = Setup(
            id=uuid.uuid4().hex,
            name=str(name).strip(),
            car=str(data.get("car", "")).strip(),
            track=str(data.get("track", "")).strip(),
            fields=_normalize_fields(data.get("fields") or {}),
            notes=str(data.get("notes", "")),
            units=_normalize_units(data.get("units")),
            created_at=now,
            updated_at=now,
        )
        self._write(setup)
        return setup.as_dict()
```

5. Update `SetupStore.update` — accept `units` and convert fields when it changes:

```python
    def update(self, setup_id: str, data: dict) -> Optional[dict]:
        """Update an existing setup. None if not found / invalid id.
        Raises ValueError if a provided name is blank.

        If `units` is supplied and differs from the stored unit, the merged
        fields are converted from the old unit to the new unit before save.
        Fields supplied in `data["fields"]` are interpreted as being in the
        OLD (stored) unit — this is the contract the editor uses, so the
        converted values returned reflect the user's last-typed state.
        """
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        merged = {k: existing[k] for k in _SETUP_KEYS if k in existing}
        merged.setdefault("units", "english")
        if "name" in data:
            merged["name"] = str(data["name"]).strip()
        if "car" in data:
            merged["car"] = str(data["car"]).strip()
        if "track" in data:
            merged["track"] = str(data["track"]).strip()
        if "notes" in data:
            merged["notes"] = str(data["notes"])
        if "fields" in data:
            merged["fields"] = _normalize_fields(data["fields"])
        if not str(merged.get("name", "")).strip():
            raise ValueError("setup 'name' cannot be empty")
        # unit conversion
        old_units = merged["units"]
        new_units = _normalize_units(data["units"]) if "units" in data else old_units
        if new_units != old_units:
            merged["fields"] = _convert_units(merged["fields"], old_units, new_units)
        merged["units"] = new_units
        merged["id"] = existing.get("id", setup_id)
        merged["created_at"] = existing.get("created_at", 0.0)
        merged["updated_at"] = time.time()
        setup = Setup(**{k: merged[k] for k in _SETUP_KEYS})
        self._write(setup)
        return setup.as_dict()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS. Also run standalone: `conda run -n fh6tuning python tests/test_setups.py` → prints `setup editor tests passed`.

- [ ] **Step 5: Commit**

```bash
git add app/store/setups.py tests/test_setups.py
git commit -m "feat(setups): Setup.units field + per-setup unit storage + server-side conversion"
```

---

### Task 3: `GET /api/setups/schema` endpoint

**Files:**
- Modify: `app/api/routes.py` (append schema route)
- Modify: `tests/test_setups.py` (add 2 schema endpoint tests)

**Interfaces:**
- Produces: `GET /api/setups/schema` returns a `dict` with `{"sections": [{key, label, fields: [{key, label, group, unit, unit_metric, unit_english, conversion}, ...]}, ...]}` for the 9 sections in schema order. Reads `SETUP_FIELD_SCHEMA` + `SETUP_FIELD_META` from `app.store.setups`; does NOT touch `router.state["setups"]`, so it returns 200 even when the store is not initialized.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_setups.py`:

```python
# ---- 10. /api/setups/schema endpoint ---------------------------------------

def test_api_schema_shape() -> None:
    from app.api.routes import setups_schema
    out = asyncio.run(setups_schema())
    assert isinstance(out, dict)
    assert "sections" in out
    sections = out["sections"]
    # 9 sections in schema order
    assert [s["key"] for s in sections] == [
        "tire_pressure", "gearing", "alignment", "anti_roll_bars",
        "springs", "damping", "aero", "brake", "differential",
    ]
    # per-section slider counts: 2/2/5/2/4/4/2/2/5
    assert [len(s["fields"]) for s in sections] == [2, 2, 5, 2, 4, 4, 2, 2, 5]
    # tire_pressure fields are front/rear
    tp = sections[0]
    assert [f["key"] for f in tp["fields"]] == ["front", "rear"]
    # every field has the metadata keys
    for s in sections:
        for f in s["fields"]:
            assert {"key", "label", "group", "unit",
                    "unit_metric", "unit_english", "conversion"} <= set(f)
            assert f["group"] in ("per_axle", "single", "list")
    # convertible fields have non-null conversion + unit labels
    front = tp["fields"][0]
    assert front["conversion"] == 0.0689476
    assert front["unit_metric"] == "bar"
    assert front["unit_english"] == "psi"
    # non-convertible fields have nulls
    align_caster = sections[2]["fields"][4]
    assert align_caster["key"] == "caster"
    assert align_caster["conversion"] is None
    assert align_caster["unit_metric"] is None
    assert align_caster["unit_english"] is None
    # gearing.gears is a list group
    gears = sections[1]["fields"][1]
    assert gears["key"] == "gears"
    assert gears["group"] == "list"


def test_api_schema_works_without_store() -> None:
    """The schema endpoint reads module constants; no store dependency."""
    from app.api import routes
    routes.router.state = {}  # no setups key
    from app.api.routes import setups_schema
    out = asyncio.run(setups_schema())
    assert len(out["sections"]) == 9
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — `ImportError: cannot import name 'setups_schema' from 'app.api.routes'`.

- [ ] **Step 3: Implement the schema endpoint**

In `app/api/routes.py`, add a new import at the top (alongside the existing `from ..store.setups import is_valid_setup_id`):

```python
from ..store.setups import (
    SETUP_FIELD_SCHEMA, SETUP_FIELD_META, is_valid_setup_id,
)
```

Then append at the end of `app/api/routes.py`:

```python
# ---- setup schema ----------------------------------------------------------
# ROADMAP item 4: the Setups editor fetches the 9-section field schema
# (label, group, unit, conversion) once on load and renders the form
# dynamically. Reads module-level constants — no store dependency, works
# even before SetupStore is initialized (no 503 path).

@router.get("/api/setups/schema")
async def setups_schema() -> dict:
    sections: list[dict] = []
    for section_key, field_keys in SETUP_FIELD_SCHEMA.items():
        fields: list[dict] = []
        for fk in field_keys:
            meta = SETUP_FIELD_META[(section_key, fk)]
            fields.append({"key": fk, **meta})
        # human-friendly section label = section_key with underscores -> spaces, titlecased
        label = section_key.replace("_", " ").title()
        sections.append({"key": section_key, "label": label, "fields": fields})
    return {"sections": sections}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_setups.py
git commit -m "feat(setups): GET /api/setups/schema endpoint"
```

---

### Task 4: `frontend/common.js` — helpers + event bus

**Files:**
- Create: `frontend/common.js`

**Interfaces:**
- Produces: `window.$ = (id) => HTMLElement` (alias of `document.getElementById`); `window.fetchJSON = async (url, opts?) => any` (fetch + JSON parse, throws on non-2xx with the response body as message); `window.bus` (tiny pub/sub: `on(evt, fn) -> unsubscribe`, `emit(evt, payload)`) for events `setup:change` (payload: setup dict or null) and `view:change` (payload: `"live" | "setups"`).

- [ ] **Step 1: Write the file**

Create `frontend/common.js`:

```javascript
// horizon6tuning shared client helpers + tiny event bus.
// Loaded by every page; exposes window.$, window.fetchJSON, window.bus.
"use strict";

(function () {
  window.$ = (id) => document.getElementById(id);

  window.fetchJSON = async function (url, opts) {
    const r = await fetch(url, opts);
    const text = await r.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = { detail: text }; }
    }
    if (!r.ok) {
      const msg = (data && (data.detail || data.error)) || `HTTP ${r.status}`;
      const err = new Error(msg);
      err.status = r.status;
      err.data = data;
      throw err;
    }
    return data;
  };

  // tiny pub/sub for cross-view state (current setup, active view)
  const subs = new Map();
  window.bus = {
    on(evt, fn) {
      if (!subs.has(evt)) subs.set(evt, new Set());
      subs.get(evt).add(fn);
      return () => subs.get(evt).delete(fn);
    },
    emit(evt, payload) {
      const set = subs.get(evt);
      if (set) for (const fn of set) { try { fn(payload); } catch (e) { console.warn(e); } }
    },
  };
})();
```

- [ ] **Step 2: Manually verify it loads**

Open `frontend/index.html` in your head (or just inspect syntax). No runtime test harness exists; this is verified when the app loads in the browser. Commit and move on; manual verification in Task 9 covers runtime.

- [ ] **Step 3: Commit**

```bash
git add frontend/common.js
git commit -m "feat(frontend): common.js — $, fetchJSON, bus"
```

---

### Task 5: `frontend/index.html` — topbar tabs + chip + Setups view container

**Files:**
- Modify: `frontend/index.html` (topbar, add Setups view, script order)

**Interfaces:**
- Produces: topbar view tabs (Live/Setups) with `role="tab"`; current-setup chip placeholder; a `<main id="setupsView" hidden>` container holding list pane + editor pane placeholders; 3 `<script>` tags in order: `common.js`, `app.js`, `setups.js`. Live `main.grid` becomes `<main id="liveView">` (kept) so JS can hide/show.

- [ ] **Step 1: Modify `frontend/index.html`**

Make the following edits in `frontend/index.html`:

1. Change the existing `<main class="grid">` to add an id, and close it. Replace the line:

```html
  <main class="grid">
```

with:

```html
  <main id="liveView" class="grid">
```

2. Just before `</main>` (end of the live grid), insert the Setups view container. Find the end of the live `</main>` and after it add:

```html
  <main id="setupsView" class="setups-view" hidden>
    <aside class="setups-list">
      <div class="setups-list-head">
        <h2>My setups</h2>
        <button id="setupsNew" class="btn primary" type="button">+ New setup</button>
      </div>
      <ul id="setupsList" class="setups-list-items" aria-label="Saved setups"></ul>
      <p id="setupsEmpty" class="setups-empty" hidden>
        No setups yet — create your first tuning sheet.
      </p>
    </aside>
    <section class="setups-editor" id="setupsEditor" hidden>
      <header class="setups-editor-head">
        <h2 id="setupsEditorTitle">New setup</h2>
        <div class="setups-editor-actions">
          <span id="setupsDirty" class="dirty-dot" hidden>● Unsaved changes</span>
          <button id="setupsCancel" class="btn" type="button">Cancel</button>
          <button id="setupsSave" class="btn primary" type="button" disabled>Save changes</button>
        </div>
      </header>
      <div class="setups-meta">
        <label>Name <input id="setupName" type="text" required maxlength="80" /></label>
        <label>Car <input id="setupCar" type="text" maxlength="80" /></label>
        <label>Track <input id="setupTrack" type="text" maxlength="80" /></label>
        <div class="units-toggle" role="group" aria-label="Units">
          <button type="button" data-units="metric">Metric</button>
          <button type="button" data-units="english">English</button>
        </div>
      </div>
      <div class="setups-strip" id="setupsStrip" aria-label="Section completeness"></div>
      <div class="setups-sections" id="setupsSections"></div>
      <label class="setups-notes">
        <span>Notes</span>
        <textarea id="setupNotes" rows="3" maxlength="2000"></textarea>
      </label>
    </section>
  </main>
```

3. In the topbar, before the existing `<div class="status">`, insert the view tabs and current-setup chip. Find this block:

```html
    <div class="topbar-right">
      <div class="status">
```

and replace with:

```html
    <div class="topbar-right">
      <div class="view-tabs" role="tablist" aria-label="Dashboard view">
        <button id="tabLive" role="tab" aria-selected="true" type="button">Live</button>
        <button id="tabSetups" role="tab" aria-selected="false" type="button">Setups</button>
      </div>
      <button id="currentSetupChip" class="current-setup-chip" type="button"
              title="Click to manage setups">
        <span class="caret">▸</span>
        <span id="currentSetupName">no setup attached</span>
      </button>
      <div class="status">
```

4. Update the script tag at the end. Find:

```html
  <script src="/static/app.js"></script>
</body>
</html>
```

and replace with:

```html
  <script src="/static/common.js"></script>
  <script src="/static/app.js"></script>
  <script src="/static/setups.js"></script>
</body>
</html>
```

- [ ] **Step 2: Verify the HTML parses**

Open the file in a browser. The topbar should now show two tabs and a chip; the live view should be visible; the setups view container should be `hidden`. If anything looks off, fix the markup before committing.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): topbar tabs + current-setup chip + Setups view container"
```

---

### Task 6: `frontend/styles.css` — Setups view + topbar tabs/chip + strip styles

**Files:**
- Modify: `frontend/styles.css` (append new sections; do not touch existing rules)

**Interfaces:**
- Produces: styles for `.view-tabs`, `.current-setup-chip`, `.setups-view` (2-pane + ≤980px single-pane), `.setups-list`/`.setups-list-items`/`.setups-empty`, `.setups-editor`/`.setups-editor-head`/`.setups-meta`/`.units-toggle`, `.setups-strip` (9 clickable segments), `.setups-sections` (`<details>`-based cards), `.dirty-dot`, `.btn`/`.btn.primary`. Extends existing tokens; no new colors or fonts.

- [ ] **Step 1: Append the new styles**

Append to `frontend/styles.css`:

```css
/* ---- topbar view tabs (ROADMAP item 4) ---- */
.view-tabs{
  display:flex;gap:2px;background:#0a0d12;border:1px solid var(--line);
  border-radius:8px;padding:3px;
}
.view-tabs button{
  background:transparent;border:0;color:var(--muted);
  font:600 12px/1 system-ui,-apple-system,Segoe UI,Roboto,Inter,sans-serif;
  letter-spacing:.4px;padding:6px 12px;border-radius:6px;cursor:pointer;
  transition:color .15s,background .15s;
}
.view-tabs button:hover{color:var(--text)}
.view-tabs button[aria-selected="true"]{
  color:var(--accent);background:rgba(255,59,48,.10);
}

/* ---- current-setup chip (topbar) ---- */
.current-setup-chip{
  display:flex;align-items:center;gap:6px;
  background:#0a0d12;border:1px solid var(--line);border-radius:8px;
  color:var(--muted);font:600 12px/1 system-ui,sans-serif;letter-spacing:.3px;
  padding:7px 10px;cursor:pointer;max-width:220px;
  transition:color .15s,border-color .15s;
}
.current-setup-chip:hover{color:var(--text);border-color:#2f3a4d}
.current-setup-chip.has-setup{color:var(--accent-2);border-color:rgba(255,176,0,.4)}
.current-setup-chip .caret{color:var(--accent-2);font-size:11px}
.current-setup-chip #currentSetupName{
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:180px;
}

/* ---- Setups view (2-pane list + editor) ---- */
.setups-view{
  display:grid;gap:16px;padding:16px;
  grid-template-columns:340px 1fr;
  max-width:1400px;margin:0 auto;
}
@media(max-width:980px){
  .setups-view{grid-template-columns:1fr}
  .setups-view .setups-list{order:1}
  .setups-view .setups-editor{order:2}
}

/* ---- list pane ---- */
.setups-list{
  background:linear-gradient(180deg,var(--panel),var(--panel-2));
  border:1px solid var(--line);border-radius:var(--radius);padding:14px;
  max-height:calc(100vh - 100px);overflow-y:auto;
}
.setups-list-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
.setups-list-head h2{margin:0;font-size:14px;letter-spacing:.4px}
.setups-list-items{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:6px}
.setups-list-items li{
  background:#0a0d12;border:1px solid var(--line);border-radius:8px;
  padding:10px;cursor:pointer;display:flex;flex-direction:column;gap:2px;
  transition:border-color .15s,background .15s;position:relative;
}
.setups-list-items li:hover{border-color:#2f3a4d}
.setups-list-items li.current{
  border-color:rgba(255,59,48,.5);box-shadow:0 0 10px rgba(255,59,48,.12);
}
.setups-list-items .row-name{font-weight:600}
.setups-list-items .row-meta{font-size:11px;color:var(--muted)}
.setups-list-items .row-actions{
  position:absolute;top:8px;right:8px;display:flex;gap:4px;opacity:0;
  transition:opacity .15s;
}
.setups-list-items li:hover .row-actions{opacity:1}
.setups-list-items .badge{
  position:absolute;top:8px;right:8px;
  background:var(--accent);color:#fff;font-size:10px;font-weight:700;
  letter-spacing:.5px;padding:2px 6px;border-radius:4px;
}
.setups-list-items li.current .row-actions{opacity:1;right:54px}
.setups-list-items .row-actions button{
  background:#11151c;border:1px solid var(--line);color:var(--text);
  font:600 10px/1 system-ui,sans-serif;letter-spacing:.4px;padding:4px 6px;
  border-radius:4px;cursor:pointer;
}
.setups-list-items .row-actions button:hover{border-color:var(--accent);color:var(--accent)}
.setups-empty{color:var(--muted);text-align:center;padding:24px 8px;margin:0}

/* ---- editor pane ---- */
.setups-editor{
  background:linear-gradient(180deg,var(--panel),var(--panel-2));
  border:1px solid var(--line);border-radius:var(--radius);padding:18px;
  display:flex;flex-direction:column;gap:14px;
}
.setups-editor-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
.setups-editor-head h2{margin:0;font-size:16px;letter-spacing:.4px}
.setups-editor-actions{display:flex;align-items:center;gap:10px}
.dirty-dot{color:var(--accent-2);font-size:12px;font-weight:600}

/* ---- buttons ---- */
.btn{
  background:#0a0d12;border:1px solid var(--line);color:var(--text);
  font:600 12px/1 system-ui,sans-serif;letter-spacing:.4px;padding:8px 14px;
  border-radius:8px;cursor:pointer;transition:color .15s,border-color .15s;
}
.btn:hover{border-color:#2f3a4d}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{box-shadow:0 0 14px rgba(255,59,48,.4)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.btn.danger{border-color:rgba(255,59,48,.4);color:var(--accent)}

/* ---- meta inputs (name/car/track/units) ---- */
.setups-meta{
  display:grid;grid-template-columns:2fr 1fr 1fr auto;gap:10px;align-items:end;
}
@media(max-width:980px){.setups-meta{grid-template-columns:1fr 1fr}}
.setups-meta label{display:flex;flex-direction:column;gap:4px;font-size:11px;color:var(--muted);letter-spacing:.4px;text-transform:uppercase}
.setups-meta input{
  background:#0a0d12;border:1px solid var(--line);color:var(--text);
  border-radius:6px;padding:7px 10px;font:14px var(--mono);
}
.setups-meta input:focus{outline:2px solid var(--accent-2);outline-offset:1px}
.units-toggle{
  display:flex;gap:2px;background:#0a0d12;border:1px solid var(--line);
  border-radius:8px;padding:3px;height:fit-content;
}
.units-toggle button{
  background:transparent;border:0;color:var(--muted);
  font:600 12px/1 system-ui,sans-serif;letter-spacing:.4px;
  padding:6px 10px;border-radius:6px;cursor:pointer;
}
.units-toggle button[aria-pressed="true"]{
  color:var(--accent);background:rgba(255,59,48,.10);
}
.setups-meta .units-toggle{align-self:end;margin-bottom:1px}

/* ---- 9-segment completeness strip ---- */
.setups-strip{
  display:grid;grid-template-columns:repeat(9,1fr);gap:4px;
  padding:4px 0 2px;
}
.setups-strip button{
  background:#1a2230;border:1px solid var(--line);border-radius:4px;
  height:18px;cursor:pointer;padding:0;transition:background .15s,border-color .15s;
}
.setups-strip button.filled{background:var(--accent);border-color:var(--accent)}
.setups-strip button:hover{border-color:#2f3a4d}
.setups-strip button.filled:hover{filter:brightness(1.15)}
.setups-strip button .seg-label{
  position:absolute;margin-top:22px;font-size:10px;color:var(--muted);
}

/* ---- section cards (9 collapsible <details>) ---- */
.setups-sections{display:flex;flex-direction:column;gap:8px}
.section-card{
  background:#0a0d12;border:1px solid var(--line);border-radius:8px;
  overflow:hidden;
}
.section-card > summary{
  list-style:none;cursor:pointer;padding:10px 14px;
  display:flex;align-items:center;justify-content:space-between;
  font-weight:600;font-size:13px;letter-spacing:.3px;
}
.section-card > summary::-webkit-details-marker{display:none}
.section-card > summary .chev{color:var(--muted);transition:transform .15s;font-size:11px}
.section-card[open] > summary .chev{transform:rotate(90deg)}
.section-card .fill-count{font-family:var(--mono);font-size:11px;color:var(--muted);font-weight:400;margin-left:8px}
.section-card .fill-count.full{color:var(--good)}
.section-card .body{padding:6px 14px 14px;display:flex;flex-direction:column;gap:10px}

/* ---- field row layouts ---- */
.field-row{display:grid;gap:10px}
.field-row.two{grid-template-columns:1fr 1fr}
.field-row.three{grid-template-columns:1fr 1fr 1fr}
.field-row.four{grid-template-columns:1fr 1fr 1fr 1fr}
@media(max-width:980px){
  .field-row.four{grid-template-columns:1fr 1fr}
  .field-row.three{grid-template-columns:1fr 1fr}
}
.field{
  display:flex;flex-direction:column;gap:4px;
}
.field > label{font-size:11px;color:var(--muted);letter-spacing:.4px;text-transform:uppercase}
.field-input-wrap{display:flex;align-items:center;gap:6px;background:#0a0d12;border:1px solid var(--line);border-radius:6px;padding:6px 8px}
.field-input-wrap input{
  background:transparent;border:0;color:var(--text);outline:none;width:100%;
  font:14px var(--mono);
}
.field-unit{font-size:11px;color:var(--muted);font-family:var(--mono);white-space:nowrap}
.field-input-wrap:focus-within{outline:2px solid var(--accent-2);outline-offset:1px}

/* ---- list group (gears) ---- */
.gears-list{display:flex;flex-direction:column;gap:6px}
.gears-row{display:grid;grid-template-columns:60px 1fr 28px;gap:8px;align-items:center}
.gears-row .gear-label{font-family:var(--mono);font-size:12px;color:var(--muted);text-align:right}
.gears-row .gear-remove{
  background:transparent;border:1px solid var(--line);color:var(--muted);
  border-radius:6px;cursor:pointer;height:28px;width:28px;line-height:0;font-size:14px;
}
.gears-row .gear-remove:hover{color:var(--accent);border-color:var(--accent)}
.gears-add{
  background:transparent;border:1px dashed var(--line);color:var(--muted);
  border-radius:6px;padding:6px 10px;cursor:pointer;font:600 11px/1 system-ui,sans-serif;
  letter-spacing:.4px;align-self:flex-start;
}
.gears-add:hover{color:var(--accent-2);border-color:var(--accent-2)}

/* ---- notes ---- */
.setups-notes{display:flex;flex-direction:column;gap:4px}
.setups-notes > span{font-size:11px;color:var(--muted);letter-spacing:.4px;text-transform:uppercase}
.setups-notes textarea{
  background:#0a0d12;border:1px solid var(--line);color:var(--text);
  border-radius:6px;padding:8px 10px;font:13px system-ui,sans-serif;resize:vertical;
}

/* ---- inline error under name ---- */
.setups-meta .err{color:var(--accent);font-size:11px;margin-top:2px}
```

- [ ] **Step 2: Verify styles load**

Reload the page in the browser. The Setups view (when shown later) should inherit dark panels + red accents; the live view should be unchanged.

- [ ] **Step 3: Commit**

```bash
git add frontend/styles.css
git commit -m "feat(frontend): styles for Setups view + topbar tabs + 9-segment strip"
```

---

### Task 7: `frontend/setups.js` — Setups view (list, editor, sections, unit toggle, hash routing)

**Files:**
- Create: `frontend/setups.js`

**Interfaces:**
- Produces: a self-contained module bound to the DOM in `index.html` that:
  - Fetches `GET /api/setups/schema` once on load and caches it.
  - Fetches `GET /api/setups` to populate the list; refreshes after every save/delete/attach.
  - Renders the saved-setups list rows with name/car·track/updated + Attach/Edit/Delete actions.
  - Opens a setup in the editor pane (or starts a new one) and renders 9 `<details>` sections grouped by `group` (per_axle → Front|Rear rows; single → one input; list → dynamic gears array).
  - Tracks `formState` (current edit) vs `loadedSetup` (disk) and toggles the dirty dot + Save button.
  - POSTs new / PUTs existing on Save; on success, reloads the saved setup, refreshes the list, emits `bus.emit("setup:change", saved)` if the saved id matches the currently-attached id (else no-op).
  - Unit toggle: on existing setup, immediately PUTs `{units: <new>, fields: <formState fields>}` (server converts); on new setup, applies `_convert` factors in-memory to formState and updates labels.
  - Hash routing: `hashchange` shows `#setups` view + hides live view, sets `aria-selected`, emits `bus.emit("view:change", "setups")`; empty hash shows live.
  - Wires topbar tab buttons (Live/Setups) to set the hash; chip click → set hash to `#setups`.
  - Listens to `bus.on("setup:change", ...)` to update the topbar chip name.
  - Exposes `window.__setupsView` with a `refreshList()` method (used by app.js if needed) and an `attachSetup(setupId)` for tests/manual use.

- [ ] **Step 1: Write `frontend/setups.js`**

Create `frontend/setups.js`:

```javascript
// horizon6tuning Setups view — list, editor, 9 sections, unit toggle, attach.
// Depends on window.$, window.fetchJSON, window.bus from common.js.
"use strict";

(function () {
  // ---- module state --------------------------------------------------------
  let SCHEMA = null;           // schema payload from /api/setups/schema
  let CURRENT_SETUP_ID = null; // currently attached to session
  let CURRENT_SETUP = null;    // its full dict (or null)
  let LIST = [];               // saved-setups summaries
  let LOADED = null;           // the setup loaded into the editor (dict or {__new:true})
  let FORM = null;             // in-memory edit state mirroring LOADED

  // ---- DOM refs ------------------------------------------------------------
  const $live = $("liveView");
  const $setups = $("setupsView");
  const $tabLive = $("tabLive");
  const $tabSetups = $("tabSetups");
  const $chip = $("currentSetupChip");
  const $chipName = $("currentSetupName");
  const $list = $("setupsList");
  const $listEmpty = $("setupsEmpty");
  const $editor = $("setupsEditor");
  const $title = $("setupsEditorTitle");
  const $name = $("setupName");
  const $car = $("setupCar");
  const $track = $("setupTrack");
  const $notes = $("setupNotes");
  const $dirty = $("setupsDirty");
  const $save = $("setupsSave");
  const $cancel = $("setupsCancel");
  const $new = $("setupsNew");
  const $strip = $("setupsStrip");
  const $sections = $("setupsSections");
  const $unitsBtns = document.querySelectorAll(".units-toggle button");

  // ---- init ----------------------------------------------------------------
  document.addEventListener("DOMContentLoaded", init);
  window.addEventListener("hashchange", onHash);
  $tabLive.addEventListener("click", () => { location.hash = ""; });
  $tabSetups.addEventListener("click", () => { location.hash = "#setups"; });
  $chip.addEventListener("click", () => { location.hash = "#setups"; });
  $new.addEventListener("click", () => loadIntoEditor({ __new: true }));
  $save.addEventListener("click", save);
  $cancel.addEventListener("click", cancel);
  $chip.classList.remove("has-setup");

  bus.on("setup:change", (s) => {
    CURRENT_SETUP = s || null;
    CURRENT_SETUP_ID = s ? s.id : null;
    renderChip();
    renderList();
  });
  bus.on("view:change", () => { /* nothing to do here; app.js reads this */ });

  async function init() {
    try {
      SCHEMA = await fetchJSON("/api/setups/schema");
    } catch (e) {
      console.error("failed to load schema", e);
      SCHEMA = { sections: [] };
    }
    try {
      const sess = await fetchJSON("/api/session/setup");
      CURRENT_SETUP = sess.setup || null;
      CURRENT_SETUP_ID = sess.setup_id || null;
    } catch { /* no session yet */ }
    renderChip();
    await refreshList();
    // units toggle
    for (const b of $unitsBtns) b.addEventListener("click", onUnitsToggle);
    onHash();
  }

  // ---- hash routing --------------------------------------------------------
  function onHash() {
    const isSetups = location.hash === "#setups";
    $setups.hidden = !isSetups;
    $live.hidden = isSetups;
    $tabLive.setAttribute("aria-selected", String(!isSetups));
    $tabSetups.setAttribute("aria-selected", String(isSetups));
    bus.emit("view:change", isSetups ? "setups" : "live");
  }

  // ---- chip + list ---------------------------------------------------------
  function renderChip() {
    if (CURRENT_SETUP) {
      $chipName.textContent = CURRENT_SETUP.name || "(unnamed)";
      $chip.classList.add("has-setup");
      $chip.title = `Current: ${CURRENT_SETUP.name} — click to manage setups`;
    } else {
      $chipName.textContent = "no setup attached";
      $chip.classList.remove("has-setup");
      $chip.title = "Click to manage setups";
    }
  }

  function relativeTime(ts) {
    if (!ts) return "";
    const s = Math.max(0, (Date.now() / 1000) - ts);
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
    return `${Math.floor(s / 86400)}d ago`;
  }

  async function refreshList() {
    try {
      const out = await fetchJSON("/api/setups");
      LIST = out.setups || [];
    } catch { LIST = []; }
    renderList();
  }

  function renderList() {
    $list.innerHTML = "";
    $listEmpty.hidden = LIST.length > 0;
    for (const s of LIST) {
      const li = document.createElement("li");
      if (CURRENT_SETUP_ID === s.id) li.classList.add("current");
      li.dataset.id = s.id;
      const carTrack = [s.car, s.track].filter(Boolean).join(" · ");
      li.innerHTML = `
        <div class="row-name"></div>
        <div class="row-meta"></div>
        <div class="row-actions"></div>`;
      li.querySelector(".row-name").textContent = s.name || "(unnamed)";
      li.querySelector(".row-meta").textContent =
        `${carTrack || "—"} · updated ${relativeTime(s.updated_at)}`;
      if (CURRENT_SETUP_ID === s.id) {
        const badge = document.createElement("span");
        badge.className = "badge";
        badge.textContent = "● Current";
        li.appendChild(badge);
        const det = btn("Detach", async (e) => {
          e.stopPropagation();
          await attach(null);
        });
        li.querySelector(".row-actions").appendChild(det);
      } else {
        const at = btn("Attach", async (e) => {
          e.stopPropagation();
          await attach(s.id);
        });
        const ed = btn("Edit", (e) => {
          e.stopPropagation();
          openSetup(s.id);
        });
        const del = btn("Delete", async (e) => {
          e.stopPropagation();
          if (!confirm(`Delete "${s.name}"? This cannot be undone.`)) return;
          await deleteSetup(s.id);
        });
        const actions = li.querySelector(".row-actions");
        actions.append(at, ed, del);
      }
      li.addEventListener("click", () => openSetup(s.id));
      $list.appendChild(li);
    }
  }

  function btn(label, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    b.addEventListener("click", onClick);
    return b;
  }

  // ---- attach / detach -----------------------------------------------------
  async function attach(setupId) {
    try {
      const out = await fetchJSON("/api/session/setup", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ setup_id: setupId }),
      });
      CURRENT_SETUP = out.setup || null;
      CURRENT_SETUP_ID = out.setup_id || null;
      bus.emit("setup:change", CURRENT_SETUP);
    } catch (e) {
      toast(`Couldn't attach: ${e.message}`);
    }
  }

  async function deleteSetup(id) {
    try {
      await fetchJSON(`/api/setups/${encodeURIComponent(id)}`, { method: "DELETE" });
      toast("Deleted");
      if (CURRENT_SETUP_ID === id) {
        CURRENT_SETUP = null;
        CURRENT_SETUP_ID = null;
        bus.emit("setup:change", null);
      }
      if (LOADED && LOADED.id === id) {
        LOADED = null; FORM = null; $editor.hidden = true;
      }
      await refreshList();
    } catch (e) {
      toast(`Couldn't delete: ${e.message}`);
    }
  }

  // ---- editor --------------------------------------------------------------
  async function openSetup(id) {
    try {
      const full = await fetchJSON(`/api/setups/${encodeURIComponent(id)}`);
      loadIntoEditor(full);
    } catch (e) {
      toast(`Couldn't open: ${e.message}`);
    }
  }

  function loadIntoEditor(setup) {
    LOADED = setup;
    FORM = setup.__new
      ? { name: "", car: "", track: "", fields: {}, notes: "", units: "english" }
      : {
          name: setup.name || "",
          car: setup.car || "",
          track: setup.track || "",
          fields: deepClone(setup.fields || {}),
          notes: setup.notes || "",
          units: setup.units || "english",
        };
    $title.textContent = setup.__new ? "New setup" : `Edit: ${setup.name || "(unnamed)"}`;
    $name.value = FORM.name;
    $car.value = FORM.car;
    $track.value = FORM.track;
    $notes.value = FORM.notes;
    syncUnitsToggle();
    $editor.hidden = false;
    renderStrip();
    renderSections();
    updateDirty();
    // scroll editor into view on narrow screens
    if (window.innerWidth <= 980) $editor.scrollIntoView({ behavior: "smooth" });
  }

  function deepClone(o) { return JSON.parse(JSON.stringify(o || {})); }

  function isDirty() {
    if (!LOADED || LOADED.__new) {
      return Boolean(FORM.name && FORM.name.trim());
    }
    return JSON.stringify(FORM) !== JSON.stringify({
      name: LOADED.name || "", car: LOADED.car || "", track: LOADED.track || "",
      fields: LOADED.fields || {}, notes: LOADED.notes || "",
      units: LOADED.units || "english",
    });
  }

  function updateDirty() {
    const d = isDirty();
    $dirty.hidden = !d;
    $save.disabled = !d;
  }

  // ---- 9-segment strip -----------------------------------------------------
  function renderStrip() {
    $strip.innerHTML = "";
    SCHEMA.sections.forEach((sec, i) => {
      const b = document.createElement("button");
      b.type = "button";
      b.title = sec.label;
      const filled = sectionFillCount(sec) === sec.fields.length && sec.fields.length > 0;
      if (filled) b.classList.add("filled");
      b.addEventListener("click", () => {
        const details = $sections.querySelectorAll("details.section-card")[i];
        if (details) {
          details.open = true;
          details.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
      $strip.appendChild(b);
    });
  }

  function sectionFillCount(sec) {
    const f = FORM.fields[sec.key] || {};
    return sec.fields.filter(fld => f[fld.key] != null && f[fld.key] !== "").length;
  }

  // ---- sections ------------------------------------------------------------
  function renderSections() {
    $sections.innerHTML = "";
    SCHEMA.sections.forEach((sec, i) => {
      const card = document.createElement("details");
      card.className = "section-card";
      card.open = i === 0;  // first section open
      const total = sec.fields.length;
      const filled = sectionFillCount(sec);
      const sum = document.createElement("summary");
      sum.innerHTML = `
        <span><span class="chev">▸</span> ${escapeHtml(sec.label)}</span>
        <span class="fill-count ${filled === total ? "full" : ""}">${filled}/${total}</span>`;
      card.appendChild(sum);
      const body = document.createElement("div");
      body.className = "body";
      // group fields by their layout (per_axle/single/list)
      renderSectionBody(body, sec);
      card.addEventListener("toggle", () => {
        // re-render fill count when toggled (no-op for content, but cheap)
        const total = sec.fields.length;
        const filled = sectionFillCount(sec);
        sum.querySelector(".fill-count").className =
          "fill-count " + (filled === total ? "full" : "");
        sum.querySelector(".fill-count").textContent = `${filled}/${total}`;
      });
      card.appendChild(body);
      $sections.appendChild(card);
    });
    // also update fill count on every input change
    $sections.addEventListener("input", onFieldInput);
  }

  function renderSectionBody(body, sec) {
    const isGears = sec.key === "gearing";
    if (isGears) {
      // special: final_drive single + gears list
      const fd = sec.fields.find(f => f.key === "final_drive");
      const gears = sec.fields.find(f => f.key === "gears");
      if (fd) body.appendChild(makeFieldRow([fd], 1));
      if (gears) {
        const list = document.createElement("div");
        list.className = "gears-list";
        const wrap = document.createElement("div");
        wrap.className = "field";
        wrap.appendChild(makeListGroup(gears, list));
        body.appendChild(wrap);
      }
      return;
    }
    // otherwise: group by group kind
    const groups = {}; // group name -> [field]
    for (const f of sec.fields) (groups[f.group] = groups[f.group] || []).push(f);
    for (const gname of Object.keys(groups)) {
      const fields = groups[gname];
      if (gname === "per_axle") {
        // pair up into Front/Rear rows by suffix
        const pairs = pairPerAxle(fields);
        for (const pair of pairs) body.appendChild(makeFieldRow(pair, 2));
      } else if (gname === "single") {
        for (const f of fields) body.appendChild(makeFieldRow([f], 1));
      } else if (gname === "list") {
        const list = document.createElement("div");
        list.className = "gears-list";
        const wrap = document.createElement("div");
        wrap.className = "field";
        wrap.appendChild(makeListGroup(fields[0], list));
        body.appendChild(wrap);
      }
    }
  }

  function pairPerAxle(fields) {
    // for fields with suffix _front/_rear, pair them; otherwise group all together as one row
    const out = [];
    const seen = new Set();
    for (const f of fields) {
      if (seen.has(f.key)) continue;
      const m = f.key.match(/^(.*)_(front|rear)$/);
      if (m) {
        const partnerKey = `${m[1]}_${m[2] === "front" ? "rear" : "front"}`;
        const partner = fields.find(x => x.key === partnerKey);
        out.push(partner ? [f, partner] : [f]);
        seen.add(f.key); if (partner) seen.add(partner.key);
      } else {
        out.push([f]);
        seen.add(f.key);
      }
    }
    return out;
  }

  function makeFieldRow(fields, cols) {
    const row = document.createElement("div");
    row.className = `field-row ${cols === 2 ? "two" : cols === 3 ? "three" : "four"}`;
    for (const f of fields) row.appendChild(makeField(f));
    return row;
  }

  function makeField(f) {
    const wrap = document.createElement("div");
    wrap.className = "field";
    const label = document.createElement("label");
    label.textContent = f.label;
    wrap.appendChild(label);
    const iw = document.createElement("div");
    iw.className = "field-input-wrap";
    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.dataset.section = currentSectionFor(f);
    input.dataset.field = f.key;
    const sec = input.dataset.section;
    const cur = (FORM.fields[sec] || {})[f.key];
    input.value = cur == null ? "" : cur;
    iw.appendChild(input);
    if (f.unit) {
      const unit = document.createElement("span");
      unit.className = "field-unit";
      unit.textContent = unitLabelFor(f);
      iw.appendChild(unit);
    }
    wrap.appendChild(iw);
    return wrap;
  }

  function currentSectionFor(fieldMeta) {
    // find the section in schema that contains this field
    for (const sec of SCHEMA.sections) {
      if (sec.fields.some(f => f.key === fieldMeta.key)) return sec.key;
    }
    return "";
  }

  function unitLabelFor(f) {
    if (!f.unit) return "";
    if (FORM.units === "metric" && f.unit_metric) return f.unit_metric;
    if (FORM.units === "english" && f.unit_english) return f.unit_english;
    return f.unit;
  }

  function makeListGroup(f, list) {
    const sec = currentSectionFor(f);
    FORM.fields[sec] = FORM.fields[sec] || {};
    const arr = Array.isArray(FORM.fields[sec][f.key]) ? FORM.fields[sec][f.key] : [];
    FORM.fields[sec][f.key] = arr;
    const labels = ["1st", "2nd", "3rd", "4th", "5th", "6th", "7th", "8th", "9th", "10th"];
    const drawRows = () => {
      list.innerHTML = "";
      arr.forEach((v, idx) => {
        const row = document.createElement("div");
        row.className = "gears-row";
        const lbl = document.createElement("div");
        lbl.className = "gear-label";
        lbl.textContent = labels[idx] || `gear ${idx + 1}`;
        const iw = document.createElement("div");
        iw.className = "field-input-wrap";
        const input = document.createElement("input");
        input.type = "number";
        input.step = "any";
        input.value = v == null ? "" : v;
        input.addEventListener("input", () => {
          const x = parseFloat(input.value);
          arr[idx] = isNaN(x) ? null : x;
          updateDirty(); renderStrip(); updateFillCounts();
        });
        iw.appendChild(input);
        const unit = document.createElement("span");
        unit.className = "field-unit";
        unit.textContent = f.unit || "";
        iw.appendChild(unit);
        const rm = document.createElement("button");
        rm.type = "button";
        rm.className = "gear-remove";
        rm.textContent = "×";
        rm.title = "Remove gear";
        rm.addEventListener("click", () => {
          arr.splice(idx, 1); drawRows(); updateDirty(); renderStrip(); updateFillCounts();
        });
        row.append(lbl, iw, rm);
        list.appendChild(row);
      });
    };
    drawRows();
    const add = document.createElement("button");
    add.type = "button";
    add.className = "gears-add";
    add.textContent = "+ gear";
    add.addEventListener("click", () => {
      const last = arr.length ? Number(arr[arr.length - 1]) : 3.0;
      const next = isNaN(last) ? 1.0 : Math.max(0.5, last * 0.75);
      arr.push(Number(next.toFixed(3)));
      drawRows(); updateDirty(); renderStrip(); updateFillCounts();
    });
    const wrap = document.createElement("div");
    wrap.append(list, add);
    return wrap;
  }

  // ---- field input handler -------------------------------------------------
  function onFieldInput(e) {
    const t = e.target;
    if (!(t instanceof HTMLInputElement)) return;
    const sec = t.dataset.section; const fk = t.dataset.field;
    if (!sec || !fk) return;
    FORM.fields[sec] = FORM.fields[sec] || {};
    const x = parseFloat(t.value);
    if (t.value === "" || isNaN(x)) {
      delete FORM.fields[sec][fk];
    } else {
      FORM.fields[sec][fk] = x;
    }
    updateDirty();
    renderStrip();
    updateFillCounts();
  }

  function updateFillCounts() {
    SCHEMA.sections.forEach((sec, i) => {
      const card = $sections.querySelectorAll("details.section-card")[i];
      if (!card) return;
      const total = sec.fields.length;
      const filled = sectionFillCount(sec);
      const fc = card.querySelector(".fill-count");
      if (fc) {
        fc.textContent = `${filled}/${total}`;
        fc.className = "fill-count " + (filled === total ? "full" : "");
      }
    });
  }

  // ---- unit toggle (immediate save for existing, in-memory for new) -------
  function syncUnitsToggle() {
    for (const b of $unitsBtns) b.setAttribute(
      "aria-pressed", String(b.dataset.units === FORM.units));
  }

  function unitFactorsForField(f) {
    // returns the english->metric factor (or null) for a field
    return f.conversion;
  }

  function convertFields(fields, from, to) {
    if (from === to) return fields;
    const out = {};
    for (const sec of SCHEMA.sections) {
      const inSec = fields[sec.key] || {};
      const outSec = {};
      for (const f of sec.fields) {
        const v = inSec[f.key];
        if (v == null) continue;
        if (f.conversion == null) { outSec[f.key] = v; continue; }
        if (from === "english" && to === "metric") outSec[f.key] = v * f.conversion;
        else if (from === "metric" && to === "english") outSec[f.key] = v / f.conversion;
        else outSec[f.key] = v;
      }
      if (Object.keys(outSec).length) out[sec.key] = outSec;
    }
    return out;
  }

  async function onUnitsToggle(e) {
    const newUnits = e.currentTarget.dataset.units;
    if (newUnits === FORM.units) return;
    const oldUnits = FORM.units;
    // convert current formState fields (interpreted as oldUnits) to newUnits
    FORM.fields = convertFields(FORM.fields, oldUnits, newUnits);
    FORM.units = newUnits;
    syncUnitsToggle();
    if (LOADED && !LOADED.__new) {
      // existing setup — immediate save (server converts too; we mirror here)
      try {
        const out = await fetchJSON(`/api/setups/${encodeURIComponent(LOADED.id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: FORM.name, car: FORM.car, track: FORM.track,
            fields: FORM.fields, notes: FORM.notes, units: newUnits,
          }),
        });
        LOADED = out;
        FORM = {
          name: out.name, car: out.car, track: out.track,
          fields: deepClone(out.fields), notes: out.notes, units: out.units,
        };
        toast(`Saved in ${newUnits}`);
        await refreshList();
        renderStrip(); renderSections(); updateDirty();
      } catch (err) {
        toast(`Couldn't save units: ${err.message}`);
      }
    } else {
      // new setup — just re-render with the new unit labels
      toast(`Units: ${newUnits}`);
      renderStrip(); renderSections(); updateDirty();
    }
  }

  // ---- save / cancel -------------------------------------------------------
  async function save() {
    if (!LOADED) return;
    if (!FORM.name || !FORM.name.trim()) {
      toast("Name is required");
      $name.focus();
      return;
    }
    const payload = {
      name: FORM.name.trim(), car: FORM.car, track: FORM.track,
      fields: FORM.fields, notes: FORM.notes, units: FORM.units,
    };
    try {
      $save.disabled = true;
      let out;
      if (LOADED.__new) {
        out = await fetchJSON("/api/setups", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } else {
        out = await fetchJSON(`/api/setups/${encodeURIComponent(LOADED.id)}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      }
      toast("Saved");
      LOADED = out;
      FORM = {
        name: out.name, car: out.car, track: out.track,
        fields: deepClone(out.fields), notes: out.notes, units: out.units,
      };
      $title.textContent = `Edit: ${out.name}`;
      syncUnitsToggle();
      renderStrip(); renderSections(); updateDirty();
      await refreshList();
    } catch (e) {
      toast(`Save failed: ${e.message}`);
    } finally {
      $save.disabled = !isDirty();
    }
  }

  async function cancel() {
    if (isDirty()) {
      if (!confirm("Discard unsaved changes?")) return;
    }
    if (LOADED && LOADED.__new) {
      LOADED = null; FORM = null;
      $editor.hidden = true;
    } else if (LOADED) {
      loadIntoEditor(LOADED);  // reload from disk
    } else {
      $editor.hidden = true;
    }
  }

  // ---- meta input handlers (name/car/track/notes) --------------------------
  $name.addEventListener("input", () => { FORM.name = $name.value; updateDirty(); });
  $car.addEventListener("input", () => { FORM.car = $car.value; updateDirty(); });
  $track.addEventListener("input", () => { FORM.track = $track.value; updateDirty(); });
  $notes.addEventListener("input", () => { FORM.notes = $notes.value; updateDirty(); });

  // ---- helpers -------------------------------------------------------------
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }
  function toast(msg) {
    console.log("[setups]", msg);
    // minimal inline toast: reuse the existing insights placeholder area
    const body = $("insightsBody");
    if (!body) return;
    const prev = body.innerHTML;
    body.innerHTML = `<p class="placeholder">${escapeHtml(msg)}</p>`;
    setTimeout(() => { body.innerHTML = prev; }, 1800);
  }

  // ---- public hook (for tests / app.js) ------------------------------------
  window.__setupsView = { refreshList, attach, openSetup, getCurrent: () => CURRENT_SETUP };
})();
```

- [ ] **Step 2: Verify it loads in the browser**

Restart `python -m app.main` + `python scripts/fake_sender.py`, open `http://127.0.0.1:8000`, click the Setups tab. The list pane should render (empty + "+ New setup" button). Click "+ New setup"; the editor pane should show Name/Car/Track inputs, the Metric/English toggle, a 9-segment strip (all empty/unfilled), the first section ("Tire Pressure") open with Front/Rear inputs in PSI, and the other 8 sections collapsed. Fill fields; the per-section `k/N` count and the 9-segment strip should update on each input. Save → toast, list shows the row. Reopen → values round-trip.

- [ ] **Step 3: Commit**

```bash
git add frontend/setups.js
git commit -m "feat(frontend): Setups view (list, editor, 9 sections, unit toggle, hash routing)"
```

---

### Task 8: `frontend/app.js` — topbar chip wired to bus

**Files:**
- Modify: `frontend/app.js` (remove local `$`; subscribe to `bus.on("setup:change", ...)`; nothing else changes)

**Interfaces:**
- Produces: topbar chip rendered from `bus` events. `app.js` no longer defines its own `$` (use the one from `common.js`); it registers a `setup:change` listener that updates the chip — but `setups.js` already does that. The only required change is removing the local `$` definition to avoid shadowing.

- [ ] **Step 1: Remove the local `$` definition**

In `frontend/app.js`, delete the line:

```javascript
const $ = (id) => document.getElementById(id);
```

(Leave the rest of `app.js` unchanged. `setups.js` already subscribes to `setup:change` and updates the chip; the bus is shared.)

- [ ] **Step 2: Reload and verify**

Reload the page. The topbar should still show status + logging toggle as before; nothing else should change visibly. Attaching a setup in the Setups view should update the chip live.

- [ ] **Step 3: Commit**

```bash
git add frontend/app.js
git commit -m "refactor(frontend): use shared $ from common.js (no behavior change)"
```

---

### Task 9: Manual end-to-end verification (no JS harness)

**Files:** none.

**Steps:**

1. Kill any running app process. Start fresh: `conda run -n fh6tuning python -m app.main` in one terminal; `conda run -n fh6tuning python scripts/fake_sender.py` in another.
2. Open `http://127.0.0.1:8000` in a browser.
3. Verify the topbar shows Live/Setups tabs + a chip reading "no setup attached".
4. Click **Setups** → URL becomes `#setups`, Setups view shown, live grid hidden. Confirm the WebSocket is still connected by switching back to Live — fresh telemetry should still be rendering.
5. Empty list shows "No setups yet — create your first tuning sheet."
6. Click **+ New setup**; the editor appears with the first section open, Save disabled until Name is non-empty.
7. Fill fields; the 9-segment strip lights up red as sections fill; per-section `k/N` counts update live.
8. Click **Save** → toast "Saved", list pane shows the new row, chip unchanged.
9. Click a row → editor reopens with values; edit one field; the dirty dot + Save button enable.
10. Click **Cancel** on a dirty form → confirm dialog appears.
11. Click **Attach** on a row → chip becomes "▸ {name}" with amber color; the row shows a red "● Current" badge.
12. Click **Detach** → chip returns to "no setup attached".
13. Click the **Metric** toggle on an existing setup → values convert (e.g. 32 PSI → 2.2 bar; 5 in → 12.7 cm); toast "Saved in metric"; reopen the setup → still in metric.
14. Open `setups/{id}.json` on disk → confirm `"units": "metric"` and metric values (file adapts).
15. Toggle back to **English** → values return to 32 PSI / 5 in (within rounding). Reopen and check again.
16. Click **Delete** on a setup → confirm dialog → row removed; if it was the current setup, the chip reverts.
17. Resize the browser to ≤980px → list/editor should swap to single pane with scroll.
18. Load `http://127.0.0.1:8000/#setups` directly → Setups view opens at page load.

If any step fails, file the issue and fix it before merging.

- [ ] **Step 1: Run the manual checklist above**

Expected: all 18 steps pass.

- [ ] **Step 2: Run the full Python test suite one more time**

```bash
conda run -n fh6tuning python -m pytest tests/ -q
```

Expected: all tests PASS (parser, laps, logger, setups — now ~30+ cases).

- [ ] **Step 3: Commit any verification fixes (if needed)**

If a step failed and you fixed it, commit the fix. If everything passed, no commit is needed.

---

### Task 10: Update ROADMAP item 4 status marker

**Files:**
- Modify: `ROADMAP.md`

**Interfaces:**
- Produces: item 4 status marker changed from `[in progress]` to `[done · branch feature/setup-editor]`; add the implementation summary note (matching the style of items 2/3).

- [ ] **Step 1: Update the marker and append the summary note**

In `ROADMAP.md`, find item 4's title line and change:

```
4. **Setup editor (v1, all 9 categories)** `[in progress]` — a single page in the dashboard
```

to:

```
4. **Setup editor (v1, all 9 categories)** `[done · branch feature/setup-editor]` — a single page in the dashboard
```

Append a summary note after item 4's last bullet (the differential one), matching the style of items 2 and 3:

```
   Attach a setup to the current session so the LLM knows the *current* setup
   when it generates insight.
   *(Implemented: `app/store/setups.py` `SETUP_FIELD_SCHEMA` + `SETUP_FIELD_META` +
   `Setup.units` + `_convert_units`; `GET /api/setups/schema`; `frontend/common.js`
   + `frontend/setups.js` with topbar tabs, hash routing, 9-segment strip,
   explicit Save, Metric/English toggle, attach/detach. Tests: 8 new cases in
   `tests/test_setups.py` cover schema shape, unit round-trip, file-adapts-on-disk,
   invalid-unit default, non-convertible pass-through. `tire_pressure` schema
   corrected to per-axle (was per-wheel). Spec at
   `docs/superpowers/specs/2026-07-05-setup-editor-design.md`. Not yet merged to
   `main`. Item 21 (in-app setup library: search/filter/duplicate) builds on this.)*
```

- [ ] **Step 2: Verify the diff is clean**

```bash
git diff ROADMAP.md
```

Expected: only item 4's marker line and the appended summary note change.

- [ ] **Step 3: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark item 4 done; summary of Setups view"
```

---

## Final verification

After Task 10, confirm the branch is in a good state:

```bash
conda run -n fh6tuning python -m pytest tests/ -q
git status
git log --oneline main..HEAD
```

Expected: all tests pass, working tree clean, ~10 commits on `feature/setup-editor` ahead of `main`.

## Self-Review (run before execution)

- **Spec coverage:**
  - Schema correction (tire_pressure per-axle) → Task 1.
  - `SETUP_FIELD_META` (label/group/unit/conversion) → Task 1.
  - `_convert_units` helper → Task 1.
  - `Setup.units` field + per-setup storage → Task 2.
  - `SetupStore.create` accepts `units` (invalid → "english") → Task 2.
  - `SetupStore.update` triggers conversion when `units` changes → Task 2.
  - `GET /api/setups/schema` → Task 3.
  - Topbar tabs + current-setup chip → Task 5.
  - Setups view container (list pane + editor pane) → Task 5.
  - Setups view styles (extends tokens; no new palette) → Task 6.
  - 9-segment strip (signature element) → Tasks 6 + 7.
  - 9 collapsible sections, per-section `k/N` counts → Task 7.
  - Explicit Save button + dirty indicator → Task 7.
  - Metric/English toggle (immediate save for existing, in-memory for new) → Task 7.
  - Attach/detach in list + topbar chip synced → Tasks 7 + 8.
  - Hash routing (`#setups` ↔ live) → Task 7.
  - New setup starts in English; user can toggle before saving → Task 7.
  - List pane refreshes after every save/delete/attach → Task 7.
  - Light client-side validation (numeric input; backend 400 → inline under Name) → Task 7.
  - Manual verification checklist → Task 9.
  - ROADMAP status marker + summary → Task 10.
  - All 8 new test cases (schema shape, schema round-trip, unit round-trip, file-adapts, default+backward-compat, invalid unit, non-convertible pass-through, existing cases) → Tasks 1, 2, 3.
- **Placeholder scan:** no TBD/TODO; every code step contains real code; every test step contains real assertions; the JS files are full implementations (not stubs).
- **Type consistency:** `SETUP_FIELD_META` is keyed by `(section, field)` and read by both `_convert_units` and the schema endpoint using the same access pattern. `Setup.units` defaults to `"english"`. `_normalize_units` is used in `create`, `update`, and `get`. The `SetupStore.update` contract (sent fields are in OLD units) is consistent between the tests and the `setups.js` unit-toggle path. `setup_id` validation is unchanged from item 3. Route names (`setups_schema`) match between tests and implementation. `SETUP_FIELD_META` field names match `SETUP_FIELD_SCHEMA` (same 28 fields + `gears`); the schema test asserts the field count and the per-section shape.
- **Known wrinkles:**
  - `app.js` had a local `const $ = ...` that shadows the one from `common.js`. Task 8 removes it.
  - The `__main__` block in `tests/test_setups.py` had to be updated to print the new test suite name — done in Task 2.
  - `unitLabelFor` in `setups.js` falls back to `f.unit` when neither `unit_metric` nor `unit_english` matches (covers non-convertible fields like camber, ARB, brake %, diff %, gear ratios).
  - The `setups.js` `convertFields` function duplicates the backend's `_convert_units` for the in-memory new-setup path. This is acceptable: the backend is the authority for saved data, and this client-side pass is for the brief new-setup editing UX. The spec calls this out ("frontend applies them only for the in-memory new-setup case").
