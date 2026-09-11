"""Check the campaign-verified requirements against measured results.

pass is True, False, or None when the campaign had no runs that exercise the requirement.

Each check returns a dict with the requirement id, pass/fail and the evidence
behind it. The numbers are the starting targets from docs/requirements.json.
"""
from ..evidence.metrics import poisson_rate, wilson


def check(records, summary):
    B = [r for r in records if r["config"] == "B" and r["split"] == "evaluation"]
    results = []

    gps_off = [r for r in B if r["fault_type"] == "gps_off"]
    lat = [r["latency"] for r in gps_off if r["detected"]]
    worst = max(lat) if lat else None
    ok = None if not gps_off else (len(lat) == len(gps_off) and worst <= 0.5)
    results.append({"id": "AERIS-REQ-FDIR-001", "pass": ok,
                    "evidence": f"GPS stale declared in {len(lat)}/{len(gps_off)} GPS-outage runs; "
                                f"worst latency {worst if worst is None else round(worst, 2)} s (limit 0.5 s)"})

    drift = [r for r in B if r["fault_type"] == "gps_drift" and r["has_vision"]
             and r["fault_params"].get("rate_mps", 0) >= 0.5]
    hit = sum(r["detected"] and r["latency"] <= 20.0 for r in drift)
    rate = wilson(hit, len(drift))
    ok = None if not drift else rate[0] >= 0.95
    results.append({"id": "AERIS-REQ-FDIR-003", "pass": ok,
                    "evidence": f"drift >= 0.5 m/s detected within 20 s in {hit}/{len(drift)} runs "
                                f"({rate[0]} , 95% CI {rate[1]}-{rate[2]}); target >= 0.95"})

    fa = summary["false_alarms"]
    per_hour = fa["per_hour"]
    ok = None if per_hour[0] is None else per_hour[0] < 0.1
    results.append({"id": "AERIS-REQ-FDIR-004", "pass": ok,
                    "evidence": f"{fa['count']} false alarms in {fa['clean_flight_hours']} fault-free flight hours "
                                f"= {per_hour[0]}/h (95% CI {per_hour[1]}-{per_hour[2]}); target < 0.1/h. "
                                f"Note: proving < 0.1/h with confidence needs > 30 clean hours."})

    t = summary["timing"]
    frac = t["deadline_misses"] / t["aeris_steps"] if t["aeris_steps"] else 1.0
    results.append({"id": "AERIS-REQ-SYS-001", "pass": frac < 0.001,
                    "evidence": f"{t['deadline_misses']} deadline misses in {t['aeris_steps']} steps "
                                f"(worst p99 {t['worst_p99_ms']} ms, worst {t['worst_max_ms']} ms; budget 20 ms)"})
    return results
