"""Run one closed-loop flight: simulator + stand-in autopilot + (optionally) AERIS.

Experiment configurations (v2 design, section 6):
  A  baseline  - autopilot and its failsafes only; AERIS off
  B  advisory  - AERIS watches, detects and diagnoses, but sends no commands
  C  active    - AERIS isolates faults and commands recovery; autopilot failsafes stay as fallback

Each tick (50 Hz):
  wind -> plant faults -> sensors -> sensor faults -> autopilot -> AERIS -> vehicle physics
"""
import math
import time

import numpy as np

from .adapters.standin import apply_commands, build_frame
from .autopilot.autopilot import Autopilot
from .autopilot.mission import GEOFENCE_ALT, GEOFENCE_RADIUS, HOME, Mission
from .core.config import AerisConfig
from .core.monitor import AerisCore
from .evidence.recorder import Recorder, manifest
from .sim.environment import Wind
from .sim.faults import FaultInjector, FaultSpec
from .sim.sensors import SensorSuite
from .sim.vehicle import Vehicle, VehicleParams

DT = 0.02
T_MAX = 420.0
CONFIGS = ("A", "B", "C")


def run_flight(scenario, config_arm="C", aeris_config=None, record_frames=False, kill_aeris_at=None):
    """Fly one scenario. Returns a plain dict (JSON-friendly) describing everything that happened."""
    if config_arm not in CONFIGS:
        raise ValueError(f"config_arm must be one of {CONFIGS}")
    cfg = aeris_config or AerisConfig()
    rng = np.random.default_rng(scenario["seed"])
    has_vision = scenario.get("vehicle", {}).get("has_vision", True)
    params = VehicleParams(has_vision=has_vision)
    vehicle = Vehicle(params, np.random.default_rng(rng.integers(1 << 32)))
    sensors = SensorSuite(np.random.default_rng(rng.integers(1 << 32)), has_vision)
    w = scenario.get("wind", {})
    wind = Wind(np.random.default_rng(rng.integers(1 << 32)), w.get("mean_mps", 0.0), w.get("dir_deg", 0.0))
    injector = FaultInjector([FaultSpec(**f) for f in scenario.get("faults", [])])
    mission = Mission()
    autopilot = Autopilot(mission)
    aeris = AerisCore(cfg, has_vision) if config_arm in ("B", "C") else None
    recorder = Recorder()

    frames, step_times, cmd_log = [], [], []
    wp_min_dist = [float("inf")] * len(mission.waypoints)
    max_cross_track, geofence_breach, took_off = 0.0, False, False
    ground_timer, t = 0.0, 0.0

    while t < T_MAX:
        t = round(t + DT, 4)
        wind_vec = wind.step(DT)
        injector.apply_plant(t, vehicle)
        msgs = injector.apply_sensors(t, sensors.sample(t, vehicle))
        cmd = autopilot.step(t, DT, msgs)

        if aeris is not None and (kill_aeris_at is None or t < kill_aeris_at):
            frame = build_frame(t, msgs, autopilot, vehicle.motor_outputs)
            if record_frames:
                frames.append(frame)
            t0 = time.perf_counter()
            commands = aeris.step(frame)
            step_times.append(time.perf_counter() - t0)
            if config_arm == "C":
                autopilot.aeris_heartbeat(t)
                for c, ok in apply_commands(commands, autopilot):
                    cmd_log.append({"t": t, "kind": c.kind, "value": _jsonable(c.value), "accepted": ok})

        vehicle.step(DT, cmd, wind_vec)
        recorder.sample(t, vehicle, autopilot, aeris, wind_vec)

        # --- truth-based bookkeeping for scoring (never visible to AERIS)
        p = vehicle.pos
        if p[2] > 1.0:
            took_off = True
        for i, (wx, wy) in enumerate(mission.waypoints):
            wp_min_dist[i] = min(wp_min_dist[i], math.hypot(p[0] - wx, p[1] - wy))
        if took_off and p[2] > 5.0:
            max_cross_track = max(max_cross_track, _dist_to_path(p[0], p[1], mission.planned_path()))
        if math.hypot(p[0], p[1]) > GEOFENCE_RADIUS or p[2] > GEOFENCE_ALT:
            geofence_breach = True
        if vehicle.crashed:
            break
        if took_off and vehicle.on_ground:
            ground_timer += DT
            if autopilot.mode == "LANDED" and ground_timer > 1.0 or ground_timer > 8.0:
                break
        else:
            ground_timer = 0.0

    landing_dist = math.hypot(vehicle.pos[0] - HOME[0], vehicle.pos[1] - HOME[1])
    landed_ok = vehicle.on_ground and not vehicle.crashed and took_off
    all_wps = all(d <= 3.0 for d in wp_min_dist)
    outcome = {
        "flight_time": round(t, 2),
        "crashed": bool(vehicle.crashed),
        "battery_depleted": bool(vehicle.battery.depleted),
        "landed": bool(landed_ok),
        "touchdown_speed": round(float(vehicle.max_impact_speed), 2),
        "landing_distance_from_home": round(landing_dist, 2),
        "geofence_breach": geofence_breach,
        "waypoints_reached_true": sum(d <= 3.0 for d in wp_min_dist),
        "max_cross_track": round(max_cross_track, 2),
        "final_soc": round(vehicle.battery.soc, 3),
        "final_mode": autopilot.mode,
        "timed_out": t >= T_MAX,
    }
    outcome["mission_success"] = bool(all_wps and landed_ok and landing_dist <= 5.0 and not geofence_breach)
    outcome["recovered"] = bool(landed_ok and vehicle.max_impact_speed < 1.5 and not geofence_breach)

    st = np.array(step_times) if step_times else np.zeros(1)
    result = {
        "manifest": manifest(scenario, config_arm, cfg),
        "truth": injector.truth(),
        "outcome": outcome,
        "aeris_events": [e.to_dict() for e in aeris.events] if aeris else [],
        "aeris_commands": cmd_log,
        "autopilot_events": [{"t": round(a, 2), "text": b} for a, b in autopilot.events],
        "deferred_failsafes": [{"t": round(a, 2), "what": b} for a, b in autopilot.deferred],
        "timeseries": {"columns": Recorder.COLUMNS, "rows": recorder.rows},
        "timing": {"aeris_steps": len(step_times), "mean_ms": round(float(st.mean()) * 1e3, 4),
                   "p99_ms": round(float(np.percentile(st, 99)) * 1e3, 4),
                   "max_ms": round(float(st.max()) * 1e3, 4),
                   "deadline_misses": int((st > DT).sum())},
        "planned_path": mission.planned_path(),
    }
    if record_frames:
        result["frames"] = frames
    return result


def _dist_to_path(x, y, path):
    best = float("inf")
    for (ax, ay), (bx, by) in zip(path, path[1:]):
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = 0.0 if L2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2))
        best = min(best, math.hypot(x - (ax + u * dx), y - (ay + u * dy)))
    return best


def _jsonable(v):
    if isinstance(v, tuple):
        return [float(x) for x in v]
    return v
