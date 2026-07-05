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
        p = self._path(setup_id)
        if p is None or not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return {k: data[k] for k in _SETUP_KEYS if k in data}

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
