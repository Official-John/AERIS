"""AerisCore: the health monitor that ties detection, diagnosis and recovery together.

Call step(frame) every tick (50 Hz). It returns a list of Commands for the autopilot.
All events (health changes, diagnoses with evidence, actions) accumulate in .events.

The pipeline, in order:
  1. detectors turn raw signals into Evidence (timeouts, stuck values, residuals)
  2. every 0.1 s each component's health state machine is updated
  3. when a component's fault is confirmed, the signature matrix names the fault
  4. the faulty sensor is isolated (excluded) or compensated
  5. the recovery manager picks the least severe action the aircraft can still fly
"""
import math

from . import diagnosis, recovery
from .config import AerisConfig
from .detectors import Cusum, Ewma, StuckTest, Threshold, TimeoutTest
from .health import ComponentHealth
from .independent import IndependentEstimator
from .twin import AccelTwin, BatteryTwin, energy_to_home_wh
from .types import COMPONENTS, DEGRADED, FAILED, NOMINAL, SUSPECT, UNKNOWN, Command, Event

G = 9.81
HOME = (0.0, 0.0)
FLYING_MODES = ("TAKEOFF", "MISSION", "HOLD", "RETURN", "LAND", "DESCEND")

COMPONENT_TESTS = {
    "gps": ["gps.timeout", "gps.stuck", "gps.vel_consistency", "gps.pos_residual"],
    "baro": ["baro.timeout", "baro.stuck"],
    "mag": ["mag.timeout", "mag.heading_residual"],
    "imu": ["imu.timeout", "imu.accel_residual"],
    "vision": ["vision.timeout"],
    "motors": ["motor.imbalance"],
    "battery": ["battery.voltage_residual"],
}
IMMEDIATE = {"gps.timeout", "gps.stuck", "baro.timeout", "baro.stuck", "mag.timeout",
             "imu.timeout", "vision.timeout"}
MODE_FOR_ACTION = {"CONTINUE_DEGRADED": "CONTINUE", "RETURN": "RETURN", "LAND": "LAND",
                   "DESCEND": "DESCEND", "TERMINATE": "TERMINATE"}


