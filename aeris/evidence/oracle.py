"""Scoring oracle: compares what AERIS did with what was really injected.

This is the only place (besides the recorder) that reads ground truth.
"""
DETECTION_WINDOW = 60.0   # s after injection within which a detection counts


def score(result):
    truth = result["truth"]
    events = result["aeris_events"]
    o = result["outcome"]
    flight_time = o["flight_time"]
    fault = truth[0] if truth else None
    start = fault["start"] if fault else None
    clean_until = start if fault else flight_time

    suspects = [e for e in events if e["kind"] == "health" and "NOMINAL -> SUSPECT" in e["text"]]
    diagnoses = [e for e in events if e["kind"] == "diagnosis"]
    false_alarms = [e for e in suspects if e["t"] < clean_until]

    rec = {
        "fault_type": fault["type"] if fault else "none",
        "component": fault["component"] if fault else None,
        "expected": fault["expected_diagnosis"] if fault else None,
        "start": start,
        "false_alarms": len(false_alarms),
        "clean_hours": min(clean_until, flight_time) / 3600.0,
        "detected": False, "latency": None, "diagnosis": None, "confidence": None,
        "isolation_correct": False, "diagnoses_made": 0, "diagnoses_correct": 0,
        "recovery_action": None,
    }
    if fault is None:
        rec["diagnoses_made"] = len(diagnoses)
        return rec

    comp = fault["component"]
    window = [e for e in suspects + diagnoses
              if e["component"] == comp and start <= e["t"] <= start + DETECTION_WINDOW]
    if window:
        first = min(e["t"] for e in window)
        rec["detected"] = True
        rec["latency"] = round(first - start, 3)
    after = [d for d in diagnoses if d["t"] >= start]
    rec["diagnoses_made"] = len(after)
    rec["diagnoses_correct"] = sum(d["data"]["fault_id"] == fault["expected_diagnosis"] for d in after)
    mine = [d for d in after if d["component"] == comp and d["t"] <= start + DETECTION_WINDOW]
    if mine:
        d = mine[0]["data"]
        rec["diagnosis"] = d["fault_id"]
        rec["confidence"] = d["confidence"]
        rec["isolation_correct"] = d["fault_id"] == fault["expected_diagnosis"]
    actions = [e for e in events if e["kind"] == "action" and e["component"] == "system" and e["t"] >= start]
    if actions:
        rec["recovery_action"] = actions[0]["text"].replace("recovery ", "")
    return rec
