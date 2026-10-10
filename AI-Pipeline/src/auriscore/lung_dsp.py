"""Respiratory measurements derived only from supported complete phase cycles."""
import numpy as np


def respiratory_measurements(events, duration_s, *, min_cycles=3, edge_margin_s=.04, minimum_phase_s=.1, minimum_cycle_s=.5):
    phases = sorted([e for e in events if e["label"] in {"inhalation", "exhalation"}], key=lambda e: e["start_s"])
    unavailable = {"respiratory_rate_per_minute": None, "inhalation_duration_s": None,
                   "exhalation_duration_s": None, "ie_ratio": None, "complete_cycle_count": 0,
                   "reason": "insufficient_complete_cycles"}
    if any(not 0 <= e["start_s"] < e["end_s"] <= duration_s for e in phases):
        return {**unavailable, "reason": "invalid_phase_bounds"}
    if any(a["end_s"] > b["start_s"] for a, b in zip(phases, phases[1:])):
        return {**unavailable, "reason": "ambiguous_overlapping_phases"}
    if any(e["end_s"] - e["start_s"] < minimum_phase_s for e in phases):
        return {**unavailable, "reason": "phase_too_short"}
    cycles = []
    for a, b, c in zip(phases, phases[1:], phases[2:]):
        if (a["label"] == c["label"] == "inhalation" and b["label"] == "exhalation"
                and a["start_s"] > edge_margin_s and c["end_s"] < duration_s - edge_margin_s):
            cycles.append((a, b, c["start_s"] - a["start_s"]))
    if len(cycles) < min_cycles:
        return {**unavailable, "complete_cycle_count": len(cycles)}
    if any(c < minimum_cycle_s for _, _, c in cycles):
        return {**unavailable, "reason": "cycle_too_short"}
    inhale = float(np.median([a["end_s"] - a["start_s"] for a, _, _ in cycles]))
    exhale = float(np.median([b["end_s"] - b["start_s"] for _, b, _ in cycles]))
    return {"respiratory_rate_per_minute": float(60 / np.median([c for _, _, c in cycles])),
            "inhalation_duration_s": inhale, "exhalation_duration_s": exhale,
            "ie_ratio": inhale / exhale, "complete_cycle_count": len(cycles), "reason": None}
