"""State estimator for the stand-in autopilot (a simplified, EKF2-like filter).

One small Kalman filter per axis, each with state [position, velocity]:
- predict with the accelerometer, rotated into the world frame by the heading estimate
- correct with GPS position/velocity, barometer height and vision velocity

Like PX4's EKF2, every measurement passes an innovation gate: if it disagrees with
the prediction by more than GATE standard deviations it is rejected. That protects
against sudden jumps. It does *not* protect against a slow drift that stays inside
the gate. The filter fuses it and follows it, which is the weakness AERIS targets.

This is a teaching stand-in, not PX4. See docs/ARCHITECTURE.md.
"""
import math

G = 9.81
GATE = 5.0             # standard deviations, like EKF2_GPS_P_GATE's default
NO_AID_TIMEOUT = 5.0   # s without horizontal aiding before position is declared invalid
RESET_AFTER = 5.0      # s of continuous GPS rejection before resetting to GPS (no other aiding)


class AxisKF:
    def __init__(self, q_accel=0.5):
        self.p, self.v = 0.0, 0.0
        self.P = [[1.0, 0.0], [0.0, 1.0]]
        self.q = q_accel * q_accel

    def predict(self, a, dt):
        self.p += self.v * dt + 0.5 * a * dt * dt
        self.v += a * dt
        (p00, p01), (p10, p11) = self.P
        q = self.q
        # P = F P F^T + Q  with F = [[1, dt], [0, 1]]
        n00 = p00 + dt * (p10 + p01) + dt * dt * p11 + 0.25 * dt ** 4 * q
        n01 = p01 + dt * p11 + 0.5 * dt ** 3 * q
        n11 = p11 + dt * dt * q
        self.P = [[n00, n01], [n01, n11]]

    def test(self, z, r, index, gate=GATE):
        """Innovation test ratio without fusing (> 1 means the measurement would be rejected)."""
        x = self.p if index == 0 else self.v
        return (z - x) ** 2 / (gate * gate * (self.P[index][index] + r))

    def update(self, z, r, index, gate=GATE):
        """Fuse measurement z of state[index] (0 = position, 1 = velocity).
        Returns the test ratio (> 1 means rejected), like EKF2's innovation test ratio."""
        x = self.p if index == 0 else self.v
        y = z - x
        s = self.P[index][index] + r
        ratio = (y * y) / (gate * gate * s)
        if ratio > 1.0:
            return ratio
        k0 = self.P[0][index] / s
        k1 = self.P[1][index] / s
        self.p += k0 * y
        self.v += k1 * y
        (p00, p01), (p10, p11) = self.P
        pi0, pi1 = self.P[index]
        self.P = [[p00 - k0 * pi0, p01 - k0 * pi1], [p10 - k1 * pi0, p11 - k1 * pi1]]
        self.P[1][0] = self.P[0][1]
        return ratio

    def reset(self, pos, var):
        self.p = pos
        self.P = [[var, 0.0], [0.0, self.P[1][1]]]


class Estimator:
    def __init__(self):
        self.axes = [AxisKF(), AxisKF(), AxisKF(q_accel=0.7)]
        self.yaw = 0.0
        self.excluded = set()          # sensors AERIS told us to stop using
        self.accel_bias_corr = (0.0, 0.0)
        self.last_h_aid = 0.0          # last time GPS or vision was fused
        self.last_v_aid = 0.0          # last time a height source was fused
        self.gps_rejected_since = None
        self.gps_test_ratio = 0.0
        self.t = 0.0

    @property
    def pos(self):
        return tuple(a.p for a in self.axes)

    @property
    def vel(self):
        return tuple(a.v for a in self.axes)

    def pos_valid(self):
        return self.t - self.last_h_aid < NO_AID_TIMEOUT

    def height_valid(self):
        return self.t - self.last_v_aid < NO_AID_TIMEOUT

    def step(self, t, dt, msgs):
        self.t = t
        if "imu" in msgs:
            (fx, fy, fz), gz = msgs["imu"]
            fx -= self.accel_bias_corr[0]
            fy -= self.accel_bias_corr[1]
            self.yaw = _wrap(self.yaw + gz * dt)
            c, s = math.cos(self.yaw), math.sin(self.yaw)
            a = (c * fx - s * fy, s * fx + c * fy, fz - G)
            for axis, acc in zip(self.axes, a):
                axis.predict(acc, dt)

        if "mag" in msgs and "mag" not in self.excluded:
            self.yaw = _wrap(self.yaw + 0.05 * _wrap(msgs["mag"] - self.yaw))

        if "gps" in msgs and "gps" not in self.excluded:
            pos, vel = msgs["gps"]["pos"], msgs["gps"]["vel"]
            # A GPS sample is judged as a whole: if its horizontal position fails the
            # innovation check, none of it (velocity, vertical) is fused.
            pos_ratio = max(self.axes[i].test(pos[i], 0.5 ** 2, 0) for i in range(2))
            self.gps_test_ratio = pos_ratio
            if pos_ratio <= 1.0:
                for i in range(2):
                    self.axes[i].update(pos[i], 0.5 ** 2, 0)
                    self.axes[i].update(vel[i], 0.15 ** 2, 1)
                self.axes[2].update(vel[2], 0.2 ** 2, 1)
                if "baro" in self.excluded and self.axes[2].update(pos[2], 1.0 ** 2, 0) <= 1.0:
                    self.last_v_aid = t
                self.last_h_aid = t
                self.gps_rejected_since = None
            else:
                if self.gps_rejected_since is None:
                    self.gps_rejected_since = t
                other_aid = self.has_vision_aiding(t)
                if t - self.gps_rejected_since > RESET_AFTER and not other_aid:
                    # Like many EKFs: after long rejection with nothing else to trust, reset to GPS.
                    self.axes[0].reset(pos[0], 0.5 ** 2)
                    self.axes[1].reset(pos[1], 0.5 ** 2)
                    self.gps_rejected_since = None

        if "vision" in msgs and "vision" not in self.excluded:
            vx, vy, vz = msgs["vision"]
            r = [self.axes[0].update(vx, 0.15 ** 2, 1), self.axes[1].update(vy, 0.15 ** 2, 1)]
            if max(r) <= 1.0:
                self.last_h_aid = t
                self._last_vision = t

        if "baro" in msgs and "baro" not in self.excluded:
            if self.axes[2].update(msgs["baro"], 0.4 ** 2, 0) <= 1.0:
                self.last_v_aid = t

    def has_vision_aiding(self, t):
        return t - getattr(self, "_last_vision", -1e9) < 1.0

    def reset_horizontal(self, x, y):
        self.axes[0].reset(x, 1.0)
        self.axes[1].reset(y, 1.0)


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi
