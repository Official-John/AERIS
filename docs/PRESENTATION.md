# Presenting AERIS

## The three results to lead with

All from the round-2 campaign: fresh seeds, 42 evaluation scenarios per fault type,
the same scenarios flown with and without AERIS.

1. **Crashes fell from 23 to 6** across 336 faulted flights, and safe landings rose
   from 76 % to 94 %.
2. **GPS drift (spoofing-like)**: the baseline finished 0 % of missions and landed a
   median 29 m from home; with AERIS, 69 % finished and the median landing was 2.5 m
   from home. Median time to flag it: 1.4 s (confirmation by a second check follows).
3. **Frozen barometer**: mission success from 2 % to 100 %, crashes from 21 % to 0 %.

And one honest number, because reviewers trust a project more when it shows one:
AERIS is *more cautious* than the baseline with weak motors and damaged batteries.
It finishes fewer of those missions (69 % against 100 %, and 48 % against 69 %), with
equal safety.

## Two-minute demo script

Open `docs/evidence/flagship_replay.html` full screen. Speed 5×.

| Time | Show | Say |
|---|---|---|
| 0:00 | Title and the two result tiles | "Same aircraft, same mission, same fault, flown twice: once with a normal autopilot, once with AERIS watching it." |
| 0:15 | Press Play | "It's a six-waypoint survey at 30 m. At 40 seconds I make the GPS start lying: it drifts north at 0.4 m/s, like a spoofing attack." |
| 0:35 | Fault marker appears; pause at t = 42, then at t = 51 | "The normal autopilot trusts the GPS, because the drift is too slow for its sanity checks. AERIS compares GPS velocity with vision odometry: GPS turns yellow, suspect, after 1.7 s. It waits for a second, independent check (position) to agree before calling it failed, at 50.6 s. That rule stops one noisy check from triggering a recovery." |
| 0:55 | Scroll to the timeline; open the evidence of the diagnosis | "Every decision comes with its evidence: which checks tripped, by how much, against which threshold." |
| 1:15 | Play on to the end | "AERIS stops using GPS and finishes on vision. The baseline gets dragged 26 m off course and lands 29 m from home." |
| 1:35 | Switch to `docs/evidence/campaign_report.html` | "One flight proves nothing, so I flew 1,620 more: eight fault types, random timing, severity and wind. Crashes went from 23 to 6." |
| 1:55 | Point at the requirement checks | "Every requirement is traced to a test or a campaign check." |

## Slide outline (6 slides)

1. **The problem.** Aircraft sensors fail, and some failures are quiet: a slow GPS drift
   looks like normal flight.
2. **The idea.** A supervisor that detects, diagnoses, explains and recovers, and never
   takes control away from the autopilot. (Use `docs/design/AERIS_architecture.png`.)
3. **How it tells faults apart.** Independent references plus the signature table.
   GPS drift and IMU bias trip different sets of checks.
4. **Demo.** The replay.
5. **Evidence.** The results table from the README. Seeds split into tuning and
   evaluation; threshold history in ADR 0004.
6. **Limits and next steps.** Stand-in autopilot, point-mass simulator, the IMU false
   alarm, then PX4 SITL and ROS 2, and a C++ core.

## Questions you'll probably get

**Is this PX4?**
No. It is a simplified PX4-like stand-in with the same kind of structure: an estimator
with innovation gates, a cascaded controller, and layered failsafes. The AERIS core
talks to it through one small adapter, so moving to PX4 over ROS 2 means writing a
new adapter, not rewriting AERIS (ADR 0001).

**How realistic is the simulator?**
A point-mass quadrotor with thrust lag, drag, gusts, a battery model and noisy sensors.
There is no roll or pitch and no validated airframe. The numbers compare two pieces of
software in the same simplified world. They don't predict real-world performance.

**How do you know you didn't tune AERIS to the test?**
Thresholds came from fault-free *tuning* flights only. When evaluation round 1 exposed
a battery bug, the fix was followed by a completely new evaluation on fresh seeds.
The whole history, including what was deliberately not fixed, is in ADR 0004.

**Why is AERIS worse with weak motors and bad batteries?**
It is deliberately more cautious: it turns home when thrust margin or predicted energy
gets thin. The simulator never punishes the baseline for flying on the edge, so the
caution only shows as cost here. Whether it's the right trade is a policy question.

**What does "digital twin" mean here?**
AERIS keeps its own model of the aircraft: expected acceleration from the autopilot's
commands, and a battery model that learns internal resistance in flight. It uses the
model to spot disagreements and to answer "can we still get home?" before committing
to a return.

**Is the false-alarm target proven?**
The measured rate is 0.05 per hour (2 in 40 flight hours), below the 0.1 target. The
95 % interval still reaches 0.18, so it isn't proven yet. Both alarms were the same
IMU weakness in strong wind, and the fix is known.

**Why Python and not C++?**
Two days, and no C++ toolchain on the machine. The core is about 1,000 lines with a
test suite, which works as the specification for a C++ port.

## CV line

Name it under your own line of work at johnayodele.dev and on
linkedin.com/in/ayodelejohn05.

> Self-Diagnosing Aircraft Digital Twin (AERIS) | Python, numpy, simulation, fault management
> Built a fault detection, isolation and recovery supervisor for a simulated quadrotor:
> residual-based detectors, a fault signature matrix, a digital twin with in-flight
> battery identification, and capability-aware recovery. Across 1,620 simulated
> flights over 8 fault types it cut crashes from 23 to 6 (of 336 faulted flights)
> against a baseline autopilot, with 43 automated tests and requirement traceability.

## Post draft

> I broke an aircraft simulator on purpose, eight different ways, and wrote software
> that tried to save it.
>
> The hardest fault was a GPS that drifts slowly, the way a spoofing attack does. The
> autopilot's own checks can't see it, because each step looks normal. My supervisor
> compares GPS with vision odometry, flags the drift within about a second and a half,
> confirms it with a second independent check, stops trusting GPS, and the mission
> finishes. Without it, the drone lands 29 m from home.
>
> Across 1,620 simulated flights, crashes fell from 23 to 6. It's also more cautious
> than I expected with weak motors and damaged batteries, and the write-up says so.
>
> The code, the tests and the full evaluation history, including what didn't work,
> are on my GitHub. More of my work: johnayodele.dev
