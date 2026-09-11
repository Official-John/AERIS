"""Health state machine for one component (GPS, barometer, IMU, ...).

    NOMINAL --any test trips--> SUSPECT --confirmed--> DEGRADED or FAILED (latched)
       ^                            |
       +-------clean for clear_time-+

Confirmation needs persistence: M of the last N evaluations must have a tripped
test, so one noisy sample can't trigger a recovery. "Immediate" tests (timeout,
stuck) confirm after two consecutive evaluations, because they already contain
their own persistence.

UNKNOWN means "no data yet" (or the sensor isn't fitted).

In this MVP, DEGRADED and FAILED latch for the rest of the flight. A later version
can let DEGRADED recover after a long clean period (see docs/ARCHITECTURE.md).
"""
from collections import deque

from .types import DEGRADED, FAILED, NOMINAL, SUSPECT, UNKNOWN


class ComponentHealth:
    def __init__(self, name, confirm_m, confirm_n, clear_time):
        self.name = name
        self.state = UNKNOWN
        self.m, self.clear_time = confirm_m, clear_time
        self.window = deque(maxlen=confirm_n)
        self.immediate_streak = 0
        self.last_trip = None
        self.suspect_since = None

    def seen_data(self):
        if self.state == UNKNOWN:
            self.state = NOMINAL
            return True
        return False

    def evaluate(self, t, tripped, immediate):
        """Feed one evaluation. Returns (new_state, confirmed_now).

        confirmed_now=True means the persistence rule is satisfied and the caller
        (the monitor) must now decide DEGRADED or FAILED via diagnosis.
        """
        if self.state in (UNKNOWN, DEGRADED, FAILED):
            return self.state, False
        self.window.append(bool(tripped))
        self.immediate_streak = self.immediate_streak + 1 if immediate else 0
        if tripped:
            self.last_trip = t
        if self.state == NOMINAL and tripped:
            self.state, self.suspect_since = SUSPECT, t
            return self.state, False
        if self.state == SUSPECT:
            if self.immediate_streak >= 2 or sum(self.window) >= self.m:
                return self.state, True
            if self.last_trip is not None and t - self.last_trip >= self.clear_time:
                self.state, self.suspect_since = NOMINAL, None
                self.window.clear()
        return self.state, False

    def set(self, state):
        self.state = state
