"""Interactive HTML replay of one scenario, flown by the baseline and by AERIS.

Open the file in any browser. Everything is inside the file (no internet needed):
a top-down map with both flight paths, a play button and time slider, AERIS's
health lights, an altitude chart and a timeline that explains every decision.
"""
import json
from html import escape

from .svg import FONT_LINKS, report_css

LABELS = {"A": "Baseline autopilot (A)", "B": "AERIS advisory (B)", "C": "AERIS active (C)"}
COLORS = {"A": "--series-a", "B": "--series-b", "C": "--series-c"}
FAULT_TEXT = {
    "gps_off": "GPS stops sending data", "gps_stuck": "GPS output freezes",
    "gps_drift": "GPS position slowly drifts (spoofing-like)", "baro_stuck": "Barometer output freezes",
    "mag_offset": "Magnetometer heading jumps", "imu_bias": "Accelerometer gains a bias",
    "motor_degradation": "One motor loses thrust", "battery_fault": "Battery loses charge, resistance rises",
}


def verdict(o):
    if o["crashed"]:
        return "Crashed"
    if o["mission_success"]:
        return "Mission complete"
    if o["recovered"]:
        return f"Landed safely, {o['landing_distance_from_home']:.0f} m from home"
    if o["landed"]:
        return f"Landed hard or off-site, {o['landing_distance_from_home']:.0f} m from home"
    return "Did not land"


def describe_fault(truth):
    if not truth:
        return "No fault injected (nominal flight)."
    f = truth[0]
    params = ", ".join(f"{k} = {v}" for k, v in f["params"].items())
    return f"{FAULT_TEXT.get(f['type'], f['type'])} at t = {f['start']:.1f} s" + (f" ({params})." if params else ".")


def build(results):
    """results: list of flight results (dicts from run_flight) for the same scenario."""
    sc = results[0]["manifest"]["scenario"]
    runs = []
    for r in results:
        cfg = r["manifest"]["config_arm"]
        runs.append({
            "cfg": cfg, "label": LABELS[cfg], "color": COLORS[cfg],
            "rows": r["timeseries"]["rows"], "outcome": r["outcome"], "verdict": verdict(r["outcome"]),
            "aeris": r["aeris_events"], "autopilot": r["autopilot_events"], "deferred": r["deferred_failsafes"],
        })
    data = {"runs": runs, "truth": results[0]["truth"], "plan": results[0]["planned_path"],
            "scenario": sc, "geofence": 150.0}
    tiles = "".join(
        f"<div class='card tile'><div class='k'><span class='sw' style='background:var({r['color']})'></span>"
        f"{escape(r['label'])}</div><div class='v'>{escape(r['verdict'])}</div>"
        f"<div class='s'>cross-track error up to {r['outcome']['max_cross_track']:.1f} m · "
        f"{r['outcome']['waypoints_reached_true']}/6 waypoints · flight {r['outcome']['flight_time']:.0f} s</div></div>"
        for r in runs)
    wind = sc.get("wind", {})
    lede = (f"{escape(describe_fault(results[0]['truth']))} Wind {wind.get('mean_mps', 0)} m/s. "
            f"Vision odometry {'fitted' if sc.get('vehicle', {}).get('has_vision', True) else 'not fitted'}. "
            f"Seed {sc['seed']}. The fault is hidden from AERIS; it only sees sensor data.")
    return (_TEMPLATE.replace("__CSS__", report_css()).replace("__FONTS__", FONT_LINKS).replace("__TITLE__", escape(sc["scenario_id"]))
            .replace("__LEDE__", lede).replace("__TILES__", tiles)
            .replace("__DATA__", json.dumps(data).replace("</", "<\\/")))


_TEMPLATE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>AERIS replay: __TITLE__</title>__FONTS__
<style>__CSS__
.layout { display:grid; grid-template-columns: minmax(0, 1.6fr) minmax(260px, 1fr); gap:16px; margin-top:16px; }
@media (max-width: 860px) { .layout { grid-template-columns: 1fr; } }
.controls { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin: 14px 0 0; }
button, select { font:inherit; padding:6px 14px; border-radius:8px; border:1px solid var(--border);
  background:var(--surface); color:var(--ink); cursor:pointer; }
button.primary { background:var(--accent); color:var(--page); font-weight:600;
  border-color:transparent; min-width:84px; }
