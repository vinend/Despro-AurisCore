"""Check the opt-in L028 temporal architecture against the L027 control."""
import numpy as np
import pytest

from auriscore.lung_models import build_model


def test_multiscale_retains_capacity_and_trains_aligned_outputs():
    tf = pytest.importorskip("tensorflow")
    shape = (309, 96)
    classes = ["wheeze", "rhonchi", "crackle"]
    control = build_model(shape, classes, temporal_dilation=16)
    model = build_model(shape, classes, temporal_dilation=16, multiscale_temporal=True)
    assert model.count_params() == control.count_params()
    assert model.output_shape == control.output_shape == (None, 309, 3)
    assert model.get_layer("temporal_local").dilation_rate == (1,)
    assert model.get_layer("temporal_context").dilation_rate == (16,)
    features = tf.random.stateless_normal((1, *shape), seed=[4, 2])
    targets = np.zeros((1, shape[0], 2 * len(classes)), dtype=np.float32)
    targets[:, 100:150, :len(classes)] = 1
    targets[..., len(classes):] = 1
    assert np.isfinite(model.train_on_batch(features, targets))
