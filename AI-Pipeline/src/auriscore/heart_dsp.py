"""Deterministic prototype Heart event and rhythm DSP.

These acoustic candidates and rate rules are engineering outputs, not clinical
diagnoses. No Murmur CNN preprocessing or model code is used here.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.ndimage import gaussian_filter1d
from scipy.signal import butter, find_peaks, hilbert, sosfiltfilt


@dataclass(frozen=True)
class HeartDSPConfig:
    """Versioned prototype thresholds; report-derived values remain configurable."""

    algorithm_version: str = "heart-dsp-prototype-0.1.0"
    band_low_hz: float = 20.0
    band_high_hz: float = 150.0
    filter_order: int = 4
    min_duration_s: float = 3.0
    min_rms: float = 1e-6
    envelope_smoothing_s: float = 0.012
    main_peak_distance_s: float = 0.12
    main_peak_height: float = 0.28
    main_peak_prominence: float = 0.18
    min_systole_s: float = 0.14
    max_systole_s: float = 0.45
    min_diastole_s: float = 0.18
    max_diastole_s: float = 1.2
    min_cycle_s: float = 0.35
    max_cycle_s: float = 1.5
    min_s1_intervals: int = 2
    irregularity_min_intervals: int = 9
    irregularity_std_ms: float = 5.0
    s3_window_s: tuple[float, float] = (0.10, 0.20)
    s4_window_s: tuple[float, float] = (0.03, 0.06)
    extra_peak_prominence: float = 0.06
    extra_peak_relative_max: float = 0.55


def inspect_heart_signal(audio: np.ndarray, sample_rate: int,
                         config: HeartDSPConfig = HeartDSPConfig()) -> dict[str, object]:
    """Return an explicit engineering validity state before any filtering."""
    result: dict[str, object] = {"valid": False, "score": None, "reason": None}
    if not isinstance(sample_rate, (int, np.integer)) or isinstance(sample_rate, (bool, np.bool_)) or sample_rate <= 2 * config.band_high_hz:
        result["reason"] = "invalid_sample_rate"
        return result
    try:
        x = np.asarray(audio, dtype=np.float64)
    except (TypeError, ValueError):
        result["reason"] = "invalid_samples"
        return result
    if x.ndim != 1:
        result["reason"] = "mono_waveform_required"
    elif x.size == 0:
        result["reason"] = "empty_signal"
    elif not np.isfinite(x).all():
        result["reason"] = "nonfinite_signal"
    elif x.size / sample_rate < config.min_duration_s:
        result["reason"] = "signal_too_short"
    elif float(np.sqrt(np.mean(np.square(x - x.mean())))) < config.min_rms:
        result["reason"] = "silent_signal"
    else:
        result["valid"] = True
    return result


def heart_band_filter(audio: np.ndarray, sample_rate: int,
                      config: HeartDSPConfig = HeartDSPConfig()) -> np.ndarray:
    """Remove DC and apply a sample-rate-aware zero-phase 20–150 Hz SOS filter."""
    quality = inspect_heart_signal(audio, sample_rate, config)
    if not quality["valid"]:
        raise ValueError(str(quality["reason"]))
    if not (0 < config.band_low_hz < config.band_high_hz < sample_rate / 2):
        raise ValueError("invalid_heart_band")
    sos = butter(config.filter_order, [config.band_low_hz, config.band_high_hz],
                 btype="bandpass", fs=sample_rate, output="sos")
    x = np.asarray(audio, dtype=np.float64)
    filtered = sosfiltfilt(sos, x - x.mean())
    if not np.isfinite(filtered).all():
        raise ValueError("nonfinite_filtered_signal")
    return filtered


def heart_envelope(filtered: np.ndarray, sample_rate: int,
                   config: HeartDSPConfig = HeartDSPConfig()) -> np.ndarray:
    """Hilbert magnitude, zero-phase Gaussian smoothing, safe normalization."""
    x = np.asarray(filtered, dtype=np.float64)
    if x.ndim != 1 or x.size == 0 or not np.isfinite(x).all():
        raise ValueError("invalid_filtered_signal")
    sigma = max(1.0, config.envelope_smoothing_s * sample_rate)
    envelope = gaussian_filter1d(np.abs(hilbert(x)), sigma=sigma, mode="nearest")
    scale = float(np.quantile(envelope, 0.95))
    if scale <= 1e-12:
        return np.zeros_like(envelope)
    return envelope / scale


def main_event_candidates(envelope: np.ndarray, sample_rate: int,
                          config: HeartDSPConfig = HeartDSPConfig()) -> np.ndarray:
    """Find prominent S1/S2-sized peaks without asserting their identities."""
    if envelope.ndim != 1 or not np.isfinite(envelope).all():
        raise ValueError("invalid_envelope")
    peaks, _ = find_peaks(envelope,
                          distance=max(1, round(config.main_peak_distance_s * sample_rate)),
                          height=config.main_peak_height,
                          prominence=config.main_peak_prominence)
    return peaks.astype(np.int64)


def pair_s1_s2(peaks: np.ndarray, envelope: np.ndarray, sample_rate: int,
               config: HeartDSPConfig = HeartDSPConfig()) -> tuple[np.ndarray, np.ndarray]:
    """Pair prominent peaks using a shorter S1→S2 than S2→next-S1 pattern.

    Equal or unsupported timing is deliberately left unlabelled. This is a
    prototype acoustic pairing rule and is not validated segmentation.
    """
    candidates = np.asarray(peaks, dtype=np.int64)
    if candidates.size < 5 or np.any(np.diff(candidates) <= 0):
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    best: tuple[np.ndarray, np.ndarray] | None = None
    best_score: tuple[float, ...] | None = None
    for start in range(min(4, len(candidates))):
        s1 = [int(candidates[start])]
        s2: list[int] = []
        current = start
        while current < len(candidates) - 2:
            first = int(candidates[current])
            possible_s2 = [j for j in range(current + 1, len(candidates))
                           if config.min_systole_s <= (candidates[j] - first) / sample_rate <= config.max_systole_s]
            if not possible_s2:
                break
            choices: list[tuple[float, int, int]] = []
            for j in possible_s2:
                for k in range(j + 1, len(candidates)):
                    systole = (candidates[j] - first) / sample_rate
                    diastole = (candidates[k] - candidates[j]) / sample_rate
                    cycle = (candidates[k] - first) / sample_rate
                    if cycle > config.max_cycle_s:
                        break
                    if (config.min_diastole_s <= diastole <= config.max_diastole_s
                            and config.min_cycle_s <= cycle <= config.max_cycle_s
                            and systole < diastole):
                        # Prefer the next supported event; strength resolves close ties.
                        choices.append((cycle - 0.02 * float(envelope[candidates[k]]), j, k))
            if not choices:
                break
            _, j, k = min(choices)
            s2.append(int(candidates[j]))
            s1.append(int(candidates[k]))
            current = k
        if len(s1) < config.min_s1_intervals + 1 or len(s2) < config.min_s1_intervals:
            continue
        systoles = (np.asarray(s2) - np.asarray(s1[:-1])) / sample_rate
        diastoles = (np.asarray(s1[1:]) - np.asarray(s2)) / sample_rate
        if np.median(systoles) >= np.median(diastoles):
            continue
        cycles = np.diff(s1) / sample_rate
        score = (float(len(s2)), -float(np.std(cycles)),
                 float(np.mean(envelope[np.asarray(s1)])))
        if best_score is None or score > best_score:
            best, best_score = (np.asarray(s1), np.asarray(s2)), score
    if best is None:
        return np.array([], dtype=np.int64), np.array([], dtype=np.int64)
    return best


def estimate_bpm(s1_times_s: np.ndarray, config: HeartDSPConfig = HeartDSPConfig()
                 ) -> tuple[float | None, list[float]]:
    """Use median plausible successive S1 intervals; require multiple cycles."""
    times = np.asarray(s1_times_s, dtype=np.float64)
    if times.ndim != 1 or not np.isfinite(times).all() or np.any(np.diff(times) <= 0):
        raise ValueError("invalid_s1_timestamps")
    intervals = np.diff(times)
    plausible = intervals[(intervals >= config.min_cycle_s) & (intervals <= config.max_cycle_s)]
    if len(plausible) < config.min_s1_intervals:
        return None, []
    bpm = 60.0 / float(np.median(plausible))
    return bpm, (plausible * 1000).astype(float).tolist()


def classify_rhythm(bpm: float | None, beat_intervals_ms: list[float],
                    config: HeartDSPConfig = HeartDSPConfig()) -> dict[str, object]:
    """Separate prototype rate category from the insufficient-data irregularity flag."""
    if bpm is None or not np.isfinite(bpm):
        bpm = None
        label = "unknown"
    elif bpm < 60:
        label = "bradycardia"
    elif bpm > 100:
        label = "tachycardia"
    else:
        label = "normal"
    intervals = np.asarray(beat_intervals_ms, dtype=np.float64)
    if intervals.size and not np.isfinite(intervals).all():
        raise ValueError("invalid_beat_intervals")
    std_ms = float(np.std(intervals, ddof=0)) if len(intervals) >= 2 else None
    irregular = (std_ms > config.irregularity_std_ms
                 if std_ms is not None and len(intervals) >= config.irregularity_min_intervals else None)
    return {"algorithm_version": config.algorithm_version,
            "heart_rate_bpm": round(bpm, 3) if bpm is not None else None,
            "label": label, "irregular": irregular,
            "interval_std_ms": round(std_ms, 3) if std_ms is not None else None,
            "beat_intervals_ms": [round(float(v), 3) for v in intervals],
            "usable_intervals": len(intervals)}


def interval_records(s1_samples: np.ndarray, s2_samples: np.ndarray, sample_rate: int
                     ) -> tuple[list[dict[str, float]], list[dict[str, float]]]:
    """Serialize ordered systoles and following diastoles without overlap."""
    s1, s2 = np.asarray(s1_samples), np.asarray(s2_samples)
    if len(s2) != len(s1) - 1 or np.any(~((s1[:-1] < s2) & (s2 < s1[1:]))):
        raise ValueError("invalid_s1_s2_pairing")

    def record(start: int, end: int) -> dict[str, float]:
        return {"start_s": round(float(start / sample_rate), 6),
                "end_s": round(float(end / sample_rate), 6),
                "duration_ms": round(float((end - start) * 1000 / sample_rate), 3)}

    return ([record(int(a), int(b)) for a, b in zip(s1[:-1], s2, strict=True)],
            [record(int(a), int(b)) for a, b in zip(s2, s1[1:], strict=True)])


def extra_sound_candidates(envelope: np.ndarray, sample_rate: int,
                           s1_samples: np.ndarray, s2_samples: np.ndarray,
                           config: HeartDSPConfig = HeartDSPConfig()) -> tuple[list[float], list[float]]:
    """Experimental low-amplitude peaks in report-derived S3/S4 windows."""
    if len(s2_samples) != len(s1_samples) - 1:
        return [], []
    peaks, _ = find_peaks(envelope, prominence=config.extra_peak_prominence,
                          distance=max(1, round(.025 * sample_rate)))
    s3, s4 = [], []
    for s2, next_s1 in zip(s2_samples, s1_samples[1:], strict=True):
        limit = config.extra_peak_relative_max * min(envelope[s2], envelope[next_s1])
        for target, low, high, anchor, sign in (
            (s3, *config.s3_window_s, s2, 1),
            (s4, *config.s4_window_s, next_s1, -1),
        ):
            possible = [p for p in peaks if low <= sign * (p - anchor) / sample_rate <= high
                        and envelope[p] <= limit and envelope[p] >= config.extra_peak_prominence]
            if possible:
                chosen = max(possible, key=lambda p: float(envelope[p]))
                target.append(round(float(chosen / sample_rate), 6))
    return sorted(set(s3)), sorted(set(s4))


def analyze_cardiac_dsp(audio: np.ndarray, sample_rate: int,
                        config: HeartDSPConfig = HeartDSPConfig()) -> tuple[dict[str, object], dict[str, object]]:
    """Produce event candidates and rate/rhythm from a valid mono waveform."""
    filtered = heart_band_filter(audio, sample_rate, config)
    envelope = heart_envelope(filtered, sample_rate, config)
    candidates = main_event_candidates(envelope, sample_rate, config)
    s1, s2 = pair_s1_s2(candidates, envelope, sample_rate, config)
    bpm, intervals = estimate_bpm(s1 / sample_rate, config)
    rhythm = classify_rhythm(bpm, intervals, config)
    if len(s2):
        systole, diastole = interval_records(s1, s2, sample_rate)
        s3, s4 = extra_sound_candidates(envelope, sample_rate, s1, s2, config)
    else:
        systole, diastole, s3, s4 = [], [], [], []
    events: dict[str, object] = {
        "algorithm_version": config.algorithm_version,
        "status": "paired_candidates" if len(s2) else "insufficient_evidence",
        "candidate_times_s": [round(float(v / sample_rate), 6) for v in candidates],
        "s1_times_s": [round(float(v / sample_rate), 6) for v in s1],
        "s2_times_s": [round(float(v / sample_rate), 6) for v in s2],
        "s3_candidates_s": s3, "s4_candidates_s": s4,
        "systolic_intervals": systole, "diastolic_intervals": diastole,
        "systolic_interval_ms": round(float(np.median([r["duration_ms"] for r in systole])), 3) if systole else None,
        "diastolic_interval_ms": round(float(np.median([r["duration_ms"] for r in diastole])), 3) if diastole else None,
    }
    return rhythm, events
