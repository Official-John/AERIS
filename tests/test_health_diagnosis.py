import unittest

from aeris.core import diagnosis
from aeris.core.health import ComponentHealth
from aeris.core.types import FAILED, NOMINAL, SUSPECT, UNKNOWN, Evidence
from aeris.trace import verifies


def ev(*tripped):
    return {t: Evidence(t, 1.0, 0.5, True) for t in tripped}


class TestHealthStateMachine(unittest.TestCase):
    def setUp(self):
        self.h = ComponentHealth("gps", confirm_m=8, confirm_n=10, clear_time=2.0)
        self.h.seen_data()

    def test_unknown_until_data(self):
        h = ComponentHealth("x", 8, 10, 2.0)
        self.assertEqual(h.state, UNKNOWN)
        h.seen_data()
        self.assertEqual(h.state, NOMINAL)

    def test_single_trip_is_only_suspect(self):
        self.assertEqual(self.h.evaluate(0.0, True, False), (SUSPECT, False))

    def test_residual_needs_m_of_n(self):
        confirmed = [self.h.evaluate(i * 0.1, True, False)[1] for i in range(8)]
        self.assertEqual(confirmed, [False] * 7 + [True])

    def test_immediate_tests_confirm_on_second_evaluation(self):
        self.assertFalse(self.h.evaluate(0.0, True, True)[1])
        self.assertTrue(self.h.evaluate(0.1, True, True)[1])

    def test_clears_after_clean_period(self):
        self.h.evaluate(0.0, True, False)
        self.assertEqual(self.h.evaluate(1.0, False, False)[0], SUSPECT)
        self.assertEqual(self.h.evaluate(2.1, False, False)[0], NOMINAL)

    def test_failed_latches(self):
        self.h.set(FAILED)
        self.assertEqual(self.h.evaluate(0.0, False, False), (FAILED, False))


class TestSignatures(unittest.TestCase):
    @verifies("AERIS-REQ-FDIR-002")
    def test_gps_drift_needs_two_residuals(self):
        one = ev("gps.vel_consistency")
        self.assertIsNone(diagnosis.match("gps", set(one), one, 0.0))
        both = ev("gps.vel_consistency", "gps.pos_residual")
        d = diagnosis.match("gps", set(both), both, 0.0)
        self.assertEqual(d.fault_id, "GPS_DRIFT")
        self.assertEqual(d.health, FAILED)

    @verifies("AERIS-REQ-FDIR-002")
    def test_timeout_alone_is_enough_for_gps_loss(self):
        e = ev("gps.timeout")
        self.assertEqual(diagnosis.match("gps", set(e), e, 0.0).fault_id, "GPS_LOSS")

    def test_imu_bias_and_gps_drift_are_told_apart(self):
        e = ev("imu.accel_residual")
        self.assertEqual(diagnosis.match("imu", set(e), e, 0.0).fault_id, "IMU_BIAS")
        e = ev("imu.accel_residual", "gps.vel_consistency")
        self.assertIsNone(diagnosis.match("imu", set(e), e, 0.0), "GPS/vision disagreement rules out IMU bias")
        e = ev("gps.vel_consistency", "gps.pos_residual", "imu.accel_residual")
        self.assertIsNone(diagnosis.match("gps", set(e), e, 0.0), "IMU disagreement rules out GPS drift")

    def test_motor_signature_excludes_imu(self):
        e = ev("motor.imbalance")
        self.assertEqual(diagnosis.match("motors", set(e), e, 0.0).fault_id, "MOTOR_DEGRADED")

    def test_diagnosis_carries_evidence(self):
        e = ev("gps.vel_consistency", "gps.pos_residual", "gps.innovation")
        d = diagnosis.match("gps", set(e), e, 0.0)
        self.assertEqual({x.test_id for x in d.evidence}, {"gps.vel_consistency", "gps.pos_residual", "gps.innovation"})
        self.assertEqual(d.confidence, 1.0)


if __name__ == "__main__":
    unittest.main()
