"""Per-lap segmentation tests — ROADMAP item 2.

Verifies lap-boundary detection (lap_number increment, current_lap reset,
session edges), glitch debounce, per-lap summary math, bounded memory, and
the three HTTP routes.

Run:  python -m pytest tests/test_laps.py -q
   or python tests/test_laps.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store.laps import LapTracker
from app.telemetry.frame import TelemetryFrame


def _frame(**overrides) -> TelemetryFrame:
    """Build a TelemetryFrame with sane defaults; override any field."""
    defaults = dict(
        is_race_on=1,
        current_engine_rpm=5000.0,
        acceleration_x=0.0,
        acceleration_y=0.0,
        acceleration_z=0.0,
        tire_combined_slip_fl=0.0,
        tire_combined_slip_fr=0.0,
        tire_combined_slip_rl=0.0,
        tire_combined_slip_rr=0.0,
        speed=0.0,
        fuel=100.0,
        boost=0.0,
        gear=3,
        lap_number=1,
        current_lap=0.0,
        best_lap=None,
        last_lap=None,
        distance_traveled=0.0,
        race_position=1,
        tire_temp_fl=80.0,
        tire_temp_fr=80.0,
        tire_temp_rl=80.0,
        tire_temp_rr=80.0,
        received_at_ns=0.0,
    )
    defaults.update(overrides)
    return TelemetryFrame(**defaults)


# ---- 1. lap_number increment ------------------------------------------------

def test_lap_number_increment() -> None:
    t = LapTracker()
    # race on -> pending (debounce), 2nd frame starts lap 1
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=0.0, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=10.0, received_at_ns=1_100_000_000))
    # lap_number increments -> pending boundary
    t.on_frame(_frame(is_race_on=1, lap_number=2, current_lap=0.1, received_at_ns=1_200_000_000))
    # confirm -> finalize lap 1, start lap 2
    t.on_frame(_frame(is_race_on=1, lap_number=2, current_lap=0.2, received_at_ns=1_300_000_000))

    completed = t.completed()
    assert len(completed) == 1, completed
    assert completed[0]["lap_number"] == 1
    assert completed[0]["ended_at_ns"] is not None
    assert completed[0]["duration_s"] is not None
    current = t.current()
    assert current is not None
    assert current["lap_number"] == 2
    assert current["ended_at_ns"] is None
    assert current["duration_s"] is None


# ---- 2. current_lap reset (lap_number unchanged) ----------------------------

def test_current_lap_reset_boundary() -> None:
    t = LapTracker()
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=0.0, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=50.0, received_at_ns=1_100_000_000))
    # current_lap wraps to a small value while lap_number unchanged
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=0.1, received_at_ns=1_200_000_000))
    # confirm
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=0.2, received_at_ns=1_300_000_000))

    completed = t.completed()
    assert len(completed) == 1, completed
    assert completed[0]["lap_number"] == 1
    current = t.current()
    assert current is not None
    assert current["lap_number"] == 1


# ---- 3. is_race_on off -> on ------------------------------------------------

def test_race_off_then_on() -> None:
    t = LapTracker()
    # start lap 1 (2 race-on frames to clear debounce)
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_100_000_000))
    # race off -> pending, then confirm -> finalize lap 1, no current
    t.on_frame(_frame(is_race_on=0, lap_number=1, received_at_ns=1_200_000_000))
    t.on_frame(_frame(is_race_on=0, lap_number=1, received_at_ns=1_300_000_000))
    assert t.current() is None
    assert len(t.completed()) == 1
    # race on -> pending, then confirm -> start lap 2
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_400_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_500_000_000))
    assert t.current() is not None
    assert t.current()["lap_number"] == 1
    assert len(t.completed()) == 1  # still just lap 1 finalized


# ---- 4. is_race_on on -> off (no new lap) -----------------------------------

def test_race_on_to_off_no_new_lap() -> None:
    t = LapTracker()
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_100_000_000))
    t.on_frame(_frame(is_race_on=0, lap_number=1, received_at_ns=1_200_000_000))
    t.on_frame(_frame(is_race_on=0, lap_number=1, received_at_ns=1_300_000_000))

    assert t.current() is None
    completed = t.completed()
    assert len(completed) == 1
    assert completed[0]["lap_number"] == 1
    assert completed[0]["ended_at_ns"] is not None


# ---- 5. glitch debounce -----------------------------------------------------

def test_glitch_debounce_no_finalize() -> None:
    t = LapTracker()
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=0.0, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=10.0, received_at_ns=1_100_000_000))
    # glitch: lap_number bumps to 2 for one frame
    t.on_frame(_frame(is_race_on=1, lap_number=2, current_lap=0.1, received_at_ns=1_200_000_000))
    # reverts -> pending cancelled, lap 1 continues
    t.on_frame(_frame(is_race_on=1, lap_number=1, current_lap=10.5, received_at_ns=1_300_000_000))

    assert t.completed() == [], "no lap should be finalized on a glitch"
    current = t.current()
    assert current is not None
    assert current["lap_number"] == 1
    # lap 1 absorbed the glitch frame and the revert frame
    assert current["frame_count"] >= 3


# ---- 6. summary math --------------------------------------------------------

def test_summary_math() -> None:
    t = LapTracker()
    # frame 1: race_on pending (not counted in any lap)
    t.on_frame(_frame(is_race_on=1, speed=0.0, fuel=100.0, received_at_ns=1_000_000_000))
    # frame 2: confirm -> lap 1 starts here
    t.on_frame(_frame(is_race_on=1, speed=10.0, fuel=100.0, received_at_ns=2_000_000_000))
    # frame 3: mid-lap
    t.on_frame(_frame(is_race_on=1, speed=20.0, fuel=90.0, received_at_ns=3_000_000_000))
    # frame 4: race off -> pending, counts toward lap 1
    t.on_frame(_frame(is_race_on=0, speed=30.0, fuel=80.0, received_at_ns=4_000_000_000))
    # frame 5: confirm race off -> finalize lap 1 (ended_at = frame 4 ns)
    t.on_frame(_frame(is_race_on=0, speed=30.0, fuel=80.0, received_at_ns=5_000_000_000))

    completed = t.completed()
    assert len(completed) == 1
    lap = completed[0]
    s = lap["summary"]

    # speeds in lap: 10, 20, 30 m/s -> 36, 72, 108 kmh
    assert s["speed_kmh"] == {"avg": 72.0, "min": 36.0, "max": 108.0}
    # lap_time = (ended_at - started_at) = (4e9 - 2e9) / 1e9 = 2.0
    assert lap["duration_s"] == 2.0
    assert s["lap_time"] == 2.0
    # fuel_used = first_fuel - last_fuel = 100 - 80 = 20
    assert s["fuel_used"] == 20.0
    assert lap["frame_count"] == 3


# ---- 7. API routes ----------------------------------------------------------

def _setup_router_state(tracker: LapTracker) -> None:
    from app.api import routes
    routes.router.state = {"laps": tracker}


def test_api_laps_endpoint() -> None:
    from app.api.routes import laps_list, lap_detail
    t = LapTracker()
    # build one completed lap + one in-progress
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_100_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=2, received_at_ns=1_200_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=2, received_at_ns=1_300_000_000))

    _setup_router_state(t)
    out = asyncio.run(laps_list())
    assert "current" in out
    assert "completed" in out
    assert out["current"] is not None
    assert out["current"]["lap_number"] == 2
    assert len(out["completed"]) == 1
    assert out["completed"][0]["lap_number"] == 1


def test_api_lap_detail_found_and_404() -> None:
    from app.api.routes import lap_detail
    from fastapi.responses import JSONResponse
    t = LapTracker()
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_000_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=1, received_at_ns=1_100_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=2, received_at_ns=1_200_000_000))
    t.on_frame(_frame(is_race_on=1, lap_number=2, received_at_ns=1_300_000_000))

    _setup_router_state(t)
    found = asyncio.run(lap_detail(1))
    assert isinstance(found, dict)
    assert found["lap_number"] == 1

    missing = asyncio.run(lap_detail(99))
    assert isinstance(missing, JSONResponse)
    assert missing.status_code == 404


# ---- 8. bounded memory ------------------------------------------------------

def _complete_one_lap(t: LapTracker, lap_number: int, base_ns: int) -> None:
    """Run a minimal start->end cycle that leaves one finalized lap and no current."""
    t.on_frame(_frame(is_race_on=1, lap_number=lap_number, received_at_ns=base_ns))
    t.on_frame(_frame(is_race_on=1, lap_number=lap_number, received_at_ns=base_ns + 1))
    t.on_frame(_frame(is_race_on=0, lap_number=lap_number, received_at_ns=base_ns + 2))
    t.on_frame(_frame(is_race_on=0, lap_number=lap_number, received_at_ns=base_ns + 3))


def test_bounded_memory() -> None:
    t = LapTracker(maxlen=3)
    for i in range(4):
        _complete_one_lap(t, lap_number=i + 1, base_ns=int((i + 1) * 1e9))
    completed = t.completed()
    assert len(completed) == 3, completed
    # oldest (lap 1) dropped, lap 2 is now the oldest
    assert completed[0]["lap_number"] == 2
    assert completed[-1]["lap_number"] == 4


if __name__ == "__main__":
    test_lap_number_increment()
    test_current_lap_reset_boundary()
    test_race_off_then_on()
    test_race_on_to_off_no_new_lap()
    test_glitch_debounce_no_finalize()
    test_summary_math()
    test_api_laps_endpoint()
    test_api_lap_detail_found_and_404()
    test_bounded_memory()
    print("lap segmentation tests passed")