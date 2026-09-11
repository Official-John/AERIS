"""Cascaded position controller: position error -> velocity setpoint -> acceleration setpoint.

It steers using the *estimated* state. If the estimate is wrong, the real
aircraft goes to the wrong place, which is how sensor faults become flight problems.
"""
import math

KP_H, KP_Z = 0.8, 1.0      # position gain (1/s)
KV_H, KV_Z = 2.0, 3.0      # velocity gain (1/s)
KI_H, KI_Z = 0.4, 0.8      # integral gain on velocity error (wind, weak motors)
A_MAX_H = 5.0              # m/s^2
V_UP, V_DOWN = 3.0, 1.5    # m/s


class PositionController:
    def __init__(self):
        self.integ = [0.0, 0.0, 0.0]
        self.last_accel_sp = (0.0, 0.0, 0.0)

    def compute(self, dt, target, pos, vel, speed_h, vz_override=None, hold_horizontal=True):
        """Return the world-frame acceleration setpoint (m/s^2, gravity not included).

        vz_override forces a vertical speed (used for landing).
        hold_horizontal=False flies "level" with no horizontal position control (Descend mode).
        """
        if hold_horizontal:
            ex, ey = target[0] - pos[0], target[1] - pos[1]
            vdx, vdy = KP_H * ex, KP_H * ey
            n = math.hypot(vdx, vdy)
            if n > speed_h:
                vdx, vdy = vdx * speed_h / n, vdy * speed_h / n
            evx, evy = vdx - vel[0], vdy - vel[1]
            self.integ[0] = _clip(self.integ[0] + KI_H * evx * dt, -3.0, 3.0)
            self.integ[1] = _clip(self.integ[1] + KI_H * evy * dt, -3.0, 3.0)
            ax, ay = KV_H * evx + self.integ[0], KV_H * evy + self.integ[1]
            n = math.hypot(ax, ay)
            if n > A_MAX_H:
                ax, ay = ax * A_MAX_H / n, ay * A_MAX_H / n
        else:
            ax = ay = 0.0

        if vz_override is not None:
            vdz = vz_override
        else:
            vdz = _clip(KP_Z * (target[2] - pos[2]), -V_DOWN, V_UP)
        evz = vdz - vel[2]
        self.integ[2] = _clip(self.integ[2] + KI_Z * evz * dt, -3.0, 3.0)
        az = _clip(KV_Z * evz + self.integ[2], -4.0, 6.0)
        self.last_accel_sp = (ax, ay, az)
        return self.last_accel_sp


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x
