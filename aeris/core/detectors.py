"""Small, testable fault detectors. Each one answers "does this look wrong?" for one signal.

- TimeoutTest: messages stopped arriving
- StuckTest:   the same value repeats exactly (real sensors always have some noise)
- Cusum:       a small but persistent shift, which a fixed threshold only catches late
- Threshold:   a value beyond a limit

Each detector returns an Evidence record, so every decision can be explained later.
"""
from .types import Evidence


class TimeoutTest:
    def __init__(self, test_id, timeout):
        self.test_id, self.timeout = test_id, timeout
        self.last = None

    def update(self, t, got_message):
        if got_message:
            self.last = t
        age = 0.0 if self.last is None else t - self.last
        return Evidence(self.test_id, age, self.timeout, self.last is not None and age > self.timeout)


class StuckTest:
    def __init__(self, test_id, repeats):
        self.test_id, self.repeats = test_id, repeats
        self.prev, self.count = None, 0

    def update(self, value):
        if value is not None:
            self.count = self.count + 1 if value == self.prev else 0
            self.prev = value
        return Evidence(self.test_id, self.count, self.repeats, self.count >= self.repeats)


class Cusum:
    """One-sided CUSUM: s = max(0, s + x - k). Alarm when s > h.

    k is the allowance (roughly half the shift you want to catch) and h sets how much
    accumulated evidence is needed. Bigger h = fewer false alarms, slower detection.
    """

    def __init__(self, test_id, k, h):
        self.test_id, self.k, self.h = test_id, k, h
        self.s = 0.0

    def update(self, x):
        if x is not None:
            self.s = max(0.0, self.s + x - self.k)
        return self.evidence()

    def evidence(self):
        return Evidence(self.test_id, self.s, self.h, self.s > self.h)

    def reset(self):
        self.s = 0.0


class Threshold:
    def __init__(self, test_id, limit):
        self.test_id, self.limit = test_id, limit
        self.value = 0.0

    def update(self, value):
        if value is not None:
            self.value = value
        return Evidence(self.test_id, self.value, self.limit, self.value > self.limit)


class Ewma:
    """Exponentially weighted moving average: a simple low-pass filter."""

    def __init__(self, tau, value=None):
        self.tau, self.value = tau, value

    def update(self, x, dt):
        if self.value is None:
            self.value = x
        else:
            a = min(dt / self.tau, 1.0)
            self.value += a * (x - self.value)
        return self.value
