# Setup Data Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Setup` data model + JSON file store + REST CRUD API + in-memory current-session link for FH6 car tuning sheets, so the dashboard (and later the LLM) can know the current setup.

**Architecture:** One new module `app/store/setups.py` holds the `Setup` dataclass, a data-driven `SETUP_FIELD_SCHEMA` constant (single source of truth for the 9 FH6 tuning sections), permissive field normalization, and a `SetupStore` file-CRUD class. Seven routes extend the existing `app/api/routes.py`. `SETUPS_DIR` is added to `app/config.py`; `main.py` wires the store into `router.state`. Approach A from the spec — flat `store/` layout, data-driven schema mirroring `app/telemetry/schema.py`.

**Tech Stack:** Python 3.10+, stdlib `dataclasses`/`json`/`uuid`/`re`/`os`/`pathlib`, FastAPI, pydantic-settings. Tests runnable via `python tests/test_setups.py` and `pytest tests/test_setups.py -q` (no new deps).

**Spec:** `docs/superpowers/specs/2026-07-04-setup-data-model-design.md`

## Global Constraints

- **Run Python via conda on this Mac:** `conda run -n fh6tuning ...` (not `.venv`). Run tests with `conda run -n fh6tuning python tests/test_setups.py` and `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`.
- **Persistence is files only:** one JSON file per setup in `setups/`. No SQLite, no DB.
- **Permissive validation:** unknown sections/fields silently dropped; numeric strings coerced to `float`; all 9 sections optional; only `name` required.
- **IDs are `uuid.uuid4().hex`** (32 lowercase hex chars). Any user-supplied id is validated against `^[a-f0-9]{32}$` before filesystem path construction — blocks path traversal cold.
- **Atomic writes:** write `{id}.json.tmp` then `os.replace` to `{id}.json`.
- **FH6 field schema is fixed** (verified against FH6 guides — see spec). Use exactly the field names in `SETUP_FIELD_SCHEMA`. Do not reintroduce per-wheel camber/toe/springs/damping, "compression" (use `bump`), brake pad/rotor, or diff preload.
- **Match existing code style:** `from __future__ import annotations`, module docstrings, `JSONResponse({"error": ...}, status_code=...)` for non-200, route functions read `router.state[...]`.
- **Tests match `tests/test_laps.py`:** `sys.path` insert, runnable standalone + under pytest, route tests call route functions directly via `asyncio.run(...)` and set `routes.router.state` by hand (no FastAPI TestClient).
- **Commit on the `feature/setup-data-model` branch** (already created and checked out). One commit per task.

## File Structure

- **Create `app/store/setups.py`** — `Setup` dataclass, `SETUP_FIELD_SCHEMA` constant, `is_valid_setup_id`, `_normalize_fields`, `_coerce_number`, `SetupStore` file-CRUD class. One responsibility: the setup data model + its file persistence.
- **Create `tests/test_setups.py`** — all tests for the above + the API routes.
- **Modify `app/config.py`** — add `setups_dir: str = "./setups"` field to `Settings`.
- **Modify `.env.example`** — document `SETUPS_DIR`.
- **Modify `.gitignore`** — add `setups/`.
- **Create `setups/.gitkeep`** — keep the dir in a fresh clone.
- **Modify `app/store/__init__.py`** — export `Setup`, `SetupStore`.
- **Modify `app/api/routes.py`** — seven new routes (setups CRUD + session link).
- **Modify `app/main.py`** — create `SetupStore` in `lifespan`, add `setups` + `current_setup_id` to `router.state`.
- **Modify `ROADMAP.md`** — correct item 4's field list to FH6 reality; mark item 3 `[done · branch feature/setup-data-model]`.

---

### Task 1: Setup dataclass + field schema + normalization + id validation

**Files:**
- Create: `app/store/setups.py`
- Create: `tests/test_setups.py`

