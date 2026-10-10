"""Verify configurable regularization and saved inference without fitting weights."""
import copy
import json
from pathlib import Path
import numpy as np
import pytest
from auriscore.lung_training_policy import load_policy, validate_policy, model_dropout, final_learning_rates

CONFIG = {"learning_rate": .001, "patience": 8}
POLICY_PATH = Path(__file__).parents[1] / "configs/lung_training_dropout.json"


def test_policy_keeps_cache_and_constant_schedule_and_freezes_final_dropout():
    before = copy.deepcopy(CONFIG)
    policy = load_policy(POLICY_PATH, CONFIG)
    assert CONFIG == before
    assert model_dropout(policy) == .4
    assert model_dropout(load_policy(None, CONFIG)) == .2
    assert policy["learning_rate_schedule"] == {"type": "constant"}
    frozen, rates = final_learning_rates({"epochs": 2, "training_policy": policy}, CONFIG)
    assert model_dropout(frozen) == .4 and rates is None


@pytest.mark.parametrize("value", [True, -.1, 1, float("nan"), float("inf"), "0.4"])
def test_invalid_dropout_rejected_in_policy_and_builder(value):
    from auriscore.lung_models import build_model
    policy = json.loads(POLICY_PATH.read_text())
    policy["model"]["dropout"] = value
    with pytest.raises(ValueError, match="dropout"):
        validate_policy(policy, CONFIG)
    with pytest.raises(ValueError, match="dropout"):
        build_model((8, 16), ["wheeze"], dropout=value)


def test_closed_versioned_model_policy():
    policy = json.loads(POLICY_PATH.read_text())
    for invalid in ({**policy, "schema_version": "lung-training-policy-v1"},
                    {key: value for key, value in policy.items() if key != "model"},
                    {**policy, "model": {"dropout": .4, "width": 128}}):
        with pytest.raises(ValueError):
            validate_policy(invalid, CONFIG)


def test_model_rate_shape_and_saved_inference_parity_without_fitting(tmp_path):
    tf = pytest.importorskip("tensorflow")
    from auriscore.lung_models import build_model
    baseline = build_model((8, 16), ["inhalation", "wheeze"])
    regularized = build_model((8, 16), ["inhalation", "wheeze"], dropout=.4)
    assert [layer.rate for layer in baseline.layers if isinstance(layer, tf.keras.layers.Dropout)] == [.2]
    assert [layer.rate for layer in regularized.layers if isinstance(layer, tf.keras.layers.Dropout)] == [.4]
    assert baseline.output_shape == regularized.output_shape == (None, 8, 2)
    # Same weights isolate inference semantics: Dropout is disabled at inference.
    regularized.set_weights(baseline.get_weights())
    audio = np.ones((1, 8, 16), np.float32)
    expected = baseline(audio, training=False).numpy()
    np.testing.assert_allclose(regularized(audio, training=False), expected)
    path = tmp_path / "model.keras"
    regularized.save(path)
    restored = tf.keras.models.load_model(path, compile=False)
    assert [layer.rate for layer in restored.layers if isinstance(layer, tf.keras.layers.Dropout)] == [.4]
    np.testing.assert_allclose(restored(audio, training=False), expected)
    assert int(regularized.optimizer.iterations.numpy()) == 0
