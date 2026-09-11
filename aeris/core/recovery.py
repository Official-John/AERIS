"""Capability-aware recovery.

A response is only valid if the aircraft can still carry it out. Each action lists
the capabilities it needs; the health states say which capabilities are left; the
manager picks the least severe action whose needs are met and which is at least as
cautious as the fault demands.
"""
from .types import FAILED, NOMINAL

ACTIONS = ["CONTINUE_DEGRADED", "RETURN", "LAND", "DESCEND", "TERMINATE"]   # least -> most severe
NEEDS = {
    "CONTINUE_DEGRADED": {"HORIZONTAL_NAV", "HEIGHT", "HEADING", "ATTITUDE", "THRUST_MARGIN", "ENERGY_MISSION"},
    "RETURN": {"HORIZONTAL_NAV", "HEIGHT", "HEADING", "ATTITUDE", "ENERGY_HOME"},
    "LAND": {"HEIGHT", "ATTITUDE"},
    "DESCEND": {"ATTITUDE"},
    "TERMINATE": set(),
}
# The least severe action each diagnosis allows.
MINIMUM_ACTION = {
    "GPS_LOSS": "CONTINUE_DEGRADED", "GPS_FROZEN": "CONTINUE_DEGRADED", "GPS_DRIFT": "CONTINUE_DEGRADED",
    "BARO_FROZEN": "CONTINUE_DEGRADED", "BARO_LOSS": "CONTINUE_DEGRADED",
    "IMU_BIAS": "CONTINUE_DEGRADED",
    "MAG_FAULT": "RETURN", "MAG_LOSS": "RETURN",       # gyro-only heading drifts; go home
    # For these two, the capabilities decide: continue only if the measured thrust
    # margin / predicted energy and voltage allow it.
    "MOTOR_DEGRADED": "CONTINUE_DEGRADED", "BATTERY_DEGRADED": "CONTINUE_DEGRADED",
    "VISION_LOSS": "CONTINUE_DEGRADED",
    "UNKNOWN": "LAND",
}


def capabilities(health, has_vision, energy_home_ok, energy_mission_ok, thrust_margin_ok=True):
    gps_ok = health["gps"] == NOMINAL
    vision_ok = has_vision and health["vision"] == NOMINAL
    caps = set()
    if gps_ok or vision_ok:
        caps.add("HORIZONTAL_NAV")
    if health["baro"] == NOMINAL or gps_ok:
        caps.add("HEIGHT")
    if health["mag"] == NOMINAL or health["mag"] == FAILED:
        caps.add("HEADING")    # a failed magnetometer is excluded; the gyro carries heading short-term
    if health["imu"] != FAILED:
        caps.add("ATTITUDE")
    if health["motors"] == NOMINAL or thrust_margin_ok:
        caps.add("THRUST_MARGIN")
    if energy_home_ok:
        caps.add("ENERGY_HOME")
    if energy_mission_ok:
        caps.add("ENERGY_MISSION")
    return caps


def select_action(caps, minimum, allow_termination=False):
    """Least severe action at or above `minimum` whose needs are all available.

    Last resort: if nothing qualifies (or TERMINATE is demanded while termination is
    disabled), DESCEND, which only needs attitude control.
    """
    start = ACTIONS.index(minimum)
    for action in ACTIONS[start:]:
        if action == "TERMINATE" and not allow_termination:
            continue
        if NEEDS[action] <= caps:
            return action
    return "DESCEND"
