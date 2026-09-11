# ADR 0001: Build a pure-Python MVP before the PX4 / ROS 2 stack

Status: accepted, 11 September 2026

## Context

The v2 design (docs/design/) targets PX4 SITL, ROS 2 Jazzy and Gazebo on Ubuntu 24.04,
over twelve weeks. The project had two days. The development machine runs Windows 11
with Python 3.11 and numpy, and has no C++ compiler, no WSL distribution and no Docker.
Setting up PX4, ROS 2 and Gazebo under WSL2 regularly takes a beginner several days
by itself.

## Decision

Build the whole AERIS pipeline in Python first, running against:

- an in-process point-mass simulator (the plant surrogate), and
- a small PX4-like stand-in autopilot (the baseline).

AERIS itself (`aeris/core`) sits behind a narrow interface: a `SensorFrame` in and
`Command`s out. A second adapter for PX4 over ROS 2 can replace
`aeris/adapters/standin.py` later, and the core doesn't change.

## Consequences

- Everything runs on the current laptop in seconds. A 1,620-flight campaign takes
  about six minutes on 11 cores.
- Results compare AERIS with a stand-in, not with PX4. Every report says so.
- The C++20 core in the v2 design becomes a port of `aeris/core`, which is small
  (about 1,000 lines including comments) and unit-tested, so the tests act as the spec for the port.
