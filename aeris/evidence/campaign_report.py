"""HTML report for a fault campaign: metrics tables, charts and requirement checks."""
from html import escape

from .svg import dot_latency, hbar_rates, report_css, seq_color, seq_ink

NAMES = {"none": "No fault", "gps_off": "GPS loss", "gps_stuck": "GPS frozen", "gps_drift": "GPS drift",
         "baro_stuck": "Barometer frozen", "mag_offset": "Magnetometer error", "imu_bias": "IMU bias",
         "motor_degradation": "Motor degradation", "battery_fault": "Battery fault"}


def _r(t, digits=0):
    if t is None or t[0] is None:
        return "n/a"
    f = lambda v: f"{100 * v:.{digits}f}%"
    return f"{f(t[0])} <span class='muted'>({f(t[1])}–{f(t[2])})</span>"


def build(summary, checks, meta):
    det = summary["detection"]
    faults = [f for f in summary["fault_types"] if f != "none"]
    out_ = summary["outcomes"]
    fa = summary["false_alarms"]

    tiles = [
        ("Flights flown", f"{meta['flights']}", f"{meta['scenarios']} scenarios × configs {', '.join(meta['configs'])}"),
        ("Evaluation flights", f"{summary['runs']}", "held-out seeds only"),
        ("Wall time", f"{meta['wall_s'] / 60:.1f} min", f"{meta['workers']} parallel workers"),
        ("False alarms", f"{fa['count']}", f"in {fa['clean_flight_hours']:.1f} fault-free flight hours"),
        ("AERIS step time", f"{summary['timing']['mean_ms']} ms", f"worst {summary['timing']['worst_max_ms']} ms of a 20 ms budget"),
    ]
    tiles_html = "".join(f"<div class='card tile'><div class='k'>{escape(k)}</div><div class='v'>{v}</div>"
                         f"<div class='s'>{escape(s)}</div></div>" for k, v, s in tiles)

    success = {}
    for cfg, label in (("C", "AERIS active (C)"), ("A", "Baseline (A)")):
        success[label] = {NAMES[f]: (*out_[f][cfg]["mission_success"], out_[f][cfg]["n"])
                          for f in summary["fault_types"] if cfg in out_.get(f, {})}
    cats = [NAMES[f] for f in summary["fault_types"]]
    chart_success = hbar_rates(cats, [("AERIS active (C)", "--series-c", success["AERIS active (C)"]),
                                      ("Baseline (A)", "--series-a", success["Baseline (A)"])])
    recovered = {}
    for cfg, label in (("C", "AERIS active (C)"), ("A", "Baseline (A)")):
        recovered[label] = {NAMES[f]: (*out_[f][cfg]["recovered"], out_[f][cfg]["n"])
                            for f in summary["fault_types"] if cfg in out_.get(f, {})}
    chart_recovered = hbar_rates(cats, [("AERIS active (C)", "--series-c", recovered["AERIS active (C)"]),
                                        ("Baseline (A)", "--series-a", recovered["Baseline (A)"])])
    lat_rows = [(NAMES[f], *det[f]["latency_median"], det[f]["latency_p95"], det[f]["n"] - det[f]["missed"])
                for f in faults]
    chart_latency = dot_latency(lat_rows)

    det_rows = "".join(
        f"<tr><td>{NAMES[f]}</td><td>{det[f]['n']}</td><td>{_r(det[f]['detection_rate'])}</td>"
        f"<td>{det[f]['latency_median'][0] if det[f]['latency_median'][0] is not None else 'n/a'} s</td>"
        f"<td>{det[f]['latency_p95'] if det[f]['latency_p95'] is not None else 'n/a'} s</td>"
        f"<td>{_r(det[f]['isolation_accuracy'])}</td></tr>" for f in faults)

    out_rows = ""
    for f in summary["fault_types"]:
        o = out_.get(f, {})
        if "A" not in o or "C" not in o:
            continue
        out_rows += (f"<tr><td>{NAMES[f]}</td><td>{o['C']['n']}</td>"
                     f"<td>{_r(o['A']['mission_success'])}</td><td>{_r(o['C']['mission_success'])}</td>"
                     f"<td>{_r(o['A']['recovered'])}</td><td>{_r(o['C']['recovered'])}</td>"
                     f"<td>{_r(o['A']['crashed'])}</td><td>{_r(o['C']['crashed'])}</td>"
                     f"<td>{o['A']['landing_distance_median'][0]} m</td><td>{o['C']['landing_distance_median'][0]} m</td></tr>")

    conf = summary["confusion"]
    head = "".join(f"<th>{escape(p)}</th>" for p in conf["predicted"])
    body = ""
    for e in conf["expected"]:
        row = conf["counts"][e]
        n = sum(row.values()) or 1
        cells = ""
        for p in conf["predicted"]:
            v = row[p] / n
            cells += (f"<td style='background:{seq_color(v)};color:{seq_ink(v)};text-align:center' "
                      f"title='{escape(e)} diagnosed as {escape(p)}: {row[p]} of {n}'>{row[p] or ''}</td>")
        body += f"<tr><th>{escape(e)}</th>{cells}</tr>"
    confusion = f"<table><tr><th>injected ↓ / diagnosed →</th>{head}</tr>{body}</table>"

    sev = summary["detection_vs_severity"]
    sev_rows = ""
    for f, bins in sev.items():
        if all(b["n"] == 0 for b in bins) or len({b["severity"] for b in bins}) < 2:
            continue
        cells = ""
        for b in bins:
            r = b["detection_rate"]
            v = r[0]
            txt = "–" if v is None else f"{100 * v:.0f}%"
            cells += (f"<td style='background:{seq_color(v)};color:{seq_ink(v)};text-align:center' "
                      f"title='n={b['n']}'>{txt}</td>")
        sev_rows += f"<tr><th>{NAMES[f]}</th>{cells}</tr>"
    sev_head = "".join(f"<th>{b}</th>" for b in ("mildest quarter", "second", "third", "most severe quarter"))

    calib = "".join(f"<tr><td>{c['bin']}</td><td>{c['n']}</td><td>{c['mean_confidence']}</td>"
                    f"<td>{_r(c['accuracy'])}</td></tr>" for c in summary["calibration"])

    def _verdict(c):
        if c["pass"] is None:
            return "<td class='muted'>not evaluated</td>"
        return f"<td class='{'pass' if c['pass'] else 'fail'}'>{'PASS' if c['pass'] else 'FAIL'}</td>"
    req = "".join(f"<tr><td><code>{c['id']}</code></td>{_verdict(c)}<td>{escape(c['evidence'])}</td></tr>"
                  for c in checks)

    legend = ("<div class='legend'><span><span class='sw' style='background:var(--series-c)'></span>AERIS active (C)</span>"
              "<span><span class='sw' style='background:var(--series-a)'></span>Baseline autopilot (A)</span>"
              "<span class='muted'>line = 95% confidence interval</span></div>")

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AERIS campaign report</title>
<style>{report_css()}</style></head><body><main>
<h1>AERIS fault campaign</h1>
<p class="lede">Every scenario was flown three times with the same seed: <b>A</b> baseline autopilot only,
<b>B</b> AERIS watching (advisory), <b>C</b> AERIS in control. Detection figures come from B, outcomes compare A with C.
All figures use the held-out evaluation split. Code {escape(meta['code_version'])}, AERIS config {escape(meta['config_hash'])}.
The baseline is a simplified PX4-like stand-in, not PX4 itself.</p>
<div class="tiles">{tiles_html}</div>

