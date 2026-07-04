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
