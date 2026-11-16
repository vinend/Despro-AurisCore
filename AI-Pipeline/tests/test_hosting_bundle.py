"""Private bundle integrity/collision checks with generated files only."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('hosting_bundle', Path(__file__).resolve().parents[2] / 'scripts/prepare_hosting_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


def fixture(tmp_path):
    manifest = {'scope': 'engineering_test_only', 'deployment_eligible': False, 'models': {}}
    for mode, keys in bundle.REQUIRED.items():
        item = {'version': 'synthetic-test', 'threshold': 0.168, 'hashes': {}}
        for key in keys:
            file = tmp_path / f'{mode}-{key}.json'
            file.write_bytes(b'fictional test asset')
            item[key] = str(file)
            item['hashes'][key] = bundle.sha256(file)
        manifest['models'][mode] = item
    path = tmp_path / 'source.json'
    path.write_text(json.dumps(manifest))
    return path, manifest


def test_bundle_preserves_assets_thresholds_and_engineering_scope(tmp_path):
    path, original = fixture(tmp_path)
    before = path.read_bytes()
    output = tmp_path / 'out'
    evidence = bundle.prepare(path, output)
    exported = json.loads((output / 'manifest.json').read_text())
    assert path.read_bytes() == before
    assert len(evidence['assets']) == 9
    assert exported['deployment_eligible'] is False
    for mode, keys in bundle.REQUIRED.items():
        assert exported['models'][mode]['threshold'] == original['models'][mode]['threshold']
        for key in keys:
            remote = exported['models'][mode][key]
            assert remote.startswith('/models/' + mode + '/')
            assert bundle.sha256(output / remote.removeprefix('/models/')) == original['models'][mode]['hashes'][key]
    with pytest.raises(FileExistsError):
        bundle.prepare(path, output)


@pytest.mark.parametrize('fault', ['hash', 'missing', 'promotion'])
def test_invalid_source_creates_no_bundle(tmp_path, fault):
    path, manifest = fixture(tmp_path)
    if fault == 'hash':
        manifest['models']['heart']['hashes']['head'] = '0' * 64
    elif fault == 'missing':
        del manifest['models']['heart']['hashes']['head']
    else:
        manifest['deployment_eligible'] = True
    path.write_text(json.dumps(manifest))
    output = tmp_path / 'out'
    with pytest.raises(ValueError):
        bundle.prepare(path, output)
    assert not output.exists()
