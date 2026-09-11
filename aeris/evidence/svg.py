"""Tiny SVG chart helpers for the HTML reports (no plotting library needed).

Colours are CSS variables defined in report_css(), so charts follow light/dark mode.
Series identity is fixed: AERIS (config C) is always --series-c (blue) and the
baseline (config A) is always --series-a (orange). Every mark has a <title>, which
browsers show as a tooltip on hover.
"""
from html import escape

FONT = 'font-family="system-ui, -apple-system, Segoe UI, sans-serif"'


def report_css():
    return """
:root { color-scheme: light;
  --page:#f9f9f7; --surface:#fcfcfb; --ink:#0b0b0b; --ink2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --border:rgba(11,11,11,.10);
  --series-c:#2a78d6; --series-a:#eb6834; --series-b:#1baf7a; --plan:#898781;
  --good:#0ca30c; --warning:#fab219; --serious:#ec835a; --critical:#d03b3b; --unknown:#b5b3ab;
  --seq-0:#f0efec; --seq-1:#cde2fb; --seq-2:#86b6ef; --seq-3:#3987e5; --seq-4:#1c5cab; --seq-5:#0d366b;
  --seq-ink-hi:#ffffff; }
@media (prefers-color-scheme: dark) { :root { color-scheme: dark;
  --page:#0d0d0d; --surface:#1a1a19; --ink:#ffffff; --ink2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --border:rgba(255,255,255,.10);
  --series-c:#3987e5; --series-a:#d95926; --series-b:#199e70; --unknown:#5f5e59;
  --seq-0:#262624; --seq-1:#104281; --seq-2:#1c5cab; --seq-3:#2a78d6; --seq-4:#6da7ec; --seq-5:#cde2fb;
  --seq-ink-hi:#0b0b0b; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--page); color:var(--ink);
  font:14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1180px; margin: 0 auto; padding: 28px 20px 60px; }
h1 { font-size: 24px; margin: 0 0 4px; } h2 { font-size: 17px; margin: 32px 0 10px; }
p.lede { color: var(--ink2); margin: 0 0 18px; max-width: 80ch; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; }
.tile .k { color: var(--ink2); font-size: 12px; } .tile .v { font-size: 22px; font-weight: 600; }
.tile .s { color: var(--muted); font-size: 12px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink2); font-weight: 600; font-size: 12px; }
.scroll { overflow-x: auto; }
.legend { display:flex; gap:16px; flex-wrap:wrap; color:var(--ink2); font-size:12px; margin:6px 0; }
.sw { display:inline-block; width:12px; height:12px; border-radius:3px; vertical-align:-2px; margin-right:6px; }
.pass { color: var(--good); font-weight: 600; } .fail { color: var(--critical); font-weight: 600; }
.muted { color: var(--muted); } code { font-size: 12.5px; white-space: nowrap; }
"""


def _pct(x):
    return "n/a" if x is None else f"{100 * x:.0f}%"


