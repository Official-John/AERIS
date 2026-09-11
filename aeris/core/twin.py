"""The digital twin: AERIS's own model of the aircraft.

Three jobs (see the v2 design document, section 4):
1. Expected state: predict the acceleration the aircraft *should* achieve from the
   autopilot's acceleration setpoint. A gap between that and the IMU is a residual.
2. Battery model: predict terminal voltage from counted charge and current.
3. What-if: before choosing Return, predict whether the energy left covers the
   flight home plus a reserve.

The parameters (drag, lag, hover power, resistance) are "calibrated" values that
match the simulator. With a real aircraft you would fit them from nominal flight logs.
"""
import math

import numpy as np

# Same cell curve as a typical 4S LiPo datasheet (identical to the simulator's).
OCV_SOC = np.array([0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 1.00])
OCV_CELL = np.array([3.00, 3.45, 3.60, 3.70, 3.78, 3.87, 4.00, 4.20])
G = 9.81


class AccelTwin:
    """Predicts achieved world acceleration from the setpoint (first-order lag + drag)."""

    def __init__(self, lag=0.10, drag_per_mass=0.15):
        self.lag, self.k_drag = lag, drag_per_mass
        self.a = [0.0, 0.0, 0.0]

    def predict(self, accel_sp, est_vel, dt):
        """accel_sp must be the setpoint the airframe was executing when the IMU sampled
        (the previous tick's), or the one-tick offset shows up as residual."""
        k = min(dt / self.lag, 1.0)
        self.a = [a + k * (sp - a) for a, sp in zip(self.a, accel_sp)]
        return tuple(a - self.k_drag * v for a, v in zip(self.a, est_vel))


class BatteryTwin:
    """Battery model with one parameter learned in flight: internal resistance.

    When the current changes (climbs, turns), the voltage moves the opposite way:
    R = -dV/dI. Each estimate compares the reading now with the one 1 s earlier (the
    open-circuit voltage barely moves in 1 s), keeps only pairs where the current
    changed by more than 1 A, and the result is the median of the last 15. The
    median ignores the few pairs that straddle a sudden voltage step, such as the
    moment a cell fails. A damaged pack shows up as a higher value.
    """

    def __init__(self, capacity_wh, resistance, cells=4):
        self.capacity, self.r_nominal, self.cells = capacity_wh, resistance, cells
        self.r_est = resistance
        self.consumed_wh = 0.0
        self._hist = []       # (volts, amps) over the last second
        self._r_samples = []

    def restart_identification(self):
        """Forget resistance samples: pairs that straddle a fault's voltage step are wrong.
        Until fresh samples arrive, fall back to the nominal value."""
        self._hist, self._r_samples = [], []
        self.r_est = self.r_nominal

    @property
    def r_ready(self):
        """15 good samples: fewer leave too much noise, and in the flat middle of the
        LiPo curve a small resistance error becomes a large state-of-charge error."""
        return len(self._r_samples) >= 15

    def count(self, volts, amps, dt):
        self.consumed_wh += volts * amps * dt / 3600.0
        self._hist.append((volts, amps))
        if len(self._hist) > 10:
            v0, i0 = self._hist.pop(0)
            di, dv = amps - i0, volts - v0
            if abs(di) > 1.0:
                self._r_samples = (self._r_samples + [min(max(-dv / di, 0.0), 1.0)])[-15:]
                if len(self._r_samples) >= 5:
                    self.r_est = float(np.median(self._r_samples))

    @property
    def soc_counted(self):
        return max(0.0, 1.0 - self.consumed_wh / self.capacity)

    def predicted_voltage(self, amps):
        """Voltage a healthy pack would show now (nominal resistance, counted charge)."""
        ocv = self.cells * float(np.interp(self.soc_counted, OCV_SOC, OCV_CELL))
        return ocv - amps * self.r_nominal

    def soc_from_voltage(self, volts, amps):
        v_cell = (volts + amps * self.r_est) / self.cells
        return float(np.interp(v_cell, OCV_CELL, OCV_SOC))

    def loaded_voltage_at(self, soc, amps):
        """What-if: terminal voltage at a future state of charge and current."""
        return self.cells * float(np.interp(max(soc, 0.0), OCV_SOC, OCV_CELL)) - amps * self.r_est


def energy_to_home_wh(pos, home, hover_power_w, cruise_speed=6.0, descent_rate=1.0):
    """Energy to fly home at cruise speed and descend, plus a 20 s margin."""
    dist = math.hypot(pos[0] - home[0], pos[1] - home[1])
    t = dist / cruise_speed + max(pos[2], 0.0) / descent_rate + 20.0
    return hover_power_w * 1.1 * t / 3600.0
