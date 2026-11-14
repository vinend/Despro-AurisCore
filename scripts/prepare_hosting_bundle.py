"""Copy only hash-verified engineering model assets into a new private bundle.

No dataset, training, threshold selection, credential, upload or model promotion.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil

REQUIRED = {
    'heart': {'model', 'normalization', 'head'},
    'abdomen': {'model', 'metadata'},
    'lung': {'model', 'source', 'normalization', 'evaluation'},
}


def sha256(path: Path) -> str:
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(manifest: Path, output: Path) -> dict:
    """Verify every input before creating the collision-protected destination."""
    if output.exists():
        raise FileExistsError('Bundle output already exists; never overwrite it')
    original = json.loads(manifest.read_text(encoding='utf-8'))
    if original.get('scope') != 'engineering_test_only' or original.get('deployment_eligible') is not False:
        raise ValueError('Only explicit engineering assets are supported')
    if set(original.get('models', {})) != set(REQUIRED):
        raise ValueError('Exactly Heart, Lung and Abdomen assets are required')
    for mode, keys in REQUIRED.items():
        item = original['models'][mode]
        if set(item.get('hashes', {})) != keys:
            raise ValueError(f'{mode}: required asset hash set differs')
        for key in keys:
            if sha256(Path(item[key])) != item['hashes'][key]:
                raise ValueError(f'{mode}/{key}: input hash mismatch')
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    exported = deepcopy(original)
    evidence = {'schema': 'auriscore-hosting-bundle-v1', 'source_manifest_sha256': sha256(manifest),
                'scope': original['scope'], 'deployment_eligible': False, 'assets': []}
    for mode, keys in REQUIRED.items():
        (output / mode).mkdir()
        for key in sorted(keys):
            src = Path(original['models'][mode][key])
            relative = Path(mode) / (key + src.suffix)
            target = output / relative
            shutil.copyfile(src, target)
            if sha256(target) != original['models'][mode]['hashes'][key]:
                raise ValueError('Copied asset failed integrity check; incomplete bundle preserved')
            exported['models'][mode][key] = '/models/' + relative.as_posix()
            evidence['assets'].append({'path': relative.as_posix(), 'bytes': target.stat().st_size,
                                       'sha256': sha256(target)})
    (output / 'manifest.json').write_text(json.dumps(exported, indent=2) + '\n', encoding='utf-8')
    evidence['manifest_sha256'] = sha256(output / 'manifest.json')
    (output / 'bundle.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    return evidence


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.manifest.resolve(), args.output.resolve())
    print(json.dumps({'status': 'BUNDLE_PREPARED_NOT_DEPLOYED', 'asset_count': len(result['assets']),
                      'bytes': sum(item['bytes'] for item in result['assets']),
                      'manifest_sha256': result['manifest_sha256']}))
