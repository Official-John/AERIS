"""Fault injector.

Faults are applied to the simulated aircraft itself (motors, battery) or to the
raw sensor messages *before* anyone reads them. The autopilot and AERIS both see
the same corrupted data, as they would on a real aircraft.

The injector also keeps the ground truth: what was injected, and when. Only the
flight recorder and the scoring oracle may read it. AERIS never gets it; a test
in tests/test_architecture.py enforces that.
"""
import math
from dataclasses import dataclass, field

# fault type -> (component it breaks, what the diagnosis should say)
FAULT_TYPES = {
    "gps_off": ("gps", "GPS_LOSS"),
    "gps_stuck": ("gps", "GPS_FROZEN"),
    "gps_drift": ("gps", "GPS_DRIFT"),
    "baro_stuck": ("baro", "BARO_FROZEN"),
    "mag_offset": ("mag", "MAG_FAULT"),
    "imu_bias": ("imu", "IMU_BIAS"),
    "motor_degradation": ("motors", "MOTOR_DEGRADED"),
    "battery_fault": ("battery", "BATTERY_DEGRADED"),
}


@dataclass
class FaultSpec:
    type: str
    start: float
    duration: float = None      # None = permanent
    params: dict = field(default_factory=dict)

    def active(self, t):
        return t >= self.start and (self.duration is None or t < self.start + self.duration)

    def to_truth(self):
        component, expected = FAULT_TYPES[self.type]
        return {"type": self.type, "component": component, "expected_diagnosis": expected,
                "start": self.start, "duration": self.duration, "params": dict(self.params)}


class FaultInjector:
    def __init__(self, specs):
        for s in specs:
            if s.type not in FAULT_TYPES:
                raise ValueError(f"unknown fault type {s.type!r}; choose from {sorted(FAULT_TYPES)}")
        self.specs = list(specs)
        self._held = {}           # frozen values for "stuck" faults
        self._plant_done = set()

    def truth(self):
        return [s.to_truth() for s in self.specs]

    def apply_plant(self, t, vehicle):
        for i, s in enumerate(self.specs):
            if not s.active(t) or i in self._plant_done:
                continue
            if s.type == "motor_degradation":
                vehicle.motor_eff[int(s.params.get("motor", 0))] = float(s.params["efficiency"])
                self._plant_done.add(i)
            elif s.type == "battery_fault":
                b = vehicle.battery
                b.energy_wh *= 1.0 - float(s.params["charge_loss"])
                b.resistance *= float(s.params.get("resistance_mult", 1.0))
                self._plant_done.add(i)

    def apply_sensors(self, t, msgs):
        for i, s in enumerate(self.specs):
            if not s.active(t):
                continue
            p = s.params
            if s.type == "gps_off":
                msgs.pop("gps", None)
            elif s.type == "gps_stuck" and "gps" in msgs:
                msgs["gps"] = self._held.setdefault(i, msgs["gps"])
            elif s.type == "gps_drift" and "gps" in msgs:
                d = math.radians(p.get("direction_deg", 0.0))
                rate = float(p["rate_mps"])
                off = rate * (t - s.start)
                x, y, z = msgs["gps"]["pos"]
                vx, vy, vz = msgs["gps"]["vel"]
                msgs["gps"] = {"pos": (x + off * math.cos(d), y + off * math.sin(d), z),
                               "vel": (vx + rate * math.cos(d), vy + rate * math.sin(d), vz)}
            elif s.type == "baro_stuck" and "baro" in msgs:
                msgs["baro"] = self._held.setdefault(i, msgs["baro"])
            elif s.type == "mag_offset" and "mag" in msgs:
                yaw = msgs["mag"] + math.radians(float(p["offset_deg"]))
                msgs["mag"] = (yaw + math.pi) % (2 * math.pi) - math.pi
            elif s.type == "imu_bias" and "imu" in msgs:
                (ax, ay, az), gz = msgs["imu"]
                msgs["imu"] = ((ax + float(p.get("bx", 0.0)), ay + float(p.get("by", 0.0)), az), gz)
        return msgs
