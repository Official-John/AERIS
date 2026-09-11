"""The stand-in autopilot: estimator + controller + a commander with modes and failsafes.

It plays the part PX4 plays in the full design. Its failsafes follow PX4's layering
in spirit:
- position estimate lost      -> Descend (no position needed)
- battery below 20 % (counted) -> Return    (non-essential, AERIS may defer it)
- battery below 10 % or voltage critical -> Land
- geofence breached           -> Return

AERIS talks to it only through the small API at the bottom of the class (set_mode,
exclude_sensor, ...). That mirrors what PX4 exposes to a ROS 2 companion computer.
When AERIS and a failsafe disagree, the more severe action wins, as in PX4, where a
failsafe can override an external mode.
"""
import math

from ..sim.vehicle import VehicleCommand   # the airframe's command format
from .controller import PositionController
from .estimator import Estimator
from .mission import ACCEPT_RADIUS, GEOFENCE_ALT, GEOFENCE_RADIUS, HOME, Mission

SEVERITY = {"PREFLIGHT": 0, "TAKEOFF": 0, "MISSION": 0, "HOLD": 0, "RETURN": 1,
            "LAND": 2, "DESCEND": 3, "TERMINATE": 4, "LANDED": 5}
BATTERY_CAPACITY_WH = 40.0
LOW_BATTERY = 0.20
CRITICAL_BATTERY = 0.10
CRITICAL_CELL_V = 3.35
AERIS_HEARTBEAT_TIMEOUT = 1.0


