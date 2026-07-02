"""Parse raw Forza telemetry UDP bytes into a TelemetryFrame.

The parser is data-driven: it builds struct format strings from the field tables
in `schema.py` and unpacks each section only if the packet is long enough, so a
232B "Sled", 311B "Dash", or 323/324B "Dash Horizon" packet all parse cleanly.
"""

from __future__ import annotations

import struct
import time

from .frame import TelemetryFrame
from .schema import (
    DASH_FIELDS,
    DASH_HORIZON_SIZE,
    DASH_SIZE,
    HORIZON_GAP_FIELDS,
    HORIZON_GAP_SIZE,
    SLED_FIELDS,
    SLED_SIZE,
)


class TelemetryParseError(ValueError):
    """Raised when a packet is too short or does not match any known format."""


_SLED_FMT = "<" + "".join(c for _, c in SLED_FIELDS)
_GAP_FMT = "<" + "".join(c for _, c in HORIZON_GAP_FIELDS)
_DASH_FMT = "<" + "".join(c for _, c in DASH_FIELDS)

assert struct.calcsize(_SLED_FMT) == SLED_SIZE
assert struct.calcsize(_GAP_FMT) == HORIZON_GAP_SIZE
assert struct.calcsize(_DASH_FMT) == DASH_SIZE


def parse(data: bytes, received_at_ns: float | None = None) -> TelemetryFrame:
    """Parse one UDP datagram into a TelemetryFrame.

    Raises TelemetryParseError if `data` is shorter than the 232B sled section.
    """
    n = len(data)
    if n < SLED_SIZE:
        raise TelemetryParseError(
            f"packet too short: {n} bytes (need >= {SLED_SIZE} for sled)"
        )

    frame = TelemetryFrame(received_at_ns=received_at_ns or time.time_ns())

    # sled (always present)
    sled_names = [name for name, _ in SLED_FIELDS]
    for name, value in zip(sled_names, struct.unpack(_SLED_FMT, data[:SLED_SIZE])):
        setattr(frame, name, value)

    # horizon gap (FH4/FH5/FH6 Dash Horizon packets only)
    if n >= SLED_SIZE + HORIZON_GAP_SIZE:
        gap_names = [name for name, _ in HORIZON_GAP_FIELDS]
        gap_bytes = data[SLED_SIZE:SLED_SIZE + HORIZON_GAP_SIZE]
        for name, value in zip(gap_names, struct.unpack(_GAP_FMT, gap_bytes)):
            setattr(frame, name, value)

    # dash extension
    dash_start = SLED_SIZE + (HORIZON_GAP_SIZE if n >= DASH_HORIZON_SIZE else 0)
    if n >= dash_start + DASH_SIZE:
        dash_names = [name for name, _ in DASH_FIELDS]
        dash_bytes = data[dash_start:dash_start + DASH_SIZE]
        for name, value in zip(dash_names, struct.unpack(_DASH_FMT, dash_bytes)):
            setattr(frame, name, value)

    return frame