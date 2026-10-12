"""Post-processing and event boundary extraction for Sound Event Detection."""
from __future__ import annotations

from typing import Any

import numpy as np
from scipy.ndimage import median_filter


def extract_events_from_curve(
    probabilities: np.ndarray,
    hop_s: float = 0.016,
    window_start_s: float = 0.0,
    onset_threshold: float = 0.50,
    offset_threshold: float = 0.25,
    min_duration_ms: float = 25.0,
    merge_gap_ms: float = 60.0,
) -> list[dict[str, Any]]:
    """Convert frame probability curve P(t) into discrete events using hysteresis thresholding."""
    probs = np.asarray(probabilities, dtype=np.float32).reshape(-1)
    if len(probs) == 0:
        return []

    # 1. Median filter (kernel size 3) to smooth one-frame spikes
    smoothed = median_filter(probs, size=3)

    # 2. Hysteresis dual-threshold tracking
    events_raw: list[tuple[int, int]] = []
    in_event = False
    event_start_idx = 0

    for i, p in enumerate(smoothed):
        if not in_event:
            if p >= onset_threshold:
                in_event = True
                event_start_idx = i
        else:
            if p < offset_threshold:
                in_event = False
                events_raw.append((event_start_idx, i))

    if in_event:
        events_raw.append((event_start_idx, len(smoothed) - 1))

    if not events_raw:
        return []

    # 3. Morphological merging of adjacent events
    merge_frames = int(round((merge_gap_ms * 1e-3) / hop_s))
    min_frames = int(round((min_duration_ms * 1e-3) / hop_s))

    merged_ranges: list[tuple[int, int]] = []
    for on_idx, off_idx in events_raw:
        if not merged_ranges:
            merged_ranges.append((on_idx, off_idx))
        else:
            prev_on, prev_off = merged_ranges[-1]
            if on_idx - prev_off <= merge_frames:
                merged_ranges[-1] = (prev_on, off_idx)
            else:
                merged_ranges.append((on_idx, off_idx))

    # 4. Filter by minimum duration and convert to seconds
    events: list[dict[str, Any]] = []
    for on_idx, off_idx in merged_ranges:
        if off_idx - on_idx >= min_frames:
            start_s = round(window_start_s + on_idx * hop_s, 3)
            end_s = round(window_start_s + off_idx * hop_s, 3)
            duration_ms = round((end_s - start_s) * 1000.0, 1)
            mean_conf = float(np.mean(smoothed[on_idx : off_idx + 1]))
            peak_conf = float(np.max(smoothed[on_idx : off_idx + 1]))

            events.append({
                "start_s": start_s,
                "end_s": end_s,
                "duration_ms": duration_ms,
                "confidence": round(mean_conf, 4),
                "peak_confidence": round(peak_conf, 4),
            })

    return events


def evaluate_event_sed(
    predicted_events: list[dict[str, Any]],
    ground_truth_events: list[dict[str, Any]],
    collar_s: float = 0.100,
) -> dict[str, float]:
    """Calculate event-based Precision, Recall, and F1-score with collar tolerance."""
    gt_matched = [False] * len(ground_truth_events)
    tp = 0
    fp = 0

    for pred in predicted_events:
        matched = False
        for idx, gt in enumerate(ground_truth_events):
            if not gt_matched[idx]:
                # Onset within collar tolerance
                onset_ok = abs(pred["start_s"] - gt["start_sec"]) <= collar_s
                # Offset within tolerance (max collar or 20% duration)
                offset_tol = max(collar_s, 0.20 * (gt["end_sec"] - gt["start_sec"]))
                offset_ok = abs(pred["end_s"] - gt["end_sec"]) <= offset_tol
                if onset_ok:
                    matched = True
                    gt_matched[idx] = True
                    tp += 1
                    break
        if not matched:
            fp += 1

    fn = len(ground_truth_events) - sum(gt_matched)

    precision = tp / (tp + fp) if tp + fp > 0 else 0.0
    recall = tp / (tp + fn) if tp + fn > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall > 0 else 0.0

    return {
        "true_positives": float(tp),
        "false_positives": float(fp),
        "false_negatives": float(fn),
        "precision": round(precision, 4),
        "recall_sensitivity": round(recall, 4),
        "event_f1": round(f1, 4),
    }
