"""Sensor models: turn the true vehicle state into noisy messages.

Rates (the simulation runs at 50 Hz):
- IMU (accelerometer + yaw gyro): 50 Hz
- GPS position and velocity, barometer, magnetometer, vision odometry, battery: 10 Hz

Each message is a plain dict/tuple. A sensor that "stops" simply produces no message.
"""
import math

import numpy as np


class GaussMarkov:
    """Slowly wandering error, typical of GPS and barometers."""

    def __init__(self, rng, sigma, tau, dim=1):
        self.rng, self.sigma, self.tau = rng, sigma, tau
        self.x = rng.normal(0.0, sigma, dim)

    def step(self, dt):
        a = math.exp(-dt / self.tau)
        self.x = a * self.x + math.sqrt(1 - a * a) * self.sigma * self.rng.normal(0.0, 1.0, self.x.shape)
        return self.x


class SensorSuite:
    DT_SLOW = 0.1

    def __init__(self, rng, has_vision=True):
        self.rng = rng
        self.has_vision = has_vision
        self.tick = 0
        self.accel_bias = rng.normal(0.0, 0.02, 3)
        self.gyro_bias = rng.normal(0.0, 0.0005)
        self.gps_err = GaussMarkov(rng, 0.3, 60.0, 3)
        self.baro_err = GaussMarkov(rng, 0.3, 120.0)
        self.vision_err = GaussMarkov(rng, 0.02, 30.0, 3)

    def sample(self, t, v):
        """Return the messages produced this tick. v is the Vehicle."""
        n = self.rng.normal
        self.tick += 1
        msgs = {}

        c, s = math.cos(v.yaw), math.sin(v.yaw)
        f = v.specific_force
        # Rotate the world-frame specific force into the body (heading) frame.
        f_body = np.array([c * f[0] + s * f[1], -s * f[0] + c * f[1], f[2]])
        accel = f_body + self.accel_bias + n(0.0, 0.08, 3)
        gyro_z = v.yaw_rate + self.gyro_bias + n(0.0, 0.003)
        msgs["imu"] = (tuple(accel), gyro_z)

        phase = self.tick % 5
        if phase == 0:
            err = self.gps_err.step(0.1)
            pos = v.pos + err * np.array([1.0, 1.0, 1.5]) + n(0.0, 1.0, 3) * np.array([0.4, 0.4, 0.8])
            vel = v.vel + n(0.0, 0.08, 3)
            msgs["gps"] = {"pos": tuple(pos), "vel": tuple(vel)}
        elif phase == 1 and self.has_vision:
            vel = v.vel + self.vision_err.step(0.1) + n(0.0, 0.08, 3)
            msgs["vision"] = tuple(vel)
        elif phase == 2:
            msgs["baro"] = float(v.pos[2] + self.baro_err.step(0.1)[0] + n(0.0, 0.25))
        elif phase == 3:
            yaw = v.yaw + n(0.0, 0.015)
            msgs["mag"] = (yaw + math.pi) % (2 * math.pi) - math.pi
        elif phase == 4:
            msgs["battery"] = (v.battery.voltage + n(0.0, 0.02), v.battery.current + n(0.0, 0.1))
        return msgs
