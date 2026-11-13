"""Read-only helpers for frozen Lung development error and overlap analysis."""
import numpy as np
from sklearn.metrics import roc_auc_score


def window_loss_matrix(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray,
                       weights: np.ndarray) -> np.ndarray:
    """Per-window/class positive and negative BCE terms, for a fixed weight vector.

    Returned shape is window x class x {positive,negative}. Probabilities are
    clipped only for offline reconstruction, never to calculate training gradients.
    """
    y, p, m = map(np.asarray, (truth, scores, mask))
    w = np.asarray(weights)
    if (y.ndim != 3 or y.shape != p.shape or y.shape != m.shape or w.shape != y.shape[2:]
            or not np.isin(y, [0, 1]).all() or not np.isin(m, [0, 1]).all()
            or not np.isfinite(p).all() or np.any((p < 0) | (p > 1))
            or not np.isfinite(w).all() or np.any(w <= 0)):
        raise ValueError('Aligned binary windows, finite scores and class weights required')
    p = np.clip(p.astype(np.float64), 1e-7, 1-1e-7)
    denominator = np.maximum(m.sum(axis=(1, 2), dtype=np.float64), 1)[:, None]
    positive = (-(y * np.log(p)) * m).sum(axis=1) * w / denominator
    negative = (-((1-y) * np.log1p(-p)) * m).sum(axis=1) / denominator
    return np.stack([positive, negative], axis=-1)


def inverse_positive_weight(scores: np.ndarray, weights: np.ndarray) -> np.ndarray:
    """Analytic posterior correction under ideal weighted BCE; not fitted calibration."""
    p, w = np.asarray(scores), np.asarray(weights)
    if (p.shape[-1:] != w.shape or not np.isfinite(p).all() or np.any((p < 0) | (p > 1))
            or not np.isfinite(w).all() or np.any(w <= 0)):
        raise ValueError('Probabilities and positive class weights required')
    return p / (w + (1-w)*p)


def merge_record_windows(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray,
                         starts: np.ndarray, physical_frames: int,
                         thresholds: np.ndarray, *, margin: int = 35) -> dict:
    """Merge exact absolute frame identities and quantify repeated-window disagreement.

    Starts are integer hop indices. Invalid padded frames are excluded. Averages
    use audio coverage only; annotation masks are used solely for evaluation.
    """
    if (truth.ndim != 3 or truth.shape != scores.shape or mask.shape != truth.shape
            or len(starts) != len(truth) or physical_frames <= 0
            or not np.issubdtype(np.asarray(starts).dtype, np.integer)
            or np.any(np.asarray(starts) < 0)):
        raise ValueError('Aligned record windows and physical frame indices required')
    n, frames, classes = truth.shape
    total = np.zeros((physical_frames, classes), np.float64)
    count = np.zeros(physical_frames, np.int32)
    positive = np.zeros_like(total); known = np.zeros_like(total)
    low = np.full_like(total, np.inf); high = np.full_like(total, -np.inf)
    inner_low = low.copy(); inner_high = high.copy(); inner_count = count.copy()
    for i, start in enumerate(starts):
        local = np.arange(frames)
        active = start + local < physical_frames
        at = start + local[active]
        p, y, m = scores[i, active], truth[i, active], mask[i, active]
        total[at] += p; count[at] += 1
        positive[at] += y*m; known[at] += m
        low[at] = np.minimum(low[at], p); high[at] = np.maximum(high[at], p)
        interior = (local[active] >= margin) & (local[active] < frames-margin)
        ii = at[interior]
        inner_count[ii] += 1
        inner_low[ii] = np.minimum(inner_low[ii], p[interior])
        inner_high[ii] = np.maximum(inner_high[ii], p[interior])
    observed = count > 0
    y = positive / np.maximum(known, 1)
    if not np.isin(y[known > 0], [0, 1]).all():
        raise ValueError('Conflicting labels for identical absolute frames')
    probability = total / np.maximum(count[:, None], 1)
    disagreement = {}
    for name, lo, hi, repeat in [('all', low, high, count > 1),
                                  ('both_interior', inner_low, inner_high, inner_count > 1)]:
        active = repeat[:, None] & (known > 0)
        delta = np.subtract(hi, lo, out=np.zeros_like(hi), where=active)
        crossing = (lo < thresholds) & (hi >= thresholds) & active
        disagreement[name] = {'valid_repeated': active.sum(axis=0).tolist(),
                              'sum_absolute_range': delta.sum(axis=0).tolist(),
                              'threshold_crossings': crossing.sum(axis=0).tolist()}
    return {'truth': y[observed].astype(np.float32), 'scores': probability[observed].astype(np.float32),
            'mask': (known[observed] > 0).astype(np.float32), 'disagreement': disagreement}


def conditional_auc(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray) -> list[dict]:
    """Within one recording: only classes with both labels can support ROC-AUC."""
    result = []
    for i in range(truth.shape[-1]):
        valid = mask[:, i] > 0
        y, p = truth[valid, i], scores[valid, i]
        positives, negatives = int(y.sum()), int((1-y).sum())
        result.append({'positive': positives, 'negative': negatives,
                       'roc_auc': float(roc_auc_score(y, p)) if positives and negatives else None})
    return result
