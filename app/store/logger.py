"""Session telemetry logger — writes key fields to CSV and/or JSONL.

One file per *active period*: a timestamped pair is opened by `start()` and
closed by `stop()`. Defaults to inactive, so launching the app creates no
files until the user opts in via the dashboard toggle (ROADMAP item 1).
`log_stride` throttles how many packets get written (telemetry is ~60Hz;
stride=5 ≈ 12 rows/sec).
"""

from __future__ import annotations

import csv
import json
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
    """File logger with an explicit start/stop lifecycle.

    `__init__` only records config — no files are opened until `start()` is
    called. `stop()` closes the current pair; a later `start()` opens a new
    timestamped pair. Each active period is exactly one session on disk.
    """

    def __init__(self, log_dir: str, stride: int = 5, fmt: str = "csv") -> None:
        self.log_dir = Path(log_dir)
        self.stride = max(1, stride)
        self.fmt = fmt.lower()
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.active: bool = False
        self.csv_path: Path | None = None
        self.jsonl_path: Path | None = None

        self._csv_file = None
        self._csv_writer = None
        self._jsonl_file = None
        self._written = 0

    def start(self) -> dict:
        """Open a fresh timestamped CSV/JSONL pair and begin logging.

        No-op (returns current info) if already active — a second click while
        logging must not create a second file.
        """
        if self.active:
            return self.info()

        stamp = time.strftime("%Y%m%d-%H%M%S")
        self._written = 0

        # Only set the path for the formats we actually open, so info() never
        # reports a file that doesn't exist on disk.
        if self.fmt in ("csv", "both"):
            self.csv_path = self.log_dir / f"telemetry-{stamp}.csv"
            self._csv_file = open(self.csv_path, "a", newline="", encoding="utf-8")
            self._csv_writer = csv.DictWriter(self._csv_file, fieldnames=CSV_COLUMNS)
            self._csv_writer.writeheader()
            self._csv_file.flush()  # header on disk immediately; a crash before the first row still yields a valid CSV
        if self.fmt in ("jsonl", "both"):
            self.jsonl_path = self.log_dir / f"telemetry-{stamp}.jsonl"
            self._jsonl_file = open(self.jsonl_path, "a", encoding="utf-8")

        self.active = True
        return self.info()

    def stop(self) -> dict:
        """Close the current files and stop logging. No-op if already inactive."""
        if not self.active:
            return self.info()
        self._close_files()
        self.active = False
        self.csv_path = None
        self.jsonl_path = None
        return self.info()

    def log(self, frame: TelemetryFrame, index: int = 0) -> None:
        if not self.active or index % self.stride != 0:
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

    def _close_files(self) -> None:
        if self._csv_file is not None:
            self._csv_file.close()
            self._csv_file = None
            self._csv_writer = None
        if self._jsonl_file is not None:
            self._jsonl_file.close()
            self._jsonl_file = None

    def close(self) -> None:
        """Shutdown close — idempotent, safe whether or not logging is active."""
        self._close_files()
        self.active = False

    def info(self) -> dict:
        return {
            "active": self.active,
            "log_dir": str(self.log_dir),
            "csv_path": str(self.csv_path) if self.csv_path else None,
            "jsonl_path": str(self.jsonl_path) if self.jsonl_path else None,
            "stride": self.stride,
            "rows_written": self._written,
        }