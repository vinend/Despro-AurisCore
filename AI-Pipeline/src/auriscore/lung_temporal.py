"""Versioned frame-grid onset/offset decoding shared by research and inference."""
import numpy as np

LOCALIZATION_VERSION = "lung-frame-events-v2"


def localize_frames(times: np.ndarray, scores: np.ndarray, classes: list[str],
                    thresholds: list[float], *, hop_s: float, duration_s: float,
                    minimum_s: float = 0, merge_gap_s: float = 0) -> list[dict]:
    """Decode frame-center scores into bounded onset/offset candidates.

    Adjacent positive frames merge with floating-point tolerance. Missing timeline
    frames are never bridged, even if gap merging is enabled. Different classes
    may overlap. Scores describe positive contributing frames, not probabilities.
    """
    times, scores, thresholds = np.asarray(times), np.asarray(scores), np.asarray(thresholds)
    if (times.ndim != 1 or scores.shape != (len(times), len(classes))
            or thresholds.shape != (len(classes),) or not classes or len(set(classes)) != len(classes)
            or not np.isfinite(times).all() or not np.isfinite(scores).all() or not np.isfinite(thresholds).all()
            or np.any((scores < 0) | (scores > 1)) or np.any((thresholds < 0) | (thresholds > 1))
            or not np.isfinite([hop_s, duration_s, minimum_s, merge_gap_s]).all()
            or hop_s <= 0 or duration_s <= 0 or min(minimum_s, merge_gap_s) < 0
            or np.any(times < 0) or np.any(times > duration_s) or np.any(np.diff(times) <= 0)):
        raise ValueError("Invalid Lung localization frames")
    epsilon = max(1e-10, hop_s * 1e-7)
    if np.any(np.diff(times) < hop_s - epsilon):
        raise ValueError("Frames must not overlap on the hop grid")
    # Partition at holes in the analyzed timeline, never inferred silence.
    segments = np.split(np.arange(len(times)), np.flatnonzero(np.diff(times) > hop_s + epsilon) + 1)
    events = []
    for column, label in enumerate(classes):
        for segment in segments:
            positive = segment[scores[segment, column] >= thresholds[column]]
            groups = []
            for index in positive:
                start, end = max(0., float(times[index] - hop_s / 2)), min(duration_s, float(times[index] + hop_s / 2))
                if groups and start - groups[-1]["end_s"] <= merge_gap_s + epsilon:
                    groups[-1]["end_s"] = end
                    groups[-1]["indices"].append(index)
                else:
                    groups.append({"start_s": start, "end_s": end, "indices": [index]})
            for group in groups:
                duration = group["end_s"] - group["start_s"]
                if duration > 0 and duration + epsilon >= minimum_s:
                    values = scores[group["indices"], column]
                    events.append({"label": label, "start_s": group["start_s"], "end_s": group["end_s"],
                                   "duration_s": duration, "mean_positive_frame_score": float(values.mean()),
                                   "maximum_frame_score": float(values.max()), "positive_frame_count": len(values),
                                   "threshold": float(thresholds[column])})
    return sorted(events, key=lambda event: (event["start_s"], event["label"]))
