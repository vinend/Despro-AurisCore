"""Development metrics for nominal one-second clips inside native Lung windows."""

import numpy as np


def nominal_clip_frames(sample_rate: int, hop_length: int) -> int:
    """Use the largest whole number of frame hops within one second."""
    if not 0 < hop_length <= sample_rate:
        raise ValueError("Clip geometry requires at least one frame per second")
    return sample_rate // hop_length


def reduce_clip_predictions(
    truth: np.ndarray,
    scores: np.ndarray,
    supervision: np.ndarray,
    valid_frames: np.ndarray,
    *,
    clip_frames: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pool complete clips without treating unknown frames as negatives.

    Each input window is chunked from frame zero. A short suffix is discarded,
    and overlapping input windows can contribute overlapping clips. Each clip
    is known positive with any supervised positive frame, or known negative
    only when all frames are supervised and none are positive. Score pooling
    uses all physical frames independently of annotation coverage.
    """
    truth, scores, supervision, valid_frames = map(
        np.asarray, (truth, scores, supervision, valid_frames)
    )
    if (
        truth.ndim != 3 or truth.shape != scores.shape or truth.shape != supervision.shape
        or valid_frames.shape != truth.shape[:2] or not 0 < clip_frames <= truth.shape[1]
        or not np.isin(truth, [0, 1]).all()
        or not np.isin(supervision, [0, 1]).all()
        or not np.isin(valid_frames, [0, 1]).all()
        or not np.isfinite(scores).all() or np.any((scores < 0) | (scores > 1))
    ):
        raise ValueError("Invalid clip prediction arrays or geometry")
    windows, frames, classes = truth.shape
    slots = frames // clip_frames
    retained = slots * clip_frames
    shape = (windows, slots, clip_frames, classes)
    targets = truth[:, :retained].reshape(shape).astype(bool)
    known = supervision[:, :retained].reshape(shape).astype(bool)
    complete = valid_frames[:, :retained].reshape(windows, slots, clip_frames).all(axis=2)
    positive = (targets & known).any(axis=2) & complete[..., None]
    eligible = (positive | known.all(axis=2)) & complete[..., None]
    clip_scores = scores[:, :retained].reshape(shape).max(axis=2)
    clip_scores = np.where(complete[..., None], clip_scores, 0)
    return positive, clip_scores, eligible