**Interfaces:**
- Produces: `Setup` dataclass with fields `{id, name, car, track, fields, notes, created_at, updated_at}` and `as_dict()`; `SETUP_FIELD_SCHEMA: dict[str, list[str]]`; `is_valid_setup_id(setup_id: str) -> bool`; `_normalize_fields(fields) -> dict`; `_coerce_number(v)`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_setups.py`:

```python
"""Setup data model + store tests — ROADMAP item 3.

Verifies field normalization, id validation, file CRUD, and the seven HTTP
routes.

Run:  conda run -n fh6tuning python -m pytest tests/test_setups.py -q
   or conda run -n fh6tuning python tests/test_setups.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store.setups import (
    Setup, SETUP_FIELD_SCHEMA, is_valid_setup_id, _normalize_fields,
)


# ---- 1. field schema shape --------------------------------------------------

def test_field_schema_has_nine_sections() -> None:
    assert set(SETUP_FIELD_SCHEMA) == {
        "tire_pressure", "gearing", "alignment", "anti_roll_bars",
        "springs", "damping", "aero", "brake", "differential",
    }


def test_field_schema_alignment_is_per_axle() -> None:
    assert SETUP_FIELD_SCHEMA["alignment"] == [
        "camber_front", "camber_rear", "toe_front", "toe_rear", "caster",
    ]


def test_field_schema_damping_uses_bump_not_compression() -> None:
    assert SETUP_FIELD_SCHEMA["damping"] == [
        "rebound_front", "rebound_rear", "bump_front", "bump_rear",
    ]


def test_field_schema_brake_is_bias_pressure() -> None:
    assert SETUP_FIELD_SCHEMA["brake"] == ["bias", "pressure"]


def test_field_schema_diff_has_no_preload() -> None:
    assert "preload_front" not in SETUP_FIELD_SCHEMA["differential"]
    assert SETUP_FIELD_SCHEMA["differential"] == [
        "accel_lock_front", "accel_lock_rear",
        "decel_lock_front", "decel_lock_rear",
        "center_balance",
    ]


# ---- 2. normalization -------------------------------------------------------

def test_normalize_drops_unknown_sections_and_fields() -> None:
    out = _normalize_fields({
        "tire_pressure": {"fl": 30, "bogus": 99},
        "not_a_section": {"x": 1},
    })
    assert out == {"tire_pressure": {"fl": 30}}
    assert "not_a_section" not in out
    assert "bogus" not in out["tire_pressure"]


def test_normalize_coerces_numeric_strings_to_float() -> None:
    out = _normalize_fields({"tire_pressure": {"fl": "32", "fr": "30.5"}})
    assert out == {"tire_pressure": {"fl": 32.0, "fr": 30.5}}
    assert isinstance(out["tire_pressure"]["fl"], float)


def test_normalize_keeps_non_numeric_strings_as_is() -> None:
    out = _normalize_fields({"brake": {"bias": "front"}})
    assert out == {"brake": {"bias": "front"}}


def test_normalize_gears_is_list_of_floats() -> None:
    out = _normalize_fields({"gearing": {"final_drive": "3.2", "gears": ["3.5", "2.1", "1.0"]}})
    assert out == {"gearing": {"final_drive": 3.2, "gears": [3.5, 2.1, 1.0]}}
    assert isinstance(out["gearing"]["gears"], list)


def test_normalize_non_dict_returns_empty() -> None:
    assert _normalize_fields(None) == {}
    assert _normalize_fields("nope") == {}


# ---- 3. id validation -------------------------------------------------------

def test_is_valid_setup_id() -> None:
    assert is_valid_setup_id("a3f1b2c4d5e6f7089a1b2c3d4e5f6071") is True
    assert is_valid_setup_id("deadbeef") is False            # too short
    assert is_valid_setup_id("not-a-uuid") is False
    assert is_valid_setup_id("../etc/passwd") is False        # path traversal
    assert is_valid_setup_id("A3F1B2C4D5E6F7089A1B2C3D4E5F6071") is False  # uppercase


# ---- 4. Setup.as_dict -------------------------------------------------------

def test_setup_as_dict_roundtrip() -> None:
    s = Setup(id="a3f1b2c4d5e6f7089a1b2c3d4e5f6071", name="R32 Fuji",
              car="R32", track="Fuji", fields={"tire_pressure": {"fl": 32.0}},
              notes="baseline", created_at=1000.0, updated_at=1000.0)
    d = s.as_dict()
    assert d["id"] == "a3f1b2c4d5e6f7089a1b2c3d4e5f6071"
    assert d["name"] == "R32 Fuji"
    assert d["fields"] == {"tire_pressure": {"fl": 32.0}}
    assert d["created_at"] == 1000.0


if __name__ == "__main__":
    _run_all = [v for k, v in sorted(globals().items())
                if k.startswith("test_") and callable(v)]
    for fn in _run_all:
        fn()
    print("setup data model tests passed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: collection error / `ModuleNotFoundError: No module named 'app.store.setups'`.

- [ ] **Step 3: Write the implementation**

Create `app/store/setups.py`:

```python
"""Setup data model + file store — ROADMAP item 3.

