# ADR 0004: How thresholds were set, and what each evaluation round found

Status: accepted, 11 September 2026

## The rule

- Every generated scenario gets a split from its seed: 30 % **tuning**, 70 % **evaluation**.
- Thresholds are set from noise measured on fault-free *tuning* flights, with a margin
  above the worst value seen. Never from evaluation results.
- If evaluation results lead to a change, the reported numbers come from a new base
  seed that nobody has looked at.

## Development (campaign seed 1000)

The first campaign had 4 false alarms in 3.8 fault-free flight hours:

- `gps.pos_residual` compared raw GPS against the independent position with a 3 m
  threshold. Ordinary GPS noise crossed it every few minutes.
- `gps.vel_consistency` started its filter from a single noisy sample at take-off.

Fixes: smooth the position residual over 2 s; wait 2 s after take-off before in-flight
tests start. Then each test's worst value was measured on 75 fault-free tuning flights:

| Test | Worst on 75 tuning flights | Threshold set |
|---|---|---|
| `gps.pos_residual` (smoothed) | 1.89 m | 3.0 m |
| `gps.vel_consistency` (CUSUM) | 0.36 | 1.5 |
| `imu.accel_residual` (CUSUM) | 0.38 | 0.6 |
| `twin.accel_residual` (CUSUM) | 22.4 at first; 1.58 after the fix below | 2.0 |
| `mag.heading_residual` | 5.1° | 10° |
| `motor.imbalance` | 0.04 | 0.12 |
| `battery.voltage_residual` | 0.04 V | 0.6 V |

The measurement exposed a bug: the twin predicted acceleration from the *current*
setpoint, but the IMU sample was taken before that setpoint existed. The one-tick
offset turned setpoint jitter into residual. Using the previous tick's setpoint cut
the vertical residual by a factor of five.

## Evaluation round 1 (campaign seed 5000, soak seed 90000). Not the reported numbers.

All four campaign-checked requirements passed, with 0 false alarms in 5.9 hours, and
1 false alarm in the 40-hour soak. Two problems came out of it:

1. **Battery policy much worse than the baseline**: 0 % mission success against 64 %,
   landing a median 93 m from home. Four causes:
   - on ticks without a battery message, the energy check silently used counted
     charge (31.9 Wh "usable" when about 16 Wh remained)
   - the in-flight resistance estimate was contaminated by the voltage step at the
     moment of the fault: 0.44 Ω estimated, 0.09 Ω true
   - the "never step back down" rule locked in a decision made on that transient estimate
   - the voltage margin was stricter than needed; failing it midway only causes the
     landing that was chosen up front anyway

   Fixes: keep the last battery reading; estimate resistance from 1-second differences
   with a median; restart the estimate when the battery becomes suspect, and let the
   decision wait (up to 15 s) for 15 good samples; require three consecutive re-checks
   before escalating; set the voltage floor to 3.40 V per cell, just above the autopilot's
   3.35 V forced-landing threshold.

2. **One false IMU-bias diagnosis in strong wind** (soak). Deliberately *not* fixed,
   because the only evidence for it came from evaluation data. It is documented below
   and left as the next exercise (docs/TWO_DAY_PLAN.md).

## Evaluation round 2 (campaign seed 7000, soak seed 95000). These are the reported numbers.

Flight code at commit `fc3e383`. The reports say `fc3e383-dirty` because docs and the
replay page's start-time feature had changed; every file that affects a flight was
identical to the commit (checked with `git diff`).

Findings to report as they are:

- **False alarms**: 2 in 40.2 soak hours, both IMU-bias diagnoses in 6–7 m/s wind:
  0.05 per hour (95 % interval 0.006–0.18). The measured rate meets the 0.1/h target,
  but proving it at 95 % confidence needs more flight hours or the IMU fix.
- **Battery faults**: mission success 48 % against the baseline's 69 %, with equal safe
  landings (100 %). AERIS returns home early when its charge estimate is marginal.
  Charge estimated from voltage is imprecise in the flat middle of the LiPo curve
  (3.70–3.78 V per cell between 20 % and 40 %).
- **Motor degradation**: 69 % against 100 %, equal safety. AERIS turns back below a 1.4
  thrust-to-weight margin. The point-mass simulator doesn't model the attitude-control
  risk of flying with little margin, so the baseline is never punished for it.
- **Timing**: one 1.1 s step in 5 million, during the soak, with 11 worker processes on a
  Windows laptop. This is operating-system scheduling. The project makes no real-time claims.
