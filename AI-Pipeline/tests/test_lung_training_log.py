"""Verify logging and callback order without fitting model weights."""
import json
import numpy as np
import pytest
from auriscore.lung_training_log import TrainingLog, process_callback, runtime_details
from auriscore.lung_training_policy import development_callbacks, load_policy


def test_timestamped_persistent_events_and_throttled_progress(tmp_path, monkeypatch, capsys):
    from auriscore import lung_training_log
    clock = [0.]
    monkeypatch.setattr(lung_training_log.time, "monotonic", lambda: clock[0])
    log = TrainingLog(30)
    log.bind(tmp_path)
    log.event("preparation", windows=100)
    log.progress("windows", 1, 100)
    clock[0] = 10
    log.progress("windows", 2, 100)
    clock[0] = 31
    log.progress("windows", 50, 100)
    log.progress("windows", 100, 100)
    records = [json.loads(line) for line in (tmp_path / "process.jsonl").read_text().splitlines()]
    assert [r.get("completed") for r in records] == [None, 1, 50, 100]
    assert records[2]["elapsed_s"] == 31
    assert records[3]["percent"] == 100
    assert all(r["timestamp"].endswith("+00:00") for r in records)
    captured = capsys.readouterr()
    assert "preparation" in captured.err and captured.out == ""


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_reject_invalid_interval(value):
    with pytest.raises(ValueError):
        TrainingLog(value)


def test_epoch_checkpoint_and_stop_logging_uses_callback_decisions_without_fitting(tmp_path):
    tf = pytest.importorskip("tensorflow")
    model = tf.keras.Sequential([tf.keras.Input(shape=(1,)), tf.keras.layers.Dense(1)])
    model.compile(optimizer=tf.keras.optimizers.Adam(.001), loss="mse")
    model.stop_training = False
    original = model.get_weights()
    log = TrainingLog()
    log.bind(tmp_path)
    config = {"learning_rate": .001, "patience": 1}
    callbacks = development_callbacks(tmp_path, config, load_policy(None, config))
    stopper = next(c for c in callbacks if isinstance(c, tf.keras.callbacks.EarlyStopping))
    callbacks.append(process_callback(log, epochs=5, steps=2, early_stopper=stopper,
                                     checkpoint=tmp_path / "best.weights.h5"))
    for callback in callbacks:
        callback.set_model(model)
        callback.on_train_begin()
    for epoch in range(2):
        for callback in callbacks:
            callback.on_epoch_begin(epoch)
        callbacks[-1].on_train_batch_end(0)
        callbacks[-1].on_test_begin()
        logs = {"loss": .5, "val_loss": 1. + epoch}
        for callback in callbacks:
            callback.on_epoch_end(epoch, logs)
    for callback in callbacks:
        callback.on_train_end()
    records = [json.loads(line) for line in (tmp_path / "process.jsonl").read_text().splitlines()]
    epochs = [r for r in records if r["stage"] == "epoch_completed"]
    assert epochs[0]["best_epoch"] == 1 and epochs[0]["early_stop"] is False
    assert epochs[1]["epochs_without_improvement"] == 1 and epochs[1]["early_stop"] is True
    assert epochs[1]["learning_rate"] == pytest.approx(.001)
    assert [r["epoch"] for r in records if r["stage"] == "best_checkpoint_saved"] == [1]
    assert records[-1]["restored_best_weights"] is True
    assert int(model.optimizer.iterations.numpy()) == 0
    for before, after in zip(original, model.get_weights()):
        np.testing.assert_array_equal(before, after)


def test_runtime_reports_cpu_and_visible_gpu():
    from types import SimpleNamespace
    def fake(gpus):
        device = SimpleNamespace(name="/device:GPU:0")
        return SimpleNamespace(__version__="test", config=SimpleNamespace(
            list_physical_devices=lambda kind: [device] if gpus else [],
            list_logical_devices=lambda kind: [device] if gpus else [],
            experimental=SimpleNamespace(get_device_details=lambda device: {"device_name": "Test GPU"})))
    assert runtime_details(fake(False))["execution"] == "CPU fallback"
    assert runtime_details(fake(True))["gpu_names"] == ["Test GPU"]