class Autopilot:
    def __init__(self, mission=None, cells=4):
        self.mission = mission or Mission()
        self.est = Estimator()
        self.ctrl = PositionController()
        self.cells = cells
        self.mode = "PREFLIGHT"
        self.mode_source = "autopilot"
        self.wp_index = 0
        self.hold_point = None
        self.land_point = None
        self.speed_limit = self.mission.cruise_speed
        self.consumed_wh = 0.0
        self.battery_v = cells * 4.2
        self.battery_i = 0.0
        self.mission_done = False
        self.reached = []
        self.events = []            # (t, text) for the flight log
        self.deferred = []          # failsafes AERIS deferred, logged as required
        self.aeris_last_hb = None
        self.aeris_alive = False
        self._landed_timer = 0.0
        self.t = 0.0
        self.armed = False

    # ------------------------------------------------------------------ telemetry
    @property
    def soc_estimate(self):
        return max(0.0, 1.0 - self.consumed_wh / BATTERY_CAPACITY_WH)

    def telemetry(self):
        return {"pos": self.est.pos, "vel": self.est.vel, "yaw": self.est.yaw,
                "accel_sp": self.ctrl.last_accel_sp, "mode": self.mode,
                "gps_test_ratio": self.est.gps_test_ratio, "pos_valid": self.est.pos_valid(),
                "soc": self.soc_estimate, "wp_index": self.wp_index,
                "remaining_wps": self.mission.waypoints[self.wp_index:], "armed": self.armed,
                "excluded": sorted(self.est.excluded), "speed_limit": self.speed_limit}

    # ------------------------------------------------------------------ main loop
    def step(self, t, dt, msgs):
        self.t = t
        self.est.step(t, dt, msgs)
        if "battery" in msgs:
            self.battery_v, self.battery_i = msgs["battery"]
            self.consumed_wh += self.battery_v * self.battery_i * 0.1 / 3600.0

        if self.mode == "PREFLIGHT":
            if t >= 1.0:
                self.armed = True
                self._set("TAKEOFF", "autopilot", "armed, taking off")
            return VehicleCommand(motors_on=self.armed, accel_z=-1.0)
        if self.mode in ("LANDED", "TERMINATE"):
            return VehicleCommand(motors_on=False)

        self._check_aeris_heartbeat(t)
        self._failsafes(t)

        pos, vel = self.est.pos, self.est.vel
        target, vz, hold_h = None, None, True
        m = self.mode
        if m == "TAKEOFF":
            target = (HOME[0], HOME[1], self.mission.altitude)
            if pos[2] > self.mission.altitude - 2.0:
                self._set("MISSION", "autopilot", "reached cruise altitude")
        if m == "MISSION":
            if self.wp_index >= len(self.mission.waypoints):
                self.mission_done = True
                self._set("RETURN", "autopilot", "mission complete, returning")
            else:
                wx, wy = self.mission.waypoints[self.wp_index]
                target = (wx, wy, self.mission.altitude)
                if math.hypot(wx - pos[0], wy - pos[1]) < ACCEPT_RADIUS:
                    self.reached.append((t, self.wp_index))
                    self.wp_index += 1
        if self.mode == "HOLD":
            target = self.hold_point
        if self.mode == "RETURN":
            target = (HOME[0], HOME[1], max(pos[2], 20.0))
            if math.hypot(HOME[0] - pos[0], HOME[1] - pos[1]) < ACCEPT_RADIUS:
                self._set("LAND", "autopilot", "over home, landing")
        if self.mode == "LAND":
            if self.land_point is None:
                self.land_point = (pos[0], pos[1])
            target = (self.land_point[0], self.land_point[1], 0.0)
            vz = -1.0 if pos[2] > 3.0 else -0.5
        if self.mode == "DESCEND":
            target, hold_h = (pos[0], pos[1], 0.0), False
            vz = -1.0
        if target is None:
            target = (pos[0], pos[1], pos[2])

        a = self.ctrl.compute(dt, target, pos, vel, self.speed_limit, vz, hold_h)
        self._land_detector(dt, vz)
        if self.mode == "LANDED":
            return VehicleCommand(motors_on=False)

        c, s = math.cos(self.est.yaw), math.sin(self.est.yaw)
        body = (c * a[0] + s * a[1], -s * a[0] + c * a[1])   # world -> heading frame
        yaw_rate = -2.0 * self.est.yaw                          # hold heading 0
        return VehicleCommand(accel_body_xy=body, accel_z=a[2], yaw_rate=yaw_rate)

    # ------------------------------------------------------------------ internals
    def _set(self, mode, source, why):
        if mode == self.mode:
            self.mode_source = source
            return
        self.events.append((self.t, f"mode {self.mode} -> {mode} ({source}: {why})"))
        self.mode, self.mode_source = mode, source
        if mode == "HOLD":
            p = self.est.pos
            self.hold_point = (p[0], p[1], p[2])
        if mode == "LAND":
            self.land_point = None

    def _escalate(self, mode, why):
        if SEVERITY[mode] > SEVERITY[self.mode]:
            self._set(mode, "failsafe", why)

    def _failsafes(self, t):
        if self.mode in ("DESCEND", "TERMINATE", "LANDED", "PREFLIGHT"):
            return
        if not self.est.pos_valid():
            self._escalate("DESCEND", "position estimate lost")
            return
        if not self.est.height_valid():
            self._escalate("DESCEND", "height estimate lost")
            return
        v_cell = self.battery_v / self.cells
        if v_cell < CRITICAL_CELL_V or self.soc_estimate < CRITICAL_BATTERY:
            self._escalate("LAND", f"battery critical ({v_cell:.2f} V/cell, {self.soc_estimate:.0%})")
            return
        if self.soc_estimate < LOW_BATTERY and SEVERITY[self.mode] < SEVERITY["RETURN"]:
            if self.aeris_alive:
                if not self.deferred or self.deferred[-1][1] != "low battery return":
                    self.deferred.append((t, "low battery return"))
                    self.events.append((t, "failsafe 'low battery return' deferred to AERIS"))
            else:
                self._escalate("RETURN", f"battery low ({self.soc_estimate:.0%})")
                return
        p = self.est.pos
        if math.hypot(p[0], p[1]) > GEOFENCE_RADIUS or p[2] > GEOFENCE_ALT:
            self._escalate("RETURN", "geofence breach")

    def _land_detector(self, dt, vz_cmd):
        if self.mode not in ("LAND", "DESCEND"):
            self._landed_timer = 0.0
            return
        v = self.est.vel
        still = abs(v[2]) < 0.25 and math.hypot(v[0], v[1]) < 0.6
        self._landed_timer = self._landed_timer + dt if still else 0.0
        if self._landed_timer > 2.0:
            self.armed = False
            self._set("LANDED", "autopilot", "landing detected, disarmed")

    def _check_aeris_heartbeat(self, t):
        if self.aeris_last_hb is None:
            return
        alive = t - self.aeris_last_hb < AERIS_HEARTBEAT_TIMEOUT
        if self.aeris_alive and not alive:
            self.events.append((t, "AERIS heartbeat lost: autopilot keeps control with its own failsafes"))
            if self.mode_source == "aeris":
                self.mode_source = "autopilot"
        self.aeris_alive = alive

    # ------------------------------------------------------------------ API for AERIS
    def aeris_heartbeat(self, t):
        self.aeris_last_hb = t
        self.aeris_alive = True

    def set_mode(self, mode, why):
        """AERIS may escalate freely, or ask to continue the mission when no failsafe holds it."""
        if not self.aeris_alive or self.mode in ("PREFLIGHT", "LANDED", "TERMINATE"):
            return False
        if mode == "CONTINUE":
            return True
        if self.mode_source == "failsafe" and SEVERITY[mode] < SEVERITY[self.mode]:
            return False     # a failsafe is in charge; AERIS cannot downgrade it
        if SEVERITY[mode] < SEVERITY[self.mode] and self.mode not in ("MISSION", "HOLD", "TAKEOFF"):
            return False
        self._set(mode, "aeris", why)
        return True

    def exclude_sensor(self, name):
        if name not in self.est.excluded:
            self.est.excluded.add(name)
            self.events.append((self.t, f"estimator stops using {name} (requested by AERIS)"))

    def set_accel_bias_correction(self, bx, by):
        self.est.accel_bias_corr = (bx, by)
        self.events.append((self.t, f"accelerometer bias correction set to ({bx:.2f}, {by:.2f}) m/s^2"))

    def set_speed_limit(self, v):
        self.speed_limit = min(self.speed_limit, v)
        self.events.append((self.t, f"speed limit reduced to {v:.1f} m/s"))

    def reset_horizontal_position(self, x, y):
        self.est.reset_horizontal(x, y)
        self.events.append((self.t, f"horizontal position reset to ({x:.1f}, {y:.1f})"))
