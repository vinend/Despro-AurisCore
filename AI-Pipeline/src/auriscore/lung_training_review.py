"""Read-only loss reconstruction for completed Lung development predictions."""
import numpy as np


def early_stop_summary(history: dict, patience: int) -> dict:
    """Describe observed loss minimum; never change an experiment's stopping rule."""
    training, validation = np.asarray(history['loss']), np.asarray(history['val_loss'])
    if (training.ndim != 1 or training.shape != validation.shape or not len(training)
            or not np.isfinite(training).all() or not np.isfinite(validation).all()
            or type(patience) is not int or patience < 1):
        raise ValueError('Finite aligned history and positive patience required')
    best = int(np.argmin(validation))
    return {'epochs_completed': len(training), 'best_epoch': best + 1,
            'epochs_without_improvement': len(training) - best - 1,
            'patience': patience, 'expected_stop_if_no_improvement': best + 1 + patience,
            'best_validation_loss': float(validation[best]),
            'training_loss_at_best': float(training[best]), 'final_training_loss': float(training[-1]),
            'final_validation_loss': float(validation[-1]),
            'validation_loss_increase_from_best': float(validation[-1] - validation[best])}


def masked_loss_components(truth: np.ndarray, scores: np.ndarray, mask: np.ndarray,
                           frames_per_window: int) -> dict:
    """Reconstruct per-window masked BCE's positive/negative class contributions.

    The TRAIN-derived positive weights can then be applied without rereading
    predictions. Using one common weight vector makes checkpoint loss comparable
    when added data changed the training class weights. No threshold is selected.
    """
    if (truth.ndim != 2 or truth.shape != scores.shape or truth.shape != mask.shape
            or type(frames_per_window) is not int or frames_per_window < 1
            or len(truth) % frames_per_window or not len(truth)
            or not np.isin(truth, [0, 1]).all() or not np.isin(mask, [0, 1]).all()
            or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1))):
        raise ValueError('Aligned finite frame predictions and full windows required')
    count = len(truth) // frames_per_window
    validity = mask.reshape(count, frames_per_window, -1)
    denominator = np.maximum(validity.sum(axis=(1, 2), dtype=np.float64), 1)
    positive, negative = [], []
    for index in range(truth.shape[1]):
        y, m = truth[:, index].astype(np.float64), mask[:, index]
        p = np.clip(scores[:, index].astype(np.float64), 1e-7, 1 - 1e-7)
        positive.append(float(((-y * np.log(p) * m).reshape(count, frames_per_window).sum(axis=1) / denominator).mean()))
        negative.append(float(((-(1 - y) * np.log1p(-p) * m).reshape(count, frames_per_window).sum(axis=1) / denominator).mean()))
    return {'positive': positive, 'negative': negative, 'windows': count}


def weighted_loss(components: dict, positive_weights: list[float]) -> dict:
    """Apply actual or fixed control weights to the same loss components."""
    weights = np.asarray(positive_weights)
    if (weights.shape != np.asarray(components['positive']).shape or not np.isfinite(weights).all()
            or np.any(weights <= 0)):
        raise ValueError('Finite positive class weights required')
    classes = weights * np.asarray(components['positive']) + np.asarray(components['negative'])
    return {'total': float(classes.sum()), 'per_class': classes.tolist()}
