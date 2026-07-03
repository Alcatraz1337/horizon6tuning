"""Per-lap segmentation — ROADMAP item 2.

Detects lap boundaries from the live UDP telemetry stream and computes
per-lap summaries alongside the existing rolling buffer. `LapTracker.on_frame`
runs inside the synchronous UDP `on_frame` callback, so it stays O(1) per
frame, does no I/O, and allocates only the accumulator updates.

Boundary detection (debounced — 2 consecutive confirming frames required):

  * `lap_number` increases while `is_race_on` (primary signal)
  * `current_lap` wraps (drops by a meaningful margin) while `is_race_on`
    and `lap_number` did not increase (backup signal)
  * `is_race_on` off -> on: finalize in-progress lap, start a new one
  * `is_race_on` on -> off: finalize in-progress lap, no new one

The per-lap `summary` reuses the aggregate shape from
`app/store/buffer.py::TelemetryBuffer.summary()` (speed/rpm/throttle/brake/
combined tire slip / lateral-g / longitudinal-g / tire temps / fuel / boost /
gear) plus `lap_time` (= `duration_s`) and `fuel_used` (first-frame fuel minus
last-frame fuel).
"""

from __future__ import annotations

import math
import time
from collections import deque
from dataclasses import dataclass, asdict
from typing import Optional

from ..telemetry.frame import TelemetryFrame


# current_lap must drop by more than this many seconds to count as a reset.
# Avoids false positives from sub-second jitter on the running lap clock.
_LAP_RESET_MARGIN_S = 1.0
# When confirming a current_lap-reset boundary, the confirming frame's
# current_lap must still be within this many seconds of the pending frame's
# value. If it jumped back up, the first frame was a glitch.
_LAP_RESET_TOLERANCE_S = 5.0

# Metrics accumulated incrementally with avg/min/max at finalize. Mirrors the
# keys produced by TelemetryBuffer.summary() so the insights service and future
# per-lap LLM mode can reuse the same consumer code.
_AGG_METRICS = (
    "speed_kmh",
    "rpm",
    "throttle_pct",
    "brake_pct",
    "combined_tire_slip_sum",
    "lateral_g",
    "longitudinal_g",
)


@dataclass
class Lap:
    """One completed or in-progress lap.

    `summary` follows `TelemetryBuffer.summary()`'s aggregate shape plus
    `lap_time` and `fuel_used`. `ended_at_ns` / `duration_s` are None while
    the lap is in progress.
    """

    lap_number: int
    started_at_ns: int
    ended_at_ns: Optional[int]
    duration_s: Optional[float]
    frame_count: int
    best_lap: Optional[float]
    last_lap: Optional[float]
    summary: dict

    def as_dict(self) -> dict:
        return asdict(self)


