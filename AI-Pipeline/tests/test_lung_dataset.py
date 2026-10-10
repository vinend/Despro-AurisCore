"""Real TensorFlow input iteration/evaluation tests; no model weights are fitted."""
import warnings
import json
from types import SimpleNamespace
import numpy as np
import pandas as pd
import pytest
from auriscore.lung_training import build_dataset

tf = pytest.importorskip("tensorflow")


@pytest.fixture
def cached_windows(tmp_path):
    rows, expected = [], {}
    for i in range(22):
        name = f"window-{i}.npz"
        features = np.full((5, 4), i / 10, dtype=np.float32)
        truth = np.tile([(i >> bit) & 1 for bit in range(3)], (5, 1)).astype(np.float32)
        mask = np.ones_like(truth)
        mask[-1] = 0
        np.savez(tmp_path / name, features=features, targets=truth, mask=mask)
        expected[i] = np.concatenate([truth, mask], axis=-1)
        rows.append({"file": name, "split": "train" if i < 20 else "validation"})
    # This sentinel must never be opened by either development branch.
    (tmp_path / "official-test.npz").write_bytes(b"sealed fictional test")
    return tmp_path, pd.DataFrame(rows), expected


def dataset(cache, rows, *, training, seed=42):
    return build_dataset(cache, rows, np.zeros(4), np.ones(4),
                         batch_size=8, training=training, seed=seed)


def epoch(data, expected):
    ids, sizes = [], []
    for features, packed in data.as_numpy_iterator():
        assert features.dtype == packed.dtype == np.float32
        assert features.shape[1:] == (5, 4) and packed.shape[1:] == (5, 6)
        sizes.append(len(features))
        for x, y in zip(features, packed):
            i = round(float(x[0, 0]) * 10)
            np.testing.assert_array_equal(y, expected[i])
            ids.append(i)
    return ids, sizes


def test_training_reshuffles_every_epoch_keeps_all_windows_and_packed_targets(cached_windows):
    cache, rows, expected = cached_windows
    training_rows = rows[rows.split == "train"]
    first = dataset(cache, training_rows, training=True)
    assert first.cardinality().numpy() == 3
    orders = [epoch(first, expected) for _ in range(3)]
    for ids, sizes in orders:
        assert sorted(ids) == list(range(20)) and sizes == [8, 8, 4]
    assert orders[0][0] != list(range(20))
    assert orders[0][0] != orders[1][0] != orders[2][0]
    # A new run with the same seed reproduces the entire epoch-order sequence.
    second = dataset(cache, training_rows, training=True)
    assert [epoch(second, expected) for _ in range(3)] == orders


def test_validation_order_and_batch_count_are_stable(cached_windows):
    cache, rows, expected = cached_windows
    validation = dataset(cache, rows[rows.split == "validation"], training=False)
    assert validation.cardinality().numpy() == 1
    assert [epoch(validation, expected) for _ in range(3)] == [([20, 21], [2])] * 3


def test_keras_evaluation_consumes_known_batches_without_exhaustion_warning(cached_windows):
    cache, rows, _ = cached_windows
    data = dataset(cache, rows[rows.split == "train"], training=True)
    inputs = tf.keras.Input(shape=(5, 4))
    outputs = tf.keras.layers.Lambda(lambda x: tf.zeros((tf.shape(x)[0], 5, 6)), output_shape=(5, 6))(inputs)
    model = tf.keras.Model(inputs, outputs)
    model.compile(loss="mse")
    assert model.trainable_weights == []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        losses = [model.evaluate(data, verbose=0) for _ in range(3)]
    assert np.isfinite(losses).all()
    assert not any("ran out of data" in str(w.message) or "shuffle=True" in str(w.message) for w in caught)
    assert int(model.optimizer.iterations.numpy()) == 0


def test_dataset_rejects_test_rows_invalid_paths_and_inconsistent_geometry(cached_windows):
    cache, rows, _ = cached_windows
    test = pd.DataFrame([{"file": "official-test.npz", "split": "test"}])
    with pytest.raises(ValueError, match="Official test"):
        dataset(cache, test, training=True)
    with pytest.raises(ValueError, match="Unsafe"):
        dataset(cache, pd.DataFrame([{"file": "../escape.npz"}]), training=False)
    with pytest.raises(ValueError, match="Nonempty"):
        dataset(cache, rows.iloc[:0], training=True)
    np.savez(cache / "bad.npz", features=np.zeros((6, 4)), targets=np.zeros((6, 3)), mask=np.ones((6, 3)))
    invalid = pd.DataFrame([{"file": "window-0.npz"}, {"file": "bad.npz"}])
    with pytest.raises(tf.errors.OpError, match="Inconsistent Lung cache geometry"):
        list(dataset(cache, invalid, training=False).as_numpy_iterator())


