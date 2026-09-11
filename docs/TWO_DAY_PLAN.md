# Two-day plan

The code, tests and evidence already exist. These two days are for understanding
the project well enough to defend it, and for packaging it: repository, demo video,
write-up. Times are rough; skip ahead if something is already clear.

## Day 1: understand it and make it yours

**Morning (3 h): run everything once**

1. Follow `docs/GETTING_STARTED.md` steps 1 to 5: tests, demo, two or three other scenarios.
2. Read `README.md` top to bottom.
3. Keep the demo replay open and read `docs/ARCHITECTURE.md`. For each row of the
   "What happened, and why" table, find the file that produced it.

Check yourself: can you explain, in two sentences each,

- why AERIS compares GPS with *vision odometry*, and not with the autopilot's own estimate?
- what configurations A, B and C are, and why B exists?
- why the fault injector must corrupt the data *before* the autopilot sees it?

**Afternoon (3 h): read the core**

Read these files in order. They're short and heavily commented.

1. `aeris/core/types.py`: what goes in and out of AERIS
2. `aeris/core/detectors.py`: four small tests
3. `aeris/core/health.py`: the state machine
4. `aeris/core/diagnosis.py`: the signature table (the "self-diagnosing" part)
5. `aeris/core/recovery.py`: capability-aware recovery
6. `aeris/core/monitor.py`: how they connect (skim `_imu_tests` the first time)

Then make one change and watch its effect. Suggested: in `aeris/core/config.py` set
`mag_threshold_deg` to `3.0`, run `python -m aeris fly scenarios/nominal.json --configs B --open`,
and look for false alarms. Put it back afterwards, and run the tests to confirm.

**Evening (1 h): publish**

- Push the repository to GitHub (see "Publishing" in `README.md`).
- Open the *Actions* tab and check the CI run goes green.

## Day 2: evidence and story

**Morning (2 h): the numbers**

- Open `docs/evidence/campaign_report.html` and `docs/evidence/soak_report.html`.
- Read `docs/adr/0004-thresholds-and-evaluation-history.md`. It explains how the
  thresholds were set, and what the first evaluation round found and fixed.
  Reviewers like this part most, because it shows the method is honest.
- Write down the three results you'll lead with (suggestions in `docs/PRESENTATION.md`).

**Midday (2 h): demo video (2 to 3 minutes)**

Record the screen with the Windows Snipping Tool (*Record*) or OBS. The script is in
`docs/PRESENTATION.md`. Do two takes; keep the better one.

**Afternoon (3 h): write-up and rehearsal**

- Slides or a one-page write-up from the outline in `docs/PRESENTATION.md`.
- Rehearse the Q&A section out loud. Hard questions are fine to get: the honest
  answers are already written down.

**Optional stretch (if time remains): fix a known weakness yourself**

The soak test found one false alarm in about 40 flight hours: a wind gust made the
IMU check trip, and AERIS diagnosed a bias that wasn't there. The fix follows the
same idea as the GPS drift signature: require a second, independent residual to agree.

1. In `aeris/core/diagnosis.py`, move `"twin.accel_residual"` from `supports` to
   `requires` for `IMU_BIAS`.
2. Run the tests.
3. Re-evaluate on seeds nobody has looked at:
   `python -m aeris campaign --per-fault 60 --seed 8000` and the soak with `--seed 96000`.
4. Record what happened in a new ADR, including whether detection of real IMU bias got slower.
