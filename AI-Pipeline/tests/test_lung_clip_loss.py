"""Check annotation and physical-frame boundaries for L025."""
import numpy as np
import pytest

from auriscore.lung_clip_loss import frame_and_clip_loss


def test_auxiliary_excludes_unknown_negatives_and_incomplete_clips():
    tf = pytest.importorskip("tensorflow")
    packed = tf.constant([[[1., 1., 1.], [0., 0., 1.],
                           [0., 1., 1.], [0., 0., 1.],
                           [0., 1., 1.], [0., 0., 0.]]])
    scores = tf.Variable([[[.4], [.8], [.2], [.9], [.3], [.9]]])
    with tf.GradientTape() as tape:
        value = frame_and_clip_loss([1.], 2, 6)(packed, scores)
    expected = -np.log([.4, .8, .7]).mean() - .5 * np.log(.8)
    np.testing.assert_allclose(value.numpy(), [expected], rtol=1e-6)
    gradient = tape.gradient(value, scores).numpy().ravel()
    assert gradient[1] < 0
    assert gradient[3] == gradient[5] == 0


def test_focused_loss_applies_only_to_selected_source_and_class():
    tf = pytest.importorskip("tensorflow")
    packed = tf.constant([[[0., 1., 1., 1., 1., 1.]] * 2,
                          [[0., 1., 1., 1., 1., 0.]] * 2])
    scores = tf.constant([[[.9, .2], [.1, .1]]] * 2)
    result = frame_and_clip_loss([1., 1.], 2, 2, focus_class=1)(packed, scores).numpy()
    np.testing.assert_allclose(result[0] - result[1], -.5 * .8**2 * np.log(.2), rtol=1e-6)
