"""Validate stopping arithmetic and identical-weight checkpoint comparisons."""
import numpy as np
import pytest
from auriscore.lung_training_review import early_stop_summary, masked_loss_components, weighted_loss


def test_epoch_ten_is_best_two_plus_patience_eight():
    summary = early_stop_summary({'loss': np.linspace(.8, .3, 10).tolist(),
        'val_loss': [.9, .8, .85, .86, .9, .95, 1., 1.1, 1.2, 1.3]}, 8)
    assert summary['best_epoch'] == 2
    assert summary['epochs_without_improvement'] == 8
    assert summary['expected_stop_if_no_improvement'] == summary['epochs_completed'] == 10


def test_loss_matches_per_window_masked_objective_not_global_frame_average():
    y = np.array([[1., 0.], [0., 1.], [1., 0.], [1., 1.]])
    p = np.array([[.8, .1], [.3, .7], [.6, .4], [.9, .2]])
    m = np.array([[1., 1.], [1., 0.], [0., 0.], [0., 1.]])
    weights = np.array([2., 3.])
    expected = []
    for start in (0, 2):
        yy, pp, mm = y[start:start+2], p[start:start+2], m[start:start+2]
        expected.append(float((-(yy * np.log(pp) * weights + (1-yy) * np.log(1-pp)) * mm).sum() / max(mm.sum(), 1)))
    components = masked_loss_components(y, p, m, 2)
    assert weighted_loss(components, weights)['total'] == pytest.approx(np.mean(expected))
    assert weighted_loss(components, [1., 1.])['total'] != pytest.approx(np.mean(expected))
    with pytest.raises(ValueError):
        masked_loss_components(y, p, m, 3)
    with pytest.raises(ValueError):
        weighted_loss(components, [1.])
