import unittest

from aeris.evidence.metrics import median_ci, poisson_rate, wilson
from aeris.evidence.oracle import score


class TestStatistics(unittest.TestCase):
    def test_wilson_known_value(self):
        p, lo, hi = wilson(19, 20)
        self.assertEqual(p, 0.95)
        self.assertAlmostEqual(lo, 0.7639, places=3)
        self.assertAlmostEqual(hi, 0.9911, places=3)

    def test_wilson_zero_successes(self):
        p, lo, hi = wilson(0, 10)
        self.assertEqual((p, lo), (0.0, 0.0))
        self.assertGreater(hi, 0.2)

    def test_poisson_zero_events_gives_upper_bound(self):
        rate, lo, hi = poisson_rate(0, 10.0)
        self.assertEqual((rate, lo), (0.0, 0.0))
        self.assertAlmostEqual(hi, 0.369, places=2)   # ~3.7 events / 10 h

    def test_median_ci_brackets_median(self):
        m, lo, hi = median_ci([1, 2, 3, 4, 5, 6, 7, 8, 9])
        self.assertEqual(m, 5.0)
        self.assertLessEqual(lo, m)
        self.assertGreaterEqual(hi, m)


class TestOracle(unittest.TestCase):
    def _result(self, events):
        return {"truth": [{"type": "gps_off", "component": "gps", "expected_diagnosis": "GPS_LOSS",
                           "start": 40.0, "duration": None, "params": {}}],
                "aeris_events": events, "outcome": {"flight_time": 120.0}}

    def test_detection_latency_and_isolation(self):
        r = self._result([
            {"t": 20.0, "kind": "health", "component": "baro", "text": "baro: NOMINAL -> SUSPECT (x)", "data": {}},
            {"t": 40.4, "kind": "health", "component": "gps", "text": "gps: NOMINAL -> SUSPECT (gps.timeout)", "data": {}},
            {"t": 40.5, "kind": "diagnosis", "component": "gps", "text": "diagnosis GPS_LOSS",
             "data": {"fault_id": "GPS_LOSS", "confidence": 0.8}},
        ])
        s = score(r)
        self.assertTrue(s["detected"])
        self.assertAlmostEqual(s["latency"], 0.4)
        self.assertTrue(s["isolation_correct"])
        self.assertEqual(s["false_alarms"], 1)          # the baro blip before the fault
        self.assertAlmostEqual(s["clean_hours"], 40.0 / 3600)

    def test_missed_fault(self):
        s = score(self._result([]))
        self.assertFalse(s["detected"])
        self.assertIsNone(s["latency"])
        self.assertFalse(s["isolation_correct"])


if __name__ == "__main__":
    unittest.main()
