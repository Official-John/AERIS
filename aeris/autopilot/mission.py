"""The reference mission: take off, fly a six-waypoint survey at 30 m, return, land."""
from dataclasses import dataclass, field

HOME = (0.0, 0.0)
CRUISE_ALT = 30.0
ACCEPT_RADIUS = 2.0   # m, a waypoint counts as reached inside this radius
GEOFENCE_RADIUS = 150.0
GEOFENCE_ALT = 60.0


@dataclass
class Mission:
    waypoints: list = field(default_factory=lambda: [
        (0.0, 40.0), (60.0, 40.0), (60.0, 80.0), (0.0, 80.0), (0.0, 120.0), (60.0, 120.0)])
    altitude: float = CRUISE_ALT
    cruise_speed: float = 6.0

    def planned_path(self):
        """Home -> waypoints -> home, for plotting and cross-track error."""
        return [HOME] + list(self.waypoints) + [HOME]
