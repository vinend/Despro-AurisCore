"""Engineering tests on synthetic audio; no clinical event-validation claim."""
from __future__ import annotations

import json

import numpy as np
import pytest

from auriscore.heart_dsp import (
    HeartDSPConfig, classify_rhythm, estimate_bpm, extra_sound_candidates,
    heart_band_filter, heart_envelope, inspect_heart_signal, interval_records,
)
from auriscore.heart_result import analyze_heart, murmur_branch


def periodic_heart(*, sample_rate: int = 8000, duration_s: float = 12.0,
                   cycle_s: float = .8, systole_s: float = .30) -> np.ndarray:
    """Synthetic narrow acoustic packets resembling periodic event timing."""
    t = np.arange(round(duration_s * sample_rate)) / sample_rate
    signal = np.zeros_like(t)
    for s1 in np.arange(.4, duration_s - .7, cycle_s):
        for center, amplitude in ((s1, 1.0), (s1 + systole_s, .72)):
            signal += amplitude * np.sin(2 * np.pi * 65 * (t - center)) * np.exp(
                -.5 * ((t - center) / .016) ** 2)
    return signal


@pytest.mark.parametrize("audio,sample_rate,reason", [
    (np.array([]), 8000, "empty_signal"),
    (np.ones((8000, 2)), 8000, "mono_waveform_required"),
    (np.array([np.nan] * 8000), 8000, "nonfinite_signal"),
    (np.array([np.inf] * 8000), 8000, "nonfinite_signal"),
    (np.ones(8000), 8000, "signal_too_short"),
    (np.zeros(32000), 8000, "silent_signal"),
    (np.ones(32000), 8000, "silent_signal"),
    (np.ones(32000), 0, "invalid_sample_rate"),
])
def test_invalid_signal_has_no_fabricated_branches(audio, sample_rate, reason):
    result = analyze_heart(audio, sample_rate,
                           murmur={"probability": .9, "threshold": .5,
                                   "model_version": "frozen-test-model"})
    assert result["quality"] == {"valid": False, "score": None, "reason": reason}
    assert result["rhythm"] is None and result["cardiac_events"] is None
    assert result["murmur"] is None
    json.dumps(result, allow_nan=False)


def test_deterministic_zero_phase_bandpass_and_finite_envelope():
    x = periodic_heart()
    first = heart_band_filter(x, 8000)
    np.testing.assert_array_equal(first, heart_band_filter(x, 8000))
    envelope = heart_envelope(first, 8000)
    assert len(envelope) == len(x) and np.isfinite(envelope).all()
    assert envelope.min() >= 0
    with pytest.raises(ValueError, match="signal_too_short"):
        heart_band_filter(x[:100], 8000)


def test_periodic_synthetic_events_bpm_and_intervals():
    result = analyze_heart(periodic_heart(), 8000)
    rhythm, events = result["rhythm"], result["cardiac_events"]
    assert result["quality"]["valid"] is True
    assert events["status"] == "paired_candidates"
    assert len(events["s1_times_s"]) >= 10
    assert len(events["s2_times_s"]) == len(events["s1_times_s"]) - 1
    assert rhythm["heart_rate_bpm"] == pytest.approx(75, abs=1)
    assert rhythm["label"] == "normal" and rhythm["irregular"] is False
    assert events["systolic_interval_ms"] == pytest.approx(300, abs=20)
    assert events["diastolic_interval_ms"] == pytest.approx(500, abs=20)
    assert all(a < b < c for a, b, c in zip(events["s1_times_s"][:-1],
                                              events["s2_times_s"],
                                              events["s1_times_s"][1:], strict=True))
    json.dumps(result, allow_nan=False)


def test_bpm_uses_median_of_known_intervals_and_requires_multiple_cycles():
    bpm, intervals = estimate_bpm(np.array([0, .8, 1.6, 2.4, 3.45]))
    assert bpm == pytest.approx(75)
    assert len(intervals) == 4
    assert estimate_bpm(np.array([0, .8])) == (None, [])
    with pytest.raises(ValueError, match="invalid_s1"):
        estimate_bpm(np.array([1., .5, .9]))


@pytest.mark.parametrize("bpm,label", [(59.9, "bradycardia"), (60, "normal"),
                                       (100, "normal"), (100.1, "tachycardia")])
def test_rate_categories_are_prototype_rules(bpm, label):
    assert classify_rhythm(bpm, [800.] * 9)["label"] == label


def test_irregular_flag_requires_enough_intervals():
    assert classify_rhythm(75, [800, 820] * 5)["irregular"] is True
    assert classify_rhythm(75, [800] * 10)["irregular"] is False
    assert classify_rhythm(75, [800, 820])['irregular'] is None
    assert classify_rhythm(None, [])["label"] == "unknown"
    assert classify_rhythm(float("nan"), [])["heart_rate_bpm"] is None


def test_interval_records_and_reject_impossible_pairing():
    systole, diastole = interval_records(np.array([800, 1600, 2400]),
                                         np.array([1100, 1900]), 1000)
    assert [x["duration_ms"] for x in systole] == [300, 300]
    assert [x["duration_ms"] for x in diastole] == [500, 500]
    with pytest.raises(ValueError, match="invalid_s1_s2"):
        interval_records(np.array([800, 1600]), np.array([1700]), 1000)


def test_experimental_s3_s4_windows():
    envelope = np.zeros(1800)
    for center, height in ((500, 1.0), (1000, 1.0), (1150, .3),
                           (1455, .25), (1500, 1.0)):
        envelope += height * np.exp(-.5 * ((np.arange(1800) - center) / 4) ** 2)
    s3, s4 = extra_sound_candidates(envelope, 1000, np.array([500, 1500]),
                                    np.array([1000]))
    assert s3 == pytest.approx([1.15], abs=.005)
    assert s4 == pytest.approx([1.455], abs=.005)


def test_missing_events_leave_rate_unknown():
    t = np.arange(32000) / 8000
    result = analyze_heart(.2 * np.sin(2 * np.pi * 70 * t), 8000)
    assert result["quality"]["valid"] is True
    assert result["rhythm"]["heart_rate_bpm"] is None
    assert result["rhythm"]["label"] == "unknown"
    assert result["cardiac_events"]["s1_times_s"] == []
    assert result["cardiac_events"]["s2_times_s"] == []
    assert result["cardiac_events"]["systolic_interval_ms"] is None


def test_unified_schema_with_and_without_murmur():
    audio = periodic_heart()
    absent = analyze_heart(audio, 8000)
    assert absent["schema_version"] == "heart-analysis-v1"
    assert absent["murmur"]["status"] == "unavailable"
    present = analyze_heart(audio, 8000, murmur=murmur_branch(.82, .30, "frozen-v1"))
    assert present["murmur"]["status"] == "available"
    assert present["murmur"]["label"] == "present"
    assert present["murmur"]["model_version"] == "frozen-v1"
    assert present["rhythm"]["algorithm_version"] != present["murmur"]["model_version"]
    json.dumps(present, allow_nan=False)


def test_murmur_adapter_rejects_invalid_or_conflicting_values():
    with pytest.raises(ValueError):
        murmur_branch(float("nan"), .5, "v1")
    with pytest.raises(ValueError):
        murmur_branch(.5, .5, "")
    with pytest.raises(ValueError):
        murmur_branch("not-a-score", .5, "v1")
    with pytest.raises(ValueError):
        analyze_heart(periodic_heart(), 8000, murmur={
            "probability": .9, "threshold": .5, "label": "absent",
            "model_version": "v1"})
