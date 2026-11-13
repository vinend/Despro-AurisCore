"""Longer context changes dilation only; no fitting performed."""
import json
from pathlib import Path
import numpy as np
import pytest
from auriscore.lung_training_policy import load_policy, model_dilation, final_learning_rates, validate_policy

CONFIG = {"learning_rate": .001, "patience": 8}
PATH = Path(__file__).parents[1] / "configs/lung_training_context.json"


def test_frozen_context_and_legacy_policy():
    policy = load_policy(PATH, CONFIG)
    assert model_dilation(policy) == 16
    assert model_dilation(load_policy(None, CONFIG)) == 1
    frozen, rates = final_learning_rates({"epochs": 2, "training_policy": policy}, CONFIG)
    assert model_dilation(frozen) == 16 and rates is None


@pytest.mark.parametrize("value", [True, 0, 17, 1.5, "16"])
def test_invalid_dilation(value):
    policy = json.loads(PATH.read_text())
    policy["model"]["temporal_dilation"] = value
    with pytest.raises(ValueError, match="dilation"):
        validate_policy(policy, CONFIG)


def test_temporal_shape_parameter_count_and_saved_dilation(tmp_path):
    tf = pytest.importorskip("tensorflow")
    from auriscore.lung_models import build_model
    baseline = build_model((80, 16), ["inhalation", "wheeze"])
    context = build_model((80, 16), ["inhalation", "wheeze"], temporal_dilation=16)
    assert baseline.count_params() == context.count_params()
    assert baseline.output_shape == context.output_shape == (None, 80, 2)
    assert [l.dilation_rate for l in context.layers if isinstance(l, tf.keras.layers.Conv1D)] == [(16,)]
    audio = np.ones((1, 80, 16), np.float32)
    expected = context(audio, training=False).numpy()
    context.save(tmp_path / "model.keras")
    restored = tf.keras.models.load_model(tmp_path / "model.keras", compile=False)
    np.testing.assert_allclose(restored(audio, training=False), expected)
    assert int(context.optimizer.iterations.numpy()) == 0