class _Accumulator:
    """Running min/max/sum/count for the in-progress lap's aggregate metrics."""

    def __init__(self) -> None:
        self.sums: dict[str, float] = {m: 0.0 for m in _AGG_METRICS}
        self.mins: dict[str, float] = {m: math.inf for m in _AGG_METRICS}
        self.maxs: dict[str, float] = {m: -math.inf for m in _AGG_METRICS}
        self.counts: dict[str, int] = {m: 0 for m in _AGG_METRICS}
        self.first_fuel: Optional[float] = None
        self.latest: Optional[TelemetryFrame] = None
        self.frame_count: int = 0

    def update(self, frame: TelemetryFrame) -> None:
        speed = frame.speed
        vals: dict[str, Optional[float]] = {
            "speed_kmh": (speed * 3.6) if speed is not None else None,
            "rpm": frame.current_engine_rpm,
            "throttle_pct": frame.throttle_pct,
            "brake_pct": frame.brake_pct,
            "combined_tire_slip_sum": (
                abs(frame.tire_combined_slip_fl) + abs(frame.tire_combined_slip_fr)
                + abs(frame.tire_combined_slip_rl) + abs(frame.tire_combined_slip_rr)
            ),
            "lateral_g": abs(frame.acceleration_y),
            "longitudinal_g": abs(frame.acceleration_x),
        }
        for m, v in vals.items():
            if v is None:
                continue
            self.sums[m] += v
            if v < self.mins[m]:
                self.mins[m] = v
            if v > self.maxs[m]:
                self.maxs[m] = v
            self.counts[m] += 1
        if frame.fuel is not None and self.first_fuel is None:
            self.first_fuel = frame.fuel
        self.latest = frame
        self.frame_count += 1

    def summary(self, duration_s: Optional[float], best_lap: Optional[float],
                last_lap: Optional[float]) -> dict:
        def agg(m: str) -> Optional[dict]:
            c = self.counts[m]
            if c == 0:
                return None
            return {"avg": round(self.sums[m] / c, 2),
                    "min": round(self.mins[m], 2),
                    "max": round(self.maxs[m], 2)}

        f = self.latest
        fuel_used: Optional[float] = None
        if f is not None and self.first_fuel is not None and f.fuel is not None:
            fuel_used = round(self.first_fuel - f.fuel, 4)

        return {
            "frames": self.frame_count,
            "window_seconds": round(duration_s, 2) if duration_s is not None else None,
            "speed_kmh": agg("speed_kmh"),
            "rpm": agg("rpm"),
            "throttle_pct": agg("throttle_pct"),
            "brake_pct": agg("brake_pct"),
            "combined_tire_slip_sum": agg("combined_tire_slip_sum"),
            "lateral_g": agg("lateral_g"),
            "longitudinal_g": agg("longitudinal_g"),
            "fuel": f.fuel if f is not None else None,
            "boost": f.boost if f is not None else None,
            "gear": f.gear_display if f is not None else "-",
            "lap_number": f.lap_number if f is not None else None,
            "race_position": f.race_position if f is not None else None,
            "best_lap": best_lap,
            "last_lap": last_lap,
            "current_lap": f.current_lap if f is not None else None,
            "tire_temps_c": f.tire_temps_c if f is not None else None,
            "is_race_on": bool(f.is_race_on) if f is not None else False,
            "generated_at": time.time(),
            "lap_time": round(duration_s, 2) if duration_s is not None else None,
            "fuel_used": fuel_used,
        }