def hbar_rates(categories, series, width=560, row_h=34):
    """Grouped horizontal bars of rates (0..1) with 95% CI whiskers.

    series: list of (label, css_var, {category: (rate, lo, hi, n)})
    """
    left, right, top = 150, 60, 8
    bar_h = (row_h - 10) / len(series)
    h = top + row_h * len(categories) + 26
    plot_w = width - left - right
    x = lambda v: left + plot_w * v
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" {FONT} font-size="12">']
    for g in (0, 0.25, 0.5, 0.75, 1.0):
        out.append(f'<line x1="{x(g):.1f}" x2="{x(g):.1f}" y1="{top}" y2="{h - 22}" stroke="var(--grid)"/>')
        out.append(f'<text x="{x(g):.1f}" y="{h - 8}" text-anchor="middle" fill="var(--muted)">{int(g * 100)}%</text>')
    for i, cat in enumerate(categories):
        y0 = top + i * row_h + 5
        out.append(f'<text x="{left - 8}" y="{y0 + (row_h - 10) / 2 + 4:.1f}" text-anchor="end" '
                   f'fill="var(--ink2)">{escape(cat)}</text>')
        for j, (label, color, data) in enumerate(series):
            if cat not in data or data[cat][0] is None:
                continue
            rate, lo, hi, n = data[cat]
            y = y0 + j * bar_h
            w = max(plot_w * rate, 2)
            tip = f"{label} · {cat}: {_pct(rate)} (95% CI {_pct(lo)}–{_pct(hi)}, n={n})"
            out.append(f'<g><title>{escape(tip)}</title>'
                       f'<rect x="{left}" y="{y:.1f}" width="{w:.1f}" height="{bar_h - 2:.1f}" rx="3" fill="var({color})"/>'
                       f'<line x1="{x(lo):.1f}" x2="{x(hi):.1f}" y1="{y + (bar_h - 2) / 2:.1f}" '
                       f'y2="{y + (bar_h - 2) / 2:.1f}" stroke="var(--ink)" stroke-width="1.2" opacity=".55"/>'
                       f'<text x="{x(max(rate, hi)) + 5:.1f}" y="{y + bar_h / 2 + 2:.1f}" fill="var(--ink2)" '
                       f'font-size="11">{_pct(rate)}</text></g>')
    out.append("</svg>")
    return "".join(out)


def dot_latency(rows, width=560, row_h=26):
    """rows: list of (category, median, lo, hi, p95, n). Log time axis 0.05..60 s."""
    import math
    left, right, top = 150, 30, 8
    h = top + row_h * len(rows) + 28
    plot_w = width - left - right
    lmin, lmax = math.log10(0.05), math.log10(60)
    x = lambda v: left + plot_w * (math.log10(min(max(v, 0.05), 60)) - lmin) / (lmax - lmin)
    out = [f'<svg viewBox="0 0 {width} {h}" width="100%" role="img" {FONT} font-size="12">']
    for g in (0.1, 0.3, 1, 3, 10, 30):
        out.append(f'<line x1="{x(g):.1f}" x2="{x(g):.1f}" y1="{top}" y2="{h - 22}" stroke="var(--grid)"/>')
        out.append(f'<text x="{x(g):.1f}" y="{h - 8}" text-anchor="middle" fill="var(--muted)">{g:g} s</text>')
    for i, (cat, med, lo, hi, p95, n) in enumerate(rows):
        y = top + i * row_h + row_h / 2
        out.append(f'<text x="{left - 8}" y="{y + 4:.1f}" text-anchor="end" fill="var(--ink2)">{escape(cat)}</text>')
        if med is None:
            out.append(f'<text x="{left + 4}" y="{y + 4:.1f}" fill="var(--muted)">no detections</text>')
            continue
        tip = f"{cat}: median {med:.2f} s (95% CI {lo:.2f}–{hi:.2f}), 95th percentile {p95:.2f} s, n={n}"
        out.append(f'<g><title>{escape(tip)}</title>'
                   f'<line x1="{x(med):.1f}" x2="{x(p95):.1f}" y1="{y:.1f}" y2="{y:.1f}" stroke="var(--series-c)" '
                   f'stroke-width="2" opacity=".45"/>'
                   f'<circle cx="{x(p95):.1f}" cy="{y:.1f}" r="4" fill="var(--surface)" stroke="var(--series-c)" stroke-width="2"/>'
                   f'<circle cx="{x(med):.1f}" cy="{y:.1f}" r="5.5" fill="var(--series-c)" stroke="var(--surface)" stroke-width="2"/>'
                   f'<rect x="{x(med) - 14:.1f}" y="{y - 11:.1f}" width="{x(p95) - x(med) + 28:.1f}" height="22" fill="transparent"/></g>')
    out.append("</svg>")
    return "".join(out)


def seq_color(v):
    """Sequential blue ramp for a value 0..1 (heatmap cells)."""
    if v is None:
        return "var(--seq-0)"
    idx = min(5, int(v * 5.999)) if v > 0 else 0
    return f"var(--seq-{idx})"


def seq_ink(v):
    return "var(--seq-ink-hi)" if v is not None and v >= 0.5 else "var(--ink)"