input[type=range] { flex:1; min-width:200px; accent-color: var(--accent); }
.clock { font-variant-numeric: tabular-nums; min-width: 70px; font-weight:600; }
.chips { display:grid; grid-template-columns: 1fr 1fr; gap:6px; }
.chip { display:flex; align-items:center; gap:8px; padding:6px 8px; border-radius:8px; border:1px solid var(--border); font-size:13px; }
.dot { width:10px; height:10px; border-radius:50%; flex:none; }
.chip .st { margin-left:auto; font-size:11px; color:var(--ink2); font-weight:600; }
.modes div { display:flex; justify-content:space-between; padding:4px 0; border-bottom:1px solid var(--grid); }
#timeline tr.future td { opacity:.35; } #timeline tr.now td { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.src { font-size:11px; font-weight:600; white-space:nowrap; }
details summary { cursor:pointer; color:var(--ink2); font-size:12px; }
ul.ev { margin:4px 0 0 16px; padding:0; font-size:12px; color:var(--ink2); }
</style></head><body><main>
<h1>AERIS flight replay: __TITLE__</h1>
<p class="lede">__LEDE__</p>
<div class="tiles">__TILES__</div>
<div class="controls card">
  <button class="primary" id="play">▶ Play</button>
  <select id="speed" aria-label="Playback speed"><option value="2">2×</option><option value="5" selected>5×</option><option value="10">10×</option><option value="20">20×</option></select>
  <input type="range" id="slider" min="0" max="100" step="0.2" value="0" aria-label="Time">
  <span class="clock" id="clock">t = 0.0 s</span>
</div>
<div class="layout">
  <div class="card"><div class="legend" id="legend"></div><svg id="map" width="100%" role="img" aria-label="Top-down map of both flights"></svg></div>
  <div class="card">
    <b>AERIS health</b> <span class="muted">(active run)</span>
    <div class="chips" id="chips" style="margin:8px 0 14px"></div>
    <b>Flight mode</b><div class="modes" id="modes" style="margin:6px 0 14px"></div>
    <b>Altitude</b><svg id="alt" width="100%" viewBox="0 0 320 150" role="img" aria-label="Altitude over time"></svg>
  </div>
</div>
<h2>What happened, and why</h2>
<p class="lede">Every event from both flights, in time order. Rows ahead of the replay clock are faded. Open a diagnosis to see the evidence behind it.</p>
<div class="card scroll"><table id="timeline"><thead><tr><th>t (s)</th><th>Source</th><th>Event</th></tr></thead><tbody></tbody></table></div>
<h2>Outcome</h2>
<div class="card scroll"><table id="outcome"></table></div>
<p class="muted" style="margin-top:18px">Generated by AERIS. Simulated flight with a simplified PX4-like stand-in autopilot; not a validated model of a real aircraft.</p>
</main>
<script>
const D = __DATA__;
const HC = ["NOMINAL","SUSPECT","DEGRADED","FAILED","UNKNOWN"];
const HCOL = {NOMINAL:"var(--good)",SUSPECT:"var(--warning)",DEGRADED:"var(--serious)",FAILED:"var(--critical)",UNKNOWN:"var(--unknown)"};
const ICON = {NOMINAL:"✓",SUSPECT:"?",DEGRADED:"!",FAILED:"✕",UNKNOWN:"–"};
const NS = "http://www.w3.org/2000/svg";
const el = (tag, attrs, parent) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); if (parent) parent.appendChild(e); return e; };
const tEnd = Math.max(...D.runs.map(r => r.rows[r.rows.length-1][0]));
const slider = document.getElementById("slider"); slider.max = tEnd.toFixed(1);

// ---------- map
const map = document.getElementById("map");
let xs = [0], ys = [0];
D.plan.forEach(p => { xs.push(p[0]); ys.push(p[1]); });
D.runs.forEach(r => r.rows.forEach(row => { xs.push(row[1]); ys.push(row[2]); }));
const pad = 12, minX = Math.min(...xs)-pad, maxX = Math.max(...xs)+pad, minY = Math.min(...ys)-pad, maxY = Math.max(...ys)+pad;
const W = 600, H = Math.max(260, Math.min(620, W * (maxY-minY)/(maxX-minX)));
const sc = Math.min(W/(maxX-minX), H/(maxY-minY));
const X = x => (x-minX)*sc, Y = y => H-(y-minY)*sc;
map.setAttribute("viewBox", `0 0 ${W} ${H}`);
for (let g = Math.ceil(minX/20)*20; g <= maxX; g += 20) el("line",{x1:X(g),x2:X(g),y1:0,y2:H,stroke:"var(--grid)","stroke-width":1},map);
for (let g = Math.ceil(minY/20)*20; g <= maxY; g += 20) el("line",{x1:0,x2:W,y1:Y(g),y2:Y(g),stroke:"var(--grid)","stroke-width":1},map);
el("polyline",{points:D.plan.map(p=>`${X(p[0])},${Y(p[1])}`).join(" "),fill:"none",stroke:"var(--plan)","stroke-width":2,"stroke-dasharray":"6 5"},map);
D.plan.slice(1,-1).forEach((p,i) => { const g = el("g",{},map); el("title",{},g).textContent = `waypoint ${i+1}`;
  el("circle",{cx:X(p[0]),cy:Y(p[1]),r:5,fill:"var(--surface)",stroke:"var(--plan)","stroke-width":2},g);
  const t = el("text",{x:X(p[0])+8,y:Y(p[1])-8,fill:"var(--muted)","font-size":11},g); t.textContent = i+1; });
