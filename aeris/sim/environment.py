"""Wind: a steady mean plus random gusts (an Ornstein-Uhlenbeck process)."""
import math

import numpy as np


class Wind:
    def __init__(self, rng, mean_mps=0.0, direction_deg=0.0, gust_sigma=0.8, gust_tau=5.0):
        d = math.radians(direction_deg)
        # direction_deg is where the wind blows *towards*, measured like yaw.
        self.mean = np.array([mean_mps * math.cos(d), mean_mps * math.sin(d), 0.0])
        self.gust = np.zeros(3)
        self.sigma = gust_sigma
        self.tau = gust_tau
        self.rng = rng

    def step(self, dt):
        k = math.sqrt(2.0 * dt / self.tau) * self.sigma
        self.gust += -self.gust * dt / self.tau + k * self.rng.normal(0.0, 1.0, 3) * np.array([1.0, 1.0, 0.3])
        return self.mean + self.gust
