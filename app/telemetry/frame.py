"""Parsed telemetry frame model + JSON serialization."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass(slots=True)
class TelemetryFrame:
    """One parsed Forza telemetry packet.

    Sled fields are always present. Horizon-gap and Dash fields are present only
    when the packet contained them (None otherwise).
    """

    # sled
    is_race_on: int = 0
    timestamp_ms: int = 0
    engine_max_rpm: float = 0.0
    engine_idle_rpm: float = 0.0
    current_engine_rpm: float = 0.0
    acceleration_x: float = 0.0
    acceleration_y: float = 0.0
    acceleration_z: float = 0.0
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    velocity_z: float = 0.0
    angular_velocity_x: float = 0.0
    angular_velocity_y: float = 0.0
    angular_velocity_z: float = 0.0
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    normalized_suspension_travel_fl: float = 0.0
    normalized_suspension_travel_fr: float = 0.0
    normalized_suspension_travel_rl: float = 0.0
    normalized_suspension_travel_rr: float = 0.0
    tire_slip_ratio_fl: float = 0.0
    tire_slip_ratio_fr: float = 0.0
    tire_slip_ratio_rl: float = 0.0
    tire_slip_ratio_rr: float = 0.0
    wheel_rotation_speed_fl: float = 0.0
    wheel_rotation_speed_fr: float = 0.0
    wheel_rotation_speed_rl: float = 0.0
    wheel_rotation_speed_rr: float = 0.0
    wheel_on_rumble_strip_fl: int = 0
    wheel_on_rumble_strip_fr: int = 0
    wheel_on_rumble_strip_rl: int = 0
    wheel_on_rumble_strip_rr: int = 0
    wheel_in_puddle_depth_fl: float = 0.0
    wheel_in_puddle_depth_fr: float = 0.0
    wheel_in_puddle_depth_rl: float = 0.0
    wheel_in_puddle_depth_rr: float = 0.0
    surface_rumble_fl: float = 0.0
    surface_rumble_fr: float = 0.0
    surface_rumble_rl: float = 0.0
    surface_rumble_rr: float = 0.0
    tire_slip_angle_fl: float = 0.0
    tire_slip_angle_fr: float = 0.0
    tire_slip_angle_rl: float = 0.0
    tire_slip_angle_rr: float = 0.0
    tire_combined_slip_fl: float = 0.0
    tire_combined_slip_fr: float = 0.0
    tire_combined_slip_rl: float = 0.0
    tire_combined_slip_rr: float = 0.0
    suspension_travel_meters_fl: float = 0.0
    suspension_travel_meters_fr: float = 0.0
    suspension_travel_meters_rl: float = 0.0
    suspension_travel_meters_rr: float = 0.0
    car_ordinal: int = 0
    car_class: int = 0
    car_performance_index: int = 0
    drivetrain_type: int = 0
    num_cylinders: int = 0

    # horizon gap (None when absent, e.g. pure Sled packets)
    horizon_car_category: Optional[int] = None
    horizon_unknown_1: Optional[int] = None
    horizon_unknown_2: Optional[int] = None

    # dash
    position_x: Optional[float] = None
    position_y: Optional[float] = None
    position_z: Optional[float] = None
    speed: Optional[float] = None
    power: Optional[float] = None
    torque: Optional[float] = None
    tire_temp_fl: Optional[float] = None
    tire_temp_fr: Optional[float] = None
    tire_temp_rl: Optional[float] = None
    tire_temp_rr: Optional[float] = None
    boost: Optional[float] = None
    fuel: Optional[float] = None
    distance_traveled: Optional[float] = None
    best_lap: Optional[float] = None
    last_lap: Optional[float] = None
    current_lap: Optional[float] = None
    current_race_time: Optional[float] = None
    lap_number: Optional[int] = None
    race_position: Optional[int] = None
    accel: Optional[int] = None
    brake: Optional[int] = None
    clutch: Optional[int] = None
    hand_brake: Optional[int] = None
    gear: Optional[int] = None
    steer: Optional[int] = None
    normalized_driving_line: Optional[int] = None
    normalized_ai_brake_difference: Optional[int] = None

    # convenience derived fields surfaced to the UI/LLM
    received_at_ns: float = 0.0

    @property
    def speed_kmh(self) -> Optional[float]:
        return None if self.speed is None else self.speed * 3.6

    @property
    def speed_mph(self) -> Optional[float]:
        return None if self.speed is None else self.speed * 2.23693629

    @property
    def throttle_pct(self) -> Optional[float]:
        return None if self.accel is None else self.accel / 255.0 * 100.0

    @property
    def brake_pct(self) -> Optional[float]:
        return None if self.brake is None else self.brake / 255.0 * 100.0

    @property
    def clutch_pct(self) -> Optional[float]:
        # 255 = fully released (0% engaged), 0 = fully engaged (100%)
        return None if self.clutch is None else (255 - self.clutch) / 255.0 * 100.0

    @property
    def handbrake_pct(self) -> Optional[float]:
        return None if self.hand_brake is None else self.hand_brake / 255.0 * 100.0

    @property
    def steer_pct(self) -> Optional[float]:
        # -127 (full left) .. 127 (full right)
        return None if self.steer is None else self.steer / 127.0 * 100.0

    @property
    def gear_display(self) -> str:
        if self.gear is None:
            return "-"
        # Forza encodes gears as small uints; 0 = Neutral, large value = Reverse
        if self.gear == 0:
            return "N"
        if self.gear >= 250:  # 0xFB..0xFF used for reverse in some titles
            return "R"
        return str(self.gear)

    @property
    def tire_temps_c(self) -> Optional[list[float]]:
        if self.tire_temp_fl is None:
            return None
        f2c = lambda f: (f - 32.0) * 5.0 / 9.0
        return [f2c(self.tire_temp_fl), f2c(self.tire_temp_fr),
                f2c(self.tire_temp_rl), f2c(self.tire_temp_rr)]

    def to_dict(self) -> dict:
        d = asdict(self)
        # add derived convenience fields used by the UI/LLM
        d["speed_kmh"] = self.speed_kmh
        d["speed_mph"] = self.speed_mph
        d["throttle_pct"] = self.throttle_pct
        d["brake_pct"] = self.brake_pct
        d["clutch_pct"] = self.clutch_pct
        d["handbrake_pct"] = self.handbrake_pct
        d["steer_pct"] = self.steer_pct
        d["gear_display"] = self.gear_display
        d["tire_temps_c"] = self.tire_temps_c
        return d