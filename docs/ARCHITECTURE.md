# How AERIS is built

This page explains what each part of the code does and how data moves through it.
Read it with `docs/design/AERIS_architecture.png` open beside it.

## The four layers

| Layer | Folder | Plays the part of | Knows the truth? |
|---|---|---|---|
| Simulation | `aeris/sim/` | the real aircraft, its sensors, the wind, and the fault injector | yes |
| Autopilot | `aeris/autopilot/` | PX4 (a simplified stand-in) | no, only sensors |
| AERIS | `aeris/core/` | the health monitor on a companion computer | no, only sensors and autopilot telemetry |
| Evidence | `aeris/evidence/`, `aeris/campaign/` | flight recorder, scoring, reports, batch runs | yes (the oracle only) |

`aeris/adapters/standin.py` is the only file that talks to both AERIS and the
autopilot. `aeris/flight.py` runs one closed-loop flight.

## One tick of a flight (50 times a second)

1. The wind changes a little (`sim/environment.py`).
2. Faults that act on the airframe are applied: a weak motor, a damaged battery (`sim/faults.py`).
3. Sensors produce noisy messages from the true state (`sim/sensors.py`): IMU at 50 Hz;
   GPS, vision odometry, barometer, magnetometer and battery at 10 Hz.
4. Sensor faults corrupt those messages (stop them, freeze them, bias them).
5. The autopilot fuses the messages into a state estimate, follows the mission, runs
   its failsafes and outputs a thrust command (`autopilot/`).
6. AERIS reads the same messages plus the autopilot's telemetry and may send commands
   back (configuration C only).
7. The airframe moves (`sim/vehicle.py`), and the recorder logs a sample every 0.2 s.

## Inside AERIS (`aeris/core/`)

```
SensorFrame ──► detectors ──► health state machines ──► signature matrix ──► isolate ──► recovery
                    ▲                                                                       │
     independent estimator + digital twin                                         Commands to autopilot
```

| File | Job |
|---|---|
| `types.py` | The data that crosses the boundary: `SensorFrame`, `Evidence`, `Diagnosis`, `Command`, `Event` |
| `config.py` | Every threshold, in one place, with a hash stored in each run's manifest |
| `detectors.py` | Timeout, stuck-value, CUSUM (slow drifts) and threshold tests |
| `independent.py` | Position from vision odometry and heading from the gyro, so GPS and magnetometer faults can be checked against something that didn't use them |
| `twin.py` | The digital twin: predicted acceleration, a battery model that learns internal resistance in flight, and the energy-to-home what-if |
| `health.py` | NOMINAL → SUSPECT → DEGRADED / FAILED, with M-of-N confirmation |
| `diagnosis.py` | The fault signature matrix: which tests each fault must trip, and which it must not |
| `recovery.py` | Capability-aware action selection: the least severe action the aircraft can still fly |
| `monitor.py` | `AerisCore`, which runs all of the above every tick |

### The detectors

| Test id | Compares | Catches |
|---|---|---|
| `gps.timeout`, `baro.timeout`, `mag.timeout`, `imu.timeout` | time since the last message | sensor stopped |
| `gps.stuck`, `baro.stuck` | consecutive identical values | frozen output |
| `gps.vel_consistency` | GPS velocity against vision velocity (CUSUM) | GPS drift or spoofing |
| `gps.pos_residual` | GPS position against the independent position (smoothed) | GPS drift, second opinion |
| `mag.heading_residual` | magnetometer against gyro-integrated heading | magnetic interference |
| `imu.accel_residual` | integrated IMU acceleration against the change in vision (or GPS) velocity | accelerometer bias |
| `twin.accel_residual` | IMU against the twin's predicted acceleration | supporting evidence |
| `motor.imbalance` | highest motor output against the median | a weak motor |
| `battery.voltage_residual` | measured voltage against the twin's prediction | charge loss, rising resistance |

### How a fault is told apart from another

The signature matrix in `diagnosis.py` holds the logic. Two examples:

- **GPS drift** must trip both GPS residuals, and must *not* trip the IMU residual.
- **IMU bias** must trip the IMU residual, and must *not* trip the GPS/vision
  consistency test, because GPS and vision still agree with each other.

A fault that matches no signature within 15 s becomes `UNKNOWN`, and AERIS lands.

### How recovery is chosen

Each action needs certain capabilities (`recovery.py`):

| Action | Needs |
|---|---|
| Continue (degraded) | horizontal navigation, height, heading, attitude, thrust margin, energy for the mission |
| Return | horizontal navigation, height, heading, attitude, energy to reach home |
| Land | height, attitude |
| Descend | attitude |

Health states decide which capabilities remain. Measured values decide some of them:
thrust margin from the motor outputs, energy and voltage headroom from the battery
twin. AERIS takes the least severe action whose needs are met. It never steps back
to a less cautious action, and a periodic re-check must ask for escalation three
times in a row before it happens.

## Simplifications to be aware of

- Point-mass dynamics: no roll or pitch, so attitude-control limits (and the risk of
  flying with little thrust margin) are not modelled.
- The stand-in autopilot is much simpler than PX4's EKF2 and commander.
- DEGRADED and FAILED latch for the rest of the flight.
- Sensor noise levels are plausible, not calibrated against real hardware.

## Adding things

- **A new fault:** add it to `FAULT_TYPES` and `FaultInjector` in `sim/faults.py`, add a
  generator in `campaign/scenarios.py`, then add a detector and a signature so AERIS
  can find it.
- **A new detector:** create it in `AerisCore.__init__`, update it in one of the
  `_..._tests` methods, and list its id in `COMPONENT_TESTS`. Then measure its noise
  on fault-free tuning flights before choosing a threshold (see ADR 0004).
