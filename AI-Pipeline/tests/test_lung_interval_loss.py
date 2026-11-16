"""Interval objective preserves mask semantics and positive gradient routing."""
import numpy as np
import pytest

from auriscore.lung_interval_loss import interval_loss


def test_interval_loss_separates_runs_and_ignores_unknown_frames():
    tf = pytest.importorskip("tensorflow")
    packed = tf.constant([[[1., 1.], [1., 1.], [1., 0.], [1., 1.], [0., 1.]],
                          [[1., 0.], [1., 0.], [0., 0.], [0., 0.], [0., 0.]]])
    scores = tf.Variable([[[.2], [.8], [.99], [.5], [.1]], [[.5]] * 5])
    with tf.GradientTape() as tape:
        losses = interval_loss([2.])(packed, scores)
        total = tf.reduce_sum(losses)
    gradient = tape.gradient(total, scores).numpy()
    expected = (-4 * np.log(.8) - 2 * np.log(.5) - np.log(.9)) / 4
    np.testing.assert_allclose(losses.numpy(), [expected, 0.], rtol=1e-6)
    assert np.isfinite(gradient).all()
    assert gradient[0, 0, 0] == gradient[0, 2, 0] == 0
    assert gradient[0, 1, 0] < 0 and gradient[0, 3, 0] < 0 and gradient[0, 4, 0] > 0
