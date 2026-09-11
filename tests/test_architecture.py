"""Architecture guards: AERIS must never see the answer key."""
import ast
import dataclasses
import inspect
import unittest
from pathlib import Path

from aeris.core import monitor
from aeris.core.types import SensorFrame
from aeris.trace import verifies

CORE = Path(__file__).resolve().parents[1] / "aeris" / "core"
FORBIDDEN = ("sim", "flight", "oracle", "faults", "campaign", "autopilot", "evidence")


class TestCoreIsolation(unittest.TestCase):
    @verifies("AERIS-REQ-ARCH-001")
    def test_core_imports_nothing_it_should_not_see(self):
        for path in CORE.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [("." * node.level) + (node.module or "")]
                for n in names:
                    parts = n.replace(".", " ").split()
                    self.assertFalse(any(p in FORBIDDEN for p in parts),
                                     f"{path.name} imports {n!r}; the AERIS core must stay blind to the simulator")

    @verifies("AERIS-REQ-ARCH-001")
    def test_sensor_frame_has_no_truth_fields(self):
        fields = {f.name for f in dataclasses.fields(SensorFrame)}
        for banned in ("truth", "fault", "true_pos", "injected"):
            self.assertFalse(any(banned in f for f in fields), f"SensorFrame field looks like ground truth: {fields}")

    def test_step_takes_only_a_frame(self):
        params = list(inspect.signature(monitor.AerisCore.step).parameters)
        self.assertEqual(params, ["self", "f"])


if __name__ == "__main__":
    unittest.main()
