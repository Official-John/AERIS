"""Scenario files and the random scenario generator for fault campaigns.

A scenario is a small JSON-friendly dict:
{
  "scenario_id": "gps_drift_0007",
  "seed": 12345,                         # makes the whole flight reproducible
  "vehicle": {"has_vision": true},
  "wind": {"mean_mps": 4.0, "dir_deg": 200},
  "faults": [{"type": "gps_drift", "start": 40.0, "params": {"rate_mps": 0.4, "direction_deg": 90}}],
  "severity": 0.43,                      # 0..1, for detection-vs-severity plots
  "split": "evaluation"                  # tuning | evaluation
}
"""
import json
import math
from pathlib import Path

import numpy as np

FAULT_FAMILIES = ["none", "gps_off", "gps_stuck", "gps_drift", "baro_stuck", "mag_offset",
                  "imu_bias", "motor_degradation", "battery_fault"]


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def split_for(seed):
    """Deterministic 30/70 split. Tune thresholds on 'tuning', report on 'evaluation'."""
    return "tuning" if seed % 10 < 3 else "evaluation"


def _fault(ftype, rng):
    """Random parameters for one fault. Returns (params, severity 0..1)."""
    u = rng.uniform
    if ftype in ("gps_off", "gps_stuck", "baro_stuck"):
        return {}, 1.0
    if ftype == "gps_drift":
        rate = u(0.1, 0.8)
        return {"rate_mps": round(rate, 3), "direction_deg": round(u(0, 360), 1)}, (rate - 0.1) / 0.7
    if ftype == "mag_offset":
        off = u(10, 60) * rng.choice([-1, 1])
        return {"offset_deg": round(off, 1)}, (abs(off) - 10) / 50
    if ftype == "imu_bias":
        mag, d = u(0.2, 1.0), u(0, 2 * math.pi)
        return {"bx": round(mag * math.cos(d), 3), "by": round(mag * math.sin(d), 3)}, (mag - 0.2) / 0.8
    if ftype == "motor_degradation":
        eff = u(0.55, 0.9)
        return {"motor": int(rng.integers(0, 4)), "efficiency": round(eff, 3)}, (0.9 - eff) / 0.35
    if ftype == "battery_fault":
        loss, rm = u(0.3, 0.8), u(1.0, 2.2)
        return {"charge_loss": round(loss, 3), "resistance_mult": round(rm, 2)}, (loss - 0.3) / 0.5
    raise ValueError(ftype)


def generate(per_fault, base_seed=1000, no_vision_fraction=0.25, families=None):
    scenarios = []
    for fi, ftype in enumerate(families or FAULT_FAMILIES):
        for k in range(per_fault):
            seed = base_seed + fi * 10000 + k
            rng = np.random.default_rng(seed)
            sc = {
                "scenario_id": f"{ftype}_{k:04d}",
                "seed": seed,
                "vehicle": {"has_vision": bool(rng.uniform() >= no_vision_fraction)},
                "wind": {"mean_mps": round(float(rng.uniform(0, 8)), 2), "dir_deg": round(float(rng.uniform(0, 360)), 1)},
                "faults": [],
                "severity": None,
                "split": split_for(seed),
            }
            if ftype != "none":
                params, sev = _fault(ftype, rng)
                sc["faults"] = [{"type": ftype, "start": round(float(rng.uniform(25, 70)), 2), "params": params}]
                sc["severity"] = round(float(sev), 3)
            scenarios.append(sc)
    return scenarios
