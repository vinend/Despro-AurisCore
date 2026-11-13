"""Frozen-review invariants: masks, weighted risk and overlapping frame identity."""
import numpy as np
import pytest
from auriscore.lung_deep_review import window_loss_matrix, inverse_positive_weight, merge_record_windows, conditional_auc


def test_window_terms_match_manual_masked_loss_and_empty_window():
    y = np.array([[[1., 0.], [0., 1.]], [[1., 1.], [1., 1.]]])
    p = np.full_like(y, .25); m = np.ones_like(y); m[1] = 0
    w = np.array([2., 3.])
    loss = window_loss_matrix(y, p, m, w)
    assert loss[0].sum() == pytest.approx(float((-(y[0]*np.log(.25)*w + (1-y[0])*np.log(.75))).mean()))
    assert loss[1].sum() == 0


def test_weighted_posterior_inverse_is_identity_for_unit_weight_and_order_preserving():
    y = np.array([[.1, .2], [.3, .7], [.9, .95]])
    np.testing.assert_allclose(inverse_positive_weight(y, np.ones(2)), y)
    corrected = inverse_positive_weight(y, np.array([2., 3.]))
    assert np.all(np.diff(corrected, axis=0) > 0)
    assert inverse_positive_weight(np.array([[2/3]]), np.array([2.]))[0, 0] == pytest.approx(.5)


def test_overlap_merge_excludes_padding_and_measures_context_disagreement():
    y = np.array([[[0.], [1.], [0.]], [[1.], [0.], [1.]]])
    p = np.array([[[.1], [.2], [.3]], [[.8], [.9], [.99]]])
    m = np.ones_like(y)
    merged = merge_record_windows(y, p, m, np.array([0, 1]), 3, np.array([.5]), margin=0)
    np.testing.assert_allclose(merged['scores'][:, 0], [.1, .5, .6])
    assert merged['disagreement']['all']['valid_repeated'] == [2]
    assert merged['disagreement']['all']['threshold_crossings'] == [2]
    assert conditional_auc(merged['truth'], merged['scores'], merged['mask'])[0]['positive'] == 1
    bad = y.copy(); bad[1, 0, 0] = 0
    with pytest.raises(ValueError, match='Conflicting'):
        merge_record_windows(bad, p, m, np.array([0, 1]), 3, np.array([.5]))


def test_feature_probe_detects_reference_shift_for_identical_shared_audio():
    from pathlib import Path
    import yaml
    from auriscore.spectrogram import extract_spectrogram_tensor
    config = yaml.safe_load((Path(__file__).parents[1] / 'configs/lung_cnn.yaml').read_text())
    rng = np.random.default_rng(42)
    audio = rng.normal(0, .02, 60000).astype(np.float32)
    # Loud energy outside the shared audio affects the first window's dB reference.
    audio[:4000] += np.sin(2*np.pi*500*np.arange(4000)/8000).astype(np.float32)
    first = extract_spectrogram_tensor(audio[:40000], config).T
    second = extract_spectrogram_tensor(audio[19968:59968], config).T
    difference = first[156:]-second[:len(first)-156]
    assert abs(float(np.median(difference))) > 10
    assert float(np.mean(np.abs(difference-np.median(difference)))) < 1e-3
