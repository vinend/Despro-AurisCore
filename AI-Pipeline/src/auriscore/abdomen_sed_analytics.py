"""Bowel Sound Event Analytics according to PRD Section 8 and INTEGRATION Section 8.

Computes report-aligned metrics from Sound Event Detection (SED) timestamps:
- Bowel Rate (events per minute & motility classification)
- Bowel Rate Variability (inter-event intervals, std, CV, regularity)
- Acoustic Pattern Categorization (Single Burst, Multiple Burst, Prolonged / CRS, Harmonic Sound)
- Safe assistive screening output schemas
"""
from __future__ import annotations

from typing import Any

import numpy as np


def compute_bowel_rate(
    events: list[dict[str, Any]],
    analyzed_duration_s: float,
) -> dict[str, Any]:
    """Calculate Bowel Rate (events/minute) and assistive motility classification."""
    duration = float(analyzed_duration_s)
    if duration <= 0.0:
        return {
            "valid": False,
            "events_count": 0,
            "analyzed_duration_s": 0.0,
            "events_per_minute": 0.0,
            "motility_category": "insufficient_duration",
            "interpretation": "Recording duration is insufficient to assess bowel rate.",
        }

    count = len(events)
    rate = round((count / duration) * 60.0, 1)

    # Clinical motility screening thresholds (assistive finding, not definitive diagnosis)
    # Reference: typical resting adult bowel rate is 5 to 30 events/minute.
    if rate < 4.0:
        category = "hypoactive"
        interp = "Hypoactive bowel sounds (reduced acoustic motility pattern observed)."
    elif rate <= 32.0:
        category = "normoactive"
        interp = "Normoactive bowel sounds (typical acoustic motility rate observed)."
    else:
        category = "hyperactive"
        interp = "Hyperactive bowel sounds (elevated acoustic motility pattern observed)."

    return {
        "valid": True,
        "events_count": count,
        "analyzed_duration_s": round(duration, 2),
        "events_per_minute": rate,
        "motility_category": category,
        "interpretation": interp,
    }


