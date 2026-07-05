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
        "tire_pressure": {"front": 30, "bogus": 99},
        "not_a_section": {"x": 1},
    })
    assert out == {"tire_pressure": {"front": 30}}
    assert "not_a_section" not in out
    assert "bogus" not in out["tire_pressure"]


def test_normalize_coerces_numeric_strings_to_float() -> None:
    out = _normalize_fields({"tire_pressure": {"front": "32", "rear": "30.5"}})
    assert out == {"tire_pressure": {"front": 32.0, "rear": 30.5}}
    assert isinstance(out["tire_pressure"]["front"], float)


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
              car="R32", track="Fuji", fields={"tire_pressure": {"front": 32.0}},
              notes="baseline", created_at=1000.0, updated_at=1000.0)
    d = s.as_dict()
    assert d["id"] == "a3f1b2c4d5e6f7089a1b2c3d4e5f6071"
    assert d["name"] == "R32 Fuji"
    assert d["fields"] == {"tire_pressure": {"front": 32.0}}
    assert d["created_at"] == 1000.0


# ---- 5. SetupStore file CRUD ------------------------------------------------

from app.store.setups import SetupStore


def test_create_get_roundtrip(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "R32 Fuji", "car": "R32", "track": "Fuji",
                            "fields": {"tire_pressure": {"front": 32}}})
    assert is_valid_setup_id(created["id"])
    assert created["name"] == "R32 Fuji"
    assert created["car"] == "R32"
    assert created["track"] == "Fuji"
    assert created["fields"] == {"tire_pressure": {"front": 32.0}}
    assert created["created_at"] == created["updated_at"]
    # persisted to disk
    assert (tmp_path / f"{created['id']}.json").exists()
    # get returns the same
    got = store.get(created["id"])
    assert got == created


def test_create_normalizes_fields(tmp_path) -> None:
    store = SetupStore(tmp_path)
    created = store.create({"name": "x", "fields": {
        "tire_pressure": {"front": "30", "bogus": 1}, "nope": {}}})
    assert created["fields"] == {"tire_pressure": {"front": 30.0}}


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


# ---- 8. main.py wiring -----------------------------------------------------

def test_create_app_has_setup_routes() -> None:
    from app.api import routes
    paths = {getattr(r, "path", None) for r in routes.router.routes}
    assert "/api/setups" in paths
    assert "/api/session/setup" in paths
    assert "/api/setups/{setup_id}" in paths


def test_e2e_schema_and_unit_toggle_via_http(tmp_path) -> None:
    """End-to-end via the live HTTP path.

    (a) Catches the route-order bug where /api/setups/{setup_id} would shadow
        /api/setups/schema and return 404. Previous tests called
        setups_schema() directly and missed this.
    (b) Pins the SetupStore.update contract: PUT with old-unit fields +
        new units must produce a single, correct conversion. The frontend
        unit-toggle path relies on this.

    Combined into one test because each TestClient(create_app()) binds the
    UDP listener in its lifespan, and pytest doesn't release the port fast
    enough between consecutive TestClient instances.
    """
    import os
    os.environ["SETUPS_DIR"] = str(tmp_path)
    try:
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)
        from fastapi.testclient import TestClient
        with TestClient(_main.create_app()) as c:
            # (a) schema endpoint
            r = c.get("/api/setups/schema")
            assert r.status_code == 200, r.text
            body = r.json()
            assert len(body["sections"]) == 9
            assert body["sections"][0]["key"] == "tire_pressure"
            assert [f["key"] for f in body["sections"][0]["fields"]] == ["front", "rear"]

            # (b) unit toggle round-trip via HTTP
            r = c.post("/api/setups", json={
                "name": "e2e", "units": "english",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            sid = r.json()["id"]
            r = c.put(f"/api/setups/{sid}", json={
                "units": "metric",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            body = r.json()
            assert body["units"] == "metric"
            # Single conversion: 32 PSI -> 2.21 bar
            # (NOT 32 * 0.0689476^2 = 0.152 — that would be a double conversion)
            assert abs(body["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
            # 500 lb/in -> 8.93 kgf/mm
            assert abs(body["fields"]["springs"]["spring_rate_front"] - 500.0 * 0.017857) < 0.01
            # 5 in -> 12.7 cm
            assert abs(body["fields"]["springs"]["ride_height_front"] - 5.0 * 2.54) < 0.01
            # File on disk reflects the single conversion
            raw = json.loads((tmp_path / f"{sid}.json").read_text())
            assert raw["units"] == "metric"
            assert abs(raw["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
    finally:
        os.environ.pop("SETUPS_DIR", None)
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)


def test_e2e_save_after_unit_toggle_back_converts(tmp_path) -> None:
    """R2-4 contract: the frontend's unit toggle is in-memory only; the
    user must click Save. The Save back-converts FORM.fields from the new
    unit back to the OLD (stored) unit before sending, so the wire
    payload satisfies the SetupStore.update contract ("sent fields are
    in the OLD unit"). The backend then runs its own OLD->new conversion.

    This test simulates that exact contract: the wire payload contains
    ENGLISH values (32 PSI, 500 lb/in, 5 in) but `units: "metric"`. The
    disk should end up in metric with converted values.

    A separate UDP port from `test_e2e_schema_and_unit_toggle_via_http` is
    used so the two TestClient lifespans (each binding the listener) don't
    collide on port 9999 — the OS doesn't release a closed UDP socket fast
    enough between back-to-back TestClient instances (see the note in the
    sibling test above).
    """
    import os
    os.environ["SETUPS_DIR"] = str(tmp_path)
    os.environ["UDP_PORT"] = "47809"
    try:
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)
        from fastapi.testclient import TestClient
        with TestClient(_main.create_app()) as c:
            r = c.post("/api/setups", json={
                "name": "r2-4", "units": "english",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            sid = r.json()["id"]

            # Simulate: user toggles unit to metric (in-memory), then clicks
            # Save. The Save back-converts FORM.fields to the OLD (english)
            # unit, so the wire payload fields ARE in english even though
            # `units: "metric"` says the new unit.
            r = c.put(f"/api/setups/{sid}", json={
                "units": "metric",
                "fields": {
                    "tire_pressure": {"front": 32.0, "rear": 30.0},   # english PSI
                    "springs": {"spring_rate_front": 500.0, "ride_height_front": 5.0},
                },
            })
            assert r.status_code == 200
            body = r.json()
            assert body["units"] == "metric"
            # Single backend conversion for all three convertible families:
            # 32 PSI -> 2.21 bar
            assert abs(body["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
            # 500 lb/in -> 8.93 kgf/mm
            assert abs(body["fields"]["springs"]["spring_rate_front"] - 500.0 * 0.017857) < 0.01
            # 5 in -> 12.7 cm
            assert abs(body["fields"]["springs"]["ride_height_front"] - 5.0 * 2.54) < 0.01
            # File on disk reflects the conversion
            raw = json.loads((tmp_path / f"{sid}.json").read_text())
            assert raw["units"] == "metric"
            assert abs(raw["fields"]["tire_pressure"]["front"] - 32.0 * 0.0689476) < 0.01
            assert abs(raw["fields"]["springs"]["spring_rate_front"] - 500.0 * 0.017857) < 0.01
            assert abs(raw["fields"]["springs"]["ride_height_front"] - 5.0 * 2.54) < 0.01
    finally:
        os.environ.pop("SETUPS_DIR", None)
        os.environ.pop("UDP_PORT", None)
        from importlib import reload
        from app import config as _config, main as _main
        reload(_config)
        reload(_main)


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
