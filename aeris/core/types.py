"""Data types shared across AERIS.

AERIS sees the world only through SensorFrame: raw sensor messages plus the
telemetry an autopilot publishes. It answers with Command objects. Keeping this
boundary small is what lets the same core run against the stand-in autopilot
today and PX4 later (see aeris/adapters/).
"""
from dataclasses import asdict, dataclass, field

# Health states, in order of severity.
NOMINAL, SUSPECT, DEGRADED, FAILED, UNKNOWN = "NOMINAL", "SUSPECT", "DEGRADED", "FAILED", "UNKNOWN"
COMPONENTS = ("gps", "baro", "mag", "imu", "vision", "motors", "battery")


@dataclass
class SensorFrame:
    t: float
    imu: tuple = None            # ((ax, ay, az) body frame m/s^2, yaw rate rad/s)
    gps_pos: tuple = None        # (x, y, z) m
    gps_vel: tuple = None        # (vx, vy, vz) m/s
    baro: float = None           # altitude m
    mag: float = None            # heading rad
    vision: tuple = None         # (vx, vy, vz) m/s, world frame
    battery: tuple = None        # (volts, amps)
    motor_outputs: tuple = None  # four values 0..1
    # autopilot telemetry
    est_pos: tuple = (0.0, 0.0, 0.0)
    est_vel: tuple = (0.0, 0.0, 0.0)
    est_yaw: float = 0.0
    accel_sp: tuple = (0.0, 0.0, 0.0)
    mode: str = "PREFLIGHT"
    gps_test_ratio: float = 0.0
    remaining_wps: tuple = ()
    armed: bool = False


@dataclass
class Evidence:
    test_id: str
    value: float
    threshold: float
    tripped: bool

    def __post_init__(self):
        # Plain Python types, so events can always be saved as JSON.
        self.value, self.threshold, self.tripped = float(self.value), float(self.threshold), bool(self.tripped)

    def text(self):
        state = "TRIPPED" if self.tripped else "ok"
        return f"{self.test_id}: {self.value:.3g} vs threshold {self.threshold:.3g} ({state})"


@dataclass
class Diagnosis:
    t: float
    fault_id: str
    component: str
    health: str
    confidence: float
    evidence: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


@dataclass
class Command:
    """kind is one of: set_mode, exclude_sensor, accel_bias, speed_limit, reset_position."""
    kind: str
    value: object
    reason: str


@dataclass
class Event:
    t: float
    kind: str          # health | diagnosis | action | info
    component: str
    text: str
    data: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)
