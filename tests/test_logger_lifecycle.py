"""TelemetryLogger lifecycle tests — ROADMAP item 1.

Verifies the logger defaults to inactive (no files), start() opens a fresh
timestamped pair, stop() closes them, a second start() opens a new pair, and
log() is a no-op while inactive.

Run:  python -m pytest tests/test_logger_lifecycle.py -q
   or python tests/test_logger_lifecycle.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.store.logger import TelemetryLogger
from app.telemetry import parser
from scripts.fake_sender import build_packet  # type: ignore


def _frame():
    return parser.parse(build_packet(3.0))


def _new_logger(tmp_path: Path, fmt: str = "both") -> TelemetryLogger:
    return TelemetryLogger(log_dir=str(tmp_path), stride=1, fmt=fmt)


def test_construct_creates_no_files(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path)
    try:
        assert logger.active is False
        info = logger.info()
        assert info["active"] is False
        assert info["csv_path"] is None
        assert info["jsonl_path"] is None
        assert list(tmp_path.glob("telemetry-*")) == []
    finally:
        logger.close()


def test_start_opens_both_files(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path, fmt="both")
    try:
        info = logger.start()
        assert info["active"] is True
        assert info["csv_path"] is not None and Path(info["csv_path"]).exists()
        assert info["jsonl_path"] is not None and Path(info["jsonl_path"]).exists()
        # CSV header is flushed to disk immediately (before any log() call)
        assert Path(info["csv_path"]).read_text(encoding="utf-8").startswith("timestamp_ms")
    finally:
        logger.close()


def test_start_is_idempotent(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path)
    try:
        first = logger.start()
        second = logger.start()
        assert first["csv_path"] == second["csv_path"]
        assert len(list(tmp_path.glob("telemetry-*.csv"))) == 1
    finally:
        logger.close()


def test_stop_closes_and_clears_paths(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path)
    try:
        logger.start()
        csv_path = logger.info()["csv_path"]
        logger.stop()
        info = logger.info()
        assert info["active"] is False
        assert info["csv_path"] is None
        assert info["jsonl_path"] is None
        assert Path(csv_path).exists()  # still on disk, just no longer tracked
    finally:
        logger.close()


def test_second_start_opens_new_pair(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path)
    try:
        first = logger.start()
        logger.stop()
        time.sleep(1.1)  # ensure a different %Y%m%d-%H%M%S stamp
        second = logger.start()
        assert first["csv_path"] != second["csv_path"]
        assert first["jsonl_path"] != second["jsonl_path"]
        # both pairs remain on disk — every "on" period is one session
        assert len(list(tmp_path.glob("telemetry-*.csv"))) == 2
    finally:
        logger.close()


def test_log_is_noop_when_inactive(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path, fmt="both")
    try:
        logger.log(_frame(), index=0)
        assert logger.info()["rows_written"] == 0
        assert list(tmp_path.glob("telemetry-*")) == []
    finally:
        logger.close()


def test_log_writes_after_start(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path, fmt="both")
    try:
        logger.start()
        logger.log(_frame(), index=0)
        logger.log(_frame(), index=1)
        assert logger.info()["rows_written"] == 2
        # CSV has header + 2 rows
        lines = Path(logger.info()["csv_path"]).read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3
    finally:
        logger.close()


def test_stop_is_idempotent(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path)
    try:
        logger.stop()  # never started — must not raise
        logger.start()
        logger.stop()
        logger.stop()  # second stop — must not raise
        assert logger.active is False
    finally:
        logger.close()


def test_csv_only_format(tmp_path: Path) -> None:
    logger = _new_logger(tmp_path, fmt="csv")
    try:
        info = logger.start()
        assert info["csv_path"] is not None and Path(info["csv_path"]).exists()
        # jsonl_path must be None — no file should be reported or created
        assert info["jsonl_path"] is None
        assert list(tmp_path.glob("telemetry-*.jsonl")) == []
        assert len(list(tmp_path.glob("telemetry-*.csv"))) == 1
    finally:
        logger.close()


if __name__ == "__main__":
    import tempfile
    for fn in [
        test_construct_creates_no_files,
        test_start_opens_both_files,
        test_start_is_idempotent,
        test_stop_closes_and_clears_paths,
        test_second_start_opens_new_pair,
        test_log_is_noop_when_inactive,
        test_log_writes_after_start,
        test_stop_is_idempotent,
        test_csv_only_format,
    ]:
        with tempfile.TemporaryDirectory() as d:
            fn(Path(d))
    print("logger lifecycle tests passed")