class AerisCore:
    def __init__(self, config=None, has_vision=True):
        self.cfg = c = config or AerisConfig()
        self.has_vision = has_vision
        self.health = {n: ComponentHealth(n, c.confirm_m, c.confirm_n, c.clear_time) for n in COMPONENTS}
        self.timeouts = {
            "gps": TimeoutTest("gps.timeout", c.gps_timeout),
            "baro": TimeoutTest("baro.timeout", c.baro_timeout),
            "mag": TimeoutTest("mag.timeout", c.mag_timeout),
            "imu": TimeoutTest("imu.timeout", c.imu_timeout),
            "vision": TimeoutTest("vision.timeout", 0.5),
        }
        self.gps_stuck = StuckTest("gps.stuck", c.stuck_repeats)
        self.baro_stuck = StuckTest("baro.stuck", c.stuck_repeats)
        self.gps_vel = Cusum("gps.vel_consistency", c.gps_vel_k, c.gps_vel_h)
        self.gps_vel_filt = [Ewma(1.0, 0.0), Ewma(1.0, 0.0)]
        self.gps_pos = Threshold("gps.pos_residual", c.gps_pos_threshold)
        self._gps_pos_f = Ewma(c.gps_pos_tau, 0.0)
        self._flying_since = None
        self.gps_innov = Threshold("gps.innovation", 0.5)
        self.mag_resid = Threshold("mag.heading_residual", c.mag_threshold_deg)
        self.imu_resid = Cusum("imu.accel_residual", c.imu_k, c.imu_h)
        self.twin_resid = Cusum("twin.accel_residual", c.twin_k, c.twin_h)
        self.motor_imb = Threshold("motor.imbalance", c.motor_imbalance)
        self.batt_resid = Threshold("battery.voltage_residual", c.battery_residual_v)

        self.indep = IndependentEstimator()
        self.accel_twin = AccelTwin()
        self.batt_twin = BatteryTwin(c.battery_capacity_wh, c.battery_resistance)
        self._prev_accel_sp = (0.0, 0.0, 0.0)
        self._twin_fast = [Ewma(0.5) for _ in range(3)]
        self._twin_base = [Ewma(20.0) for _ in range(3)]
        self._motor_f = Ewma(1.0)
        self._motor_each = [Ewma(1.0) for _ in range(4)]
        self.thrust_margin = c.thrust_to_weight
        self._batt_f = Ewma(2.0)
        self._imu_acc = [0.0, 0.0]        # integral of IMU world acceleration in the window
        self._imu_win_start = None        # (t, vx, vy) of the external velocity at window start
        self._imu_bias_hist = []          # recent window residuals, for bias estimation
        self._vision_prop = None          # (t_sample, [vx, vy]) vision velocity carried forward by the IMU
        self._last_batt_t = None
        self.last_battery = None          # latest (volts, amps); battery messages come at 10 Hz only
        self._soc_v_f = Ewma(5.0)
        self._soc_v_smoothed = None
        self._escalate_votes = 0          # consecutive re-checks asking for a more severe action

        self.evidence = {}
        self.events = []
        self.active = {}                  # component -> Diagnosis
        self.action = None
        self.t = 0.0
        self._last_t = None
        self._next_eval = 0.0
        self._next_decision = 0.0
        self.flying = False

    # ------------------------------------------------------------------ main entry
    def step(self, f):
        self.t = t = f.t
        dt = 0.02 if self._last_t is None else max(t - self._last_t, 1e-6)
        self._last_t = t
        airborne = f.armed and f.mode in FLYING_MODES and f.est_pos[2] > 2.0
        if airborne and self._flying_since is None:
            self._flying_since = t
        elif not airborne:
            self._flying_since = None
        # In-flight residual tests wait until the aircraft has settled after take-off.
        self.flying = airborne and t - self._flying_since >= self.cfg.settle_time
        commands = []

        self._timeouts_and_presence(f)
        self.indep.update(f, gps_trusted=self._ok("gps"), mag_trusted=self._ok("mag"),
                          vision_trusted=self._ok("vision"))
        self._imu_tests(f, dt)
        self._gps_tests(f)
        self._baro_mag_tests(f)
        self._motor_battery_tests(f, dt)

        if t >= self._next_eval:
            self._next_eval = t + self.cfg.health_period
            commands += self._evaluate_health(t, f)
        if self.active and t >= self._next_decision:
            commands += self._decide(t, f, reason="periodic re-check")
        if "imu" in self.active:
            commands += self._refine_bias(t)
        return commands

    # ------------------------------------------------------------------ detectors
    def _ok(self, comp):
        return self.health[comp].state == NOMINAL

    def _record(self, ev):
        self.evidence[ev.test_id] = ev
        return ev

    def _timeouts_and_presence(self, f):
        present = {"gps": f.gps_pos is not None, "baro": f.baro is not None, "mag": f.mag is not None,
                   "imu": f.imu is not None, "vision": f.vision is not None}
        for comp, got in present.items():
            if comp == "vision" and not self.has_vision:
                continue
            self._record(self.timeouts[comp].update(f.t, got))
            if got and self.health[comp].seen_data():
                self._event(f.t, "health", comp, f"{comp}: data arriving, NOMINAL")
        for comp, got in (("motors", f.motor_outputs is not None), ("battery", f.battery is not None)):
            if got and self.health[comp].seen_data():
                self._event(f.t, "health", comp, f"{comp}: data arriving, NOMINAL")

    def _gps_tests(self, f):
        self._record(self.gps_innov.update(f.gps_test_ratio))
        if f.gps_pos is None:
            for ev in (self.gps_stuck.update(None), self.gps_vel.evidence(), self.gps_pos.update(None)):
                self._record(ev)
            return
        self._record(self.gps_stuck.update(tuple(f.gps_pos)))
        # Vision and GPS arrive at different instants; the vision velocity has been carried
        # forward with the IMU so both describe the same moment.
        vp = self._vision_prop
        if self.flying and vp is not None and f.t - vp[0] < 0.25 and self._ok("vision"):
            dx = self.gps_vel_filt[0].update(f.gps_vel[0] - vp[1][0], 0.1)
            dy = self.gps_vel_filt[1].update(f.gps_vel[1] - vp[1][1], 0.1)
            self._record(self.gps_vel.update(math.hypot(dx, dy)))
        else:
            self._record(self.gps_vel.evidence())
        if self.flying and self.indep.pos is not None and self.has_vision and self._ok("vision"):
            r = math.hypot(f.gps_pos[0] - self.indep.pos[0], f.gps_pos[1] - self.indep.pos[1])
            self._record(self.gps_pos.update(self._gps_pos_f.update(r, 0.1)))
        else:
            self._record(self.gps_pos.update(0.0))

    def _baro_mag_tests(self, f):
        self._record(self.baro_stuck.update(f.baro))
        if f.mag is not None and self.indep.heading is not None:
            err = abs(math.degrees(_wrap(f.mag - self.indep.heading)))
            self._record(self.mag_resid.update(err))
        elif "mag.heading_residual" not in self.evidence:
            self._record(self.mag_resid.update(0.0))

    def _imu_tests(self, f, dt):
        if f.imu is None:
            return
        (fx, fy, fz), _ = f.imu
        # Residual 1: IMU against the change in an external velocity (vision, else GPS).
        # Uses AERIS's own gyro-based heading, so a magnetometer fault doesn't leak in.
        hd = self.indep.heading if self.indep.heading is not None else f.est_yaw
        c, s = math.cos(hd), math.sin(hd)
        awx, awy = c * fx - s * fy, s * fx + c * fy
        self._imu_acc[0] += awx * dt
        self._imu_acc[1] += awy * dt
        if f.vision is not None:
            self._vision_prop = (f.t, [f.vision[0], f.vision[1]])
        elif self._vision_prop is not None:
            self._vision_prop[1][0] += awx * dt
            self._vision_prop[1][1] += awy * dt
        ext = None
        if f.vision is not None and self._ok("vision"):
            ext = f.vision
        elif f.gps_vel is not None and self._ok("gps") and not self.has_vision:
            ext = f.gps_vel
        if ext is not None:
            if self._imu_win_start is None or not self.flying:
                self._imu_win_start = (f.t, ext[0], ext[1])
                self._imu_acc = [0.0, 0.0]
            elif f.t - self._imu_win_start[0] >= self.cfg.imu_window - 1e-9:
                t0, vx0, vy0 = self._imu_win_start
                T = f.t - t0
                rx = (self._imu_acc[0] - (ext[0] - vx0)) / T
                ry = (self._imu_acc[1] - (ext[1] - vy0)) / T
                self._imu_bias_hist = (self._imu_bias_hist + [(rx, ry, hd, f.t)])[-60:]
                self._record(self.imu_resid.update(math.hypot(rx, ry)))
                self._imu_win_start = (f.t, ext[0], ext[1])
                self._imu_acc = [0.0, 0.0]
        if "imu.accel_residual" not in self.evidence:
            self._record(self.imu_resid.evidence())

        # Residual 2: IMU against the twin's predicted acceleration (analytical redundancy).
        # Rotated with the autopilot's heading, the same frame the setpoint was made in.
        c, s = math.cos(f.est_yaw), math.sin(f.est_yaw)
        meas = (c * fx - s * fy, s * fx + c * fy, fz - G)
        # The IMU sample was taken before this tick's setpoint existed: use the previous one.
        pred = self.accel_twin.predict(self._prev_accel_sp, f.est_vel, dt)
        self._prev_accel_sp = f.accel_sp
        d2 = 0.0
        for i in range(3):
            r = meas[i] - pred[i]
            fast = self._twin_fast[i].update(r, dt)
            base = self._twin_base[i].update(r, dt) if self.flying else self._twin_base[i].value or 0.0
            d2 += (fast - base) ** 2
        self._twin_d = math.sqrt(d2)

    def _motor_battery_tests(self, f, dt):
        if f.motor_outputs is not None and self.flying:
            u = sorted(f.motor_outputs)
            spread = u[-1] - 0.5 * (u[1] + u[2])
            self._record(self.motor_imb.update(self._motor_f.update(spread, dt)))
            # Thrust headroom: a weak motor needs a higher command for the same thrust,
            # so median/max output estimates its efficiency, and the weakest motor
            # limits the whole aircraft.
            each = sorted(e.update(x, dt) for e, x in zip(self._motor_each, f.motor_outputs))
            if each[-1] > 1e-3:
                self.thrust_margin = self.cfg.thrust_to_weight * 0.5 * (each[1] + each[2]) / each[-1]
        elif "motor.imbalance" not in self.evidence:
            self._record(self.motor_imb.update(0.0))
        if f.battery is not None:
            v, i = f.battery
            self.last_battery = (v, i)
            if self._last_batt_t is not None:
                self.batt_twin.count(v, i, f.t - self._last_batt_t)
            self._last_batt_t = f.t
            if f.armed:
                resid = self.batt_twin.predicted_voltage(i) - v
                self._record(self.batt_resid.update(self._batt_f.update(resid, 0.1)))
            if self.health["battery"].state in (DEGRADED, FAILED) and self.batt_twin.r_ready:
                # voltage-based charge is noisy; smooth it before any what-if decision
                self._soc_v_smoothed = self._soc_v_f.update(self.batt_twin.soc_from_voltage(v, i), 0.1)
        if "battery.voltage_residual" not in self.evidence:
            self._record(self.batt_resid.update(0.0))

    # ------------------------------------------------------------------ health + diagnosis
    def _evaluate_health(self, t, f):
        if self.flying:
            self._record(self.twin_resid.update(getattr(self, "_twin_d", 0.0)))
        else:
            self.twin_resid.reset()
            self._record(self.twin_resid.evidence())
            self.imu_resid.reset()
            self._record(self.imu_resid.evidence())
            self.gps_vel.reset()
        tripped = {k for k, e in self.evidence.items() if e.tripped}
        commands = []
        for comp, h in self.health.items():
            if h.state in (UNKNOWN, DEGRADED, FAILED):
                continue
            comp_trips = [x for x in COMPONENT_TESTS[comp] if x in tripped]
            before = h.state
            state, confirmed = h.evaluate(t, bool(comp_trips), any(x in IMMEDIATE for x in comp_trips))
            if before == NOMINAL and state == SUSPECT:
                self._event(t, "health", comp, f"{comp}: NOMINAL -> SUSPECT ({', '.join(comp_trips)})")
                if comp == "battery":
                    self.batt_twin.restart_identification()
            elif before == SUSPECT and state == NOMINAL:
                self._event(t, "health", comp, f"{comp}: SUSPECT -> NOMINAL (cleared)")
            if confirmed:
                d = diagnosis.match(comp, tripped, self.evidence, t)
                if d is None and t - h.suspect_since >= self.cfg.isolation_wait:
                    d = diagnosis.unknown(comp, tripped, self.evidence, t)
                if d is not None:
                    commands += self._confirm(t, f, d)
        return commands

    def _confirm(self, t, f, d):
        h = self.health[d.component]
        h.set(d.health)
        self.active[d.component] = d
        self._event(t, "health", d.component, f"{d.component}: SUSPECT -> {d.health}")
        self._event(t, "diagnosis", d.component,
                    f"diagnosis {d.fault_id} (confidence {d.confidence:.2f})", d.to_dict())
        return self._isolate(t, f, d) + self._decide(t, f, reason=d.fault_id)

    def _isolate(self, t, f, d):
        cmds = []
        fid = d.fault_id
        if fid.startswith("GPS"):
            cmds.append(Command("exclude_sensor", "gps", f"{fid}: stop fusing GPS"))
            if self.indep.pos is not None and self.has_vision and self._ok("vision"):
                cmds.append(Command("reset_position", self.indep.pos,
                                    "re-anchor position on the independent vision estimate"))
        elif fid.startswith("BARO"):
            cmds.append(Command("exclude_sensor", "baro", f"{fid}: use GPS height"))
        elif fid.startswith("MAG"):
            cmds.append(Command("exclude_sensor", "mag", f"{fid}: hold heading on the gyro"))
        elif fid == "VISION_LOSS":
            cmds.append(Command("exclude_sensor", "vision", fid))
        elif fid == "IMU_BIAS" and self._imu_bias_hist:
            self._bias_since = self.health["imu"].suspect_since or 0.0
            cmds.append(Command("accel_bias", self._bias_estimate(), "compensate the estimated accelerometer bias"))
            self._next_bias_update = t + 5.0
        elif fid == "MOTOR_DEGRADED":
            cmds.append(Command("speed_limit", 3.0, "reduce the flight envelope for a weak motor"))
        for cmd in cmds:
            self._event(t, "action", d.component, f"{cmd.kind} {_fmt(cmd.value)}: {cmd.reason}")
            if cmd.kind == "accel_bias":
                self._last_bias = cmd.value
        return cmds

    def _bias_estimate(self):
        """Average IMU residual since the fault began, rotated into the body frame."""
        wins = [r for r in self._imu_bias_hist if r[3] >= self._bias_since] or self._imu_bias_hist[-1:]
        bx = by = 0.0
        for rx, ry, hd, _ in wins:   # rotate each window with its own heading
            c, s = math.cos(hd), math.sin(hd)
            bx += c * rx + s * ry
            by += -s * rx + c * ry
        return (bx / len(wins), by / len(wins))

    def _refine_bias(self, t):
        """The residual uses the raw IMU, so more windows keep sharpening the estimate."""
        if t < getattr(self, "_next_bias_update", float("inf")):
            return []
        self._next_bias_update = t + 5.0
        est = self._bias_estimate()
        if math.hypot(est[0] - self._last_bias[0], est[1] - self._last_bias[1]) < 0.05:
            return []
        self._last_bias = est
        self._event(t, "action", "imu", f"accel_bias {_fmt(est)}: refined bias estimate")
        return [Command("accel_bias", est, "refined accelerometer bias estimate")]

    # ------------------------------------------------------------------ recovery
    def energy_status(self, f):
        """What-if check with the twin: can we still fly home / finish the mission?

        Energy must cover the flight plus the reserve, AND the predicted loaded voltage
        at the end must stay above min_cell_voltage (a sagging pack can trigger a
        forced landing long before it is empty).
        """
        c = self.cfg
        cap = c.battery_capacity_wh
        bt = self.batt_twin
        batt = self.last_battery
        if self.health["battery"].state in (DEGRADED, FAILED) and batt is not None:
            soc = self._soc_v_smoothed if self._soc_v_smoothed is not None else bt.soc_from_voltage(*batt)
        else:
            soc = bt.soc_counted
        usable = soc * cap - c.reserve_fraction * cap
        home = energy_to_home_wh(f.est_pos, HOME, c.hover_power_w)
        path = [f.est_pos[:2]] + [tuple(w) for w in f.remaining_wps] + [HOME]
        dist = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(path, path[1:]))
        mission = c.hover_power_w * 1.1 * (dist / 6.0 + f.est_pos[2] + 20.0) / 3600.0
        amps = batt[1] if batt is not None else 12.0
        v_min = bt.cells * c.min_cell_voltage
        home_ok = usable > home and bt.loaded_voltage_at(soc - home / cap, amps) > v_min
        mission_ok = usable > mission and bt.loaded_voltage_at(soc - mission / cap, amps) > v_min
        return usable, home, mission, home_ok, mission_ok

    def _decide(self, t, f, reason):
        self._next_decision = t + 1.0
        if f.mode in ("LANDED", "PREFLIGHT"):
            return []
        batt = self.active.get("battery")
        if batt is not None and not self.batt_twin.r_ready and t - batt.t < 15.0 and self.action is None:
            # Battery decisions wait (up to 15 s) for a fresh resistance estimate; the
            # autopilot's critical-voltage failsafe still protects the aircraft meanwhile.
            if not getattr(self, "_batt_wait_logged", False):
                self._batt_wait_logged = True
                self._event(t, "info", "battery", "waiting for a fresh battery resistance estimate before deciding")
            return []
        usable, e_home, e_mission, home_ok, mission_ok = self.energy_status(f)
        states = {n: h.state for n, h in self.health.items()}
        caps = recovery.capabilities(states, self.has_vision, home_ok, mission_ok,
                                     self.thrust_margin >= self.cfg.min_thrust_margin)
        minimum = max((recovery.MINIMUM_ACTION.get(d.fault_id, "LAND") for d in self.active.values()),
                      key=recovery.ACTIONS.index)
        action = recovery.select_action(caps, minimum, self.cfg.allow_termination)
        if self.action is not None and recovery.ACTIONS.index(action) <= recovery.ACTIONS.index(self.action):
            self._escalate_votes = 0
            return []     # never step back down to a less cautious action
        if self.action is not None and reason == "periodic re-check":
            # A re-check escalates only if it asks for it three times in a row, so one
            # noisy estimate can't lock the aircraft into a worse action.
            self._escalate_votes += 1
            if self._escalate_votes < 3:
                return []
        self._escalate_votes = 0
        self.action = action
        why = (f"{reason}: least severe feasible action is {action} "
               f"(needs {sorted(recovery.NEEDS[action]) or 'nothing'}; missing "
               f"{sorted(set().union(*recovery.NEEDS.values()) - caps) or 'nothing'}; "
               f"usable energy {usable:.1f} Wh, mission {e_mission:.1f} Wh, home {e_home:.1f} Wh; "
               f"thrust margin {self.thrust_margin:.2f})")
        self._event(t, "action", "system", f"recovery {action}", {"why": why, "capabilities": sorted(caps)})
        return [Command("set_mode", MODE_FOR_ACTION[action], why)]

    # ------------------------------------------------------------------ utilities
    def _event(self, t, kind, comp, text, data=None):
        self.events.append(Event(round(t, 2), kind, comp, text, data or {}))

    def health_snapshot(self):
        return {n: h.state for n, h in self.health.items()}


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def _fmt(v):
    if isinstance(v, tuple):
        return "(" + ", ".join(f"{x:.2f}" for x in v) + ")"
    return str(v)
