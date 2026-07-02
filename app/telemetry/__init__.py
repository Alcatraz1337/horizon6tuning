"""Forza "Dash Horizon" UDP packet schema.

Data-driven field tables (name, struct char) for the three contiguous sections of
the Forza telemetry packet. The parser builds a struct format string from these
tables, so any offset/type correction for a future title is a one-place edit here.

All values are little-endian. Section sizes:
  * Sled            232 bytes (offsets 0..231)   — base telemetry, all FM/FH titles
  * Horizon gap      12 bytes (offsets 232..243) — FH4/FH5 (and expected FH6) only
  * Dash             79 bytes (offsets 244..322) — "Car Dash" extension

References (verified against FH4/FH5 "Dash Horizon" 323-324B format):
  * https://github.com/0x20F/forza-telemetry          (Rust decoder, all formats)
  * https://github.com/jasperan/forza-horizon-5-telemetry-listener
  * https://github.com/Grvs44/Forza-Telemetry-Export/blob/main/README.md
  * https://forums.forza.net/t/data-out-telemetry-variables-and-structure/535984
"""

from __future__ import annotations

# struct chars: i=s32, I=u32, f=f32, H=u16, B=u8, b=s8
SLED_FIELDS: list[tuple[str, str]] = [
    ("is_race_on", "i"),
    ("timestamp_ms", "I"),
    ("engine_max_rpm", "f"),
    ("engine_idle_rpm", "f"),
    ("current_engine_rpm", "f"),
    ("acceleration_x", "f"),
    ("acceleration_y", "f"),
    ("acceleration_z", "f"),
    ("velocity_x", "f"),
    ("velocity_y", "f"),
    ("velocity_z", "f"),
    ("angular_velocity_x", "f"),
    ("angular_velocity_y", "f"),
    ("angular_velocity_z", "f"),
    ("yaw", "f"),
    ("pitch", "f"),
    ("roll", "f"),
    ("normalized_suspension_travel_fl", "f"),
    ("normalized_suspension_travel_fr", "f"),
    ("normalized_suspension_travel_rl", "f"),
    ("normalized_suspension_travel_rr", "f"),
    ("tire_slip_ratio_fl", "f"),
    ("tire_slip_ratio_fr", "f"),
    ("tire_slip_ratio_rl", "f"),
    ("tire_slip_ratio_rr", "f"),
    ("wheel_rotation_speed_fl", "f"),
    ("wheel_rotation_speed_fr", "f"),
    ("wheel_rotation_speed_rl", "f"),
    ("wheel_rotation_speed_rr", "f"),
    ("wheel_on_rumble_strip_fl", "i"),
    ("wheel_on_rumble_strip_fr", "i"),
    ("wheel_on_rumble_strip_rl", "i"),
    ("wheel_on_rumble_strip_rr", "i"),
    ("wheel_in_puddle_depth_fl", "f"),
    ("wheel_in_puddle_depth_fr", "f"),
    ("wheel_in_puddle_depth_rl", "f"),
    ("wheel_in_puddle_depth_rr", "f"),
    ("surface_rumble_fl", "f"),
    ("surface_rumble_fr", "f"),
    ("surface_rumble_rl", "f"),
    ("surface_rumble_rr", "f"),
    ("tire_slip_angle_fl", "f"),
    ("tire_slip_angle_fr", "f"),
    ("tire_slip_angle_rl", "f"),
    ("tire_slip_angle_rr", "f"),
    ("tire_combined_slip_fl", "f"),
    ("tire_combined_slip_fr", "f"),
    ("tire_combined_slip_rl", "f"),
    ("tire_combined_slip_rr", "f"),
    ("suspension_travel_meters_fl", "f"),
    ("suspension_travel_meters_fr", "f"),
    ("suspension_travel_meters_rl", "f"),
    ("suspension_travel_meters_rr", "f"),
    ("car_ordinal", "i"),
    ("car_class", "i"),
    ("car_performance_index", "i"),
    ("drivetrain_type", "i"),
    ("num_cylinders", "i"),
]
SLED_SIZE = 232

# FH4/FH5 (and expected FH6) insert 12 undocumented bytes between sled and dash.
# First 4 bytes appear to be a car-category ordinal; the rest are unknown.
HORIZON_GAP_FIELDS: list[tuple[str, str]] = [
    ("horizon_car_category", "i"),
    ("horizon_unknown_1", "i"),
    ("horizon_unknown_2", "i"),
]
HORIZON_GAP_SIZE = 12

DASH_FIELDS: list[tuple[str, str]] = [
    ("position_x", "f"),
    ("position_y", "f"),
    ("position_z", "f"),
    ("speed", "f"),               # m/s
    ("power", "f"),               # watts
    ("torque", "f"),              # Nm
    ("tire_temp_fl", "f"),        # Fahrenheit in the raw packet
    ("tire_temp_fr", "f"),
    ("tire_temp_rl", "f"),
    ("tire_temp_rr", "f"),
    ("boost", "f"),
    ("fuel", "f"),
    ("distance_traveled", "f"),   # meters
    ("best_lap", "f"),            # seconds
    ("last_lap", "f"),
    ("current_lap", "f"),
    ("current_race_time", "f"),
    ("lap_number", "H"),
    ("race_position", "B"),
    ("accel", "B"),               # 0-255
    ("brake", "B"),               # 0-255
    ("clutch", "B"),              # 0-255 (255 = fully released)
    ("hand_brake", "B"),          # 0-255
    ("gear", "B"),                # 0=N, 1..n=forward, -1 via uint wrap handled below
    ("steer", "b"),               # -127..127
    ("normalized_driving_line", "b"),
    ("normalized_ai_brake_difference", "b"),
]
DASH_SIZE = 79
DASH_HORIZON_SIZE = SLED_SIZE + HORIZON_GAP_SIZE + DASH_SIZE  # 323 (324 w/ trailing byte)