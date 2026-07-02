"""Parser round-trip test: build a known packet, parse it, assert key fields.

Run:  python -m pytest tests/test_parser.py -q
   or python tests/test_parser.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.telemetry import parser
from app.telemetry.schema import DASH_HORIZON_SIZE


def test_roundtrip_dash_horizon():
    # minimal but representative: race on, rpm 5000, speed 50 m/s, gear 3
    # build via the fake_sender's packer
    from scripts.fake_sender import build_packet  # type: ignore
    pkt = build_packet(12.0)
    assert len(pkt) >= DASH_HORIZON_SIZE

    frame = parser.parse(pkt)
    assert frame.is_race_on == 1
    assert 0 < frame.current_engine_rpm < 9000
    assert frame.speed is not None and 0 < frame.speed < 200
    assert frame.gear == 1 + (12 // 2 % 6)  # gear = 1 + floor(t*0.5)%6
    assert frame.gear_display == str(frame.gear)
    assert frame.speed_kmh is not None and frame.speed_kmh > 0
    assert frame.tire_temps_c is not None and len(frame.tire_temps_c) == 4
    assert frame.horizon_car_category == 13


def test_short_packet_raises():
    raised = False
    try:
        parser.parse(b"\x00" * 10)
    except parser.TelemetryParseError:
        raised = True
    assert raised, "expected TelemetryParseError for a 10-byte packet"


def test_sled_only_packet():
    # a 232-byte packet (no dash) should parse sled fields, leave dash as None
    from scripts.fake_sender import build_packet
    pkt = build_packet(1.0)[:232]
    frame = parser.parse(pkt)
    assert frame.is_race_on == 1
    assert frame.speed is None
    assert frame.gear is None
    assert frame.speed_kmh is None


if __name__ == "__main__":
    test_roundtrip_dash_horizon()
    test_short_packet_raises()
    test_sled_only_packet()
    print("parser tests passed")