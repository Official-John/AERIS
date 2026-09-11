"""Command line interface. Run `python -m aeris --help` to see every command.

  python -m aeris demo                      fly the flagship GPS-drift scenario (A vs C), write a replay
  python -m aeris fly scenarios/X.json      fly any scenario file
  python -m aeris campaign --per-fault 20   randomized fault campaign with metrics and a report
  python -m aeris check results/campaign    re-check requirements on a finished campaign
  python -m aeris trace --check             requirement -> test trace matrix
"""
import argparse
import json
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _fly(scenario_path, configs, out_root, open_browser):
    from .campaign.scenarios import load
    from .evidence.flight_report import build, verdict
    from .flight import run_flight

    sc = load(scenario_path)
    print(f"Scenario {sc['scenario_id']} (seed {sc['seed']})")
    results = []
    for cfg in configs:
        r = run_flight(sc, cfg)
        results.append(r)
        o = r["outcome"]
        print(f"  config {cfg}: {verdict(o)}  (waypoints {o['waypoints_reached_true']}/6, "
              f"max cross-track {o['max_cross_track']:.1f} m, landing {o['landing_distance_from_home']:.1f} m from home)")
        for e in r["aeris_events"]:
            if e["kind"] in ("diagnosis", "action"):
                print(f"      t={e['t']:7.2f}  AERIS {e['text']}")
    out = Path(out_root) / sc["scenario_id"]
    out.mkdir(parents=True, exist_ok=True)
    for r in results:
        (out / f"result_{r['manifest']['config_arm']}.json").write_text(json.dumps(r, indent=1), encoding="utf-8")
    html = out / "replay.html"
    html.write_text(build(results), encoding="utf-8")
    print(f"\nReplay written to {html}")
    if open_browser:
        webbrowser.open(html.resolve().as_uri())
    return results


def cmd_demo(a):
    _fly(ROOT / "scenarios" / "flagship_gps_drift.json", ["A", "C"], a.out, not a.no_open)


def cmd_fly(a):
    _fly(a.scenario, a.configs.split(","), a.out, a.open)


def cmd_campaign(a):
    from .campaign.requirements_check import check
    from .campaign.runner import run_campaign
    from .campaign.scenarios import generate
    from .evidence.campaign_report import build
    from .evidence.metrics import summarize

    per = 3 if a.quick else a.per_fault
    families = a.families.split(",") if a.families else None
    scenarios = generate(per, base_seed=a.seed, families=families)
    configs = a.configs.split(",")
    print(f"Campaign: {len(scenarios)} scenarios x {len(configs)} configs = {len(scenarios) * len(configs)} flights")
    records, wall = run_campaign(scenarios, configs, a.workers, a.out)
    split = None if a.quick else "evaluation"
    summary = summarize(records, split=split)
    checks = check([dict(r, split="evaluation") for r in records] if a.quick else records, summary)
    meta = {"flights": len(records), "scenarios": len(scenarios), "configs": configs, "wall_s": wall,
            "workers": a.workers or "auto", "code_version": records[0]["code_version"],
            "config_hash": records[0]["config_hash"]}
    out = Path(a.out)
    (out / "summary.json").write_text(json.dumps({"meta": meta, "summary": summary, "checks": checks}, indent=1),
                                      encoding="utf-8")
    (out / "report.html").write_text(build(summary, checks, meta), encoding="utf-8")
    print(f"\nDone in {wall / 60:.1f} min. Report: {out / 'report.html'}")
    _print_checks(checks)
    if a.open:
        webbrowser.open((out / "report.html").resolve().as_uri())


def _print_checks(checks):
    print("\nRequirement checks:")
    for c in checks:
        tag = "n/a " if c["pass"] is None else ("PASS" if c["pass"] else "FAIL")
        print(f"  {tag}  {c['id']}: {c['evidence']}")


def cmd_check(a):
    data = json.loads((Path(a.campaign_dir) / "summary.json").read_text(encoding="utf-8"))
    _print_checks(data["checks"])
    sys.exit(1 if any(c["pass"] is False for c in data["checks"]) else 0)


def cmd_report(a):
    """Rebuild report.html from a finished campaign's summary.json (no flights)."""
    from .evidence.campaign_report import build
    out = Path(a.campaign_dir)
    data = json.loads((out / "summary.json").read_text(encoding="utf-8"))
    (out / "report.html").write_text(build(data["summary"], data["checks"], data["meta"]), encoding="utf-8")
    print(f"Rebuilt {out / 'report.html'}")


def cmd_replay(a):
    """Rebuild replay.html from saved result_*.json files (no flights)."""
    from .evidence.flight_report import build
    folder = Path(a.folder)
    results = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(folder.glob("result_*.json"))]
    (folder / "replay.html").write_text(build(results), encoding="utf-8")
    print(f"Rebuilt {folder / 'replay.html'}")


def cmd_trace(a):
    from .trace import build_trace
    ok, md = build_trace(ROOT)
    path = ROOT / "docs" / "trace_matrix.md"
    path.write_text(md, encoding="utf-8")
    print(f"Trace matrix written to {path}")
    if a.check and not ok:
        print("FAIL: some requirements have no verifying test (see the matrix).")
        sys.exit(1)


def main(argv=None):
    p = argparse.ArgumentParser(prog="python -m aeris", description="AERIS: self-diagnosing aircraft digital twin")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", help="fly the flagship GPS-drift scenario and open the replay")
    d.add_argument("--out", default="results/demo")
    d.add_argument("--no-open", action="store_true", help="don't open the browser")
    d.set_defaults(func=cmd_demo)

    f = sub.add_parser("fly", help="fly one scenario file")
    f.add_argument("scenario")
    f.add_argument("--configs", default="A,C", help="comma list of A (baseline), B (advisory), C (active)")
    f.add_argument("--out", default="results/flights")
    f.add_argument("--open", action="store_true")
    f.set_defaults(func=cmd_fly)

    c = sub.add_parser("campaign", help="randomized fault campaign")
    c.add_argument("--per-fault", type=int, default=20, help="scenarios per fault type (9 types incl. none)")
    c.add_argument("--configs", default="A,B,C")
    c.add_argument("--workers", type=int, default=None)
    c.add_argument("--seed", type=int, default=1000, help="base seed; use a new one for a fresh evaluation set")
    c.add_argument("--families", default=None,
                   help="comma list of fault types to include (default: all). 'none' alone = fault-free soak test")
    c.add_argument("--out", default="results/campaign")
    c.add_argument("--quick", action="store_true", help="3 scenarios per fault, no split (smoke test)")
    c.add_argument("--open", action="store_true")
    c.set_defaults(func=cmd_campaign)

    k = sub.add_parser("check", help="print requirement checks of a finished campaign")
    k.add_argument("campaign_dir")
    k.set_defaults(func=cmd_check)

    r = sub.add_parser("report", help="rebuild a campaign report.html from its summary.json")
    r.add_argument("campaign_dir")
    r.set_defaults(func=cmd_report)

    rp = sub.add_parser("replay", help="rebuild replay.html from saved result_*.json files")
    rp.add_argument("folder")
    rp.set_defaults(func=cmd_replay)

    t = sub.add_parser("trace", help="write docs/trace_matrix.md")
    t.add_argument("--check", action="store_true", help="exit 1 if a requirement has no verifying test")
    t.set_defaults(func=cmd_trace)

    a = p.parse_args(argv)
    a.func(a)


if __name__ == "__main__":
    main()
