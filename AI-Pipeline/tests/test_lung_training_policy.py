"""Exercise LR callback lifecycles without fitting or optimizing any weights."""
import copy
import csv
import json
from pathlib import Path

import numpy as np
import pytest

from auriscore.lung_training_policy import (
    development_callbacks, final_learning_rates, learning_rate_logger, load_policy, validate_policy,
)

CONFIG = {"learning_rate": .001, "patience": 8}
POLICY = json.loads((Path(__file__).parents[1] / "configs/lung_training_plateau.json").read_text())


@pytest.mark.parametrize("key,value", [
    ("monitor", "test_loss"), ("factor", 1), ("factor", True),
    ("min_lr", 0), ("min_lr", .001), ("min_delta", float("nan")),
    ("patience", 8), ("patience", 2.5), ("cooldown", -1),
])
def test_invalid_policies_are_rejected(key, value):
    policy = copy.deepcopy(POLICY)
    policy["learning_rate_schedule"][key] = value
    with pytest.raises(ValueError):
        validate_policy(policy, CONFIG)


def test_baseline_and_opt_in_policy(tmp_path):
    assert load_policy(None, CONFIG)["learning_rate_schedule"] == {"type": "constant"}
    path = tmp_path / "policy.json"
    path.write_text(json.dumps(POLICY))
    assert load_policy(path, CONFIG) == POLICY
    policy = copy.deepcopy(POLICY)
    policy["unexpected"] = True
    with pytest.raises(ValueError, match="schema"):
        validate_policy(policy, CONFIG)


def model_without_fitting():
    tf = pytest.importorskip("tensorflow")
    model = tf.keras.Sequential([tf.keras.Input(shape=(1,)), tf.keras.layers.Dense(1)])
    model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss="mse")
    model.stop_training = False
    return model


def test_plateau_reduces_before_stopping_logs_used_rates_and_preserves_weights(tmp_path):
    model = model_without_fitting()
    weights = [w.copy() for w in model.get_weights()]
    callbacks = development_callbacks(tmp_path, CONFIG, POLICY)
    for callback in callbacks:
        callback.set_model(model)
        callback.on_train_begin()
    used, upcoming = [], []
    for epoch in range(9):
        for callback in callbacks:
            callback.on_epoch_begin(epoch)
        logs = {"loss": .5, "val_loss": 1.0 if epoch == 0 else 1.1}
        for callback in callbacks:
            callback.on_epoch_end(epoch, logs)
        used.append(logs["learning_rate"])
        upcoming.append(logs["next_learning_rate"])
        assert model.stop_training == (epoch == 8)
    for callback in callbacks:
        callback.on_train_end()
    assert used[:4] == pytest.approx([.001, .001, .001, .0005])
    assert upcoming[2] == pytest.approx(.0005)
    assert (tmp_path / "best.weights.h5").exists()
    rows = list(csv.DictReader((tmp_path / "history.csv").open()))
    assert float(rows[2]["learning_rate"]) == pytest.approx(.001)
    assert float(rows[2]["next_learning_rate"]) == pytest.approx(.0005)
    assert int(model.optimizer.iterations.numpy()) == 0
    for before, after in zip(weights, model.get_weights()):
        np.testing.assert_array_equal(before, after)


def test_floor_and_constant_baseline(tmp_path):
    tf = pytest.importorskip("tensorflow")
    baseline = development_callbacks(tmp_path, CONFIG, load_policy(None, CONFIG))
    assert not any(isinstance(c, tf.keras.callbacks.ReduceLROnPlateau) for c in baseline)
    model = model_without_fitting()
    callback = development_callbacks(tmp_path, CONFIG, POLICY)[0]
    callback.set_model(model)
    callback.on_train_begin()
    for epoch in range(40):
        callback.on_epoch_end(epoch, {"val_loss": 1.0})
    assert float(model.optimizer.learning_rate.numpy()) == pytest.approx(1e-6)
    assert int(model.optimizer.iterations.numpy()) == 0


def test_final_schedule_requires_frozen_rates_and_replays_without_validation():
    tf = pytest.importorskip("tensorflow")
    selection = {"epochs": 4, "training_policy": POLICY}
    with pytest.raises(ValueError, match="frozen"):
        final_learning_rates(selection, CONFIG)
    selection["learning_rates"] = [.001, .001, .001, .0005]
    policy, rates = final_learning_rates(selection, CONFIG)
    assert policy == POLICY
    model = model_without_fitting()
    callbacks = [tf.keras.callbacks.LearningRateScheduler(lambda epoch, current: rates[epoch]), learning_rate_logger()]
    for callback in callbacks:
        callback.set_model(model)
    for epoch, expected in enumerate(rates):
        for callback in callbacks:
            callback.on_epoch_begin(epoch)
        logs = {}
        for callback in callbacks:
            callback.on_epoch_end(epoch, logs)
        assert logs["learning_rate"] == pytest.approx(expected)
    assert int(model.optimizer.iterations.numpy()) == 0
    for invalid in ([.001], [.001, .0005, .001, .0005], [.001, .001, 0, .0005],
                    [.001, .001, .001, 1e-8], [True, .001, .001, .0005]):
        with pytest.raises(ValueError):
            final_learning_rates({**selection, "learning_rates": invalid}, CONFIG)
    with pytest.raises(ValueError, match="Constant"):
        final_learning_rates({"epochs": 4, "learning_rates": rates}, CONFIG)
