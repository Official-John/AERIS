"""Turn scored runs into metrics with 95 % confidence intervals.

Why intervals: "detected 19 of 20" and "detected 950 of 1000" are both 95 %, but
the second is far more trustworthy. The interval shows how much.
"""
import math

import numpy as np

Z = 1.959964   # 95 %


def wilson(k, n):
    """Rate k/n with a Wilson score interval. Returns (rate, low, high)."""
    if n == 0:
        return (None, None, None)
    p = k / n
    d = 1 + Z * Z / n
    centre = (p + Z * Z / (2 * n)) / d
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / d
    return (round(p, 4), round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4))


def poisson_rate(count, exposure):
    """Events per unit exposure with Byar's approximate 95 % interval."""
    if exposure <= 0:
        return (None, None, None)
    lo = 0.0 if count == 0 else count * (1 - 1 / (9 * count) - Z / (3 * math.sqrt(count))) ** 3
    hi = (count + 1) * (1 - 1 / (9 * (count + 1)) + Z / (3 * math.sqrt(count + 1))) ** 3
    return (round(count / exposure, 4), round(lo / exposure, 4), round(hi / exposure, 4))


def median_ci(values, n_boot=1000, seed=0):
    """Median with a bootstrap 95 % interval."""
    if not values:
        return (None, None, None)
    v = np.asarray(values, dtype=float)
    rng = np.random.default_rng(seed)
    boots = np.median(rng.choice(v, size=(n_boot, len(v)), replace=True), axis=1)
    return (round(float(np.median(v)), 3), round(float(np.percentile(boots, 2.5)), 3),
            round(float(np.percentile(boots, 97.5)), 3))


def summarize(records, split="evaluation"):
    """records: list of dicts (scenario info + oracle score + outcome), one per run."""
    recs = [r for r in records if split is None or r["split"] == split]
    by = {}
    for r in recs:
        by.setdefault(r["config"], []).append(r)
    summary = {"split": split, "runs": len(recs), "configs": sorted(by)}
    fault_types = sorted({r["fault_type"] for r in recs})
    summary["fault_types"] = fault_types

    # --- detection and diagnosis: advisory runs (B), where AERIS can't change the flight
    B = by.get("B", [])
    det = {}
    for ft in fault_types:
        if ft == "none":
            continue
        rows = [r for r in B if r["fault_type"] == ft]
        lat = [r["latency"] for r in rows if r["detected"]]
        det[ft] = {
            "n": len(rows),
            "detection_rate": wilson(sum(r["detected"] for r in rows), len(rows)),
            "latency_median": median_ci(lat),
            "latency_p95": round(float(np.percentile(lat, 95)), 3) if lat else None,
            "isolation_accuracy": wilson(sum(r["isolation_correct"] for r in rows), len(rows)),
            "missed": sum(not r["detected"] for r in rows),
        }
    summary["detection"] = det
    fa = sum(r["false_alarms"] for r in B)
    hours = sum(r["clean_hours"] for r in B)
    summary["false_alarms"] = {"count": fa, "clean_flight_hours": round(hours, 3),
                               "per_hour": poisson_rate(fa, hours)}
    made = sum(r["diagnoses_made"] for r in B)
    correct = sum(r["diagnoses_correct"] for r in B)
    summary["diagnosis_precision"] = wilson(correct, made)

    labels = sorted({r["expected"] for r in B if r["expected"]})
    predicted = sorted({r["diagnosis"] or "none" for r in B if r["expected"]} | {"none"})
    matrix = {e: {p: 0 for p in predicted} for e in labels}
    for r in B:
        if r["expected"]:
            matrix[r["expected"]][r["diagnosis"] or "none"] += 1
    summary["confusion"] = {"expected": labels, "predicted": predicted, "counts": matrix}

    bins = [(0.0, 0.85), (0.85, 0.95), (0.95, 1.01)]
    calib = []
    for lo, hi in bins:
        rows = [r for r in B if r["confidence"] is not None and lo <= r["confidence"] < hi]
        calib.append({"bin": f"{lo:.2f}-{min(hi, 1.0):.2f}", "n": len(rows),
                      "mean_confidence": round(float(np.mean([r["confidence"] for r in rows])), 3) if rows else None,
                      "accuracy": wilson(sum(r["isolation_correct"] for r in rows), len(rows))})
    summary["calibration"] = calib

    sev = {}
    for ft in fault_types:
        rows = [r for r in B if r["fault_type"] == ft and r["severity"] is not None]
        if not rows or ft == "none":
            continue
        edges = np.linspace(0.0, 1.0, 5)
        sev[ft] = []
        for lo, hi in zip(edges, edges[1:]):
            sub = [r for r in rows if lo <= r["severity"] < hi or (hi == 1.0 and r["severity"] == 1.0)]
            sev[ft].append({"severity": f"{lo:.2f}-{hi:.2f}", "n": len(sub),
                            "detection_rate": wilson(sum(r["detected"] for r in sub), len(sub))})
    summary["detection_vs_severity"] = sev

    # --- outcomes: baseline (A) against AERIS active (C), same scenarios
    out = {}
    for ft in fault_types:
        out[ft] = {}
        for cfg in ("A", "C"):
            rows = [r for r in by.get(cfg, []) if r["fault_type"] == ft]
            if not rows:
                continue
            n = len(rows)
            out[ft][cfg] = {
                "n": n,
                "mission_success": wilson(sum(r["mission_success"] for r in rows), n),
                "recovered": wilson(sum(r["recovered"] for r in rows), n),
                "crashed": wilson(sum(r["crashed"] for r in rows), n),
                "geofence_breach": wilson(sum(r["geofence_breach"] for r in rows), n),
                "landing_distance_median": median_ci([r["landing_distance_from_home"] for r in rows]),
            }
    summary["outcomes"] = out

    steps = [r for r in recs if r["timing"]["aeris_steps"]]
    summary["timing"] = {
        "runs": len(steps),
        "aeris_steps": sum(r["timing"]["aeris_steps"] for r in steps),
        "deadline_misses": sum(r["timing"]["deadline_misses"] for r in steps),
        "worst_p99_ms": max((r["timing"]["p99_ms"] for r in steps), default=None),
        "worst_max_ms": max((r["timing"]["max_ms"] for r in steps), default=None),
        "mean_ms": round(float(np.mean([r["timing"]["mean_ms"] for r in steps])), 4) if steps else None,
    }
    return summary
