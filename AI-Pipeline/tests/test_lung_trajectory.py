"""Trajectory evidence survives best restoration and does not perform optimizer updates."""
import copy
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
import yaml
from auriscore.lung_training_policy import load_policy, validate_policy
from auriscore.lung_trajectory import select_probes, trajectory_callback

ROOT = Path(__file__).parents[1]


def test_closed_trajectory_policy_preserves_v6_objective():
    config = yaml.safe_load((ROOT / 'configs/lung_cnn_fixed_reference.yaml').read_text())
    policy = load_policy(ROOT / 'configs/lung_training_fixed_reference_trajectory.json', config)
    old = load_policy(ROOT / 'configs/lung_training_window_objective.json', config)
    assert {k: v for k, v in policy.items() if k not in ('trajectory', 'schema_version')} == {
        k: v for k, v in old.items() if k != 'schema_version'}
    for key, value in [('every_epochs', 2), ('recordings_per_device_partition', True), ('thresholds', [.5])]:
        bad = copy.deepcopy(policy); bad['trajectory'][key] = value
        with pytest.raises(ValueError, match='trajectory'):
            validate_policy(bad, config)


def fixture_rows(tmp_path):
    rows = []
    for i in range(8):
        y = np.tile([[0, 1], [1, 0]], (4, 1)).astype(np.float32)
        np.savez(tmp_path / f'{i}.npz', features=np.full((8, 16), i/10, np.float32), targets=y, mask=np.ones_like(y))
        rows.append({'file': f'{i}.npz', 'recording_id': f'r{i}', 'split': 'train' if i < 4 else 'validation',
                     'group': 'a' if i < 4 else 'b', 'device': 'steth' if i % 2 else 'trunc'})
    frame = pd.DataFrame(rows)
    return frame.iloc[:4].copy(), frame.iloc[4:].copy(), frame


def test_probe_selection_is_reproducible_grouped_and_test_guarded(tmp_path):
    fitting, held, metadata = fixture_rows(tmp_path)
    a = select_probes(fitting, held, metadata, count=1, seed=42)
    b = select_probes(fitting, held, metadata, count=1, seed=42)
    pd.testing.assert_frame_equal(a, b)
    assert len(a) == 4 and a.recording_id.nunique() == 4
    with pytest.raises(ValueError, match='disjoint'):
        select_probes(fitting, fitting, metadata, count=1, seed=42)
    bad = held.copy(); bad['split'] = 'test'
    with pytest.raises(ValueError, match='Official test'):
        select_probes(fitting, bad, metadata, count=1, seed=42)


def test_epoch_weights_predictions_and_metrics_survive_restoration(tmp_path):
    tf = pytest.importorskip('tensorflow')
    from auriscore.lung_models import build_model
    tf.keras.utils.set_random_seed(42)
    fitting, held, metadata = fixture_rows(tmp_path)
    folder = tmp_path / 'fold'; folder.mkdir()
    policy = {'trajectory': {'every_epochs': 1, 'recordings_per_device_partition': 1, 'thresholds': [.5, .5]}}
    model = build_model((8, 16), ['wheeze', 'crackle'], positive_weights=[2, 3], loss_numerics='stable_bce')
    callback = trajectory_callback(folder, tmp_path, fitting, held, metadata, np.zeros(16), np.ones(16),
        [0, 1], ['wheeze', 'crackle'], np.array([2, 3]), policy, seed=42, batch_size=2)
    callback.set_model(model)
    stopper = tf.keras.callbacks.EarlyStopping(monitor='val_loss', patience=1, restore_best_weights=True)
    stopper.set_model(model)
    stopper.on_train_begin()
    original = model.get_weights()
    logs = {'loss': .7, 'val_loss': .8}
    stopper.on_epoch_end(0, logs)
    callback.on_epoch_end(0, logs)
    model.layers[-1].bias.assign([1., -1.])
    stopper.on_epoch_end(1, logs)
    callback.on_epoch_end(1, logs)
    stopper.on_train_end()
    for restored, expected in zip(model.get_weights(), original):
        np.testing.assert_array_equal(restored, expected)
    restored_last = build_model((8, 16), ['wheeze', 'crackle'])
    restored_last.load_weights(folder / 'trajectory/epoch-0002/weights.weights.h5')
    np.testing.assert_array_equal(restored_last.layers[-1].bias.numpy(), [1., -1.])
    report = json.loads((folder / 'trajectory/epoch-0002/metrics.json').read_text())
    assert report['optimizer_updates'] == model.optimizer.iterations.numpy() == 0
    assert report['thresholds_reselected'] is False
    assert set(report['metrics']) == {'fitting', 'inner_validation'}
    assert report['metrics']['fitting']['classes']['crackle']['roc_auc'] is not None
    assert logs == {'loss': .7, 'val_loss': .8}
    assert (folder / 'trajectory/epoch-0001/predictions.npz').exists()
    with pytest.raises(FileExistsError):
        callback.on_epoch_end(1, logs)
