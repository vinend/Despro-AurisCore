"""Artifact-contract, corruption and immutable packaging regression checks."""
import json
from pathlib import Path
import shutil

import pytest

from auriscore.model_audit import audit_candidate, audit_repository, package_candidate, verify_package

ROOT = Path(__file__).resolve().parents[1]
A005 = ROOT / 'results/EXP-A005-abdomen-cnn-residual-se'


@pytest.fixture
def candidate(tmp_path):
    folder = tmp_path / A005.name
    folder.mkdir()
    for name in ('heart_cnn.keras', 'heart_cnn.json', 'metrics.json'):
        shutil.copyfile(A005 / name, folder / name)
    return folder


def mutate_metadata(folder, change):
    path = folder / 'heart_cnn.json'
    value = json.loads(path.read_text())
    change(value)
    path.write_text(json.dumps(value))


def test_real_inventory_preserves_deployment_boundary():
    report = audit_repository(ROOT)
    assert len(report['candidates']) >= 13
    assert all(item['structural_valid'] for item in report['candidates'])
    assert report['selection']['abdomen']['engineering_candidate'] == A005.name
    assert report['selection']['heart']['deployment_model'] is None
    assert report['h021']['deployment']['final_model_exists'] is False
    assert len(report['h021']['fold_artifacts']) == 15
    assert all(not item['deployment_eligible'] for item in report['candidates'])


@pytest.mark.parametrize('change', [
    lambda m: m.update(decision_threshold=float('nan')),
    lambda m: m.update(decision_threshold=0.5),
    lambda m: m.update(input_shape=[40, 100, 1]),
    lambda m: m['config'].update(spectrogram_frequency_std=[0] * 40),
    lambda m: m['config'].update(spectrogram_frequency_mean=[]),
    lambda m: m['config'].update(feature_fmax=9000),
    lambda m: m['config'].update(overlap=1),
    lambda m: m['config'].update(dataset_dir='data/external/circor'),
    lambda m: m['config'].update(n_fft=512.5),
])
def test_reject_incompatible_contract(candidate, change):
    mutate_metadata(candidate, change)
    result = audit_candidate(candidate)
    assert not result['structural_valid']
    assert result['errors']


def test_missing_weights_is_explicit(candidate):
    (candidate / 'heart_cnn.keras').unlink()
    assert not audit_candidate(candidate)['structural_valid']


def test_corrupt_archive_is_rejected(candidate):
    (candidate / 'heart_cnn.keras').write_bytes(b'not a keras archive')
    assert not audit_candidate(candidate)['structural_valid']


def test_package_normalizes_domain_and_preserves_sources(candidate, tmp_path):
    original = (candidate / 'heart_cnn.json').read_bytes()
    destination = tmp_path / 'packages/abdomen-a005-v1'
    package_candidate(candidate, destination)
    manifest = verify_package(destination)
    assert manifest['mode'] == 'abdomen'
    assert manifest['target'] == 'bowel_sound_activity'
    assert manifest['threshold']['inference_rule'] is None
    assert not manifest['deployment_eligible']
    assert (candidate / 'heart_cnn.json').read_bytes() == original
    with pytest.raises(FileExistsError):
        package_candidate(candidate, destination)


def test_package_detects_changed_weights(candidate, tmp_path):
    destination = tmp_path / 'package'
    package_candidate(candidate, destination)
    with (destination / 'model.keras').open('ab') as stream:
        stream.write(b'tampered')
    with pytest.raises(ValueError, match='integrity'):
        verify_package(destination)


def test_package_detects_changed_contract(candidate, tmp_path):
    destination = tmp_path / 'package'
    package_candidate(candidate, destination)
    path = destination / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest['threshold']['value'] = 0.5
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='contract'):
        verify_package(destination)


def test_bad_candidate_cannot_be_packaged(candidate, tmp_path):
    mutate_metadata(candidate, lambda m: m.update(input_shape=[1, 2, 3]))
    destination = tmp_path / 'package'
    with pytest.raises(ValueError, match='failed audit'):
        package_candidate(candidate, destination)
    assert not destination.exists()


@pytest.mark.parametrize('field,value', [('mode', 'heart'), ('target', 'disease'), ('deployment_eligible', True)])
def test_package_rejects_semantic_promotion(candidate, tmp_path, field, value):
    destination = tmp_path / 'package'
    package_candidate(candidate, destination)
    path = destination / 'manifest.json'
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        verify_package(destination)
