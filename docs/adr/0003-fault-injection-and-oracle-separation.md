# ADR 0003: Inject faults upstream of everything; keep ground truth away from AERIS

Status: accepted, 11 September 2026

## Context

If faults were applied only to the data AERIS reads, the aircraft would fly
normally while AERIS "detected" faults that affected nothing. And if AERIS could see
what was injected, even by accident, every score would be perfect and worthless.

## Decision

- `aeris/sim/faults.py` corrupts raw sensor messages (or changes the airframe:
  motor efficiency, battery charge and resistance) *before* the autopilot or AERIS
  sees them. Both read the same corrupted data, as on a real aircraft.
- The injector's ground truth goes only to the recorder and the scoring oracle
  (`aeris/evidence/oracle.py`).
- `tests/test_architecture.py` parses every file in `aeris/core` and fails if one
  imports the simulator, the injector, the oracle or the campaign code. It also
  checks that `SensorFrame` has no field that looks like ground truth.

## Consequences

The detection numbers in the reports are earned. Adding a fault type means adding
it to `FAULT_TYPES` and `FaultInjector`, never to AERIS.
