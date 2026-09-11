import itertools
import unittest

from aeris.core import recovery
from aeris.core.config import AerisConfig
from aeris.core.monitor import AerisCore
from aeris.core.types import COMPONENTS, DEGRADED, FAILED, NOMINAL, SUSPECT, UNKNOWN, SensorFrame
from aeris.trace import verifies

ALL_CAPS = sorted(set().union(*recovery.NEEDS.values()))


class TestActionSelection(unittest.TestCase):
    @verifies("AERIS-REQ-REC-002")
    def test_exhaustive_capability_combinations(self):
        """Every subset of capabilities x every minimum action x termination on/off."""
        checked = 0
        for r in range(len(ALL_CAPS) + 1):
            for caps in itertools.combinations(ALL_CAPS, r):
                caps = set(caps)
                for minimum in recovery.ACTIONS:
                    for term in (False, True):
                        a = recovery.select_action(caps, minimum, term)
                        feasible = recovery.NEEDS[a] <= caps
                        # The only allowed exception: nothing is feasible and termination is
                        # disabled, so the last resort is DESCEND.
                        if not feasible:
                            self.assertEqual(a, "DESCEND")
                            self.assertFalse(term)
                            self.assertNotIn("ATTITUDE", caps)
                        if minimum == "TERMINATE" and not term:
                            # Termination demanded but disabled (no parachute): the most
                            # severe action left is DESCEND.
                            self.assertEqual(a, "DESCEND")
                        else:
                            self.assertGreaterEqual(recovery.ACTIONS.index(a), recovery.ACTIONS.index(minimum))
                        if a == "TERMINATE":
                            self.assertTrue(term)
                        checked += 1
        self.assertEqual(checked, 2 ** len(ALL_CAPS) * len(recovery.ACTIONS) * 2)

    @verifies("AERIS-REQ-REC-002")
    def test_capabilities_follow_health_exhaustively(self):
        states = [NOMINAL, SUSPECT, DEGRADED, FAILED, UNKNOWN]
        for combo in itertools.product(states, repeat=len(COMPONENTS)):
            health = dict(zip(COMPONENTS, combo))
            for vision in (True, False):
                caps = recovery.capabilities(health, vision, True, True, thrust_margin_ok=False)
                nav = health["gps"] == NOMINAL or (vision and health["vision"] == NOMINAL)
                self.assertEqual("HORIZONTAL_NAV" in caps, nav)
                self.assertEqual("ATTITUDE" in caps, health["imu"] != FAILED)
                self.assertEqual("THRUST_MARGIN" in caps, health["motors"] == NOMINAL)

    def test_gps_lost_without_vision_cannot_return(self):
        health = {c: NOMINAL for c in COMPONENTS}
        health["gps"] = FAILED
        caps = recovery.capabilities(health, has_vision=False, energy_home_ok=True, energy_mission_ok=True)
        self.assertEqual(recovery.select_action(caps, "CONTINUE_DEGRADED"), "LAND")


class TestEnergyCheck(unittest.TestCase):
    def _core_with(self, consumed_wh):
        core = AerisCore(AerisConfig())
        core.batt_twin.consumed_wh = consumed_wh
        return core

    @verifies("AERIS-REQ-REC-003")
    def test_return_needs_energy_above_reserve(self):
        far = SensorFrame(t=0.0, est_pos=(100.0, 100.0, 30.0), battery=(15.0, 12.0), remaining_wps=())
        ok_core = self._core_with(consumed_wh=10.0)       # 75 % left
        _, home, _, home_ok, _ = ok_core.energy_status(far)
        self.assertTrue(home_ok)
        low_core = self._core_with(consumed_wh=32.0)      # 20 % left, reserve is 15 %
        usable, home, _, home_ok, _ = low_core.energy_status(far)
        self.assertLess(usable, home)
        self.assertFalse(home_ok)

    @verifies("AERIS-REQ-REC-003")
    def test_return_needs_voltage_headroom(self):
        core = self._core_with(consumed_wh=18.0)
        core.batt_twin.r_est = 0.4                       # badly damaged pack sags under load
        f = SensorFrame(t=0.0, est_pos=(100.0, 100.0, 30.0), battery=(15.0, 12.0), remaining_wps=())
        usable, home, _, home_ok, _ = core.energy_status(f)
        self.assertGreater(usable, home)                  # energy alone would allow it...
        self.assertFalse(home_ok)                         # ...but the voltage would collapse


if __name__ == "__main__":
    unittest.main()
