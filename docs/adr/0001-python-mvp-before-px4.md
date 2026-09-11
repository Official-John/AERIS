# ADR 0001: Build the pipeline in Python before targeting PX4

Status: accepted, 11 September 2026

## Context

The design this project came from targets PX4 SITL, ROS 2 Jazzy and Gazebo on Ubuntu,
with the health monitor written in C++20. None of that runs on the development machine
as it stands: Windows, Python, no C++ toolchain, no Linux environment and no container
runtime. Standing that stack up is a prerequisite that produces no evidence of its own.

The open questions at this point are about detection and recovery logic, not about
which autopilot sits underneath: whether a slow GPS drift can be caught at all,
whether faults can be told apart from each other, whether a recovery policy can be
held to what the aircraft can still fly. Those questions can be answered against any
autopilot that has an estimator, a controller and failsafes.

## Decision

Build the whole pipeline in Python first, running against:

- an in-process point-mass simulator, the plant surrogate, and
- a small PX4-like stand-in autopilot, which is also the baseline to beat.

AERIS itself (`aeris/core`) sits behind a narrow interface: a `SensorFrame` in,
`Command`s out. A second adapter for PX4 over ROS 2 can replace
`aeris/adapters/standin.py` later, and the core does not change.

## Consequences

- The full loop runs on one laptop in seconds, so statistical evidence is affordable:
  a 1,620-flight campaign takes about six minutes across 11 cores. The same campaign
  on Gazebo at real time would run for days.
- Results compare AERIS against a stand-in, not against PX4. Every report says so, and
  the claim stays "better than this baseline", never "better than PX4".
- The C++20 core becomes a port of `aeris/core`, which is small (about 1,000 lines
  including comments) and unit-tested, so the tests are the specification for the port.
- The risk accepted here is that the stand-in flatters AERIS somewhere PX4 would not.
  `docs/OPEN_ISSUES.md` records the case already identified: the thrust-margin policy,
  which a point-mass model cannot judge.