class LapTracker:
    """Tracks per-lap summaries from the telemetry stream.

    Boundaries are debounced: a single glitched frame cannot finalize a lap —
    the next frame must confirm the boundary signal before the previous lap is
    closed and a new one is opened.
    """

    def __init__(self, maxlen: int = 200) -> None:
        self._completed: deque[Lap] = deque(maxlen=maxlen)
        self._maxlen = maxlen
        self._current: Optional[Lap] = None
        self._acc: Optional[_Accumulator] = None
        self._pending: Optional[str] = None  # "lap_inc" | "current_lap_reset" | "race_on" | "race_off"
        self._pending_frame: Optional[TelemetryFrame] = None
        self._prev: Optional[TelemetryFrame] = None

    # ---- public API --------------------------------------------------------

    def on_frame(self, frame: TelemetryFrame) -> None:
        prev = self._prev
        self._prev = frame

        # If a boundary is pending from the previous frame, check confirmation.
        if self._pending is not None:
            if self._confirms(frame, self._pending):
                self._apply_boundary(frame, self._pending)
            else:
                # glitch — cancel pending, continue the current lap (if any)
                self._pending = None
                self._pending_frame = None
                if self._current is not None and self._acc is not None:
                    self._acc.update(frame)
            return

        signal = self._detect_signal(prev, frame)
        if signal is not None:
            self._pending = signal
            self._pending_frame = frame
            # the boundary frame still counts toward the in-progress lap
            if self._current is not None and self._acc is not None:
                self._acc.update(frame)
        else:
            if self._current is not None and self._acc is not None:
                self._acc.update(frame)

    def current(self) -> Optional[dict]:
        """In-progress lap as a Lap.as_dict()-shaped dict, or None."""
        if self._current is None or self._acc is None:
            return None
        lap = self._current
        f = self._acc.latest
        return {
            "lap_number": lap.lap_number,
            "started_at_ns": lap.started_at_ns,
            "ended_at_ns": None,
            "duration_s": None,
            "frame_count": self._acc.frame_count,
            "best_lap": f.best_lap if f is not None else None,
            "last_lap": f.last_lap if f is not None else None,
            "summary": self._acc.summary(
                duration_s=None,
                best_lap=f.best_lap if f is not None else None,
                last_lap=f.last_lap if f is not None else None,
            ),
        }

    def completed(self) -> list[dict]:
        return [lap.as_dict() for lap in self._completed]

    def lap(self, lap_number: int) -> Optional[dict]:
        for lap in self._completed:
            if lap.lap_number == lap_number:
                return lap.as_dict()
        cur = self.current()
        if cur is not None and cur["lap_number"] == lap_number:
            return cur
        return None

    def reset(self) -> None:
        """Clear all tracked laps (e.g. a brand new session)."""
        self._completed.clear()
        self._current = None
        self._acc = None
        self._pending = None
        self._pending_frame = None
        self._prev = None

    # ---- internals ---------------------------------------------------------

    def _detect_signal(self, prev: Optional[TelemetryFrame],
                       frame: TelemetryFrame) -> Optional[str]:
        if frame.is_race_on != 1:
            # race off transition (was on, now off)
            if prev is not None and prev.is_race_on == 1:
                return "race_off"
            return None

        # race is on
        if prev is None or prev.is_race_on != 1:
            # off -> on (or very first frame)
            return "race_on"

        # race was already on — look for lap-boundary signals
        if (prev.lap_number is not None and frame.lap_number is not None
                and frame.lap_number > prev.lap_number):
            return "lap_inc"

        if (prev.current_lap is not None and frame.current_lap is not None
                and frame.current_lap < prev.current_lap - _LAP_RESET_MARGIN_S
                # lap_number did not increase (backup signal only)
                and not (frame.lap_number is not None and prev.lap_number is not None
                         and frame.lap_number > prev.lap_number)):
            return "current_lap_reset"

        return None

    def _confirms(self, frame: TelemetryFrame, signal: str) -> bool:
        pf = self._pending_frame
        if pf is None:
            return False
        if signal == "lap_inc":
            return (frame.lap_number is not None and pf.lap_number is not None
                    and frame.lap_number >= pf.lap_number
                    and frame.is_race_on == 1)
        if signal == "current_lap_reset":
            return (frame.current_lap is not None and pf.current_lap is not None
                    and frame.current_lap < pf.current_lap + _LAP_RESET_TOLERANCE_S
                    and frame.is_race_on == 1)
        if signal == "race_off":
            return frame.is_race_on != 1
        if signal == "race_on":
            return frame.is_race_on == 1
        return False

    def _apply_boundary(self, frame: TelemetryFrame, signal: str) -> None:
        pending_ns = int(self._pending_frame.received_at_ns) if self._pending_frame else int(frame.received_at_ns)
        # finalize the in-progress lap (if any) at the boundary frame
        if self._current is not None and self._acc is not None:
            self._finalize_current(pending_ns)
        # start a new lap unless the session just ended
        if signal != "race_off":
            self._start_new_lap(frame)
        self._pending = None
        self._pending_frame = None

    def _finalize_current(self, ended_at_ns: int) -> None:
        assert self._current is not None and self._acc is not None
        lap = self._current
        duration_s = (ended_at_ns - lap.started_at_ns) / 1e9
        f = self._acc.latest
        best_lap = f.best_lap if f is not None else None
        last_lap = f.last_lap if f is not None else None
        lap.ended_at_ns = ended_at_ns
        lap.duration_s = duration_s
        lap.frame_count = self._acc.frame_count
        lap.best_lap = best_lap
        lap.last_lap = last_lap
        lap.summary = self._acc.summary(duration_s=duration_s, best_lap=best_lap, last_lap=last_lap)
        self._completed.append(lap)
        self._current = None
        self._acc = None

    def _start_new_lap(self, frame: TelemetryFrame) -> None:
        lap_number = frame.lap_number if frame.lap_number is not None else 0
        self._current = Lap(
            lap_number=lap_number,
            started_at_ns=int(frame.received_at_ns),
            ended_at_ns=None,
            duration_s=None,
            frame_count=0,
            best_lap=frame.best_lap,
            last_lap=frame.last_lap,
            summary={},
        )
        self._acc = _Accumulator()
        self._acc.update(frame)