"""Independent reference estimates, kept separate from the autopilot's estimator.

Why this exists: the autopilot's estimator fuses GPS, so comparing GPS against it
shows almost no disagreement during a slow GPS drift. These estimates avoid the
sensor under suspicion:

- horizontal position: integrate vision-odometry velocity, with only a very slow
  pull towards GPS while GPS is trusted (time constant 30 s)
- heading: integrate the gyro, with a very slow pull towards the magnetometer while
  the magnetometer is trusted

Each slow pull stops the moment its sensor becomes suspect, so the reference
doesn't follow the fault.
"""
import math

PULL_TAU = 30.0


class IndependentEstimator:
    def __init__(self):
        self.pos = None          # (x, y) from vision dead reckoning
        self.heading = None
        self._last_vision_t = None
        self._last_imu_t = None

    def update(self, frame, gps_trusted, mag_trusted, vision_trusted):
        t = frame.t
        if frame.imu is not None:
            gz = frame.imu[1]
            if self.heading is not None and self._last_imu_t is not None:
                self.heading = _wrap(self.heading + gz * (t - self._last_imu_t))
            self._last_imu_t = t
        if frame.mag is not None:
            if self.heading is None:
                self.heading = frame.mag
            elif mag_trusted:
                self.heading = _wrap(self.heading + (0.1 / PULL_TAU) * _wrap(frame.mag - self.heading))

        if frame.vision is not None and vision_trusted and self.pos is not None:
            if self._last_vision_t is not None:
                dt = t - self._last_vision_t
                self.pos = (self.pos[0] + frame.vision[0] * dt, self.pos[1] + frame.vision[1] * dt)
            self._last_vision_t = t
        if frame.gps_pos is not None:
            if self.pos is None:
                self.pos = (frame.gps_pos[0], frame.gps_pos[1])
            elif gps_trusted:
                k = 0.1 / PULL_TAU
                self.pos = (self.pos[0] + k * (frame.gps_pos[0] - self.pos[0]),
                            self.pos[1] + k * (frame.gps_pos[1] - self.pos[1]))


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi
