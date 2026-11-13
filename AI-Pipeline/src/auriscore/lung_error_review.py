"""Bounded development-error selection; no automatic relabeling or test access."""
import numpy as np


def window_errors(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray,
                  classes: list[str], thresholds: list[float], frames: int) -> dict:
    """Count candidate errors on valid frames; fragmentation is a review cue only."""
    if (truth.ndim != 2 or truth.shape != scores.shape or truth.shape != mask.shape
            or truth.shape[1] != len(classes) or len(thresholds) != len(classes)
            or type(frames) is not int or frames < 2 or not len(truth) or len(truth) % frames
            or len(set(classes)) != len(classes)
            or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1))
            or not np.isin(truth, [0, 1]).all() or not np.isin(mask, [0, 1]).all()
            or not np.isfinite(thresholds).all() or np.any((np.asarray(thresholds) < 0) | (np.asarray(thresholds) > 1))):
        raise ValueError('Aligned finite development scores/masks and window geometry required')
    y = truth.reshape(-1, frames, len(classes)) > 0
    valid = mask.reshape(y.shape) > 0
    predicted = scores.reshape(y.shape) >= np.asarray(thresholds)[None, None, :]
    output = {}
    if {'inhalation', 'exhalation'}.issubset(classes):
        i, e = classes.index('inhalation'), classes.index('exhalation')
        joint = valid[:, :, i] & valid[:, :, e]
        wrong_both = predicted[:, :, i] & predicted[:, :, e] & ~(y[:, :, i] & y[:, :, e]) & joint
        output['phase_conflict'] = (wrong_both.sum(axis=1), joint.sum(axis=1))
        phase_valid, phase_predicted = valid[:, :, [i, e]], predicted[:, :, [i, e]]
        adjacent = phase_valid[:, 1:, :] & phase_valid[:, :-1, :]
        transitions = (phase_predicted[:, 1:, :] != phase_predicted[:, :-1, :]) & adjacent
        output['phase_fragmentation'] = (transitions.sum(axis=(1, 2)), adjacent.sum(axis=(1, 2)))
    if 'crackle' in classes:
        i = classes.index('crackle')
        negative = ~y[:, :, i] & valid[:, :, i]
        output['crackle_false_positive'] = ((predicted[:, :, i] & negative).sum(axis=1), negative.sum(axis=1))
    for label in ('stridor', 'rhonchi'):
        if label in classes:
            i = classes.index(label)
            positive = y[:, :, i] & valid[:, :, i]
            output[label + '_miss'] = ((~predicted[:, :, i] & positive).sum(axis=1), positive.sum(axis=1))
    return output
