"""End-to-end scenario tests: real closed-loop flights through the simulator."""
import unittest

from aeris.core.monitor import AerisCore
from aeris.flight import run_flight
from aeris.trace import verifies

from .helpers import events, fly, scenario


class TestNominal(unittest.TestCase):
    @verifies("AERIS-REQ-FDIR-004")
    def test_quiet_and_successful_without_faults(self):
        for seed in (7, 11, 23):
            r = fly(scenario(seed=seed), "B")
            self.assertTrue(r["outcome"]["mission_success"], f"seed {seed}")
            self.assertEqual(events(r, text="NOMINAL -> SUSPECT"), [], f"false alarm with seed {seed}")

    def test_baseline_flies_the_mission(self):
        self.assertTrue(fly(scenario(), "A")["outcome"]["mission_success"])


class TestGps(unittest.TestCase):
    @verifies("AERIS-REQ-FDIR-001")
    def test_gps_loss_declared_within_half_a_second(self):
        r = fly(scenario("gps_off", start=40.0), "B")
        first = events(r, kind="health", component="gps", text="NOMINAL -> SUSPECT")[0]
        self.assertLessEqual(first["t"] - 40.0, 0.5)
        self.assertIn("GPS_LOSS", [e["data"]["fault_id"] for e in events(r, kind="diagnosis")])

    @verifies("AERIS-REQ-REC-001")
    def test_drift_is_isolated_and_recovery_requested_within_1s(self):
        r = fly(scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90}), "C")
        diag = events(r, kind="diagnosis", component="gps")[0]
        self.assertEqual(diag["data"]["fault_id"], "GPS_DRIFT")
        cmds = [c for c in r["aeris_commands"] if c["t"] >= diag["t"]]
        exclude = next(c for c in cmds if c["kind"] == "exclude_sensor")
        mode = next(c for c in cmds if c["kind"] == "set_mode")
        self.assertEqual(exclude["value"], "gps")
        self.assertLessEqual(mode["t"] - diag["t"], 1.0)
        self.assertTrue(mode["accepted"])

    def test_flagship_result_holds(self):
        """The headline: the baseline is dragged off course by the drift, AERIS is not."""
        sc = scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90})
        a, c = fly(sc, "A")["outcome"], fly(sc, "C")["outcome"]
        self.assertFalse(a["mission_success"])
        self.assertGreater(a["landing_distance_from_home"], 15.0)
        self.assertTrue(c["mission_success"])


class TestOtherFaults(unittest.TestCase):
    def test_each_fault_gets_the_right_diagnosis(self):
        cases = {
            "gps_stuck": ({}, "GPS_FROZEN"), "baro_stuck": ({}, "BARO_FROZEN"),
            "mag_offset": ({"offset_deg": 40}, "MAG_FAULT"), "imu_bias": ({"bx": 0.6, "by": 0.0}, "IMU_BIAS"),
            "motor_degradation": ({"motor": 1, "efficiency": 0.62}, "MOTOR_DEGRADED"),
            "battery_fault": ({"charge_loss": 0.6, "resistance_mult": 1.5}, "BATTERY_DEGRADED"),
        }
        for ftype, (params, expected) in cases.items():
            with self.subTest(fault=ftype):
                r = fly(scenario(ftype, params), "B")
                got = [e["data"]["fault_id"] for e in events(r, kind="diagnosis")]
                self.assertEqual(got[:1], [expected])

    def test_weak_motor_continues_severe_motor_returns(self):
        weak = fly(scenario("motor_degradation", {"motor": 1, "efficiency": 0.8}), "C")
        severe = fly(scenario("motor_degradation", {"motor": 1, "efficiency": 0.62}), "C")
        self.assertEqual(events(weak, text="recovery")[0]["text"], "recovery CONTINUE_DEGRADED")
        self.assertEqual(events(severe, text="recovery")[0]["text"], "recovery RETURN")


class TestSystem(unittest.TestCase):
    @verifies("AERIS-REQ-SYS-002")
    def test_autopilot_carries_on_when_aeris_dies(self):
        sc = scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90}, start=60.0)
        r = run_flight(sc, "C", kill_aeris_at=50.0)
        texts = [e["text"] for e in r["autopilot_events"]]
        self.assertTrue(any("heartbeat lost" in t for t in texts))
        self.assertTrue(all(c["t"] < 50.0 for c in r["aeris_commands"]))
        self.assertTrue(r["outcome"]["landed"])
        self.assertFalse(r["outcome"]["crashed"])

    @verifies("AERIS-REQ-SYS-001")
    def test_step_time_within_budget(self):
        t = fly(scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90}), "C")["timing"]
        self.assertGreater(t["aeris_steps"], 5000)
        self.assertLess(t["deadline_misses"] / t["aeris_steps"], 0.001)
        self.assertLess(t["p99_ms"], 20.0)


class TestEvidence(unittest.TestCase):
    @verifies("AERIS-REQ-LOG-001")
    def test_every_decision_is_explained(self):
        r = fly(scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90}), "C")
        diags = events(r, kind="diagnosis")
        self.assertTrue(diags)
        for d in diags:
            self.assertTrue(d["data"]["evidence"], "a diagnosis without evidence")
            self.assertTrue(any(e["tripped"] for e in d["data"]["evidence"]))
        recov = events(r, kind="action", component="system")
        self.assertTrue(recov and all("why" in e["data"] for e in recov))
        self.assertTrue(events(r, kind="health", text="SUSPECT"))

    @verifies("AERIS-REQ-LOG-002")
    def test_manifest_regenerates_the_run_exactly(self):
        r1 = fly(scenario("imu_bias", {"bx": 0.6, "by": 0.0}), "C")
        m = r1["manifest"]
        for key in ("code_version", "aeris_config_hash", "seed", "scenario", "config_arm"):
            self.assertIn(key, m)
        r2 = run_flight(m["scenario"], m["config_arm"])
        self.assertEqual(r1["outcome"], r2["outcome"])
        self.assertEqual(r1["aeris_events"], r2["aeris_events"])


class TestReplay(unittest.TestCase):
    def test_tier0_replay_reproduces_aeris_decisions(self):
        """Feed recorded sensor frames into a fresh AERIS core: same events, bit for bit."""
        r = run_flight(scenario("gps_drift", {"rate_mps": 0.4, "direction_deg": 90}), "B", record_frames=True)
        core = AerisCore()
        for frame in r["frames"]:
            core.step(frame)
        self.assertEqual([e.to_dict() for e in core.events], r["aeris_events"])


if __name__ == "__main__":
    unittest.main()
