# ADR 0002: The autopilot stays in charge; AERIS supervises (simplex pattern)

Status: accepted, 11 September 2026

## Context

Autopilots such as PX4 already detect some faults and run their own failsafes
(position loss, low battery, geofence). If AERIS and the autopilot both react to the
same fault, the result depends on who acts first, and the measurements mean nothing.

## Decision

- The autopilot keeps final authority and all of its failsafes.
- AERIS acts only through the autopilot's API: change mode, exclude a sensor,
  set an accelerometer bias correction, limit speed, reset the position estimate.
  It never writes motor commands.
- When AERIS and a failsafe disagree, the more severe action wins. AERIS cannot
  downgrade a failsafe.
- AERIS may defer exactly one non-essential failsafe (low-battery return) while it is
  alive, because it runs its own energy check. Each deferral is logged.
- If AERIS stops sending heartbeats for 1 s, the autopilot carries on alone
  (requirement AERIS-REQ-SYS-002, tested by killing AERIS mid-flight).

Every scenario is flown three ways: A (autopilot only), B (AERIS watching, no
commands) and C (AERIS active). A against C is the headline comparison; B gives clean
detection statistics because AERIS can't influence the flight.

## Consequences

This mirrors how PX4's ROS 2 interface library works (external modes that PX4 can
override), so the design carries over to the real stack.