el("rect",{x:X(0)-7,y:Y(0)-7,width:14,height:14,rx:3,fill:"var(--ink)"},map);
const ht = el("text",{x:X(0),y:Y(0)+4,"text-anchor":"middle",fill:"var(--surface)","font-size":10,"font-weight":700},map); ht.textContent="H";
const runsG = D.runs.map(r => {
  el("polyline",{points:r.rows.map(q=>`${X(q[1])},${Y(q[2])}`).join(" "),fill:"none",stroke:`var(${r.color})`,"stroke-width":1.5,opacity:.18},map);
  const trail = el("polyline",{fill:"none",stroke:`var(${r.color})`,"stroke-width":2.5,"stroke-linejoin":"round"},map);
  const marker = el("circle",{r:7,fill:`var(${r.color})`,stroke:"var(--surface)","stroke-width":2.5},map);
  const tip = el("title",{},marker);
  return {trail, marker, tip};
});
let faultMark = null;
if (D.truth.length) {
  const f = D.truth[0], r0 = D.runs[0], i = Math.min(r0.rows.length-1, Math.round(f.start/0.2));
  faultMark = el("g",{opacity:0},map);
  el("circle",{cx:X(r0.rows[i][1]),cy:Y(r0.rows[i][2]),r:11,fill:"none",stroke:"var(--critical)","stroke-width":2.5},faultMark);
  const t = el("text",{x:X(r0.rows[i][1])+14,y:Y(r0.rows[i][2])-10,fill:"var(--critical)","font-size":12,"font-weight":600,stroke:"var(--surface)","stroke-width":4,"paint-order":"stroke","stroke-linejoin":"round"},faultMark);
  t.textContent = "⚠ fault injected";
}
document.getElementById("legend").innerHTML = D.runs.map(r => `<span><span class="sw" style="background:var(${r.color})"></span>${r.label}</span>`).join("")
  + `<span><span class="sw" style="background:transparent;border:2px dashed var(--plan)"></span>planned route</span><span class="muted">grid = 20 m</span>`;

// ---------- altitude chart
const alt = document.getElementById("alt");
const AX = t => 30 + 280*t/tEnd, AY = z => 130 - 110*Math.min(z,45)/45;
[0,15,30,45].forEach(z => { el("line",{x1:30,x2:310,y1:AY(z),y2:AY(z),stroke:"var(--grid)"},alt);
  const t = el("text",{x:24,y:AY(z)+4,"text-anchor":"end",fill:"var(--muted)","font-size":10},alt); t.textContent = z+" m"; });
D.runs.forEach(r => el("polyline",{points:r.rows.map(q=>`${AX(q[0]).toFixed(1)},${AY(q[3]).toFixed(1)}`).join(" "),fill:"none",stroke:`var(${r.color})`,"stroke-width":2},alt));
if (D.truth.length) el("line",{x1:AX(D.truth[0].start),x2:AX(D.truth[0].start),y1:15,y2:130,stroke:"var(--critical)","stroke-dasharray":"3 3"},alt);
const cursor = el("line",{x1:30,x2:30,y1:15,y2:130,stroke:"var(--ink)","stroke-width":1},alt);
const tl = el("text",{x:310,y:146,"text-anchor":"end",fill:"var(--muted)","font-size":10},alt); tl.textContent = `time (0–${tEnd.toFixed(0)} s)`;

// ---------- timeline
const tbody = document.querySelector("#timeline tbody"); const evRows = [];
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const add = (t, src, color, html) => evRows.push({t, src, color, html});
D.truth.forEach(f => add(f.start, "Ground truth", "--critical", `<b>Fault injected:</b> ${esc(f.type)} ${esc(JSON.stringify(f.params))} <span class="muted">(AERIS is not told)</span>`));
D.runs.forEach(r => {
  r.autopilot.forEach(e => { if (e.t > 0.5) add(e.t, `Autopilot ${r.cfg}`, r.color, esc(e.text)); });
  r.aeris.forEach(e => {
    if (e.text.includes("data arriving")) return;
    let h = esc(e.text);
    if (e.kind === "diagnosis") h = `<b>${h}</b><details><summary>evidence</summary><ul class="ev">${e.data.evidence.map(v =>
      `<li>${esc(v.test_id)}: ${(+v.value).toPrecision(3)} vs ${(+v.threshold).toPrecision(3)} ${v.tripped ? "<b>tripped</b>" : "ok"}</li>`).join("")}</ul></details>`;
    if (e.kind === "action" && e.data.why) h = `<b>${h}</b><div class="muted" style="font-size:12px">${esc(e.data.why)}</div>`;
    add(e.t, `AERIS (${r.cfg})`, r.color, h);
  });
});
evRows.sort((a,b) => a.t - b.t);
evRows.forEach(e => { const tr = document.createElement("tr");
  tr.innerHTML = `<td>${e.t.toFixed(2)}</td><td class="src" style="color:var(${e.color})">${esc(e.src)}</td><td>${e.html}</td>`;
  e.tr = tr; tbody.appendChild(tr); });

