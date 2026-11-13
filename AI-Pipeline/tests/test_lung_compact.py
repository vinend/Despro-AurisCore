"""Compact-model shape/provenance and masked error-cue checks; no weights fitted."""
import json
from pathlib import Path
import numpy as np
import pytest
import yaml
from auriscore.lung_training_policy import validate_policy, load_policy, model_bottleneck, final_learning_rates
from auriscore.lung_error_review import window_errors
from auriscore.lung_research_queue import compare_evaluations

ROOT = Path(__file__).parents[1]
CONFIG = yaml.safe_load((ROOT / 'configs/lung_cnn.yaml').read_text())
POLICY = json.loads((ROOT / 'configs/lung_training_compact_phase.json').read_text())


@pytest.mark.parametrize('channels', [None, True, 0, 63, 256, '64', 1.5])
def test_compact_policy_requires_explicit_valid_channels(channels):
    policy = {**POLICY, 'model': {**POLICY['model'], 'bottleneck_channels': channels}}
    with pytest.raises(ValueError, match='[Bb]ottleneck'):
        validate_policy(policy, CONFIG)


def test_compact_policy_replay_and_legacy_model_are_separate():
    frozen, rates = final_learning_rates({'epochs': 2, 'training_policy': POLICY}, CONFIG)
    assert model_bottleneck(frozen) == 64 and rates is None
    assert model_bottleneck(load_policy(ROOT / 'configs/lung_training_phase_only.json', CONFIG)) is None
    with pytest.raises(ValueError):
        validate_policy({**POLICY, 'schema_version': 'lung-training-policy-v4'}, CONFIG)


@pytest.mark.parametrize('task,expected', [('phase', 93186), ('sound', 93316)])
def test_compact_model_reduces_capacity_preserves_time_and_survives_save(tmp_path, task, expected):
    tf = pytest.importorskip('tensorflow')
    from auriscore.lung_models import build_model
    policy = load_policy(ROOT / f'configs/lung_training_compact_{task}.json', CONFIG)
    classes = policy['classes']
    baseline = build_model((309, 96), classes, temporal_dilation=16)
    model = build_model((309, 96), classes, temporal_dilation=16, bottleneck_channels=64)
    assert model.output_shape == baseline.output_shape == (None, 309, len(classes))
    assert model.count_params() == expected and model.count_params() < baseline.count_params() * .4
    projection = model.get_layer('frequency_bottleneck')
    assert projection.kernel_size == (1,) and projection.filters == 64
    x = np.ones((1, 309, 96), np.float32)
    output = model(x, training=False).numpy()
    assert np.isfinite(output).all()
    model.save(tmp_path / 'model.keras')
    restored = tf.keras.models.load_model(tmp_path / 'model.keras', compile=False)
    np.testing.assert_allclose(restored(x, training=False).numpy(), output, atol=1e-6)
    assert int(model.optimizer.iterations.numpy()) == 0


def test_error_cues_respect_unknown_masks_and_legitimate_phase_overlap():
    y = np.array([[1, 0], [1, 1], [0, 1], [0, 0]], np.float32)
    p = np.ones_like(y) * .9
    m = np.ones_like(y); m[-1] = 0
    errors = window_errors(y, p, m, ['inhalation', 'exhalation'], [.5, .5], 4)
    assert errors['phase_conflict'][0].tolist() == [2]
    assert errors['phase_conflict'][1].tolist() == [3]
    assert errors['phase_fragmentation'][0].tolist() == [0]
    labels = ['crackle', 'stridor', 'rhonchi']
    y = np.array([[0, 1, 0], [1, 1, 1]], np.float32)
    p = np.array([[.9, .1, .1], [.1, .1, .1]], np.float32)
    m = np.ones_like(y); m[1, 1] = 0
    errors = window_errors(y, p, m, labels, [.5] * 3, 2)
    assert errors['crackle_false_positive'][0].tolist() == [1]
    assert errors['stridor_miss'][0].tolist() == [1]
    assert errors['rhonchi_miss'][0].tolist() == [1]
    with pytest.raises(ValueError):
        window_errors(y, p, m, labels, [.5] * 3, 3)


def test_matching_control_identity_is_not_mislabeled_l006():
    metric = {'tp': 2, 'fn': 1, 'tn': 4, 'fp': 1, 'sensitivity': 2/3, 'specificity': .8,
              'f1': 2/3, 'precision': 2/3, 'roc_auc': .7, 'pr_auc': .6}
    evaluation = {'role': 'development_only', 'groups': ['1'], 'classes': ['inhalation'],
                  'thresholds': [.5], 'metrics': [metric]}
    result = compare_evaluations(evaluation, evaluation, baseline_id='EXP-L010-phase-only')['inhalation']
    assert result['comparison_baseline'] == 'EXP-L010-phase-only'
    assert result['deltas_from_baseline']['pr_auc'] == 0
    assert 'deltas_from_L006' not in result
