"""Read-only model inventory and immutable candidate packaging; never trains."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import shutil
import tempfile
from typing import Any
import zipfile


def digest(path: Path) -> str:
    """Hash artifact bytes without loading executable model data."""
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'Expected JSON object: {path.name}')
    return value


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def audit_candidate(folder: Path, *, runtime: bool = False) -> dict[str, Any]:
    """Validate archive, tensor contract, normalization, and validation provenance."""
    result: dict[str, Any] = {
        'experiment_id': folder.name, 'structural_valid': False,
        'runtime': {'status': 'not_checked'}, 'deployment_eligible': False,
        'errors': [], 'warnings': [],
    }
    errors, warnings = result['errors'], result['warnings']
    try:
        model, metadata_path, metrics_path = (folder / name for name in
            ('heart_cnn.keras', 'heart_cnn.json', 'metrics.json'))
        metadata, metrics = read_json(metadata_path), read_json(metrics_path)
        config = metadata['config']
        if not isinstance(config, dict):
            raise ValueError('Preprocessing configuration must be an object')
        mode = 'abdomen' if folder.name.startswith('EXP-A') else 'heart'
        dataset = str(config.get('dataset_dir', ''))
        if (mode == 'abdomen' and 'bowel-sounds' not in dataset) or (mode == 'heart' and 'circor' not in dataset):
            raise ValueError('Experiment domain and dataset disagree')
        result.update(mode=mode, target='bowel_sound_activity' if mode == 'abdomen' else 'murmur_presence')
        threshold = metadata['decision_threshold']
        if not finite(threshold) or not 0 <= threshold <= 1:
            raise ValueError('Invalid decision threshold')
        if threshold != metrics['threshold_selection']['threshold']:
            raise ValueError('Metadata and evaluation thresholds disagree')
        for key in ('sample_rate', 'window_seconds', 'n_fft', 'hop_length', 'n_mels', 'cnn_top_db'):
            if not finite(config[key]) or config[key] <= 0:
                raise ValueError(f'Invalid preprocessing field: {key}')
        for key in ('sample_rate', 'n_fft', 'hop_length', 'n_mels'):
            if not isinstance(config[key], int):
                raise ValueError(f'Expected integer preprocessing field: {key}')
        if config['n_fft'] <= 1 or not 0 <= config.get('feature_fmin', 0) < config['feature_fmax'] <= config['sample_rate'] / 2:
            raise ValueError('Invalid spectrogram frequency range')
        if not finite(config['overlap']) or not 0 <= config['overlap'] < 1:
            raise ValueError('Invalid segmentation overlap')
        if config.get('filter_enabled') and not 0 < config['filter_low_hz'] < config['filter_high_hz'] < config['sample_rate'] / 2:
            raise ValueError('Invalid bandpass range')
        normalization = config.get('spectrogram_normalization', 'minmax')
        if normalization not in ('minmax', 'none', 'per_frequency'):
            raise ValueError('Unsupported normalization')
        if config.get('spectrogram_type', 'logmel') != 'logmel':
            raise ValueError('Candidate audit currently supports log-mel models only')
        if normalization == 'per_frequency':
            means, stds = config.get('spectrogram_frequency_mean', []), config.get('spectrogram_frequency_std', [])
            if len(means) != config['n_mels'] or len(stds) != config['n_mels'] or not all(finite(x) for x in means) or not all(finite(x) and x > 0 for x in stds):
                raise ValueError('Missing or invalid trained normalization statistics')
        samples = round(config['sample_rate'] * config['window_seconds'])
        frames = 1 + (samples if config.get('spectrogram_center', True) else samples - config['n_fft']) // config['hop_length']
        shape = [config['n_mels'], frames, 1]
        if metadata['input_shape'] != shape:
            raise ValueError('Metadata tensor shape disagrees with preprocessing')
        with zipfile.ZipFile(model) as archive:
            if archive.testzip() is not None:
                raise ValueError('Corrupt model archive')
            if not {'config.json', 'metadata.json', 'model.weights.h5'}.issubset(archive.namelist()):
                raise ValueError('Missing Keras archive components')
            architecture = json.loads(archive.read('config.json'))
            layers = architecture['config']['layers']
            inputs = [layer['config'] for layer in layers if layer['class_name'] == 'InputLayer']
            if len(inputs) != 1 or list(inputs[0].get('batch_shape', inputs[0].get('batch_input_shape', [])))[1:] != shape:
                raise ValueError('Keras input shape disagrees with metadata')
            output = layers[-1]['config']
            if output.get('units') != 1 or output.get('activation') != 'sigmoid':
                raise ValueError('Expected binary sigmoid output')
        subjects = metrics.get('development_split_counts', {}).get('validation', {}).get('subjects')
        result.update(input_shape=shape, decision_threshold=threshold,
            threshold_unit=metadata.get('threshold_selection', {}).get('selection_unit', 'linked participant'),
            validation_subjects=subjects,
            validation_summary=metrics.get('validation', {}).get('subject', {}), preprocessing=config,
            artifacts={p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in (model, metadata_path, metrics_path)})
        if mode == 'abdomen':
            warnings.append('Legacy metadata uses Heart/murmur names; normalized package target is bowel_sound_activity.')
            warnings.append('Window activity threshold must not be reused for recording means without evaluation.')
        else:
            warnings.append('Participant-selected threshold does not establish a single-WAV decision rule.')
        if not isinstance(subjects, int) or subjects < 2:
            warnings.append('Validation contains fewer than two independent participants.')
        warnings.append('No frozen deployment decision exists; candidate package is not production-authorized.')
        result['structural_valid'] = True
        if runtime:
            result['runtime'] = runtime_probe(model, metadata)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        errors.append(str(exc))
    return result


def runtime_probe(model_path: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    """Exercise trained weights with deterministic synthetic audio, not evaluation data."""
    try:
        import numpy as np
        from .cnn import require_tensorflow
        from .preprocessing import preprocess
        from .spectrogram import extract_spectrogram_tensor
        config = metadata['config']
        sr = int(config['sample_rate'])
        t = np.arange(round(sr * config['window_seconds'])) / sr
        audio = 0.2 * np.sin(2 * np.pi * 180 * t) + 0.05 * np.sin(2 * np.pi * 360 * t)
        tensor = extract_spectrogram_tensor(preprocess(audio, sr, config), config)[None, ..., None]
        model = require_tensorflow().keras.models.load_model(model_path, compile=False, safe_mode=True)
        first = np.asarray(model(tensor, training=False)).reshape(-1)
        second = np.asarray(model(tensor, training=False)).reshape(-1)
        if first.shape != (1,) or not np.isfinite(first).all() or not ((0 <= first) & (first <= 1)).all() or not np.allclose(first, second, rtol=1e-6, atol=1e-7):
            raise ValueError('Nonfinite, invalid, or nondeterministic prediction')
        return {'status': 'passed', 'input_shape': list(tensor.shape), 'synthetic_score': float(first[0]),
                'note': 'Loadability check only; no performance or calibration claim.'}
    except Exception as exc:
        return {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}


def audit_repository(root: Path, *, runtime: bool = False) -> dict[str, Any]:
    """Inventory saved CNNs and preserve the H021 deployment prohibition."""
    candidates = [audit_candidate(path, runtime=runtime) for path in sorted((root / 'results').glob('EXP-*'))
                  if (path / 'heart_cnn.keras').exists()]
    freeze_path = root / 'analysis/HEART-DEVELOPMENT-FREEZE-H021/artifact_manifest.json'
    expected_manifest = (freeze_path.parent / 'artifact_manifest_sha256.txt').read_text().strip()
    if digest(freeze_path) != expected_manifest:
        raise ValueError('H021 freeze manifest hash mismatch; preserve original artifact bytes')
    freeze = read_json(freeze_path)
    for name in ('protocol.json', 'config.json', 'metrics.json'):
        if digest(freeze_path.parent / name) != freeze['frozen_files'][name]['sha256']:
            raise ValueError(f'H021 frozen file hash mismatch: {name}')
    if (freeze.get('deployment', {}).get('status') != 'unavailable'
            or freeze['deployment'].get('final_model_exists') is not False
            or freeze['deployment'].get('predeclared_ensemble') is not False
            or [fold['fold'] for fold in freeze.get('folds', [])] != [1, 2, 3, 4, 5]):
        raise ValueError('Unexpected H021 deployment state; re-audit the declared protocol')
    fold_artifacts = []
    for fold in freeze.get('folds', []):
        for role in ('stage1_model', 'normalization', 'scaler_logistic'):
            entry = fold['artifacts'][role]
            path = (root / entry['path']).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError('Unsafe H021 artifact path')
            status = 'missing'
            if path.is_file():
                status = 'verified' if digest(path) == entry['sha256'] else 'hash_mismatch'
            fold_artifacts.append({'fold': fold['fold'], 'role': role, 'path': entry['path'], 'status': status})
    a005 = next((item for item in candidates if item['experiment_id'] == 'EXP-A005-abdomen-cnn-residual-se'), None)
    return {'schema_version': 'model-audit-v1', 'candidates': candidates,
            'h021': {'deployment': freeze['deployment'], 'manifest_sha256': digest(freeze_path), 'fold_artifacts': fold_artifacts},
            'selection': {
                'heart': {'deployment_model': None, 'reason': 'H021 is evaluation-only; older CNNs have no validated deployment rule.'},
                'abdomen': {'engineering_candidate': a005['experiment_id'] if a005 and a005['structural_valid'] else None,
                            'deployment_model': None, 'reason': 'A005 is a preliminary candidate, not a validated production selection.'}}}


def package_candidate(folder: Path, destination: Path, *, runtime: bool = False) -> Path:
    """Publish an immutable, hash-bound candidate without modifying its experiment."""
    audit = audit_candidate(folder, runtime=runtime)
    if not audit['structural_valid'] or (runtime and audit['runtime']['status'] != 'passed'):
        raise ValueError(f'Candidate failed audit: {audit}')
    if destination.exists():
        raise FileExistsError(f'Refusing to overwrite candidate: {destination}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix='.candidate-', dir=destination.parent))
    try:
        for original, renamed in [('heart_cnn.keras', 'model.keras'), ('heart_cnn.json', 'source_metadata.json'), ('metrics.json', 'source_metrics.json')]:
            shutil.copyfile(folder / original, temporary / renamed)
            if digest(temporary / renamed) != audit['artifacts'][original]['sha256']:
                raise ValueError('Artifact changed during packaging')
        manifest = {'schema_version': 'model-candidate-v1', 'experiment_id': folder.name,
            'mode': audit['mode'], 'target': audit['target'], 'classes': ['absent', 'present'],
            'status': 'engineering_candidate', 'deployment_eligible': False,
            'preprocessing': audit['preprocessing'], 'input_shape': audit['input_shape'],
            'threshold': {'value': audit['decision_threshold'], 'selection_unit': audit['threshold_unit'], 'inference_rule': None},
            'runtime': audit['runtime'], 'limitations': audit['warnings'],
            'files': {p.name: {'sha256': digest(p), 'bytes': p.stat().st_size} for p in sorted(temporary.iterdir())}}
        (temporary / 'manifest.json').write_text(json.dumps(manifest, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        temporary.rename(destination)
    finally:
        if temporary.exists():
            if temporary.resolve().parent != destination.parent.resolve():
                raise ValueError('Unsafe temporary candidate cleanup path')
            shutil.rmtree(temporary)
    return destination


def verify_package(folder: Path) -> dict[str, Any]:
    """Reject changed, incomplete, or unsafe candidate package contents."""
    manifest = read_json(folder / 'manifest.json')
    if manifest.get('schema_version') != 'model-candidate-v1' or manifest.get('deployment_eligible') is not False:
        raise ValueError('Unsupported candidate manifest or unauthorized deployment promotion')
    if set(manifest['files']) != {'model.keras', 'source_metadata.json', 'source_metrics.json'}:
        raise ValueError('Unexpected candidate file inventory')
    for name, expected in manifest['files'].items():
        path = folder / name
        if path.is_symlink() or not path.is_file() or digest(path) != expected['sha256'] or path.stat().st_size != expected['bytes']:
            raise ValueError(f'Candidate integrity failure: {name}')
    metadata = read_json(folder / 'source_metadata.json')
    if manifest['preprocessing'] != metadata['config'] or manifest['input_shape'] != metadata['input_shape'] or manifest['threshold']['value'] != metadata['decision_threshold']:
        raise ValueError('Candidate contract differs from source metadata')
    mode = 'abdomen' if manifest['experiment_id'].startswith('EXP-A') else 'heart'
    target = 'bowel_sound_activity' if mode == 'abdomen' else 'murmur_presence'
    if (manifest['mode'] != mode or manifest['target'] != target
            or manifest['classes'] != ['absent', 'present']
            or manifest['status'] != 'engineering_candidate'
            or manifest['threshold']['inference_rule'] is not None
            or manifest['threshold']['selection_unit'] != metadata.get('threshold_selection', {}).get('selection_unit', 'linked participant')):
        raise ValueError('Candidate contract changes domain or threshold semantics')
    return manifest
