# Open issues

Known weaknesses, how to reproduce each one, and what the fix is likely to be. The
README lists these as limitations; this file carries the detail.

## False IMU-bias diagnosis in strong wind

Across a 1,200-flight fault-free soak, two flights raised an IMU-bias diagnosis with
no fault present, both in 6 to 7 m/s wind. That is 0.05 per flight hour, inside the
target of 0.1, but both alarms share one cause: a sustained gust pushes the aircraft
hard enough that the IMU residual against vision velocity accumulates past its CUSUM
threshold before the wind estimate settles.

Reproduce:

```bash
python -m aeris campaign --families none --per-fault 1200 --configs B --seed 95000 --out results/soak
```

Likely fix: demand a second, independent residual before confirming, the same rule
that keeps GPS drift honest. In `aeris/core/diagnosis.py`, move `twin.accel_residual`
from `supports` to `requires` for `IMU_BIAS`. The cost to measure afterwards is
detection latency on real IMU bias, already the slowest at a median of 2.5 s, and the
detection rate on mild biases.

Re-evaluate on seeds that have never been used, then record the outcome in a new ADR:

```bash
python -m aeris campaign --per-fault 60 --seed 8000
python -m aeris campaign --families none --per-fault 1200 --configs B --seed 96000 --out results/soak2
```

## Battery charge estimate in the flat part of the discharge curve

Between 20 % and 40 % charge, a LiPo cell moves only from 3.70 V to 3.78 V, so charge
estimated from voltage is least precise exactly where the recovery decision matters.
AERIS is conservative there and returns home early, which is why its mission success
on battery faults (48 %) trails the baseline (69 %) while safe landings stay equal.

A fix needs a better charge estimate rather than a different policy: coulomb counting
as the primary signal, re-anchored on voltage only when current is low, with the
in-flight resistance estimate used to correct the sag.

## Thrust-margin policy is untested by this simulator

AERIS turns back below a thrust-to-weight margin of 1.4. The point-mass model has no
attitude dynamics, so flying on a thin margin never costs the baseline anything, and
the policy looks like pure loss in the numbers. Whether 1.4 is the right line needs a
simulator with attitude control, or hardware.

## Diagnosis confidence is under-stated

Diagnoses issued at 0.80 confidence were correct 99.6 % of the time on the evaluation
set. The confidence number comes from counting how many tests in a signature matched,
which is a proxy, not a calibrated probability. Fitting it against observed accuracy
would make the number mean what it says.

## Detection gaps without vision odometry

A quarter of the campaign scenarios fly without vision odometry. Without it there is
no independent horizontal position reference, so GPS drift cannot be caught and GPS
loss cannot be flown around: all 11 undetected drifts and all 10 failed GPS-loss
missions were on those aircraft. Closing this needs a second independent source, such
as optical flow with a rangefinder, or terrain-relative positioning.