<h2>Requirement checks</h2>
<div class="card scroll"><table><tr><th>Requirement</th><th>Result</th><th>Evidence</th></tr>{req}</table></div>

<h2>Mission outcome: baseline against AERIS</h2>
<div class="grid2">
<div class="card"><b>Mission success</b> <span class="muted">(all waypoints within 3 m, landed within 5 m of home)</span>{legend}{chart_success}</div>
<div class="card"><b>Safe landing</b> <span class="muted">(landed gently, no geofence breach, no crash)</span>{legend}{chart_recovered}</div>
</div>
<div class="card scroll" style="margin-top:16px"><table>
<tr><th>Fault</th><th>n</th><th>Mission success A</th><th>Mission success C</th><th>Safe landing A</th><th>Safe landing C</th>
<th>Crash A</th><th>Crash C</th><th>Median landing distance A</th><th>… C</th></tr>{out_rows}</table></div>

<h2>Detection and diagnosis (advisory runs)</h2>
<div class="grid2">
<div class="card"><b>Time to detect</b> <span class="muted">(filled dot = median, open dot = 95th percentile; log scale)</span>{chart_latency}</div>
<div class="card scroll"><table><tr><th>Fault</th><th>n</th><th>Detected</th><th>Median latency</th><th>95th pct</th><th>Correctly diagnosed</th></tr>{det_rows}</table></div>
</div>

<h2>Confusion matrix</h2>
<p class="lede">Rows are the fault really injected, columns what AERIS concluded. A perfect result is a diagonal. "none" means nothing was confirmed.</p>
<div class="card scroll">{confusion}</div>

<h2>Detection against fault severity</h2>
<p class="lede">Small faults hide in sensor noise. A good detector misses only the mildest ones.</p>
<div class="card scroll"><table><tr><th>Fault</th>{sev_head}</tr>{sev_rows}</table></div>

<h2>Diagnosis confidence calibration</h2>
<div class="card scroll"><table><tr><th>Stated confidence</th><th>n</th><th>Mean stated</th><th>Actually correct</th></tr>{calib}</table></div>

<h2>False alarms</h2>
<div class="card">{fa['count']} transitions out of NOMINAL with no active fault, over {fa['clean_flight_hours']} fault-free flight hours:
{fa['per_hour'][0]} per hour (95% CI {fa['per_hour'][1]}–{fa['per_hour'][2]}). Diagnosis precision {_r(summary['diagnosis_precision'])}.</div>
</main></body></html>"""
