"""Run many scenarios in parallel and save compact, scored records.

Every scenario is flown in each configuration (A baseline, B advisory, C active)
with the same seed, so the comparison is like-for-like.
"""
import json
import os
import time
from multiprocessing import Pool
from pathlib import Path

from ..evidence.oracle import score
from ..flight import run_flight


def _one(job):
    scenario, cfg = job
    r = run_flight(scenario, cfg)
    rec = {
        "scenario_id": scenario["scenario_id"], "seed": scenario["seed"], "config": cfg,
        "split": scenario.get("split", "evaluation"), "severity": scenario.get("severity"),
        "has_vision": scenario.get("vehicle", {}).get("has_vision", True),
        "wind": scenario.get("wind", {}).get("mean_mps", 0.0),
        "fault_params": scenario["faults"][0]["params"] if scenario.get("faults") else {},
        "timing": r["timing"], "config_hash": r["manifest"]["aeris_config_hash"],
        "code_version": r["manifest"]["code_version"],
    }
    rec.update(r["outcome"])
    rec.update(score(r))
    return rec


def run_campaign(scenarios, configs=("A", "B", "C"), workers=None, out_dir=None, progress=True):
    jobs = [(s, c) for s in scenarios for c in configs]
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    t0 = time.time()
    records = []
    with Pool(workers) as pool:
        for i, rec in enumerate(pool.imap_unordered(_one, jobs, chunksize=2), 1):
            records.append(rec)
            if progress and (i % 25 == 0 or i == len(jobs)):
                el = time.time() - t0
                print(f"  {i}/{len(jobs)} flights  ({el:.0f} s elapsed, ~{el / i * (len(jobs) - i):.0f} s left)",
                      flush=True)
    records.sort(key=lambda r: (r["scenario_id"], r["config"]))
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "runs.jsonl", "w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r) + "\n")
        (out / "scenarios.json").write_text(json.dumps(scenarios, indent=1), encoding="utf-8")
    return records, time.time() - t0
