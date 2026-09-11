"""Flight recorder: a downsampled time series plus every event, and the run manifest.

The manifest holds everything needed to regenerate a run: code version, config hash,
scenario and seed (requirement AERIS-REQ-LOG-002).
"""
import functools
import platform
import subprocess
from pathlib import Path

import numpy as np

HEALTH_CODE = {"NOMINAL": 0, "SUSPECT": 1, "DEGRADED": 2, "FAILED": 3, "UNKNOWN": 4}


@functools.lru_cache(maxsize=1)
def code_version():
    try:
        root = Path(__file__).resolve().parents[2]
        sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                             text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                               text=True, timeout=5).stdout.strip()
        return (sha or "unknown") + ("-dirty" if dirty else "")
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def manifest(scenario, config_arm, aeris_config):
    return {
        "scenario_id": scenario["scenario_id"],
        "seed": scenario["seed"],
        "config_arm": config_arm,
        "aeris_config_hash": aeris_config.config_hash(),
        "code_version": code_version(),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "simulator": "aeris in-process point-mass simulator + stand-in autopilot",
        "scenario": scenario,
    }


class Recorder:
    def __init__(self, every_n_ticks=10):
        self.every = every_n_ticks
        self.rows = []
        self.tick = 0

    def sample(self, t, vehicle, autopilot, aeris, wind):
        self.tick += 1
        if self.tick % self.every:
            return
        est = autopilot.est.pos
        health = aeris.health_snapshot() if aeris is not None else {}
        self.rows.append([
            round(t, 2),
            round(float(vehicle.pos[0]), 2), round(float(vehicle.pos[1]), 2), round(float(vehicle.pos[2]), 2),
            round(float(est[0]), 2), round(float(est[1]), 2), round(float(est[2]), 2),
            autopilot.mode,
            {k: HEALTH_CODE[v] for k, v in health.items()},
            round(vehicle.battery.soc, 3), round(float(vehicle.battery.voltage), 2),
            round(float(np.hypot(wind[0], wind[1])), 1),
        ])

    COLUMNS = ["t", "x", "y", "z", "est_x", "est_y", "est_z", "mode", "health", "soc", "volts", "wind"]