// ---------- outcome table
const O = [["Result", r => r.verdict], ["Waypoints reached (within 3 m)", r => `${r.outcome.waypoints_reached_true}/6`],
  ["Max cross-track error", r => `${r.outcome.max_cross_track.toFixed(1)} m`], ["Landing distance from home", r => `${r.outcome.landing_distance_from_home.toFixed(1)} m`],
  ["Touchdown speed", r => `${r.outcome.touchdown_speed.toFixed(2)} m/s`], ["Geofence breach", r => r.outcome.geofence_breach ? "yes" : "no"],
  ["Battery left (true)", r => `${(100*r.outcome.final_soc).toFixed(0)}%`], ["Flight time", r => `${r.outcome.flight_time.toFixed(0)} s`]];
document.getElementById("outcome").innerHTML = `<tr><th></th>${D.runs.map(r=>`<th style="color:var(${r.color})">${r.label}</th>`).join("")}</tr>` +
  O.map(([k,f]) => `<tr><th>${k}</th>${D.runs.map(r=>`<td>${esc(f(r))}</td>`).join("")}</tr>`).join("");

// ---------- update loop
const aerisRun = D.runs.find(r => r.cfg === "C") || D.runs.find(r => r.cfg === "B");
function update(t) {
  document.getElementById("clock").textContent = `t = ${t.toFixed(1)} s`;
  D.runs.forEach((r, k) => {
    const i = Math.max(0, Math.min(r.rows.length-1, Math.round(t/0.2)-1)); const q = r.rows[i];
    runsG[k].trail.setAttribute("points", r.rows.slice(0, i+1).map(p=>`${X(p[1]).toFixed(1)},${Y(p[2]).toFixed(1)}`).join(" "));
    runsG[k].marker.setAttribute("cx", X(q[1])); runsG[k].marker.setAttribute("cy", Y(q[2]));
    runsG[k].tip.textContent = `${r.label}: t=${q[0]}s, altitude ${q[3]} m, mode ${q[7]}`;
  });
  if (faultMark) faultMark.setAttribute("opacity", t >= D.truth[0].start ? 1 : 0);
  cursor.setAttribute("x1", AX(t)); cursor.setAttribute("x2", AX(t));
  document.getElementById("modes").innerHTML = D.runs.map(r => { const q = r.rows[Math.max(0, Math.min(r.rows.length-1, Math.round(t/0.2)-1))];
    return `<div><span style="color:var(${r.color});font-weight:600">${r.cfg}</span><span>${q[7]} · ${q[3].toFixed(1)} m</span></div>`; }).join("");
  if (aerisRun) { const q = aerisRun.rows[Math.max(0, Math.min(aerisRun.rows.length-1, Math.round(t/0.2)-1))];
    document.getElementById("chips").innerHTML = Object.entries(q[8]).map(([c, code]) => { const s = HC[code];
      return `<div class="chip" title="${c}: ${s}"><span class="dot" style="background:${HCOL[s]}"></span>${c}<span class="st">${ICON[s]} ${s}</span></div>`; }).join(""); }
  else document.getElementById("chips").innerHTML = '<span class="muted">AERIS was not running</span>';
  let last = null; evRows.forEach(e => { e.tr.className = e.t > t ? "future" : ""; if (e.t <= t) last = e; });
  if (last) last.tr.className = "now";
}
let playing = false, t = 0, prev = null;
function frame(ts) { if (!playing) return; if (prev !== null) { t += (ts-prev)/1000 * +document.getElementById("speed").value;
  if (t >= tEnd) { t = tEnd; playing = false; document.getElementById("play").textContent = "▶ Play"; } slider.value = t; update(t); }
  prev = ts; if (playing) requestAnimationFrame(frame); }
document.getElementById("play").onclick = () => { playing = !playing; prev = null; if (playing && t >= tEnd) t = 0;
  document.getElementById("play").textContent = playing ? "❚❚ Pause" : "▶ Play"; if (playing) requestAnimationFrame(frame); };
slider.oninput = () => { t = +slider.value; update(t); };
const startAt = (location.hash.match(/t=([\d.]+)/) || [])[1];   // e.g. replay.html#t=60
t = startAt ? Math.min(+startAt, tEnd) : 0; slider.value = t; update(t);
</script></body></html>"""
