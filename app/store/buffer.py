"""Rolling in-memory buffer of recent telemetry frames + running aggregate stats.

The buffer feeds two consumers:
  * the live WebSocket/UI (recent frames for sparklines)
  * the insights service (a compact summary of the window for the LLM)

Telemetry arrives many times per second; we keep only the last N frames.
"""

from __future__ import annotations

import time
from collections import deque
from statistics import mean

from ..telemetry.frame import TelemetryFrame


class TelemetryBuffer:
    def __init__(self, maxlen: int = 600) -> None:
        self._frames: deque[TelemetryFrame] = deque(maxlen=maxlen)
        self._maxlen = maxlen

    def append(self, frame: TelemetryFrame) -> None:
        self._frames.append(frame)

    def latest(self) -> TelemetryFrame | None:
        return self._frames[-1] if self._frames else None

    def recent(self, n: int = 200) -> list[TelemetryFrame]:
        if n >= len(self._frames):
            return list(self._frames)
        return list(self._frames)[-n:]

    def __len__(self) -> int:
        return len(self._frames)

    def summary(self) -> dict:
        """Compact, LLM-friendly aggregate of the current window."""
        frames = list(self._frames)
        if not frames:
            return {"frames": 0, "empty": True}

        speeds = [f.speed for f in frames if f.speed is not None]
        rpms = [f.current_engine_rpm for f in frames]
        throttles = [f.throttle_pct for f in frames if f.throttle_pct is not None]
        brakes = [f.brake_pct for f in frames if f.brake_pct is not None]
        slips = [abs(f.tire_combined_slip_fl) + abs(f.tire_combined_slip_fr)
                 + abs(f.tire_combined_slip_rl) + abs(f.tire_combined_slip_rr)
                 for f in frames]
        lat_g = [abs(f.acceleration_y) for f in frames]
        long_g = [abs(f.acceleration_x) for f in frames]

        latest_frame = frames[-1]
        window_s = (latest_frame.received_at_ns - frames[0].received_at_ns) / 1e9

        def agg(vals):
            if not vals:
                return None
            return {"avg": round(mean(vals), 2),
                    "min": round(min(vals), 2),
                    "max": round(max(vals), 2)}

        return {
            "frames": len(frames),
            "window_seconds": round(window_s, 2),
            "speed_kmh": agg([s * 3.6 for s in speeds]),
            "rpm": agg(rpms),
            "throttle_pct": agg(throttles),
            "brake_pct": agg(brakes),
            "combined_tire_slip_sum": agg(slips),
            "lateral_g": agg(lat_g),
            "longitudinal_g": agg(long_g),
            "fuel": latest_frame.fuel,
            "boost": latest_frame.boost,
            "gear": latest_frame.gear_display,
            "lap_number": latest_frame.lap_number,
            "race_position": latest_frame.race_position,
            "best_lap": latest_frame.best_lap,
            "last_lap": latest_frame.last_lap,
            "current_lap": latest_frame.current_lap,
            "tire_temps_c": latest_frame.tire_temps_c,
            "is_race_on": bool(latest_frame.is_race_on),
            "generated_at": time.time(),
        }