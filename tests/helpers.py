"""Shared helpers for tests: build scenarios and cache flights (each takes ~1.5 s)."""
import functools
import json

from aeris.flight import run_flight

WIND = {"mean_mps": 4.0, "dir_deg": 200}


def scenario(fault_type=None, params=None, start=40.0, seed=7, vision=True, wind=WIND):
    sc = {"scenario_id": f"test_{fault_type or 'nominal'}", "seed": seed,
          "vehicle": {"has_vision": vision}, "wind": dict(wind), "faults": []}
    if fault_type:
        sc["faults"] = [{"type": fault_type, "start": start, "params": params or {}}]
    return sc


@functools.lru_cache(maxsize=64)
def _fly_cached(key, config):
    return run_flight(json.loads(key), config)


def fly(sc, config="C"):
    """Cached flight: the same scenario and config is only simulated once per test session."""
    return _fly_cached(json.dumps(sc, sort_keys=True), config)


def events(result, kind=None, text=None, component=None):
    out = result["aeris_events"]
    if kind:
        out = [e for e in out if e["kind"] == kind]
    if text:
        out = [e for e in out if text in e["text"]]
    if component:
        out = [e for e in out if e["component"] == component]
    return out
