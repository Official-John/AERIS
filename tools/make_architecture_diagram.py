"""Draw docs/design/AERIS_architecture.png.

Needs matplotlib (not a runtime dependency):  python -m pip install matplotlib
Then:                                         python tools/make_architecture_diagram.py

Colours follow the site theme used by the HTML reports (aeris/evidence/svg.py).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.family"] = "Segoe UI"

INK = "#edf4f2"
MUTED = "#9aaba8"
MINT = "#9be8d8"
TEAL = "#00aa95"
ORANGE = "#f15a07"
PAGE = "#05080b"
SURFACE = "#0a1015"
LINE = "#5f706d"
fig, ax = plt.subplots(figsize=(7.2, 4.3), dpi=220)
fig.patch.set_facecolor(PAGE)
ax.set_facecolor(PAGE)
ax.set_xlim(0, 100)
ax.set_ylim(0, 60)
ax.axis("off")


def group(x0, y0, x1, y1, title, fill, edge, sub=None):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=1.2",
                                fc=fill, ec=edge, lw=1.0))
    ax.text(x0 + 1.2, y1 - 1.6, title, fontsize=7.6, fontweight="bold",
            color=MINT if edge == TEAL else MUTED, va="top")
    if sub:
        ax.text(x0 + 1.2, y1 - 4.4, sub, fontsize=6.0, color=MUTED, va="top", style="italic")


def box(x0, y0, x1, y1, title, sub=None, edge=LINE, fill=SURFACE, tcolor=INK):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.8",
                                fc=fill, ec=edge, lw=0.9))
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    if sub:
        ax.text(cx, cy + 1.0, title, ha="center", va="center", fontsize=6.9, fontweight="bold", color=tcolor)
        ax.text(cx, cy - 1.5, sub, ha="center", va="center", fontsize=5.8, color=MUTED)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=6.9, fontweight="bold", color=tcolor)


def arrow(pts, color=INK, ls="-", lw=1.0, label=None, lpos=None, lha="center", lcolor=None):
    xs, ys = zip(*pts)
    if len(pts) > 2:
        ax.plot(xs[:-1], ys[:-1], color=color, lw=lw, ls=ls, solid_capstyle="butt")
    ax.annotate("", xy=pts[-1], xytext=pts[-2],
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, mutation_scale=8,
                                shrinkA=0, shrinkB=0))
    if label:
        ax.text(lpos[0], lpos[1], label, fontsize=5.8, color=lcolor or MUTED, ha=lha, va="center")


# ---- layer containers
group(1, 19, 25, 57, "SIMULATION", "#0b1317", LINE, "plant surrogate for the aircraft")
group(36, 19, 60, 57, "AUTOPILOT", "#0b1116", LINE, "PX4-like stand-in: inner loop + failsafes")
group(70, 19, 99, 57, "AERIS", "#08201d", TEAL, "health monitor")
group(1, 1, 99, 14.5, "EVIDENCE LAYER", "#0a1015", LINE)

# ---- simulation
box(3, 41, 23, 49, "Vehicle dynamics", "airframe · motors · battery · wind")
box(3, 31, 23, 38.5, "Sensor models", "IMU · GPS · baro · mag · vision")
box(3, 21, 23, 28.5, "Fault injector", "8 fault types · sensors and airframe",
    edge=ORANGE, fill="#26100e", tcolor="#ff7a45")

# ---- PX4
box(38, 41, 58, 49, "Controllers", "position · attitude · rate")
box(38, 31, 58, 38.5, "Estimator", "fuses sensors → state, gates outliers")
box(38, 21, 58, 28.5, "Commander", "modes + built-in failsafes")

# ---- AERIS chain
box(72, 44, 97, 50.5, "Digital twin", "expected state · energy what-if", edge=TEAL)
box(72, 37, 97, 42, "Residuals + detectors", edge=TEAL)
box(72, 30, 97, 35, "Diagnosis + evidence trail", edge=TEAL)
box(72, 21, 97, 28, "Recovery manager", "least severe action still flyable", edge=TEAL)
for y_top, y_bot in [(44, 42), (37, 35), (30, 28)]:
    arrow([(84.5, y_top), (84.5, y_bot)], color=TEAL)

# ---- closed control loop (sim <-> PX4)
arrow([(13, 41), (13, 38.5)])
arrow([(23, 34.75), (38, 34.75)], label="sensor data", lpos=(30.5, 36.3))
arrow([(48, 38.5), (48, 41)])
arrow([(38, 45), (23, 45)], label="actuator cmds", lpos=(30.5, 46.5))
arrow([(48, 28.5), (48, 31)], color=MUTED, lw=0.8)
arrow([(13, 28.5), (13, 31)], color=ORANGE)

# ---- PX4 <-> AERIS
arrow([(58, 34.75), (65, 34.75), (65, 47.25), (72, 47.25)], color=TEAL,
      label="state +\nsensor topics\n(uXRCE-DDS)", lpos=(65, 30.6), lcolor=TEAL)
arrow([(72, 24.5), (58, 24.5)], color=TEAL, label="mode requests", lpos=(65, 26.0), lcolor=TEAL)

# ---- evidence layer
box(3, 3, 25, 10.5, "Scoring oracle", "ground truth → metrics")
box(27.5, 3, 49.5, 10.5, "Flight recorder", "time series · event log")
box(52, 3, 74, 10.5, "Campaign runner", "seeds · manifests · splits")
box(76.5, 3, 97, 10.5, "Replay + reports", "timeline · A/B comparison")
arrow([(17, 21), (17, 10.5)], color=ORANGE, ls=(0, (3, 2)),
      label="ground-truth labels (hidden from AERIS)", lpos=(18.2, 16.8), lha="left", lcolor=ORANGE)
arrow([(48, 21), (48, 10.5)], color=MUTED, ls=(0, (3, 2)), lw=0.8)
arrow([(84.5, 21), (84.5, 10.5)], color=MUTED, ls=(0, (3, 2)), lw=0.8)
ax.text(49.2, 16.8, "all topics + events logged", fontsize=5.8, color=MUTED, ha="left", va="center")

plt.subplots_adjust(0, 0, 1, 1)
fig.savefig("docs/design/AERIS_architecture.png", dpi=220, facecolor=PAGE)
print("ok")
