"""Opt-in stable gradients, TRAIN-only objective weighting and legacy replay."""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import yaml

from auriscore.lung_objective import plan_supervision
from auriscore.lung_training_policy import load_policy, loss_settings, validate_policy

ROOT = Path(__file__).parents[1]


def test_closed_policy_and_one_factor_sequence():
    config = yaml.safe_load((ROOT / 'configs/lung_cnn.yaml').read_text())
    old = load_policy(ROOT / 'configs/lung_training_three_sound.json', config)
    policies = [load_policy(ROOT / f'configs/lung_training_{name}.json', config)
                for name in ('stable_loss', 'window_objective', 'supervised_windows')]
    assert loss_settings(old) == {'numerics': 'legacy_clip', 'positive_weighting': 'global_frame',
                                  'empty_training_windows': 'keep'}
    assert {k: v for k, v in old.items() if k != 'schema_version'} == {
        k: v for k, v in policies[0].items() if k not in ('loss', 'runtime', 'schema_version')}
    for previous, following, key in zip(policies, policies[1:], ('positive_weighting', 'empty_training_windows')):
        expected = copy.deepcopy(previous)
        expected['loss'][key] = following['loss'][key]
        assert expected == following
    for key, value in [('numerics', 'arbitrary'), ('positive_weighting', 'validation'),
                       ('empty_training_windows', True), ('unknown', 'silent')]:
        bad = copy.deepcopy(policies[0]); bad['loss'][key] = value
        with pytest.raises(ValueError):
            validate_policy(bad, config)
    with pytest.raises(ValueError):
        validate_policy({**policies[0], 'extra': 1}, config)


def test_supervision_weights_match_actual_window_risk_and_ignore_heldout(tmp_path):
    rows = []
    for name, size, label, active in [('positive', 10, 1, 1), ('negative', 100, 0, 1), ('empty', 20, 1, 0)]:
        y = np.full((size, 1), label, np.float32)
        np.savez(tmp_path / f'{name}.npz', features=np.zeros((size, 8)), targets=y,
                 mask=np.full_like(y, active))
        rows.append({'file': f'{name}.npz', 'split': 'train', 'group': 'a'})
    (tmp_path / 'validation.npz').write_bytes(b'held-out sentinel must not be read')
    (tmp_path / 'official-test.npz').write_bytes(b'sealed sentinel')
    rows = pd.DataFrame(rows)
    settings = {'positive_weighting': 'global_frame', 'empty_training_windows': 'keep'}
    selected, weights, report = plan_supervision(tmp_path, rows, [0], settings)
    assert weights.tolist() == [10.] and len(selected) == 3 and report['empty_windows'] == 1
    selected, weights, report = plan_supervision(tmp_path, rows, [0],
        {**settings, 'positive_weighting': 'window_mass', 'empty_training_windows': 'drop'})
    assert weights.tolist() == [1.]
    assert selected.file.tolist() == ['positive.npz', 'negative.npz']
    assert report['positive_mass'] == report['negative_mass'] == [1.]
    with pytest.raises(ValueError, match='Official test'):
        plan_supervision(tmp_path, pd.DataFrame([{'file': 'official-test.npz', 'split': 'test'}]), [0], settings)
    with pytest.raises(ValueError, match='Unsafe'):
        plan_supervision(tmp_path, pd.DataFrame([{'file': '../escape.npz'}]), [0], settings)
    with pytest.raises(ValueError, match='positive/negative'):
        plan_supervision(tmp_path, rows.iloc[:1], [0], settings)


@pytest.mark.parametrize('numerics', ['legacy_clip', 'stable_bce'])
def test_actual_dense_path_extreme_gradients_and_mask(numerics):
    tf = pytest.importorskip('tensorflow')
    from auriscore.lung_models import build_model
    model = build_model((8, 16), ['wheeze', 'rhonchi', 'crackle'],
                        positive_weights=[6., 6., 6.], loss_numerics=numerics)
    dense = model.layers[-1]
    dense.kernel.assign(tf.zeros_like(dense.kernel))
    dense.bias.assign([30., -30., .5])
    x = tf.zeros((1, 8, 16))
    truth = tf.broadcast_to([0., 1., 1.], (1, 8, 3))
    mask = tf.broadcast_to([1., 1., 0.], (1, 8, 3))
    with tf.GradientTape() as tape:
        probability = model(x, training=False)
        loss = tf.reduce_sum(model.loss(tf.concat([truth, mask], axis=-1), probability))
    gradients = tape.gradient(loss, model.trainable_variables)
    assert all(g is not None and np.isfinite(g.numpy()).all() for g in gradients)
    gradient = gradients[-1].numpy()
    expected = [0., 0., 0.] if numerics == 'legacy_clip' else [.5, -3., 0.]
    np.testing.assert_allclose(gradient, expected, atol=1e-6)
    assert np.isfinite(loss.numpy())
    assert model.optimizer.iterations.numpy() == 0


def test_stable_loss_matches_logits_reference_and_saved_inference(tmp_path):
    tf = pytest.importorskip('tensorflow')
    from auriscore.lung_models import build_model
    tf.keras.utils.set_random_seed(42)
    # CPU provides an explicit deterministic reference for artifact reload.
    with tf.device('/CPU:0'):
        model = build_model((8, 16), ['wheeze', 'crackle'], positive_weights=[2., 3.], loss_numerics='stable_bce')
        x = tf.random.normal((2, 8, 16))
        truth = tf.cast(tf.random.uniform((2, 8, 2)) > .5, tf.float32)
        mask = tf.cast(tf.random.uniform((2, 8, 2)) > .3, tf.float32)
        p = model(x, training=False)
        h = tf.keras.Model(model.inputs, model.layers[-2].output)(x, training=False)
        logits = tf.linalg.matmul(h, model.layers[-1].kernel) + model.layers[-1].bias
        expected = tf.nn.sigmoid_cross_entropy_with_logits(labels=truth, logits=logits) * (1-truth+truth*[2., 3.])
        expected = tf.reduce_sum(expected*mask, axis=(1, 2))/tf.maximum(tf.reduce_sum(mask, axis=(1, 2)), 1.)
        np.testing.assert_allclose(model.loss(tf.concat([truth, mask], -1), p), expected, atol=1e-6)
        assert np.all(model.loss(tf.concat([truth, tf.zeros_like(mask)], -1), p) == 0)
        path = tmp_path / 'model.keras'; model.save(path)
        reloaded = tf.keras.models.load_model(path, compile=False)
        np.testing.assert_array_equal(reloaded(x, training=False), p)
        assert model.optimizer.iterations.numpy() == 0


def test_stratified_fixed_threshold_metrics_preserve_support_and_undefined_auc():
    from auriscore.lung_diagnostics import stratified_scores
    y = np.array([[[1], [0]], [[0], [0]]], np.float32)
    p = np.array([[[.8], [.7]], [[.2], [.1]]], np.float32)
    report = stratified_scores(y, p, np.ones_like(y), ['crackle'], [.5], ['a', 'b'], ['x', 'y'])
    a = report['device']['a']['metrics']['crackle']
    b = report['device']['b']['metrics']['crackle']
    assert (a['tp'], a['fp'], b['tn']) == (1, 1, 2)
    assert b['roc_auc'] is None and b['pr_auc'] is None
    assert report['thresholds_reselected'] is False
    with pytest.raises(ValueError, match='Aligned'):
        stratified_scores(y, p, np.ones_like(y), ['crackle'], [.5], ['a'], ['x', 'y'])
