"""Unit tests for CRNN Sound Event Detection (SED) components."""
from __future__ import annotations

import numpy as np

from auriscore.sed_dataset import generate_frame_mask
from auriscore.sed_postprocessing import evaluate_event_sed, extract_events_from_curve


def test_generate_frame_mask() -> None:
    """Verify that timestamp intervals are accurately converted to binary frame mask."""
    time_frames = 100
    hop_s = 0.050  # 50 ms per frame -> 5.0 seconds total
    window_start_s = 0.0
    window_dur_s = 5.0

    # Event 1: from 1.0s to 2.0s (frames 20 to 40)
    # Event 2: from 3.5s to 4.0s (frames 70 to 80)
    events = [
        {"start_sec": 1.0, "end_sec": 2.0, "is_active": True},
        {"start_sec": 3.5, "end_sec": 4.0, "is_active": True},
        {"start_sec": 4.5, "end_sec": 4.8, "is_active": False},  # Non-active ignored
    ]

    mask = generate_frame_mask(window_start_s, window_dur_s, time_frames, hop_s, events)
    assert mask.shape == (time_frames, 1)

    # Frames around 0.5s should be 0.0
    assert mask[10, 0] == 0.0

    # Frames inside 1.0s - 2.0s should be 1.0
    assert mask[25, 0] == 1.0
    assert mask[35, 0] == 1.0

    # Frames inside 2.5s should be 0.0
    assert mask[50, 0] == 0.0

    # Frames inside 3.5s - 4.0s should be 1.0
    assert mask[75, 0] == 1.0

    # Inactive event should be 0.0
    assert mask[92, 0] == 0.0


def test_extract_events_from_curve() -> None:
    """Verify hysteresis thresholding extracts event onset and offset."""
    time_frames = 200
    hop_s = 0.016  # 16 ms per frame
    probs = np.zeros(time_frames, dtype=np.float32)

    # Synthetic probability burst from frame 50 to 80 (approx 0.80s to 1.28s)
    probs[50:81] = 0.85
    # Minor noise spike below threshold (should be ignored)
    probs[120:122] = 0.35

    events = extract_events_from_curve(
        probs,
        hop_s=hop_s,
        window_start_s=0.0,
        onset_threshold=0.50,
        offset_threshold=0.25,
        min_duration_ms=25.0,
    )

    assert len(events) == 1
    ev = events[0]
    expected_start = round(50 * hop_s, 3)
    expected_end = round(80 * hop_s, 3)
    assert abs(ev["start_s"] - expected_start) <= hop_s * 2
    assert abs(ev["end_s"] - expected_end) <= hop_s * 2
    assert ev["confidence"] >= 0.80


def test_evaluate_event_sed_collar() -> None:
    """Verify event-based Precision, Recall, and F1 calculation with collar tolerance."""
    gt_events = [
        {"start_sec": 1.000, "end_sec": 1.300},
        {"start_sec": 3.000, "end_sec": 3.400},
        {"start_sec": 5.000, "end_sec": 5.250},
    ]

    # Pred 1 matches GT 1 (onset error 0.04s < 0.10s collar) -> TP
    # Pred 2 matches GT 2 (onset error 0.05s < 0.10s collar) -> TP
    # Pred 3 is a false alarm at 7.00s -> FP
    # GT 3 (at 5.0s) was missed -> FN
    pred_events = [
        {"start_s": 1.040, "end_s": 1.320},
        {"start_s": 2.950, "end_s": 3.420},
        {"start_s": 7.000, "end_s": 7.200},
    ]

    metrics = evaluate_event_sed(pred_events, gt_events, collar_s=0.100)
    assert metrics["true_positives"] == 2.0
    assert metrics["false_positives"] == 1.0
    assert metrics["false_negatives"] == 1.0

    # Precision = 2 / 3 = 0.6667
    assert abs(metrics["precision"] - (2 / 3)) < 1e-3
    # Recall = 2 / 3 = 0.6667
    assert abs(metrics["recall_sensitivity"] - (2 / 3)) < 1e-3
    # F1 = 0.6667
    assert abs(metrics["event_f1"] - (2 / 3)) < 1e-3
