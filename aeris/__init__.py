"""AERIS: Autonomous aircraft health monitoring, fault diagnosis and recovery.

Packages:
  aeris.core       AERIS itself (knows nothing about the simulator)
  aeris.autopilot  a small PX4-like autopilot used as the baseline
  aeris.sim        the simulated aircraft, sensors, wind and fault injection
  aeris.adapters   glue between AERIS and an autopilot
  aeris.evidence   recording, scoring, metrics and reports
  aeris.campaign   scenario generation and batch runs
"""
__version__ = "0.1.0"
