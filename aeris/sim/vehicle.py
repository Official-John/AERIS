"""The simulated aircraft: the "plant surrogate".

This module stands in for the real quadrotor and knows its *true* state.
Nothing in AERIS is allowed to read it. AERIS only sees sensor messages,
exactly as it would on a real aircraft.

Deliberate simplifications, so the whole thing runs in pure Python:
- point-mass translational dynamics; roll and pitch are not simulated, yaw is
- the thrust vector follows the command with a first-order lag
- linear aerodynamic drag against the air, so wind pushes the vehicle
- four motors share the thrust equally, so the weakest motor limits the total

Frame convention: x = east, y = north, z = up (metres). Yaw is measured
counter-clockwise from the x axis, in radians.
"""
import math
from dataclasses import dataclass

import numpy as np

from .battery import Battery

G = 9.81


@dataclass
class VehicleParams:
    mass: float = 2.0                # kg
    thrust_to_weight: float = 2.0    # all four motors at full command
    drag: float = 0.30               # N per m/s of airspeed
    thrust_tau: float = 0.10         # s, how fast the thrust vector responds
    max_tilt_deg: float = 35.0
    hover_power_w: float = 170.0
    avionics_power_w: float = 10.0
    has_vision: bool = True          # vision odometry fitted (like PX4's gz_x500_vision)


@dataclass
class VehicleCommand:
    """What the autopilot asks the airframe to do, in the vehicle's own heading frame."""
    accel_body_xy: tuple = (0.0, 0.0)   # m/s^2, forward/left
    accel_z: float = 0.0                # m/s^2, world up (not counting gravity)
    yaw_rate: float = 0.0               # rad/s
    motors_on: bool = True


class Vehicle:
    def __init__(self, params, rng):
        self.p = params
        self.rng = rng
        self.pos = np.zeros(3)
        self.vel = np.zeros(3)
        self.yaw = 0.0
        self.yaw_rate = 0.0
        self.thrust = np.array([0.0, 0.0, params.mass * G])  # actual thrust vector (N)
        self.specific_force = np.array([0.0, 0.0, G])        # what an ideal accelerometer feels
        self.motor_eff = np.ones(4)                          # 1.0 = healthy motor
        self.motor_outputs = np.full(4, 0.5)
        self.battery = Battery()
        self.on_ground = True
        self.max_impact_speed = 0.0
        self.crashed = False
        self.t_mm = params.thrust_to_weight * params.mass * G / 4.0  # max thrust per motor

    # ------------------------------------------------------------------ helpers
    def available_thrust(self):
        if self.battery.depleted:
            return 0.0
        return 4.0 * float(np.min(self.motor_eff)) * self.t_mm

    def thrust_margin(self):
        """Available thrust divided by weight. Below ~1.2 the vehicle struggles."""
        return self.available_thrust() / (self.p.mass * G)

    # ------------------------------------------------------------------ physics
    def step(self, dt, cmd, wind):
        m = self.p.mass
        c, s = math.cos(self.yaw), math.sin(self.yaw)
        ax_b, ay_b = cmd.accel_body_xy
        # The airframe tilts in its *true* heading frame. If the autopilot's heading
        # estimate is wrong, this is where the error turns into a wrong direction.
        a_h = np.array([c * ax_b - s * ay_b, s * ax_b + c * ay_b])

        f_des = np.array([m * a_h[0], m * a_h[1], m * (cmd.accel_z + G)])
        f_des[2] = max(f_des[2], 0.0)
        tilt_max = math.tan(math.radians(self.p.max_tilt_deg))
        h = math.hypot(f_des[0], f_des[1])
        if h > tilt_max * f_des[2] and h > 1e-9:
            f_des[:2] *= tilt_max * f_des[2] / h

        t_avail = self.available_thrust() if cmd.motors_on else 0.0
        t_req = float(np.linalg.norm(f_des))
        if t_req > t_avail:
            # Not enough thrust: keep as much vertical thrust as possible, cut horizontal.
            fz = min(f_des[2], t_avail)
            h_max = math.sqrt(max(t_avail * t_avail - fz * fz, 0.0))
            h = math.hypot(f_des[0], f_des[1])
            scale = min(1.0, h_max / h) if h > 1e-9 else 0.0
            f_des = np.array([f_des[0] * scale, f_des[1] * scale, fz])

        # Motor outputs: each motor carries a quarter of the thrust; a weak motor must
        # be driven harder for the same thrust. Small noise mimics attitude control.
        per_motor = float(np.linalg.norm(f_des)) / 4.0
        u = per_motor / (self.motor_eff * self.t_mm)
        u = u + self.rng.normal(0.0, 0.015, 4) * (1.0 if cmd.motors_on else 0.0)
        self.motor_outputs = np.clip(u, 0.0, 1.0)

        # The real thrust vector lags the command.
        self.thrust += (f_des - self.thrust) * min(dt / self.p.thrust_tau, 1.0)
        if not cmd.motors_on or self.battery.depleted:
            self.thrust[:] = 0.0

        t_mag = float(np.linalg.norm(self.thrust))
        power = self.p.hover_power_w * (t_mag / (m * G)) ** 1.5 + self.p.avionics_power_w
        delivered = self.battery.draw(power, dt)
        if delivered < 0.9 * power and t_mag > 0.0:
            # Brown-out: the pack sags so far that it can't power the motors.
            self.thrust *= delivered / power

        drag = -self.p.drag * (self.vel - wind)
        force = self.thrust + drag
        accel = force / m - np.array([0.0, 0.0, G])

        self.yaw_rate = cmd.yaw_rate
        self.yaw = (self.yaw + self.yaw_rate * dt + math.pi) % (2 * math.pi) - math.pi

        if self.on_ground:
            if self.thrust[2] > m * G * 1.01:
                self.on_ground = False
            else:
                self.vel[:] = 0.0
                self.specific_force = np.array([0.0, 0.0, G])
                return

        self.vel += accel * dt
        self.pos += self.vel * dt
        self.specific_force = force / m

        if self.pos[2] <= 0.0:
            impact = math.sqrt(self.vel[2] ** 2 + 0.25 * (self.vel[0] ** 2 + self.vel[1] ** 2))
            self.max_impact_speed = max(self.max_impact_speed, impact)
            if impact > 3.0:
                self.crashed = True
            self.pos[2] = 0.0
            self.vel[:] = 0.0
            self.on_ground = True
            self.specific_force = np.array([0.0, 0.0, G])
