"""Checks for clip coverage, score pooling and padded tail handling."""

import numpy as np
import pytest

from auriscore.lung_clip_evaluation import nominal_clip_frames, reduce_clip_predictions


def test_positive_negative_and_unknown_have_distinct_coverage():
    truth = np.array([[[1], [0], [0], [0], [0], [1]]])
    known = np.array([[[1], [0], [1], [1], [1], [0]]])
    scores = np.array([[[.2], [.9], [.3], [.4], [.5], [.6]]])
    y, p, mask = reduce_clip_predictions(
        truth, scores, known, np.ones((1, 6)), clip_frames=2
    )
    np.testing.assert_array_equal(y[0, :, 0], [True, False, False])
    np.testing.assert_array_equal(mask[0, :, 0], [True, True, False])
    np.testing.assert_allclose(p[0, :, 0], [.9, .4, .6])


def test_incomplete_clips_and_short_suffix_are_excluded():
    truth = np.ones((1, 5, 2))
    y, p, mask = reduce_clip_predictions(
        truth, truth, truth, np.array([[1, 1, 1, 0, 0]]), clip_frames=2
    )
    assert y.shape == p.shape == mask.shape == (1, 2, 2)
    assert y[0, 0].all() and p[0, 0].all() and mask[0, 0].all()
    assert not y[0, 1].any() and not p[0, 1].any() and not mask[0, 1].any()


def test_nominal_geometry_and_invalid_data():
    assert nominal_clip_frames(8000, 128) == 62
    with pytest.raises(ValueError, match="geometry"):
        nominal_clip_frames(8, 16)
    scores = np.array([[[np.nan]]])
    truth = np.ones((1, 1, 1))
    with pytest.raises(ValueError, match="arrays"):
        reduce_clip_predictions(truth, scores, truth, np.ones((1, 1)), clip_frames=1)
