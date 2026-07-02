"""Session telemetry logger — writes key fields to CSV and/or JSONL.

One file per session (timestamped filename). `log_stride` throttles how many
packets get written (telemetry is ~60Hz; stride=5 ≈ 12 rows/sec).
"""

from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path

from ..telemetry.frame import TelemetryFrame

# Columns persisted to CSV. Keep this small & flat — full per-frame data lives in JSONL.
CSV_COLUMNS = [
    "timestamp_ms", "received_at_ns",
    "is_race_on", "current_engine_rpm", "engine_max_rpm",
    "speed_kmh", "speed_mph", "gear_display",
    "throttle_pct", "brake_pct", "clutch_pct", "handbrake_pct", "steer_pct",
    "acceleration_x", "acceleration_y", "acceleration_z",
    "lap_number", "race_position", "current_lap", "last_lap", "best_lap",
    "fuel", "boost", "power", "torque",
    "tire_temp_fl", "tire_temp_fr", "tire_temp_rl", "tire_temp_rr",
    "tire_combined_slip_fl", "tire_combined_slip_fr",
    "tire_combined_slip_rl", "tire_combined_slip_rr",
    "distance_traveled",
]


class TelemetryLogger:
    def __init__(self, log_dir: str, stride: int = 5, fmt: str = "csv") -> None:
        self.log_dir = Path(log_dir)
        self.stride = max(1, stride)
        self.fmt = fmt.lower()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        stamp = time.strftime("%Y%m%d-%H%M%S")
        self.csv_path = self.log_dir / f"telemetry-{stamp}.csv"
        self.jsonl_path = self.log_dir / f"telemetry-{stamp}.jsonl"

        self._csv_file = None
        self._csv_writer = None
        self._jsonl_file = None
        self._written = 0

        if self.fmt in ("csv", "both"):
            self._csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=CSV_COLUMNS)
            self._csv_writer.writeheader()
        if self.fmt in ("jsonl", "both"):
            self._jsonl_file = open(self.jsonl_path, "a", encoding="utf-8")

    def log(self, frame: TelemetryFrame, index: int = 0) -> None:
        if index % self.stride != 0:
            return
        d = frame.to_dict()

        if self._csv_writer is not None:
            row = {c: d.get(c) for c in CSV_COLUMNS}
            self._csv_writer.writerow(row)
            self._csv_file.flush()  # safe to flush periodically; stride keeps volume low

        if self._jsonl_file is not None:
            self._jsonl_file.write(json.dumps(d) + "\n")
            self._jsonl_file.flush()

        self._written += 1

    def close(self) -> None:
        if self._csv_file is not None:
            self._csv_file.close()
        if self._jsonl_file is not None:
            self._jsonl_file.close()

    def info(self) -> dict:
        return {
            "log_dir": str(self.log_dir),
            "csv_path": str(self.csv_path) if self._csv_file else None,
            "jsonl_path": str(self.jsonl_path) if self._jsonl_file else None,
            "stride": self.stride,
            "rows_written": self._written,
        }