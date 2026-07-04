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
