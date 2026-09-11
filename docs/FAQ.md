# Design questions

The questions this project draws most often, and the honest answers. Headline results
are in the README; the method behind them is in `docs/adr/`.

## Is the autopilot PX4?

No. `aeris/autopilot/` is a simplified stand-in with the same shape as PX4: a state
estimator with innovation gates, a cascaded position controller, and layered failsafes
that escalate from Return to Land to Descend. Every report repeats this, and no number
here should be read as a PX4 benchmark. AERIS reaches it through one small adapter
(`aeris/adapters/standin.py`), so targeting real PX4 over ROS 2 means writing a second
adapter instead of changing the health monitor. See
[ADR 0001](adr/0001-python-mvp-before-px4.md).

## How realistic is the simulator?

A point-mass quadrotor with thrust lag, aerodynamic drag, gusts, a battery model and
noisy sensors at realistic rates. There is no roll or pitch, and the airframe is not
validated against a real one. The numbers compare two pieces of software inside the
same simplified world. They do not predict real-world performance.

## How do you know the thresholds were not tuned to the test?

Every generated scenario is split by its seed: 30 % tuning, 70 % evaluation.
Thresholds come from noise measured on fault-free tuning flights, with a margin above
the worst value seen. When the first evaluation round exposed a bug in the battery
policy, the fix was followed by a completely fresh evaluation on seeds that had never
been looked at. [ADR 0004](adr/0004-thresholds-and-evaluation-history.md) records the
whole history, including the one weakness left unfixed because the only evidence for
it came from evaluation data.

## Why does AERIS do worse than the baseline on weak motors and damaged batteries?

It is deliberately more cautious. It turns back when the measured thrust margin or
the twin-predicted energy gets thin, which costs missions it might have finished:
69 % against 100 % on motor degradation, 48 % against 69 % on battery faults, with
identical safe-landing rates. The point-mass simulator never punishes the baseline
for flying on a thin margin, so the caution shows up purely as cost here. Whether
that trade is right is a policy question, and the thresholds sit in
`aeris/core/config.py` for anyone who wants to argue with them.

## What does "digital twin" mean in this project?

Not the simulator. The simulator is the plant surrogate, standing in for the physical
aircraft. The twin is the model AERIS carries in `aeris/core/twin.py`: it predicts the
acceleration the airframe should achieve from the autopilot's own commands, and it
models the battery, learning internal resistance in flight from how voltage responds
to current. Those predictions give the residuals that detection runs on, and they
answer "is there enough energy to reach home?" before a return is committed.

## Is the false-alarm requirement met?

The measured rate is 0.05 per flight hour, two alarms across 40 fault-free flight
hours, against a target below 0.1. The 95 % interval still reaches 0.18, so the
target is met in measurement but not yet proven at that confidence. Both alarms came
from the same weakness, described in [open issues](OPEN_ISSUES.md).

## Why Python rather than C++?

The target stack needs Linux, and the C++ core in the design needs a toolchain the
development machine did not have. Building the pipeline in Python first put a working
end-to-end evaluation in place before any of that investment. `aeris/core` carries no
framework dependency, runs to about 1,000 lines including comments, and has a test
suite that doubles as the specification for a C++ port.

## What would it take to trust these numbers on real hardware?

More than this project claims. In order: swap the stand-in for PX4 SITL and repeat the
campaign, check the detectors against recorded flights from a real airframe (the CMU
AirLab ALFA dataset has labelled fault times), then hardware in the loop. Each step
tests a different assumption, and the first one that breaks is the interesting result.
