"""Research-policy isolation, target preservation and evaluation-population checks."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from auriscore.lung_training_policy import validate_policy, final_learning_rates, optimizer_settings
from auriscore.lung_research_queue import compare_evaluations, run_queue

ROOT = Path(__file__).parents[1]
CONFIG = yaml.safe_load((ROOT / 'configs/lung_cnn.yaml').read_text())
POLICY = json.loads((ROOT / 'configs/lung_training_lower_lr.json').read_text())


@pytest.mark.parametrize('section,key,value', [
    ('optimizer', 'initial_learning_rate', True), ('optimizer', 'initial_learning_rate', 0),
    ('optimizer', 'initial_learning_rate', .002), ('optimizer', 'weight_decay', -1),
    ('optimizer', 'weight_decay', float('nan')), ('augmentation', 'frequency_mask_bins', True),
    ('augmentation', 'frequency_mask_bins', 9), ('augmentation', 'frequency_mask_bins', -1)])
def test_invalid_research_controls(section, key, value):
    policy = copy.deepcopy(POLICY)
    policy[section][key] = value
    with pytest.raises(ValueError):
        validate_policy(policy, CONFIG)


@pytest.mark.parametrize('classes', [[], ['disease'], ['wheeze', 'wheeze'], ['exhalation', 'inhalation'], False])
def test_invalid_class_projection(classes):
    policy = {**POLICY, 'classes': classes}
    with pytest.raises(ValueError):
        validate_policy(policy, CONFIG)


def test_lower_lr_final_replay_and_legacy_defaults():
    policy, rates = final_learning_rates({'epochs': 2, 'training_policy': POLICY, 'learning_rates': [.0003, .0003]}, CONFIG)
    assert optimizer_settings(policy, CONFIG) == (.0003, 0) and rates == [.0003, .0003]
    with pytest.raises(ValueError):
        final_learning_rates({'epochs': 2, 'training_policy': POLICY, 'learning_rates': [.001, .001]}, CONFIG)
    assert optimizer_settings({}, CONFIG) == (.001, 0)


def test_frequency_mask_reproducibility_and_projection_preserve_targets(tmp_path):
    pytest.importorskip('tensorflow')
    from auriscore.lung_training import build_dataset
    rows = []
    for i in range(12):
        name = f'{i}.npz'
        y = np.tile(np.arange(6) % 2, (8, 1)).astype(np.float32)
        m = np.ones_like(y); m[-1] = 0
        np.savez(tmp_path / name, features=np.full((8, 16), i + 1., np.float32), targets=y, mask=m)
        rows.append({'file': name, 'split': 'train'})
    frame = pd.DataFrame(rows)

    def data(training=True, width=4):
        return build_dataset(tmp_path, frame, np.zeros(16), np.ones(16), batch_size=5,
                             training=training, seed=42, class_indices=[0, 2, 5], frequency_mask=width)
    first, second = list(data().as_numpy_iterator()), list(data().as_numpy_iterator())
    assert sum(len(x) for x, _ in first) == 12
    assert any(np.any(x == 0) for x, _ in first)
    for (x, y), (xx, yy) in zip(first, second):
        np.testing.assert_array_equal(x, xx); np.testing.assert_array_equal(y, yy)
        assert y.shape[-1] == 6
        np.testing.assert_array_equal(y[0, :-1, :3], np.tile([0, 0, 1], (7, 1)))
        assert np.all(y[:, -1, 3:] == 0)
    assert all(np.all(x > 0) for x, _ in data(False, 0).as_numpy_iterator())
    with pytest.raises(ValueError, match='TRAIN-only'):
        data(False, 4)


@pytest.mark.parametrize('policy_name', ['lower_lr', 'weight_decay', 'frequency_mask', 'phase_only', 'sound_only', 'compact_phase', 'compact_sound', 'three_sound', 'stable_loss', 'window_objective', 'supervised_windows', 'fixed_reference_trajectory'])
def test_actual_development_wiring_without_fitting(tmp_path, monkeypatch, policy_name):
    pytest.importorskip('tensorflow')
    from auriscore import lung_training, lung_models
    rows = []
    for i in range(8):
        name = f'{i}.npz'
        truth = ((np.arange(8)[:, None] + np.arange(6)[None, :]) % 2).astype(np.float32)
        mask = np.ones_like(truth)
        if i == 0 and policy_name in ('stable_loss', 'window_objective', 'supervised_windows'):
            mask[:, [2, 3, 5]] = 0
        np.savez(tmp_path / name, features=np.ones((8, 16), np.float32) * i,
                 targets=truth, mask=mask)
        rows.append({'file': name, 'recording_id': f'r{i}', 'split': 'train' if i < 6 else 'validation', 'group': '0' if i < 6 else '1'})
    pd.DataFrame(rows).to_csv(tmp_path / 'index.csv', index=False)
    audit = tmp_path / 'audit.json'; audit.write_text('{}')
    if policy_name == 'fixed_reference_trajectory':
        pd.DataFrame([{**row, 'device': 'steth' if i % 2 else 'trunc'} for i, row in enumerate(rows)]).to_csv(tmp_path / 'recordings.csv', index=False)
    config = {**CONFIG, 'epochs': 2, 'batch_size': 4}
    monkeypatch.setattr(lung_training, 'preflight', lambda *_: (config, pd.DataFrame(rows)))
    actual = lung_models.build_model
    seen = []

    def builder(shape, classes, **kwargs):
        if policy_name.startswith('compact_'):
            assert kwargs['bottleneck_channels'] == 64
        model = actual(shape, classes, **kwargs)
        before = [w.numpy().copy() for w in model.weights]

        def no_fit(data, **fit_kwargs):
            assert fit_kwargs['shuffle'] is False
            if policy_name in ('stable_loss', 'window_objective', 'supervised_windows'):
                assert kwargs['loss_numerics'] == 'stable_bce'
                assert sum(len(x) for x, _ in data.as_numpy_iterator()) == (5 if policy_name == 'supervised_windows' else 6)
                assert sum(len(x) for x, _ in fit_kwargs['validation_data'].as_numpy_iterator()) == 2
            for x, y in data.as_numpy_iterator():
                assert y.shape[-1] == len(classes) * 2
            for x, y in fit_kwargs['validation_data'].as_numpy_iterator():
                assert y.shape[-1] == len(classes) * 2
            assert all(np.array_equal(w.numpy(), old) for w, old in zip(model.weights, before))
            seen.append((classes, float(model.optimizer.learning_rate.numpy()), kwargs['weight_decay']))
            return SimpleNamespace(history={'loss': [1.], 'val_loss': [1.]})
        model.fit = no_fit
        return model

    monkeypatch.setattr(lung_models, 'build_model', builder)
    path = ROOT / f'configs/lung_training_{policy_name}.json'
    policy = json.loads(path.read_text())
    output = tmp_path / 'output'
    lung_training.train(tmp_path, audit, output, authorized=True, training_policy=path)
    classes = policy['classes'] or config['classes']
    assert seen[0][0] == classes
    assert seen[0][1] == pytest.approx(policy['optimizer']['initial_learning_rate'])
    assert seen[0][2] == policy['optimizer']['weight_decay']
    evaluation = json.loads((output / 'fold-0/evaluation.json').read_text())
    assert evaluation['classes'] == classes and len(evaluation['metrics']) == len(classes)
    source = json.loads((output / 'source.json').read_text())
    assert source['config'] == config and source['model_classes'] == classes


def test_comparison_rejects_support_group_and_role_changes():
    metric = {'tp': 2, 'fn': 1, 'tn': 4, 'fp': 1, 'sensitivity': 2/3, 'specificity': .8,
              'f1': 2/3, 'precision': 2/3, 'roc_auc': .7, 'pr_auc': .6}
    evaluation = {'role': 'development_only', 'groups': ['1'], 'classes': ['wheeze'],
                  'thresholds': [.5], 'metrics': [metric]}
    assert compare_evaluations(evaluation, evaluation)['wheeze']['deltas_from_L006']['f1'] == 0
    for candidate in ({**evaluation, 'groups': ['2']}, {**evaluation, 'role': 'official_test'},
                      {**evaluation, 'metrics': [{**metric, 'tp': 3}]}):
        with pytest.raises(ValueError):
            compare_evaluations(evaluation, candidate)
    with pytest.raises(PermissionError):
        run_queue(Path('missing'), Path('missing'), Path('missing'), Path('missing'), Path('missing'))


@pytest.mark.parametrize('pipeline_audit', [False, True])
def test_serial_queue_freezes_protocol_and_preserves_failed_runs(tmp_path, monkeypatch, pipeline_audit):
    tf = pytest.importorskip('tensorflow')
    from auriscore import lung_research_queue as queue
    from auriscore.acquisition_lung import digest
    cache = tmp_path / 'cache'; cache.mkdir()
    (cache / 'index.csv').write_text('fictional')
    audit = tmp_path / 'audit.json'; audit.write_text('{}')
    results = tmp_path / 'results'
    baseline = results / 'EXP-L006-control'; (baseline / 'fold-0').mkdir(parents=True)
    (baseline / 'status.json').write_text(json.dumps({'status': 'completed'}))
    (baseline / 'source.json').write_text(json.dumps({'config': CONFIG,
        'index_sha256': digest(cache / 'index.csv'), 'audit_sha256': digest(audit)}))
    metric = {'tp': 2, 'fn': 1, 'tn': 4, 'fp': 1, 'sensitivity': 2/3, 'specificity': .8,
              'f1': 2/3, 'precision': 2/3, 'roc_auc': .7, 'pr_auc': .6}
    evaluation = {'role': 'development_only', 'groups': ['1'], 'classes': CONFIG['classes'],
                  'thresholds': [.5] * 6, 'metrics': [metric] * 6}
    (baseline / 'fold-0/evaluation.json').write_text(json.dumps(evaluation))
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'schema_version': 'lung-development-queue-v1', 'baseline': baseline.name,
        'runs': [{'experiment_id': 'EXP-L007-fictional', 'policy': 'configs/lung_training_lower_lr.json', 'pipeline_audit': pipeline_audit},
                 {'experiment_id': 'EXP-L008-fictional', 'policy': 'configs/lung_training_weight_decay.json', 'comparison_baseline': 'EXP-L007-fictional'}]}))
    monkeypatch.setattr(queue, 'preflight', lambda *_: (CONFIG, None))
    monkeypatch.setattr(tf.config, 'list_physical_devices', lambda *_: [object()])
    monkeypatch.setattr(queue.subprocess, 'check_output', lambda *args, **kwargs: 'fictional-package==1.0\n')
    calls = []

    def command(arguments, **kwargs):
        calls.append(arguments)
        if '--authorized-training' in arguments:
            assert '--require-gpu' in arguments
            destination = Path(arguments[arguments.index('--output') + 1])
            if destination.name == 'EXP-L008-fictional':
                destination.mkdir()
                (destination / 'status.json').write_text('{"status":"failed"}')
                raise RuntimeError('fictional trainer failure')
            (destination / 'fold-0').mkdir(parents=True)
            (destination / 'fold-0/evaluation.json').write_text(json.dumps(evaluation))
        else:
            Path(arguments[arguments.index('--output') + 1]).write_text('{}')
    monkeypatch.setattr(queue.subprocess, 'run', command)
    output = tmp_path / 'evidence'
    with pytest.raises(RuntimeError, match='fictional trainer'):
        queue.run_queue(plan, cache, audit, results, output, authorized=True)
    status = json.loads((output / 'status.json').read_text())
    assert status['status'] == 'failed' and status['completed'] == ['EXP-L007-fictional']
    assert (output / 'protocol.json').exists()
    assert (results / 'EXP-L008-fictional/status.json').exists()
    assert len(calls) == (6 if pipeline_audit else 4)
    if pipeline_audit:
        assert any('--require-parity' in call for call in calls)
    with pytest.raises(ValueError, match='Fresh'):
        queue.run_queue(plan, cache, audit, results, output, authorized=True)
