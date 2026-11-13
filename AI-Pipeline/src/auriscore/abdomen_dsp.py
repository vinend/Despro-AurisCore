"""Deterministic prototype Abdomen bowel sound burst detector and motility DSP.

Detects exact millisecond onsets, offsets, and acoustic bursts using
Hilbert envelope extraction, adaptive noise-floor thresholding, and morphological merging.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import butter, hilbert, sosfiltfilt


@dataclass(frozen=True)
class AbdomenDSPConfig:
    """Configurable parameters for bowel sound acoustic burst detection."""

    algorithm_version: str = "abdomen-dsp-v1"
    band_low_hz: float = 100.0
    band_high_hz: float = 1000.0
    filter_order: int = 4
    min_duration_s: float = 3.0
    envelope_smoothing_s: float = 0.020  # 20 ms Gaussian envelope smoothing
    threshold_multiplier: float = 3.5    # Threshold = median + multiplier * (1.4826 * MAD)
    min_event_duration_ms: float = 25.0  # Minimum burst duration (ms)
    max_event_duration_s: float = 3.5    # Maximum single burst duration (s)
    merge_gap_ms: float = 60.0           # Merge bursts separated by <= 60 ms


def detect_bowel_bursts(
    audio: np.ndarray,
    sample_rate: int,
    config: AbdomenDSPConfig = AbdomenDSPConfig(),
) -> dict[str, Any]:
    """Detect acoustic bowel bursts with millisecond onset/offset and motility metrics."""
    audio = np.asarray(audio, dtype=np.float64)
    duration_s = len(audio) / sample_rate

    if audio.ndim != 1 or len(audio) == 0 or not np.isfinite(audio).all():
        return {
            "algorithm_version": config.algorithm_version,
            "bowel_events": [],
            "bowel_event_count": 0,
            "bowel_rate_per_minute": None,
            "bowel_rate_variability": None,
            "pattern_categories": [],
        }

    # 1. Bandpass filter in bowel sound dominant band (100 - 1000 Hz)
    sos = butter(
        config.filter_order,
        [config.band_low_hz, config.band_high_hz],
        btype="bandpass",
        fs=sample_rate,
        output="sos",
    )
    filtered = sosfiltfilt(sos, audio)

    # 2. Analytic signal and smoothed Hilbert envelope
    analytic = hilbert(filtered)
    envelope = np.abs(analytic)
    sigma = max(1, int(round(config.envelope_smoothing_s * sample_rate)))
    smoothed = gaussian_filter1d(envelope, sigma=sigma)

    # 3. Robust noise-floor estimation via Median Absolute Deviation (MAD)
    median = float(np.median(smoothed))
    mad = float(np.median(np.abs(smoothed - median)))
    robust_std = mad * 1.4826
    threshold = median + config.threshold_multiplier * max(robust_std, 1e-6)

    # 4. Binary thresholding for burst intervals
    above = smoothed > threshold
    if not np.any(above):
        return {
            "algorithm_version": config.algorithm_version,
            "bowel_events": [],
            "bowel_event_count": 0,
            "bowel_rate_per_minute": 0.0 if duration_s >= 5.0 else None,
            "bowel_rate_variability": None,
            "pattern_categories": ["hypoactive_motility"] if duration_s >= 10.0 else [],
        }

    diff = np.diff(above.astype(int))
    onsets = np.where(diff == 1)[0] + 1
    offsets = np.where(diff == -1)[0] + 1

    if above[0]:
        onsets = np.r_[0, onsets]
    if above[-1]:
        offsets = np.r_[offsets, len(above) - 1]

    # 5. Extract and merge adjacent bursts
    merge_gap_samples = int(round(config.merge_gap_ms * 1e-3 * sample_rate))
    min_dur_samples = int(round(config.min_event_duration_ms * 1e-3 * sample_rate))

    merged_onsets: list[int] = []
    merged_offsets: list[int] = []

    for on, off in zip(onsets, offsets, strict=True):
        if not merged_onsets:
            merged_onsets.append(int(on))
            merged_offsets.append(int(off))
        else:
            prev_off = merged_offsets[-1]
            if on - prev_off <= merge_gap_samples:
                # Merge into previous burst
                merged_offsets[-1] = int(off)
            else:
                merged_onsets.append(int(on))
                merged_offsets.append(int(off))

    events: list[dict[str, Any]] = []
    for on, off in zip(merged_onsets, merged_offsets, strict=True):
        dur_samples = off - on
        if dur_samples >= min_dur_samples:
            peak = float(np.max(smoothed[on : off + 1]))
            start_s = round(float(on) / sample_rate, 3)
            end_s = round(float(off) / sample_rate, 3)
            duration_ms = round((end_s - start_s) * 1000, 1)
            events.append({
                "start_s": start_s,
                "end_s": end_s,
                "duration_ms": duration_ms,
                "peak_envelope": round(peak, 5),
            })

    # 6. Motility metrics calculation
    event_count = len(events)
    rate_per_minute: float | None = None
    rate_variability: float | None = None
    pattern_categories: list[str] = []

    if duration_s >= 5.0:
        rate_per_minute = round(float(event_count) / (duration_s / 60.0), 1)

    if event_count >= 2:
        onset_times = [e["start_s"] for e in events]
        intervals_s = np.diff(onset_times)
        intervals_ms = intervals_s * 1000.0
        rate_variability = round(float(np.std(intervals_ms)), 1)

    # Motility categorization (clinical heuristic: 4-30 bursts/min normal)
    if rate_per_minute is not None:
        if rate_per_minute < 4.0:
            pattern_categories.append("hypoactive_motility")
        elif rate_per_minute > 30.0:
            pattern_categories.append("hyperactive_motility")
        else:
            pattern_categories.append("normal_motility")

    return {
        "algorithm_version": config.algorithm_version,
        "bowel_events": events,
        "bowel_event_count": event_count,
        "bowel_rate_per_minute": rate_per_minute,
        "bowel_rate_variability": rate_variability,
        "pattern_categories": pattern_categories,
    }