def compute_bowel_rate_variability(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate Inter-Event Interval (IEI) variability and rhythm metrics."""
    if len(events) < 2:
        return {
            "available": False,
            "reason": "At least 2 detected bowel events are required to calculate interval variability.",
            "mean_interval_s": None,
            "std_interval_s": None,
            "cv_interval": None,
            "min_interval_s": None,
            "max_interval_s": None,
            "rhythm_regularity": None,
        }

    # Extract event onsets and calculate consecutive intervals: start[i+1] - start[i]
    onsets = [float(e["start_s"]) for e in events]
    intervals = [round(onsets[i + 1] - onsets[i], 3) for i in range(len(onsets) - 1)]

    mean_val = float(np.mean(intervals))
    std_val = float(np.std(intervals, ddof=1)) if len(intervals) > 1 else 0.0
    cv_val = float(std_val / mean_val) if mean_val > 0.0 else 0.0

    # Physiologically, bowel sounds are inherently stochastic (irregular intervals are typical)
    regularity = "semi_regular" if cv_val < 0.40 else "irregular"

    return {
        "available": True,
        "reason": None,
        "interval_count": len(intervals),
        "mean_interval_s": round(mean_val, 2),
        "std_interval_s": round(std_val, 2),
        "cv_interval": round(cv_val, 2),
        "min_interval_s": round(float(np.min(intervals)), 2),
        "max_interval_s": round(float(np.max(intervals)), 2),
        "rhythm_regularity": regularity,
    }


def categorize_event_pattern(duration_ms: float) -> str:
    """Classify a single burst by duration according to PRD pattern definitions."""
    dur = float(duration_ms)
    if dur <= 200.0:
        return "single_burst"
    elif dur <= 1000.0:
        return "multiple_burst"
    else:
        return "prolonged_sound"


def categorize_bowel_patterns(
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Group detected events into report-defined pattern categories."""
    sb_count = 0
    mb_count = 0
    crs_count = 0
    hs_candidate_count = 0

    annotated_events: list[dict[str, Any]] = []
    for idx, ev in enumerate(events):
        dur = float(ev.get("duration_ms", 0.0))
        pattern = categorize_event_pattern(dur)
        if pattern == "single_burst":
            sb_count += 1
        elif pattern == "multiple_burst":
            mb_count += 1
        else:
            crs_count += 1

        # Check for potential harmonic sound candidates (e.g. prolonged with high confidence)
        is_hs = False
        if dur >= 300.0 and float(ev.get("confidence", 0.0)) >= 0.85:
            hs_candidate_count += 1
            is_hs = True

        annotated_events.append({
            "event_id": f"event_{idx + 1:03d}",
            "start_s": float(ev["start_s"]),
            "end_s": float(ev["end_s"]),
            "duration_ms": dur,
            "confidence": float(ev.get("confidence", 0.0)),
            "pattern": pattern,
            "harmonic_candidate": is_hs,
        })

    total = len(events)
    dist = {
        "single_burst_fraction": round(sb_count / total, 3) if total > 0 else 0.0,
        "multiple_burst_fraction": round(mb_count / total, 3) if total > 0 else 0.0,
        "prolonged_sound_fraction": round(crs_count / total, 3) if total > 0 else 0.0,
    }

    return {
        "total_events": total,
        "single_burst_count": sb_count,
        "multiple_burst_count": mb_count,
        "prolonged_sound_count": crs_count,
        "harmonic_sound_candidate_count": hs_candidate_count,
        "distribution": dist,
        "annotated_events": annotated_events,
    }


def build_unified_abdomen_analysis(
    events: list[dict[str, Any]],
    analyzed_duration_s: float,
    model_version: str = "EXP-A105-abdomen-crnn-specaugment-noise",
    threshold_profile: str = "balanced_screening",
) -> dict[str, Any]:
    """Produce a complete, schema-compliant abdomen-analysis-v1 dictionary."""
    rate_result = compute_bowel_rate(events, analyzed_duration_s)
    variability_result = compute_bowel_rate_variability(events)
    patterns_result = categorize_bowel_patterns(events)

    # Activity approximation (fraction of time with active sound)
    total_active_ms = sum(float(e["duration_ms"]) for e in events)
    active_fraction = min(1.0, round((total_active_ms / 1000.0) / max(0.1, analyzed_duration_s), 4))

    return {
        "schema_version": "abdomen-analysis-v1",
        "mode": "abdomen",
        "quality": {
            "valid": True,
            "reason": None,
        },
        "model_version": model_version,
        "threshold_profile": threshold_profile,
        "activity": {
            "target": "bowel_sound_sed",
            "active_duration_s": round(total_active_ms / 1000.0, 3),
            "analyzed_duration_s": round(analyzed_duration_s, 2),
            "active_fraction": active_fraction,
            "detected_event_count": len(events),
        },
        "bowel_events": patterns_result["annotated_events"],
        "bowel_rate_per_minute": rate_result,
        "bowel_rate_variability": variability_result,
        "pattern_categories": {
            "total_events": patterns_result["total_events"],
            "single_burst_count": patterns_result["single_burst_count"],
            "multiple_burst_count": patterns_result["multiple_burst_count"],
            "prolonged_sound_count": patterns_result["prolonged_sound_count"],
            "harmonic_sound_candidate_count": patterns_result["harmonic_sound_candidate_count"],
            "distribution": patterns_result["distribution"],
        },
        "limitations": [
            "Assistive screening result only; not a definitive clinical diagnosis.",
            "Bowel sound events reflect acoustic motility patterns detected in the 100-1000 Hz frequency band.",
            "Harmonic sound candidates reflect prolonged acoustic resonance and require clinical correlation.",
        ],
    }
