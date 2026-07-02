"""Synthetic Forza "Dash Horizon" packet sender — for testing without the game.

Builds realistic 324B packets (sin-wave RPM/speed, oscillating pedals, lap times)
and streams them to UDP_PORT at ~60Hz so the dashboard, buffer, logger, and
WebSocket paths can all be exercised.

Run:  python scripts/fake_sender.py   (with the dashboard already running)
"""

from __future__ import annotations

import math
import socket
import struct
import sys
import time

# reuse the data-driven schema so the sender stays in sync with the parser
sys.path.insert(0, ".")
from app.telemetry.schema import (  # noqa: E402
    DASH_FIELDS, DASH_HORIZON_SIZE, DASH_SIZE,
    HORIZON_GAP_FIELDS, HORIZON_GAP_SIZE, SLED_FIELDS, SLED_SIZE,
)
from app.config import get_settings  # noqa: E402

SLED_FMT = "<" + "".join(c for _, c in SLED_FIELDS)
GAP_FMT = "<" + "".join(c for _, c in HORIZON_GAP_FIELDS)
DASH_FMT = "<" + "".join(c for _, c in DASH_FIELDS)


def build_packet(t: float) -> bytes:
    # sled (58 fields)
    rpm = 3500 + 4000 * (0.5 + 0.5 * math.sin(t * 1.3))
    speed = 60 + 70 * (0.5 + 0.5 * math.sin(t * 0.7))  # m/s
    sled = struct.pack(
        SLED_FMT,
        1,                       # is_race_on
        int(t * 1000) % 1_000_000,  # timestamp_ms
        8500.0,                  # engine_max_rpm
        900.0,                   # engine_idle_rpm
        rpm,                     # current_engine_rpm
        0.2, 9.81, 0.0,          # accel x/y/z
        speed, 0.0, 0.0,         # velocity
        0.0, 0.1, 0.0,           # angular velocity
        0.0, 0.0, 0.0,           # yaw/pitch/roll
        0.5, 0.5, 0.5, 0.5,      # normalized suspension travel
        0.02, 0.02, 0.05, 0.05,  # tire slip ratio
        50, 50, 48, 48,          # wheel rotation speed
        0, 0, 0, 0,              # wheel on rumble strip
        0.0, 0.0, 0.0, 0.0,      # puddle depth
        0.0, 0.0, 0.0, 0.0,      # surface rumble
        0.01, 0.01, 0.02, 0.02,  # tire slip angle
        0.05, 0.05, 0.1, 0.1,    # tire combined slip
        0.1, 0.1, 0.12, 0.12,    # suspension travel meters
        1, 2, 600, 1, 6,         # car ordinal/class/perf/drivetrain/cylinders
    )
    assert len(sled) == SLED_SIZE

    # horizon gap (3 x i32)
    gap = struct.pack(GAP_FMT, 13, 0, 0)
    assert len(gap) == HORIZON_GAP_SIZE

    # dash (27 fields)
    throttle = int(255 * (0.5 + 0.5 * math.sin(t * 2.0)))
    brake = int(255 * max(0.0, math.sin(t * 1.0 + 1.0)))
    gear = int(1 + (math.floor(t * 0.5) % 6))
    steer = int(80 * math.sin(t * 1.7))
    dash = struct.pack(
        DASH_FMT,
        0.0, 0.0, 0.0,           # position
        speed,                   # speed (m/s)
        220_000.0, 380.0,        # power, torque
        210, 215, 200, 205,      # tire temp (F)
        0.0,                     # boost
        0.6,                     # fuel
        float(t * 30),           # distance traveled
        62.3, 64.1, float(t % 65), float(t),  # best/last/current lap, race time
        int(1 + (t // 65) % 3),  # lap number
        2,                       # race position
        throttle, brake, 255, 0, gear,
        steer,
        0, 0,                    # normalized driving line / ai brake diff
    )
    assert len(dash) == DASH_SIZE

    packet = sled + gap + dash
    # some titles send a trailing byte; pad to 324 to match common FH5 wire size
    if len(packet) < DASH_HORIZON_SIZE + 1:
        packet += b"\x00"
    return packet


def main() -> None:
    settings = get_settings()
    host, port = "127.0.0.1", settings.udp_port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"Sending synthetic 324B Forza packets to udp://{host}:{port} at ~60Hz. Ctrl-C to stop.")
    t0 = time.monotonic()
    try:
        while True:
            t = time.monotonic() - t0
            sock.sendto(build_packet(t), (host, port))
            time.sleep(1 / 60)
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    main()