A `Setup` is a car's tuning sheet: the 9 FH6 tuning categories the user fills
in (tire pressure, gearing, alignment, anti-roll bars, springs, damping, aero,
brake, differential). Setups are stored as one JSON file per setup in
`setups/`. The current live session can reference one setup via an in-memory
id (persisted later by ROADMAP item 5's sessions.json).

Per CLAUDE.md, only gearing is derivable from the live UDP stream; the other 8
sections are per-setup metadata the user enters. Live telemetry gives measured
behavior on those dimensions, not the intended values.
"""

from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# The 9 FH6 tuning sections and their canonical field names — single source of
# truth that the item 4 editor UI will also read. Verified against FH6-specific
# guides (see docs/superpowers/specs/2026-07-04-setup-data-model-design.md).
# Per FH6: camber/toe/spring-rate/ride-height/rebound/bump are per-axle
# (front/rear), not per-wheel; tire pressure is per-wheel; caster is single;
# damping uses "bump" (the FH6 slider label), not "compression"; brake tuning
# is bias+pressure (pad/rotor are upgrade parts, not sliders); diff has
# accel/decel lock per axle + a single center_balance for AWD, no preload.
SETUP_FIELD_SCHEMA: dict[str, list[str]] = {
    "tire_pressure":   ["fl", "fr", "rl", "rr"],
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

# uuid4 hex: 32 lowercase hex chars. Used to validate user-supplied ids before
# any filesystem path is constructed, blocking path traversal cold.
_ID_RE = re.compile(r"^[a-f0-9]{32}$")

# Keys kept when re-reading a setup file (guards against hand-edited extras).
_SETUP_KEYS = ("id", "name", "car", "track", "fields", "notes",
               "created_at", "updated_at")


@dataclass
class Setup:
    """One car tuning sheet. `fields` is a subset of SETUP_FIELD_SCHEMA."""

    id: str
    name: str
    car: str = ""
    track: str = ""
    fields: dict = field(default_factory=dict)
    notes: str = ""
    created_at: float = 0.0
    updated_at: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def is_valid_setup_id(setup_id: str) -> bool:
    """True if `setup_id` is a 32-char lowercase hex string (uuid4.hex)."""
    return isinstance(setup_id, str) and bool(_ID_RE.match(setup_id))


def _coerce_number(v):
    """Coerce numeric strings to float; leave everything else untouched."""
    if isinstance(v, bool):
        return v  # don't treat True/False as 1/0
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v)
        except ValueError:
            return v
    return v


def _normalize_fields(fields) -> dict:
    """Keep only known sections/fields from SETUP_FIELD_SCHEMA.

    Unknown sections and unknown field names are silently dropped. Numeric
    strings are coerced to float. `gearing.gears`, if present, is kept as a
    list of coerced numbers. Missing keys are omitted (treated as null on
    read).
    """
    if not isinstance(fields, dict):
        return {}
    out: dict = {}
    for section, field_names in SETUP_FIELD_SCHEMA.items():
        section_in = fields.get(section)
        if not isinstance(section_in, dict):
            continue
        section_out: dict = {}
        for fn in field_names:
            if fn not in section_in:
                continue
            v = section_in[fn]
            if fn == "gears":
                if isinstance(v, list):
                    section_out[fn] = [_coerce_number(x) for x in v]
                continue
            section_out[fn] = _coerce_number(v)
        out[section] = section_out
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS (the `__main__` block runs too if executed directly).

- [ ] **Step 5: Commit**

```bash
git add app/store/setups.py tests/test_setups.py
git commit -m "feat(setups): Setup dataclass, field schema, normalization, id validation"
```

---

### Task 2: SetupStore file CRUD

**Files:**
- Modify: `app/store/setups.py` (append `SetupStore` class)
- Modify: `tests/test_setups.py` (append store tests)

**Interfaces:**
- Consumes: `Setup`, `is_valid_setup_id`, `_normalize_fields`, `_SETUP_KEYS` from Task 1.
- Produces: `SetupStore(setups_dir)` with `list() -> list[dict]`, `get(setup_id) -> dict | None`, `create(data) -> dict` (raises `ValueError` on missing name), `update(setup_id, data) -> dict | None` (raises `ValueError` on empty name), `delete(setup_id) -> bool`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_setups.py` (before the `if __name__ == "__main__":` block — move that block to the very end after all tests):

```python
# ---- 5. SetupStore file CRUD ------------------------------------------------

from app.store.setups import SetupStore


def test_create_get_roundtrip(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "R32 Fuji", "car": "R32", "track": "Fuji",
                            "fields": {"tire_pressure": {"fl": 32}}})
    assert is_valid_setup_id(created["id"])
    assert created["name"] == "R32 Fuji"
    assert created["car"] == "R32"
    assert created["track"] == "Fuji"
    assert created["fields"] == {"tire_pressure": {"fl": 32.0}}
    assert created["created_at"] == created["updated_at"]
    # persisted to disk
    assert (tmp_path / f"{created['id']}.json").exists()
    # get returns the same
    got = store.get(created["id"])
    assert got == created


def test_create_normalizes_fields(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "fields": {
        "tire_pressure": {"fl": "30", "bogus": 1}, "nope": {}}})
    assert created["fields"] == {"tire_pressure": {"fl": 30.0}}


def test_create_requires_name(tmp_path) -> None:
    store = SetupStore(tmp_path)
    try:
        store.create({"car": "R32"})
    except ValueError:
        return
    raise AssertionError("expected ValueError for missing name")


def test_create_empty_name_rejected(tmp_path) -> None:
    store = SetupStore(tmp_path)
    try:
        store.create({"name": "   "})
    except ValueError:
        return
    raise AssertionError("expected ValueError for blank name")


def test_list_returns_summaries_sorted_desc(tmp_path) -> None:
    store = SetupStore(tmp_path)
    a = store.create({"name": "a"})
    b = store.create({"name": "b"})
    c = store.create({"name": "c"})
    summaries = store.list()
    assert len(summaries) == 3
    # newest first (c created last)
    assert summaries[0]["id"] == c["id"]
    assert summaries[-1]["id"] == a["id"]
    # summaries have no `fields`
    for s in summaries:
        assert set(s) == {"id", "name", "car", "track", "notes", "updated_at"}
        assert "fields" not in s


def test_update_preserves_id_and_created_at(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "old", "fields": {"aero": {"front_downforce": 100}}})
    updated = store.update(created["id"], {"name": "new",
                                           "fields": {"aero": {"rear_downforce": 200}}})
    assert updated is not None
    assert updated["id"] == created["id"]
    assert updated["created_at"] == created["created_at"]
    assert updated["updated_at"] >= created["updated_at"]
    assert updated["name"] == "new"
    # fields replaced, not merged
    assert updated["fields"] == {"aero": {"rear_downforce": 200.0}}
    assert "front_downforce" not in updated["fields"]["aero"]


def test_update_missing_returns_none(tmp_path) -> None:
    store = SetupStore(tmp_path)
    assert store.update("a3f1b2c4d5e6f7089a1b2c3d4e5f6071", {"name": "x"}) is None


def test_update_empty_name_rejected(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "ok"})
    try:
        store.update(created["id"], {"name": ""})
    except ValueError:
        return
    raise AssertionError("expected ValueError for empty name on update")


def test_delete(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x"})
    assert store.delete(created["id"]) is True
    assert store.get(created["id"]) is None
    assert store.delete(created["id"]) is False  # already gone


def test_bad_id_rejection(tmp_path) -> None:
    store = SetupStore(tmp_path)
    for bad in ("../etc/passwd", "not-a-uuid", "deadbeef"):
        assert store.get(bad) is None
        assert store.update(bad, {"name": "x"}) is None
        assert store.delete(bad) is False
    # no files were created for bad ids
    assert list(tmp_path.glob("*")) == []


def test_atomic_write_leaves_no_tmp(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x"})
    assert list(tmp_path.glob("*.tmp")) == []
    data = json.loads((tmp_path / f"{created['id']}.json").read_text())
    assert data["name"] == "x"


def test_store_creates_dir_if_missing(tmp_path) -> None:
    sub = tmp_path / "nested" / "setups"
    store = SetupStore(sub)
    assert sub.exists()
    store.create({"name": "x"})
    assert sub.is_dir()
```

Now move the `if __name__ == "__main__":` block to the end of the file (after all the tests above). Replace the existing `__main__` block with one that collects every `test_*` function in the module:

```python
if __name__ == "__main__":
    _run_all = [v for k, v in sorted(globals().items())
                if k.startswith("test_") and callable(v)]
    for fn in _run_all:
        # tmp_path tests need a temp dir; make one per call
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            try:
                fn(d)
                continue
            except TypeError:
                pass
            fn()
    print("setup data model tests passed")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — `ImportError: cannot import name 'SetupStore' from 'app.store.setups'`.

- [ ] **Step 3: Write the implementation**

Append to `app/store/setups.py`:

```python
class SetupStore:
    """File-CRUD store for setups. One JSON file per setup in `setups_dir`."""

    def __init__(self, setups_dir: str | Path) -> None:
        self._dir = Path(setups_dir)
        os.makedirs(self._dir, exist_ok=True)

    # ---- public API --------------------------------------------------------

    def list(self) -> list[dict]:
        """Summaries (no `fields`), sorted by updated_at descending."""
        summaries: list[dict] = []
        for p in self._dir.glob("*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            summaries.append({
                "id": data.get("id", p.stem),
                "name": data.get("name", ""),
                "car": data.get("car", ""),
                "track": data.get("track", ""),
                "notes": data.get("notes", ""),
                "updated_at": data.get("updated_at", 0.0),
            })
        summaries.sort(key=lambda s: s["updated_at"], reverse=True)
        return summaries

    def get(self, setup_id: str) -> Optional[dict]:
        """Full setup dict, or None if missing / invalid id."""
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return {k: data.get(k) for k in _SETUP_KEYS if k in data} | data \
            if False else {k: data[k] for k in _SETUP_KEYS if k in data}

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
            created_at=now,
            updated_at=now,
        )
        self._write(setup)
        return setup.as_dict()

    def update(self, setup_id: str, data: dict) -> Optional[dict]:
        """Update an existing setup. None if not found / invalid id.
        Raises ValueError if a provided name is blank."""
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            existing = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        merged = {k: existing[k] for k in _SETUP_KEYS if k in existing}
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
        merged["id"] = existing.get("id", setup_id)
        merged["created_at"] = existing.get("created_at", 0.0)
        merged["updated_at"] = time.time()
        setup = Setup(**{k: merged[k] for k in _SETUP_KEYS})
        self._write(setup)
        return setup.as_dict()

    def delete(self, setup_id: str) -> bool:
        """True if deleted, False if not found / invalid id."""
        p = self._path(setup_id)
        if p is None or not p.exists():
            return False
        try:
            p.unlink()
            return True
        except OSError:
            return False

    # ---- internals ---------------------------------------------------------

    def _path(self, setup_id: str) -> Optional[Path]:
        if not is_valid_setup_id(setup_id):
            return None
        return self._dir / f"{setup_id}.json"

    def _write(self, setup: Setup) -> None:
        target = self._dir / f"{setup.id}.json"
        tmp = self._dir / f"{setup.id}.json.tmp"
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(setup.as_dict(), f, indent=2)
            f.write("\n")
        os.replace(tmp, target)
```

Note: the `get` method's first return line is convoluted. Replace it with the clean version — the body of `get` should be:

```python
    def get(self, setup_id: str) -> Optional[dict]:
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return {k: data[k] for k in _SETUP_KEYS if k in data}
```

(Use this clean version; the convoluted line above was a typo to discard.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS. Also run standalone: `conda run -n fh6tuning python tests/test_setups.py` → prints `setup data model tests passed`.

- [ ] **Step 5: Commit**

```bash
git add app/store/setups.py tests/test_setups.py
git commit -m "feat(setups): SetupStore file CRUD with atomic writes + bad-id guard"
```

---

### Task 3: Config, env, gitignore, gitkeep, store exports

**Files:**
- Modify: `app/config.py`
- Modify: `.env.example`
- Modify: `.gitignore`
- Create: `setups/.gitkeep`
- Modify: `app/store/__init__.py`
- Modify: `tests/test_setups.py` (append a config/export test)

**Interfaces:**
- Produces: `Settings.setups_dir` (default `"./setups"`); `app.store` exports `Setup`, `SetupStore`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_setups.py`:

```python
# ---- 6. config + package exports -------------------------------------------

def test_settings_has_setups_dir_default() -> None:
    from app.config import Settings
    s = Settings()
    assert s.setups_dir == "./setups"


def test_store_package_exports() -> None:
    import app.store as store_pkg
    assert hasattr(store_pkg, "Setup")
    assert hasattr(store_pkg, "SetupStore")
    assert "Setup" in store_pkg.__all__
    assert "SetupStore" in store_pkg.__all__
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'setups_dir'` and export assertions fail.

- [ ] **Step 3: Write the implementation**

In `app/config.py`, add after the `log_format` field (inside `Settings`):

```python
    # Setup library (one JSON file per setup)
    setups_dir: str = "./setups"
```

In `.env.example`, append at the end:

```
# ---- Setup library ----
# Where setup JSON files are stored (one file per setup).
SETUPS_DIR=./setups
```

In `.gitignore`, add a section after the `# Telemetry logs` block:

```
# Setup library (generated at runtime; one JSON file per user setup)
setups/
```

Create `setups/.gitkeep` (empty file):

```bash
mkdir -p setups && touch setups/.gitkeep
```

In `app/store/__init__.py`, replace the contents with:

```python
"""Persistence layer: rolling buffer + file logger + setup store."""

from .buffer import TelemetryBuffer
from .logger import TelemetryLogger
from .setups import Setup, SetupStore

__all__ = ["TelemetryBuffer", "TelemetryLogger", "Setup", "SetupStore"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py .env.example .gitignore setups/.gitkeep app/store/__init__.py tests/test_setups.py
git commit -m "feat(setups): SETUPS_DIR config, gitignore, package exports"
```

---

### Task 4: API routes (setups CRUD + session link)

**Files:**
- Modify: `app/api/routes.py`
- Modify: `tests/test_setups.py` (append API tests)

**Interfaces:**
- Consumes: `SetupStore` from `app.store.setups`; `is_valid_setup_id` for the 400-vs-404 split on `POST /api/session/setup`.
- Produces: seven routes — `GET /api/setups`, `GET /api/setups/{setup_id}`, `POST /api/setups`, `PUT /api/setups/{setup_id}`, `DELETE /api/setups/{setup_id}`, `POST /api/session/setup`, `GET /api/session/setup`. All read `router.state["setups"]` and `router.state["current_setup_id"]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_setups.py`:

```python
# ---- 7. API routes ---------------------------------------------------------

def _setup_router_state_with_store(store: SetupStore) -> None:
    from app.api import routes
    routes.router.state = {"setups": store, "current_setup_id": None}


def _setup_router_state_no_store() -> None:
    from app.api import routes
    routes.router.state = {}


def test_api_setups_list_and_create() -> None:
    from app.api.routes import setups_list, setup_create
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        out = asyncio.run(setups_list())
        assert out == {"setups": []}
        created = asyncio.run(setup_create({"name": "R32", "car": "R32"}))
        assert is_valid_setup_id(created["id"])
        out = asyncio.run(setups_list())
        assert len(out["setups"]) == 1
        assert out["setups"][0]["name"] == "R32"


def test_api_setup_create_400_missing_name() -> None:
    from app.api.routes import setup_create
    from fastapi.responses import JSONResponse
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        res = asyncio.run(setup_create({"car": "x"}))
        assert isinstance(res, JSONResponse)
        assert res.status_code == 400


def test_api_setup_detail_found_and_404() -> None:
    from app.api.routes import setup_detail, setup_create
    from fastapi.responses import JSONResponse
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        created = asyncio.run(setup_create({"name": "x"}))
        got = asyncio.run(setup_detail(created["id"]))
        assert isinstance(got, dict)
        assert got["id"] == created["id"]
        missing = asyncio.run(setup_detail("a3f1b2c4d5e6f7089a1b2c3d4e5f6071"))
        assert isinstance(missing, JSONResponse)
        assert missing.status_code == 404


def test_api_setup_update_and_delete() -> None:
    from app.api.routes import setup_create, setup_update, setup_delete
    from fastapi.responses import JSONResponse
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        created = asyncio.run(setup_create({"name": "old"}))
        updated = asyncio.run(setup_update(created["id"], {"name": "new"}))
        assert isinstance(updated, dict)
        assert updated["name"] == "new"
        # 404 on missing
        miss = asyncio.run(setup_update("a3f1b2c4d5e6f7089a1b2c3d4e5f6071", {"name": "x"}))
        assert isinstance(miss, JSONResponse) and miss.status_code == 404
        # delete
        deleted = asyncio.run(setup_delete(created["id"]))
        assert deleted == {"deleted": created["id"]}
        miss2 = asyncio.run(setup_delete(created["id"]))
        assert isinstance(miss2, JSONResponse) and miss2.status_code == 404


def test_api_session_attach_and_read() -> None:
    from app.api.routes import (
        session_current_setup, session_attach_setup, setup_create,
    )
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        # initially nothing
        out = asyncio.run(session_current_setup())
        assert out == {"setup_id": None, "setup": None}
        # attach
        created = asyncio.run(setup_create({"name": "R32"}))
        attached = asyncio.run(session_attach_setup({"setup_id": created["id"]}))
        assert attached["setup_id"] == created["id"]
        assert attached["setup"]["name"] == "R32"
        # read back
        out = asyncio.run(session_current_setup())
        assert out["setup_id"] == created["id"]
        assert out["setup"]["name"] == "R32"
        # detach with null
        detached = asyncio.run(session_attach_setup({"setup_id": None}))
        assert detached == {"setup_id": None, "setup": None}
        assert asyncio.run(session_current_setup()) == {"setup_id": None, "setup": None}


def test_api_session_attach_400_bad_format() -> None:
    from app.api.routes import session_attach_setup
    from fastapi.responses import JSONResponse
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        for bad in ("not-a-uuid", "deadbeef", "../etc/passwd"):
            res = asyncio.run(session_attach_setup({"setup_id": bad}))
            assert isinstance(res, JSONResponse) and res.status_code == 400, bad


def test_api_session_attach_404_valid_but_missing() -> None:
    from app.api.routes import session_attach_setup
    from fastapi.responses import JSONResponse
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        res = asyncio.run(session_attach_setup(
            {"setup_id": "a3f1b2c4d5e6f7089a1b2c3d4e5f6071"}))
        assert isinstance(res, JSONResponse) and res.status_code == 404


def test_api_session_dangling_after_delete() -> None:
    from app.api.routes import (
        session_attach_setup, session_current_setup, setup_create, setup_delete,
    )
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = SetupStore(d)
        _setup_router_state_with_store(store)
        created = asyncio.run(setup_create({"name": "x"}))
        asyncio.run(session_attach_setup({"setup_id": created["id"]}))
        asyncio.run(setup_delete(created["id"]))
        out = asyncio.run(session_current_setup())
        assert out["setup_id"] == created["id"]   # dangling id stays
        assert out["setup"] is None               # but the setup is gone


def test_api_setups_503_when_store_missing() -> None:
    from app.api.routes import setups_list
    from fastapi.responses import JSONResponse
    _setup_router_state_no_store()
    res = asyncio.run(setups_list())
    assert isinstance(res, JSONResponse) and res.status_code == 503
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: FAIL — `ImportError: cannot import name 'setups_list' from 'app.api.routes'`.

- [ ] **Step 3: Write the implementation**

In `app/api/routes.py`, add `is_valid_setup_id` to the existing store import. Find the import block at the top and add after the existing `from ..store...` imports (the file currently imports `InsightsService`, `TelemetryFrame`, `TelemetryServer` from `..`-packages; add a new line):

```python
from ..store.setups import is_valid_setup_id
```

Then append at the end of `app/api/routes.py`:

```python
# ---- setup library ----------------------------------------------------------
# ROADMAP item 3: setups stored as JSON in setups/; the current live session
# can reference one setup via an in-memory id (persisted by item 5's
# sessions.json). State lives on router.state["setups"] + ["current_setup_id"].


@router.get("/api/setups")
async def setups_list() -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    return {"setups": store.list()}


@router.get("/api/setups/{setup_id}")
async def setup_detail(setup_id: str):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    out = store.get(setup_id)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return out


@router.post("/api/setups")
async def setup_create(payload: dict | None = None) -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    try:
        return store.create(payload or {})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)


@router.put("/api/setups/{setup_id}")
async def setup_update(setup_id: str, payload: dict | None = None):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    try:
        out = store.update(setup_id, payload or {})
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return out


@router.delete("/api/setups/{setup_id}")
async def setup_delete(setup_id: str):
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    if not store.delete(setup_id):
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    return {"deleted": setup_id}


@router.post("/api/session/setup")
async def session_attach_setup(payload: dict | None = None) -> dict:
    store = router.state.get("setups")
    if store is None:
        return JSONResponse({"error": "setups store not initialized"}, status_code=503)
    setup_id = (payload or {}).get("setup_id")
    if setup_id is None:
        router.state["current_setup_id"] = None
        return {"setup_id": None, "setup": None}
    # Validate format BEFORE store lookup so bad format = 400, missing = 404.
    if not is_valid_setup_id(setup_id):
        return JSONResponse(
            {"error": "setup_id must be a 32-char lowercase hex string"},
            status_code=400,
        )
    out = store.get(setup_id)
    if out is None:
        return JSONResponse({"error": f"setup {setup_id} not found"}, status_code=404)
    router.state["current_setup_id"] = setup_id
    return {"setup_id": setup_id, "setup": out}


@router.get("/api/session/setup")
async def session_current_setup() -> dict:
    store = router.state.get("setups")
    setup_id = router.state.get("current_setup_id")
    if not setup_id:
        return {"setup_id": None, "setup": None}
    setup = store.get(setup_id) if store is not None else None
    return {"setup_id": setup_id, "setup": setup}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py -q`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/routes.py tests/test_setups.py
git commit -m "feat(setups): REST CRUD + current-session setup link routes"
```

---

### Task 5: Wire SetupStore into main.py lifespan

**Files:**
- Modify: `app/main.py`
- Modify: `tests/test_setups.py` (append a wiring smoke test)

**Interfaces:**
- Consumes: `SetupStore` from `app.store.setups`; `Settings.setups_dir` from `app.config`.
- Produces: `router.state["setups"]` (a `SetupStore`) and `router.state["current_setup_id"]` (None) set during `lifespan`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_setups.py`:

```python
# ---- 8. main.py wiring -----------------------------------------------------

def test_create_app_has_setup_routes() -> None:
    from app.main import create_app
    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/setups" in paths
    assert "/api/session/setup" in paths
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `conda run -n fh6tuning python -m pytest tests/test_setups.py::test_create_app_has_setup_routes -q`
Expected: may already PASS (routes are registered at import time, before lifespan wiring). If it passes, that's fine — it confirms the routes are mounted. The real wiring (lifespan creating the store) is verified by the manual smoke check in Step 4.

- [ ] **Step 3: Write the implementation**

In `app/main.py`, add `SetupStore` to the existing store import line. Change:

```python
from .store.buffer import TelemetryBuffer
from .store.laps import LapTracker
from .store.logger import TelemetryLogger
```

to:

```python
from .store.buffer import TelemetryBuffer
from .store.laps import LapTracker
from .store.logger import TelemetryLogger
from .store.setups import SetupStore
```

In `lifespan`, after `laps = LapTracker(maxlen=200)` and before/after the `logger = TelemetryLogger(...)` line, add:

```python
    setups = SetupStore(setups_dir=settings.setups_dir)
```

Then in the `router.state = {...}` dict, add two keys so it reads:

```python
    router.state = {
        "telemetry_server": telemetry,
        "insights": insights,
        "buffer": buffer,
        "laps": laps,
        "logger": logger,
        "settings": settings,
        "setups": setups,
        "current_setup_id": None,
    }
```

- [ ] **Step 4: Verify the app boots and the store is wired**

Smoke check (does not bind the UDP port — just imports + constructs):

```bash
conda run -n fh6tuning python -c "from app.main import create_app; app = create_app(); print('ok', app.title)"
```
Expected: `ok horizon6tuning`

Then run the full test suite to confirm nothing regressed:

```bash
conda run -n fh6tuning python -m pytest tests/ -q
```
Expected: all tests PASS (parser, laps, logger, setups).

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_setups.py
git commit -m "feat(setups): wire SetupStore into lifespan + router.state"
```

---

### Task 6: Update ROADMAP (item 4 field list + item 3 status marker)

**Files:**
- Modify: `ROADMAP.md`

**Interfaces:**
- Consumes: the corrected FH6 field schema from the spec / `SETUP_FIELD_SCHEMA`.

- [ ] **Step 1: Update item 3's status marker**

In `ROADMAP.md`, change item 3's title line from:

```
3. **Setup data model** `[in progress]` — define a `Setup` as
```

to:

```
3. **Setup data model** `[done · branch feature/setup-data-model]` — define a `Setup` as
```

- [ ] **Step 2: Correct item 4's field list to FH6 reality**

Replace item 4's bullet list. The current text is:

```
4. **Setup editor (v1, all 9 categories)** — a single page in the dashboard
   with 9 collapsible sections the user fills in:
   - **Tire pressure** — cold pressure FL/FR/RL/RR (PSI)
   - **Gearing** — final drive, individual gear ratios (1st..top)
   - **Alignment** — camber FL/FR/RL/RR, toe FL/FR/RL/RR, caster FL/FR
   - **Anti-roll bars** — ARB front, ARB rear (stiffness)
   - **Springs** — spring rate FL/FR/RL/RR, ride height FL/FR/RL/RR
   - **Damping** — rebound FL/FR/RL/RR, compression FL/FR/RL/RR
   - **Aero** — front downforce, rear downforce
   - **Brake** — brake bias, pad compound, rotor size
   - **Differential** — accel lock, decel lock, preload (front/rear/center)
```

Replace with (FH6-verified — see `docs/superpowers/specs/2026-07-04-setup-data-model-design.md`):

```
4. **Setup editor (v1, all 9 categories)** — a single page in the dashboard
   with 9 collapsible sections the user fills in (FH6-verified field shapes;
   the canonical field list lives in `app/store/setups.py::SETUP_FIELD_SCHEMA`):
   - **Tire pressure** — cold pressure FL/FR/RL/RR (PSI, per-wheel)
   - **Gearing** — final drive, individual gear ratios (1st..top, list)
   - **Alignment** — camber front/rear, toe front/rear, caster (single)
   - **Anti-roll bars** — ARB front, ARB rear (stiffness)
   - **Springs** — spring rate front/rear, ride height front/rear
   - **Damping** — rebound front/rear, bump front/rear (FH6 labels
     compression "bump")
   - **Aero** — front downforce, rear downforce
   - **Brake** — brake bias, brake pressure (pad compound / rotor size are
     upgrade parts, not tuning sliders)
   - **Differential** — accel lock front/rear, decel lock front/rear,
     center balance (AWD only; FH6 has no diff preload)
```

- [ ] **Step 3: Verify the diff is clean**

```bash
git diff ROADMAP.md
```
Expected: only item 3's marker and item 4's bullet list changed.

- [ ] **Step 4: Commit**

```bash
git add ROADMAP.md
git commit -m "docs(roadmap): mark item 3 done; correct item 4 field list to FH6"
```

---

## Final verification

After Task 6, run the whole suite once more and confirm the branch is clean:

```bash
conda run -n fh6tuning python -m pytest tests/ -q
git status
git log --oneline main..HEAD
```

Expected: all tests pass, working tree clean, six commits on `feature/setup-data-model` ahead of `main`.

## Self-Review (run before execution)

- **Spec coverage:** spec sections 1–5 map to Tasks 1–5; spec's ROADMAP update maps to Task 6. The data model, field schema, store, API, wiring, and tests are all covered. The session-link in-memory behavior (attach/detach/dangling) is covered by Task 4 tests.
- **Placeholder scan:** no TBD/TODO; every code step contains real code; every test step contains real assertions.
- **Type consistency:** `SetupStore` method names (`list`/`get`/`create`/`update`/`delete`) and `is_valid_setup_id` are used identically across Tasks 1–4. `SETUP_FIELD_SCHEMA` field names in tests (Task 1) match the implementation and the ROADMAP update (Task 6). Route function names (`setups_list`, `setup_detail`, `setup_create`, `setup_update`, `setup_delete`, `session_attach_setup`, `session_current_setup`) match between Task 4 tests and implementation.
- **Known wrinkle:** the `get` method in Task 2 Step 3 contains a deliberate convoluted line followed by the clean version to use — implementer must use the clean version. (Flagged inline.)