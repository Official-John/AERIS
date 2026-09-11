import unittest

import numpy as np

from aeris.core.detectors import Cusum, StuckTest, Threshold, TimeoutTest
from aeris.trace import verifies


class TestTimeout(unittest.TestCase):
    @verifies("AERIS-REQ-FDIR-001")
    def test_trips_only_after_timeout(self):
        t = TimeoutTest("gps.timeout", 0.3)
        self.assertFalse(t.update(0.0, False).tripped, "no data yet must not count as stale")
        t.update(1.0, True)
        self.assertFalse(t.update(1.25, False).tripped)
        self.assertTrue(t.update(1.35, False).tripped)
        self.assertFalse(t.update(1.40, True).tripped, "a new message clears it")


class TestStuck(unittest.TestCase):
    def test_identical_values_trip(self):
        s = StuckTest("x.stuck", 5)
        for _ in range(5):
            ev = s.update((1.0, 2.0, 3.0))
        self.assertFalse(ev.tripped)          # first sample + 4 repeats
        self.assertTrue(s.update((1.0, 2.0, 3.0)).tripped)

    def test_noisy_values_never_trip(self):
        s = StuckTest("x.stuck", 5)
        rng = np.random.default_rng(1)
        self.assertFalse(any(s.update(float(v)).tripped for v in rng.normal(0, 0.1, 5000)))


class TestCusum(unittest.TestCase):
    def test_quiet_on_noise_below_allowance(self):
        c = Cusum("c", k=0.3, h=3.0)
        rng = np.random.default_rng(2)
        trips = sum(c.update(abs(v)).tripped for v in rng.normal(0, 0.1, 20000))
        self.assertEqual(trips, 0)

    def test_detects_persistent_shift(self):
        c = Cusum("c", k=0.3, h=3.0)
        n = next(i for i in range(1000) if c.update(0.5).tripped)
        # accumulates 0.2 per sample, so it passes 3.0 after about 15 samples
        # (floating point decides whether it is the 15th or the 16th)
        self.assertIn(n, (14, 15))


class TestThreshold(unittest.TestCase):
    def test_holds_last_value(self):
        th = Threshold("t", 1.0)
        self.assertTrue(th.update(2.0).tripped)
        self.assertTrue(th.update(None).tripped)
        self.assertFalse(th.update(0.5).tripped)


if __name__ == "__main__":
    unittest.main()
