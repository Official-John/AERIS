# Getting started (beginner guide)

This guide assumes nothing beyond "I can open a terminal". Every command is typed in
**PowerShell** from the project folder. Expected output is shown so you know it worked.

## 1. Open a terminal in the project folder

In VS Code: *File → Open Folder…* → choose the `AERIS` folder, then *Terminal → New Terminal*.
Or in PowerShell:

```powershell
cd "C:\Users\ADMIN\Desktop\JOHN\Claude Works\AERIS"
```

## 2. Check Python

```powershell
python --version
```

You need 3.10 or newer (this machine has 3.11.6). If `python` isn't found, try `py`
instead everywhere below. The only library needed is numpy:

```powershell
python -m pip install -r requirements.txt
```

## 3. Run the tests (about 20 seconds)

```powershell
python -m unittest discover -s tests -t .
```

Expected ending:

```
Ran 43 tests in 19.3s

OK
```

Each test proves one small thing: that a frozen GPS is noticed in under half a
second, that AERIS never picks an action the aircraft can no longer fly, that AERIS
can't see the answer key, and so on. `docs/trace_matrix.md` lists which test proves
which requirement.

## 4. Watch the flagship demo

```powershell
python -m aeris demo
```

It flies the same mission twice with the same GPS fault: once with the baseline
autopilot alone, once with AERIS. Your browser opens `results/demo/flagship_gps_drift/replay.html`.

In the replay:

- press **Play** (5× speed is a good default) or drag the slider
- the **orange** path is the baseline, the **blue** path is AERIS, the dashed line is the plan
- the **⚠ fault injected** marker appears at t = 40 s
- the **health lights** on the right turn from green (NOMINAL) to yellow (SUSPECT) to red (FAILED)
- scroll down to **What happened, and why**; open the *evidence* of the diagnosis
  row to see the exact numbers AERIS used

What to notice: the GPS starts lying slowly, 0.4 m/s towards the north. The baseline
autopilot believes it and gets dragged about 26 m off course. AERIS notices that GPS
and vision odometry disagree, stops using GPS, and finishes the mission.

## 5. Fly other scenarios

Each file in `scenarios/` is one situation:

| File | What happens |
|---|---|
| `nominal.json` | no fault; AERIS should stay quiet |
| `flagship_gps_drift.json` | slow GPS drift (the demo) |
| `gps_drift_no_vision.json` | same drift without vision odometry: AERIS has no independent reference, so it can't catch it |
| `gps_loss.json` | GPS stops; both cope, because vision odometry takes over |
| `baro_frozen.json` | barometer freezes; the baseline loses its height estimate while landing |
| `mag_error.json` | compass off by 40°; the baseline's position estimate falls apart and it lands 95 m away |
| `imu_bias.json` | accelerometer bias; AERIS measures it and cancels it |
| `motor_weak.json` / `motor_severe.json` | a weak motor: AERIS continues carefully, or turns home |
| `battery_fault.json` | sudden charge loss |

```powershell
python -m aeris fly scenarios/baro_frozen.json --open
```

Add `--configs A,B,C` to include the advisory run.

## 6. Make your own scenario

Copy a file, rename it, and edit it. For example `scenarios/my_test.json`:

```json
{
  "scenario_id": "my_test",
  "seed": 42,
  "vehicle": {"has_vision": true},
  "wind": {"mean_mps": 6.0, "dir_deg": 90},
  "faults": [{"type": "mag_offset", "start": 30.0, "params": {"offset_deg": -25}}]
}
```

Fault types and their parameters:

| type | params |
|---|---|
| `gps_off`, `gps_stuck`, `baro_stuck` | none |
| `gps_drift` | `rate_mps`, `direction_deg` |
| `mag_offset` | `offset_deg` |
| `imu_bias` | `bx`, `by` (m/s²) |
| `motor_degradation` | `motor` (0–3), `efficiency` (0–1) |
| `battery_fault` | `charge_loss` (0–1), `resistance_mult` |

The same seed always gives exactly the same flight, so you can rerun anything.

## 7. Run a fault campaign

A campaign flies hundreds of random scenarios, each three ways, and measures everything.

```powershell
python -m aeris campaign --quick --open                 # 81 flights, about 30 seconds
python -m aeris campaign --per-fault 60 --seed 7000     # 1,620 flights, about 6 minutes
```

Open `results/campaign/report.html`. How to read it:

- Requirement checks: PASS or FAIL against the numbers in `docs/requirements.json`.
- Mission outcome: blue bars (AERIS) against orange bars (baseline), for each fault.
  The thin black line on each bar is the 95 % confidence interval, the range the real
  value probably lies in.
- Time to detect: how quickly each fault is noticed (log scale).
- Confusion matrix: which fault was injected (row) and what AERIS concluded
  (column). A perfect result is a diagonal.
- Detection against severity: small faults are harder to see.

A fault-free "soak" test, for false alarms only:

```powershell
python -m aeris campaign --families none --per-fault 1200 --configs B --seed 95000 --out results/soak
```

## 8. Useful words

| Word | Meaning |
|---|---|
| Residual | the difference between what a sensor says and what something independent predicts |
| CUSUM | a test that adds up small, repeated disagreements, so slow drifts get caught |
| Health state | NOMINAL (fine), SUSPECT (something looks off), DEGRADED (usable with care), FAILED (not used) |
| Signature | the pattern of tests a particular fault trips |
| Digital twin | AERIS's own model of the aircraft, used to predict what should happen |
| Configuration A / B / C | baseline alone / AERIS watching / AERIS in control |
| Seed | the number that makes a random scenario repeatable |
| Confidence interval | the range the true value probably lies in, given how many flights were run |

## 9. Troubleshooting

- `python` is not recognized: use `py -m aeris demo`, or reinstall Python with
  "Add to PATH" ticked.
- The browser didn't open: open the `replay.html` path printed at the end by hand.
- A campaign seems stuck: always run it as `python -m aeris campaign ...` from the
  project folder. On Windows, parallel workers can't start from a script piped into
  Python.
- Different numbers from mine: check the seed and `--per-fault`. Same seed and same
  code give the same result.