@pytest.mark.parametrize("final", [False, True])
@pytest.mark.parametrize("plateau", [False, True])
def test_both_trainers_wire_known_shuffled_data_without_fitting_weights(cached_windows, monkeypatch, final, plateau):
    from auriscore import lung_training, lung_models
    from auriscore.acquisition_lung import digest
    cache, rows, _ = cached_windows
    rows = rows.copy()
    rows["split"] = ["train"] * 16 + ["validation"] * 6
    rows["group"] = ["0"] * 16 + ["1"] * 6
    rows.to_csv(cache / "index.csv", index=False)
    audit = cache / "audit.json"
    audit.write_text("{}")
    config = {"seed": 42, "classes": ["inhalation", "exhalation", "wheeze"],
              "batch_size": 8, "epochs": 2, "patience": 1, "learning_rate": .001}
    policy_path = None
    if plateau:
        from pathlib import Path
        config["patience"] = 8
        policy_path = Path(__file__).parents[1] / "configs/lung_training_plateau.json"
        policy = json.loads(policy_path.read_text())
    monkeypatch.setattr(lung_training, "preflight", lambda *args: (config, rows))
    seen = []

    class NoWeights:
        def fit(self, data, **kwargs):
            # Stand-in only: exercise exactly what both trainers pass to Keras.
            assert kwargs["shuffle"] is False
            callbacks = kwargs["callbacks"]
            if final:
                assert not any(isinstance(c, (tf.keras.callbacks.ReduceLROnPlateau,
                                              tf.keras.callbacks.EarlyStopping)) for c in callbacks)
                assert any(isinstance(c, tf.keras.callbacks.LearningRateScheduler) for c in callbacks) == plateau
            else:
                assert any(isinstance(c, tf.keras.callbacks.ReduceLROnPlateau) for c in callbacks) == plateau
            count = 22 if final else 16
            assert data.cardinality().numpy() == (count + 7) // 8
            orders = []
            for _ in range(kwargs["epochs"]):
                order = [float(x[0, 0]) for batch, _ in data.as_numpy_iterator() for x in batch]
                assert len(order) == len(set(order)) == count
                orders.append(order)
            assert sorted(orders[0]) == sorted(orders[1]) and orders[0] != orders[1]
            if not final:
                validation = kwargs["validation_data"]
                assert validation.cardinality().numpy() == 1
                assert sum(len(x) for x, _ in validation.as_numpy_iterator()) == 6
            seen.append(True)
            return SimpleNamespace(history={"loss": [1., .9], "val_loss": [1., .95]})

        def save(self, path):
            path.write_bytes(b"fictional model stub; no weights fitted")

        def __call__(self, x, training=False):
            return np.full((1, x.shape[1], 3), .5)

    monkeypatch.setattr(lung_models, "build_model", lambda *args, **kwargs: NoWeights())
    output = cache / "experiment"
    if final:
        selection = cache / "selection.json"
        selection.write_text(json.dumps({"role": "development_validation", "config": config,
            "index_sha256": digest(cache / "index.csv"), "epochs": 2, "thresholds": [.5] * 3,
            "postprocessing": {"minimum_s": 0, "merge_gap_s": 0},
            **({"training_policy": policy, "learning_rates": [.001, .001]} if plateau else {})}))
        lung_training.train_final(cache, audit, selection, output, authorized=True)
    else:
        lung_training.train(cache, audit, output, authorized=True, training_policy=policy_path)
    assert seen == [True]
    assert json.loads((output / "status.json").read_text())["status"] == "completed"
    assert json.loads((output / "source.json").read_text())["input_pipeline_version"] == lung_training.INPUT_PIPELINE_VERSION
    source = json.loads((output / "source.json").read_text())
    events = [json.loads(line) for line in (output / "process.jsonl").read_text().splitlines()]
    assert events[0]["stage"] == "runtime"
    assert events[-1]["stage"] == "experiment_completed"
    assert any(event["stage"] == "statistics_completed" for event in events)
    if not final:
        assert sum(event["stage"] == "class_evaluation" for event in events) == 3
    if not final:
        assert source["config"] == config
    assert source["training_policy"]["learning_rate_schedule"]["type"] == ("reduce_on_plateau" if plateau else "constant")
    if plateau and not final:
        assert source["training_policy_sha256"] == digest(policy_path)
