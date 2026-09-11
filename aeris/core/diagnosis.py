"""Diagnosis with a fault signature matrix.

Each known fault has a signature: the tests it must trip ("requires"), tests it must
NOT trip ("excludes"), and optional supporting tests. The observed pattern of
tripped tests is matched against every signature.

Example: an IMU accelerometer bias makes the IMU disagree with the external velocity
(imu.accel_residual) but leaves GPS and vision agreeing with each other. A GPS drift
does the opposite. That difference is how AERIS tells them apart.
"""
from .types import DEGRADED, FAILED, Diagnosis

SIGNATURES = {
    "GPS_LOSS": {"component": "gps", "requires": ["gps.timeout"], "severity": FAILED},
    "GPS_FROZEN": {"component": "gps", "requires": ["gps.stuck"], "severity": FAILED},
    "GPS_DRIFT": {"component": "gps", "requires": ["gps.vel_consistency", "gps.pos_residual"],
                  "excludes": ["imu.accel_residual"], "supports": ["gps.innovation"], "severity": FAILED},
    "BARO_FROZEN": {"component": "baro", "requires": ["baro.stuck"], "severity": FAILED},
    "BARO_LOSS": {"component": "baro", "requires": ["baro.timeout"], "severity": FAILED},
    "MAG_FAULT": {"component": "mag", "requires": ["mag.heading_residual"], "severity": FAILED},
    "MAG_LOSS": {"component": "mag", "requires": ["mag.timeout"], "severity": FAILED},
    "IMU_BIAS": {"component": "imu", "requires": ["imu.accel_residual"],
                 "excludes": ["gps.vel_consistency"], "supports": ["twin.accel_residual"], "severity": DEGRADED},
    "MOTOR_DEGRADED": {"component": "motors", "requires": ["motor.imbalance"],
                       "excludes": ["imu.accel_residual"], "supports": ["twin.accel_residual"],
                       "severity": DEGRADED},
    "BATTERY_DEGRADED": {"component": "battery", "requires": ["battery.voltage_residual"], "severity": DEGRADED},
    "VISION_LOSS": {"component": "vision", "requires": ["vision.timeout"], "severity": FAILED},
}


def match(component, tripped, evidence, t):
    """Return the best full-signature Diagnosis for this component, or None.

    tripped:  set of test ids tripped right now (across all components)
    evidence: dict test_id -> Evidence, used to build the explanation
    """
    best = None
    for fault_id, sig in SIGNATURES.items():
        if sig["component"] != component:
            continue
        req = sig["requires"]
        if not all(r in tripped for r in req):
            continue
        if any(x in tripped for x in sig.get("excludes", [])):
            continue
        support = [s for s in sig.get("supports", []) if s in tripped]
        confidence = min(1.0, 0.8 + 0.1 * (len(req) - 1) + 0.1 * len(support))
        used = req + sig.get("excludes", []) + sig.get("supports", [])
        ev = [evidence[u] for u in used if u in evidence]
        cand = Diagnosis(t, fault_id, component, sig["severity"], round(confidence, 2), ev)
        if best is None or len(req) > len(SIGNATURES[best.fault_id]["requires"]):
            best = cand
    return best


def unknown(component, tripped, evidence, t):
    ev = [e for k, e in evidence.items() if k in tripped]
    return Diagnosis(t, "UNKNOWN", component, DEGRADED, 0.3, ev)
