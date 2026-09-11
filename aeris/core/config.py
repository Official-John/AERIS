"""Every AERIS threshold in one place.

Change values here, never inline in the code. Each run records config_hash(), so a
result can always be traced back to the thresholds that produced it.
"""
import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class AerisConfig:
    # --- timing
    health_period: float = 0.1          # s, health/diagnosis evaluation (10 Hz)
    # --- GPS
    gps_timeout: float = 0.3            # s without a GPS message -> stale
    stuck_repeats: int = 5              # identical consecutive samples -> frozen
    gps_vel_k: float = 0.12             # m/s, CUSUM allowance on |GPS vel - vision vel| (1 s filtered)
    gps_vel_h: float = 1.5              # CUSUM alarm level
    gps_pos_threshold: float = 3.0      # m, GPS vs independent position (2 s filtered); worst of 75
                                        # fault-free tuning flights was 1.89 m (docs/adr/0004)
    gps_pos_tau: float = 2.0            # s, smoothing of that residual
    settle_time: float = 2.0            # s after take-off before in-flight residual tests start
    # --- barometer / magnetometer
    baro_timeout: float = 0.5
    mag_timeout: float = 0.5
    mag_threshold_deg: float = 10.0     # mag heading vs gyro heading
    # --- IMU
    imu_timeout: float = 0.1
    imu_window: float = 1.0             # s, window for IMU vs external velocity
    imu_k: float = 0.25                 # m/s^2 CUSUM allowance
    imu_h: float = 0.6
    twin_k: float = 0.40                # m/s^2 CUSUM allowance on twin residual (gusts reach ~0.36)
    twin_h: float = 2.0
    # --- motors / battery
    motor_imbalance: float = 0.12       # max output minus median output
    battery_residual_v: float = 0.6     # V below the twin's predicted voltage
    battery_capacity_wh: float = 40.0
    battery_resistance: float = 0.06
    reserve_fraction: float = 0.15      # energy that must remain at landing
    hover_power_w: float = 180.0
    min_cell_voltage: float = 3.40      # V/cell under load that must hold until landing: just above
                                        # the autopilot's 3.35 forced-landing threshold (docs/adr/0004)
    thrust_to_weight: float = 2.0       # airframe value from the twin's calibration
    min_thrust_margin: float = 1.4      # thrust/weight needed to keep flying the mission
    # --- health confirmation
    confirm_m: int = 8                  # M of the last N evaluations must trip...
    confirm_n: int = 10
    clear_time: float = 2.0             # s clean before SUSPECT returns to NOMINAL
    isolation_wait: float = 15.0        # s to wait for a full signature before UNKNOWN
    # --- recovery policy
    allow_termination: bool = False     # no parachute simulated

    def to_dict(self):
        return asdict(self)

    def config_hash(self):
        raw = json.dumps(self.to_dict(), sort_keys=True).encode()
        return hashlib.sha1(raw).hexdigest()[:10]
