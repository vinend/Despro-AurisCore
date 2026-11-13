"""Actual-risk class weighting and saturated-gradient reproducibility."""
import numpy as np
import pytest
from auriscore.lung_loss_audit import window_mass, constant_optimum, gradient_probe


def test_global_frame_balance_does_not_balance_per_window_objective():
    positive = np.ones((10, 1)); negative = np.zeros((100, 1))
    a, b = window_mass(positive, np.ones_like(positive))
    c, d = window_mass(negative, np.ones_like(negative))
    # Inverse frame frequency is 10, but both windows carry equal loss mass.
    assert constant_optimum(a+c, b+d, np.array([10.])) == pytest.approx([10/11])
    assert constant_optimum(a+c, b+d, np.array([1.])) == pytest.approx([.5])


def test_unknown_labels_have_zero_objective_mass():
    y = np.array([[1, 0], [0, 1]], np.float32)
    m = np.array([[0, 1], [1, 0]], np.float32)
    p, n = window_mass(y, m)
    np.testing.assert_array_equal(p, [0, 0])
    np.testing.assert_array_equal(n, [.5, .5])
    with pytest.raises(ValueError):
        constant_optimum(np.array([0.]), np.array([0.]), np.array([1.]))


def test_manual_probability_clip_loses_extreme_wrong_example_gradients():
    pytest.importorskip('tensorflow')
    result = gradient_probe()
    assert result['gradients']['legacy'][:2] == [0., 0.]
    np.testing.assert_allclose(result['gradients']['keras_stable'], result['gradients']['logits_reference'], atol=1e-6)
    assert result['gradients']['keras_stable'][:2] == pytest.approx([1., -6.])
    assert result['optimizer_steps'] == 0
