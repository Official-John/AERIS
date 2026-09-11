"""Battery model for the simulated aircraft.

A 4-cell lithium-polymer pack described by three things:
- remaining energy (Wh), the real "fuel gauge"
- open-circuit voltage (OCV), which depends on state of charge
- internal resistance, which makes the voltage sag when current flows

The aircraft only ever sees terminal voltage and current, like a real power module.
"""
import math

import numpy as np

# Open-circuit voltage of one LiPo cell against state of charge (0..1).
OCV_SOC = np.array([0.00, 0.05, 0.10, 0.20, 0.40, 0.60, 0.80, 1.00])
OCV_CELL = np.array([3.00, 3.45, 3.60, 3.70, 3.78, 3.87, 4.00, 4.20])


def ocv_per_cell(soc):
    return float(np.interp(soc, OCV_SOC, OCV_CELL))


def soc_from_ocv_per_cell(v_cell):
    return float(np.interp(v_cell, OCV_CELL, OCV_SOC))


class Battery:
    def __init__(self, cells=4, capacity_wh=40.0, resistance_ohm=0.06):
        self.cells = cells
        self.capacity_wh = capacity_wh
        self.energy_wh = capacity_wh
        self.resistance = resistance_ohm
        self.voltage = cells * ocv_per_cell(1.0)
        self.current = 0.0
        self.depleted = False

    @property
    def soc(self):
        """True state of charge relative to the nominal capacity."""
        return max(0.0, self.energy_wh / self.capacity_wh)

    def draw(self, power_w, dt):
        """Deliver power_w for dt seconds. Returns the power actually delivered."""
        if self.depleted:
            self.voltage, self.current = 0.0, 0.0
            return 0.0
        v_oc = self.cells * ocv_per_cell(self.soc)
        # Solve P = (V_oc - I R) I for the current I.
        disc = v_oc * v_oc - 4.0 * self.resistance * power_w
        if disc < 0.0:
            # The pack can't deliver this much power: deliver the maximum it can.
            current = v_oc / (2.0 * self.resistance)
        else:
            current = (v_oc - math.sqrt(disc)) / (2.0 * self.resistance)
        self.current = current
        self.voltage = v_oc - current * self.resistance
        self.energy_wh -= v_oc * current * dt / 3600.0
        if self.energy_wh <= 0.0 or self.voltage < self.cells * 2.8:
            self.energy_wh = max(self.energy_wh, 0.0)
            self.depleted = True
        return self.voltage * current
