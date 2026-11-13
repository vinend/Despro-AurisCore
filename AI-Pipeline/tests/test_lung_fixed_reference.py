"""Opt-in fixed Lung features preserve legacy tensors, targets and shared branches."""
import copy
from pathlib import Path
import numpy as np
import pytest
import yaml
from auriscore.lung_preprocessing import windows, extract_lung_features, validate_config, config_digest
from auriscore.spectrogram import extract_spectrogram_tensor

ROOT = Path(__file__).parents[1]


def configs():
    return [yaml.safe_load((ROOT / f'configs/{name}.yaml').read_text())
            for name in ('lung_cnn', 'lung_cnn_fixed_reference')]


def test_fixed_reference_overlap_is_identical_and_legacy_is_unchanged():
    old, new = configs()
    assert {k: v for k, v in new.items() if k != 'lung_feature_policy'} == old
    assert config_digest(old) != config_digest(new)
    rng = np.random.default_rng(42)
    audio = rng.normal(0, .02, 60000).astype(np.float32)
    audio[:4000] += np.sin(2*np.pi*500*np.arange(4000)/8000).astype(np.float32)
    a, b = audio[:40000], audio[19968:59968]
    np.testing.assert_array_equal(extract_lung_features(a, old), extract_spectrogram_tensor(a, old).T)
    first, second = extract_lung_features(a, new), extract_lung_features(b, new)
    np.testing.assert_allclose(first[156:], second[:len(first)-156], atol=1e-5, rtol=0)
    # Shared Heart/Abdomen feature extractor remains independent of this Lung-only key.
    np.testing.assert_array_equal(extract_spectrogram_tensor(a, old), extract_spectrogram_tensor(a, new))
    silent = extract_lung_features(np.zeros(40000, np.float32), new)
    np.testing.assert_array_equal(silent, np.full_like(silent, -80))


def test_targets_masks_timestamps_and_physical_tail_stay_identical():
    old, new = configs()
    audio = np.random.default_rng(4).normal(size=61000).astype(np.float32)
    labels = [{'label': 'inhalation', 'start_s': .2, 'end_s': 6.9},
              {'label': 'crackle', 'start_s': 3.1, 'end_s': 3.4}]
    a, b = [list(windows(audio, 8000, labels, c, valid_end_s=7.2, coverage=True)) for c in (old, new)]
    assert len(a) == len(b)
    for left, right in zip(a, b):
        for key in ('targets', 'mask', 'times_s', 'start_sample'):
            np.testing.assert_array_equal(left[key], right[key])
        end = right['times_s'] + new['n_fft']/(2*new['sample_rate'])
        assert np.all(right['mask'][end > 7.2] == 0)
        assert np.isfinite(right['features']).all()


@pytest.mark.parametrize('key,value', [('reference_power', True), ('reference_power', 0),
    ('floor_db', float('nan')), ('floor_db', -1000), ('schema_version', 'unknown')])
def test_invalid_fixed_policy_is_rejected(key, value):
    config = copy.deepcopy(configs()[1]); config['lung_feature_policy'][key] = value
    with pytest.raises(ValueError, match='feature policy'):
        validate_config(config)
