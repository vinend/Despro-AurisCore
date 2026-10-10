"""Lung frame metrics, development-only thresholds and one-to-one event matching."""
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.metrics import average_precision_score, roc_auc_score


def frame_metrics(truth, scores, mask, thresholds):
    truth, scores, mask = np.asarray(truth), np.asarray(scores), np.asarray(mask)
    if truth.shape != scores.shape or mask.shape != truth.shape or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1)):
        raise ValueError("Invalid Lung predictions")
    result = []
    for i, threshold in enumerate(thresholds):
        y, p = truth[..., i][mask[..., i] > 0].astype(bool), scores[..., i][mask[..., i] > 0]
        positive = p >= threshold
        tp, fp = int(np.sum(y & positive)), int(np.sum(~y & positive))
        fn, tn = int(np.sum(y & ~positive)), int(np.sum(~y & ~positive))
        divide = lambda a, b: a / b if b else None
        result.append({"tn": tn, "fp": fp, "fn": fn, "tp": tp,
                       "sensitivity": divide(tp, tp + fn), "specificity": divide(tn, tn + fp),
                       "precision": divide(tp, tp + fp), "f1": divide(2 * tp, 2 * tp + fp + fn),
                       "roc_auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
                       "pr_auc": float(average_precision_score(y, p)) if np.any(y) else None})
    return result


def select_thresholds(truth, scores, mask):
    """Select deterministic maximum-F1 thresholds on development predictions only."""
    thresholds = []
    for i in range(truth.shape[-1]):
        support = truth[..., i][mask[..., i] > 0]
        if len(np.unique(support)) != 2:
            raise ValueError("Threshold selection requires both labels per class")
        candidates = np.linspace(.05, .95, 37)
        values = [frame_metrics(truth[..., i:i+1], scores[..., i:i+1], mask[..., i:i+1], [t])[0]["f1"] for t in candidates]
        thresholds.append(float(candidates[int(np.argmax(values))]))
    return thresholds


def extract_events(times, scores, classes, thresholds, *, hop_s, minimum_s=.0, merge_gap_s=.0, duration_s=None):
    """Convert thresholded frames into bounded intervals; one event per contiguous run."""
    times, scores = np.asarray(times), np.asarray(scores)
    if scores.shape != (len(times), len(classes)) or len(thresholds) != len(classes) or hop_s <= 0:
        raise ValueError("Invalid event geometry")
    events = []
    for i, label in enumerate(classes):
        intervals = []
        for index in np.flatnonzero(scores[:, i] >= thresholds[i]):
            start, end = max(0., float(times[index] - hop_s / 2)), float(times[index] + hop_s / 2)
            if duration_s is not None:
                end = min(end, duration_s)
            if intervals and start - intervals[-1][1] <= merge_gap_s + 1e-9:
                intervals[-1][1] = end
            else:
                intervals.append([start, end])
        events.extend({"label": label, "start_s": a, "end_s": b} for a, b in intervals if b - a >= minimum_s and b > a)
    return sorted(events, key=lambda e: (e["start_s"], e["label"]))


def event_metrics(reference, predicted, *, onset_tolerance_s=.1, offset_tolerance_s=.1):
    """Maximum-cardinality one-to-one matching with explicit boundary tolerances."""
    if min(onset_tolerance_s, offset_tolerance_s) < 0:
        raise ValueError("Nonnegative matching tolerance required")
    matches = []
    if reference and predicted:
        valid = np.array([[a["label"] == b["label"] and abs(a["start_s"] - b["start_s"]) <= onset_tolerance_s
                           and abs(a["end_s"] - b["end_s"]) <= offset_tolerance_s for b in predicted] for a in reference])
        rows, columns = linear_sum_assignment(valid.astype(int), maximize=True)
        matches = [(i, j) for i, j in zip(rows, columns) if valid[i, j]]
    tp, fp, fn = len(matches), len(predicted) - len(matches), len(reference) - len(matches)
    return {"tp": tp, "fp": fp, "fn": fn, "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
            "duration_mae_s": float(np.mean([abs((reference[i]["end_s"] - reference[i]["start_s"])
                                - (predicted[j]["end_s"] - predicted[j]["start_s"])) for i, j in matches])) if matches else None}


def merge_predictions(blocks, *, sample_rate, hop_length, n_fft):
    """Average overlap by absolute frame index; no duplicate timeline events."""
    if not blocks:
        raise ValueError("No inference frames")
    totals, counts = {}, {}
    for start_sample, probabilities, valid_samples in blocks:
        for index, probability in enumerate(probabilities):
            local = index * hop_length
            if local + n_fft > valid_samples:
                continue
            sample = start_sample + local
            totals[sample] = totals.get(sample, 0) + probability
            counts[sample] = counts.get(sample, 0) + 1
    positions = sorted(totals)
    return np.array([(p + n_fft / 2) / sample_rate for p in positions]), np.array([totals[p] / counts[p] for p in positions])
