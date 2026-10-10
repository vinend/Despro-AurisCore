"""Unit tests for Abdomen DSP bowel burst onset-offset detection."""
from __future__ import annotations

import numpy as np

from auriscore.abdomen_dsp import AbdomenDSPConfig, detect_bowel_bursts


def test_detect_bowel_bursts_synthetic() -> None:
    """Verify that known acoustic bursts are detected with millisecond accuracy."""
    sr = 8000
    duration_s = 8.0
    t = np.arange(int(duration_s * sr)) / sr
    audio = 0.002 * np.random.default_rng(42).standard_normal(len(t))

    # Burst 1: 1.50s - 1.70s (200 ms @ 250 Hz)
    b1 = (t >= 1.50) & (t <= 1.70)
    audio[b1] += 0.20 * np.sin(2 * np.pi * 250 * t[b1]) * np.hanning(np.sum(b1))

    # Burst 2: 4.00s - 4.25s (250 ms @ 350 Hz)
    b2 = (t >= 4.00) & (t <= 4.25)
    audio[b2] += 0.25 * np.sin(2 * np.pi * 350 * t[b2]) * np.hanning(np.sum(b2))

    cfg = AbdomenDSPConfig(threshold_multiplier=3.5)
    results = detect_bowel_bursts(audio, sr, cfg)

    events = results["bowel_events"]
    assert len(events) == 2, f"Expected 2 bursts, got {len(events)}"

    e1, e2 = events[0], events[1]
    # Onset within 50 ms tolerance
    assert abs(e1["start_s"] - 1.50) < 0.05
    assert abs(e1["end_s"] - 1.70) < 0.05
    assert 150.0 <= e1["duration_ms"] <= 300.0

    assert abs(e2["start_s"] - 4.00) < 0.05
    assert abs(e2["end_s"] - 4.25) < 0.05
    assert 200.0 <= e2["duration_ms"] <= 350.0
    assert results["bowel_event_count"] == 2
    assert results["bowel_rate_per_minute"] is not None
    assert results["bowel_rate_per_minute"] == round(2.0 / (8.0 / 60.0), 1)
    assert results["bowel_rate_variability"] is not None


def test_detect_bowel_bursts_silent() -> None:
    """Verify that pure silence returns 0 events safely."""
    sr = 8000
    audio = np.zeros(sr * 10, dtype=np.float64)
    results = detect_bowel_bursts(audio, sr)

    assert results["bowel_events"] == []
    assert results["bowel_event_count"] == 0
    assert results["bowel_rate_per_minute"] == 0.0
    assert "hypoactive_motility" in results["pattern_categories"]


def test_detect_bowel_bursts_invalid_audio() -> None:
    """Verify that empty or non-finite audio fails safely without crashing."""
    results = detect_bowel_bursts(np.array([]), 8000)
    assert results["bowel_events"] == []
    assert results["bowel_event_count"] == 0

    results_nan = detect_bowel_bursts(np.array([1.0, np.nan, 2.0]), 8000)
    assert results_nan["bowel_events"] == []
    assert results_nan["bowel_event_count"] == 0


def test_detect_bowel_bursts_merging() -> None:
    """Verify that two bursts closer than merge_gap_ms are merged into one."""
    sr = 8000
    duration_s = 6.0
    t = np.arange(int(duration_s * sr)) / sr
    audio = 0.001 * np.random.default_rng(123).standard_normal(len(t))

    # Two bursts separated by only 30 ms (less than merge_gap_ms = 60 ms)
    # Burst A: 2.00s - 2.10s
    b_a = (t >= 2.00) & (t <= 2.10)
    audio[b_a] += 0.20 * np.sin(2 * np.pi * 300 * t[b_a])
    # Burst B: 2.13s - 2.23s (gap = 30 ms)
    b_b = (t >= 2.13) & (t <= 2.23)
    audio[b_b] += 0.20 * np.sin(2 * np.pi * 300 * t[b_b])

    cfg = AbdomenDSPConfig(merge_gap_ms=60.0, min_event_duration_ms=25.0)
    results = detect_bowel_bursts(audio, sr, cfg)

    assert len(results["bowel_events"]) == 1
    merged = results["bowel_events"][0]
    assert abs(merged["start_s"] - 2.00) < 0.10
    assert abs(merged["end_s"] - 2.23) < 0.10
