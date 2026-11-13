"""Immutable HF control cache plus audited SPRSound TRAIN acoustic windows."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import resample_poly
import soundfile as sf

from .acquisition_lung import digest
from .lung_preprocessing import windows
from .lung_training import preflight
from .sprsound import REVISION, parse_annotation, acoustic_mask


def normalized_fingerprint(audio: np.ndarray, rate: int) -> str:
    """Additional gain/DC normalized 4-kHz hash; not exhaustive acoustic deduplication."""
    import math
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    divisor = math.gcd(rate, 4000)
    mono = resample_poly(mono.astype(np.float64), 4000 // divisor, rate // divisor)
    mono -= mono.mean()
    return hashlib.sha256(np.round(mono / max(float(np.max(np.abs(mono))), 1e-12) * 4096).astype('<i2').tobytes()).hexdigest()


def build_cache(base_cache: Path, base_audit: Path, source: Path, output: Path) -> dict:
    """Keep HF validation unchanged; append source TRAIN with phases masked.

    Original HF cache payloads are hard-linked read-only by convention. No source
    payload or metadata is edited. New artifacts always use a fresh directory.
    """
    base_cache, base_audit, source, output = map(Path, (base_cache, base_audit, source, output))
    config, index = preflight(base_cache, base_audit)
    receipt = json.loads((source / 'receipt.json').read_text())
    if (receipt.get('revision') != REVISION or receipt.get('official_test_labels_opened') is not False
            or receipt.get('official_test_audio_downloaded') is not False):
        raise ValueError('Pinned TRAIN-only source receipt required')
    if output.exists():
        raise ValueError('Never overwrite a multi-source cache')
    receipts = {entry['path']: entry for entry in receipt['files']}
    license_path = source / 'LICENSE'
    if digest(license_path) != receipts['LICENSE']['sha256'] or 'Attribution 4.0 International' not in license_path.read_text():
        raise ValueError('Pinned source license required')
    records = pd.read_csv(base_audit.parent / 'recordings.csv', dtype={'group': str})
    events = pd.read_csv(base_audit.parent / 'events.csv')
    hashes = set(records.sha256)
    normalized = set(records.normalized_pcm_sha256.dropna())
    added, event_rows, blocks = [], [], []
    rejected = []
    observed = {}
    patient_support = {}
    # Prepare and validate source records before creating the new cache.
    label_paths = [source / path for path in receipts if path.startswith('BioCAS2022/train2022_json/') and path.endswith('.json')]
    for label_path in sorted(label_paths):
        stem = label_path.stem
        audio_path = source / 'BioCAS2022/train2022_wav' / f'{stem}.wav'
        if any(digest(path) != receipts[path.relative_to(source).as_posix()]['sha256'] for path in (label_path, audio_path)):
            raise ValueError('Source changed after acquisition audit')
        try:
            x, rate = sf.read(audio_path, dtype='float32', always_2d=True)
            duration = len(x) / rate
            if (not x.size or not np.isfinite(x).all() or rate < 4000 or duration < 5
                    or np.mean(np.abs(x) >= .999) > .01 or np.std(x) < 1e-6):
                raise ValueError('Invalid/short/clipped/silent audio')
            labels, coverage = parse_annotation(json.loads(label_path.read_text()), duration)
            fingerprint = normalized_fingerprint(x, rate)
            sha = digest(audio_path)
            if sha in hashes or fingerprint in normalized:
                raise ValueError('Duplicate audio or normalized-PCM match')
            hashes.add(sha); normalized.add(fingerprint)
            identity = f'spr2022_{stem}'
            patient = stem.split('_')[0]
            group = 'spr2022:' + hashlib.sha256(patient.encode()).hexdigest()[:20]
            for event in labels:
                observed[event['label']] = observed.get(event['label'], 0) + 1
                patient_support.setdefault(event['label'], set()).add(group)
            added.append({'recording_id': identity, 'group': group, 'device': 'SPRSound-Yunting-II', 'source': 'SPRSound-2022',
                          'file_path': str(audio_path), 'label_path': str(label_path), 'original_split': 'train',
                          'split': 'train', 'sample_rate': rate, 'channels': x.shape[1], 'duration_s': duration,
                          'valid_end_s': duration, 'sha256': sha, 'label_sha256': digest(label_path),
                          'normalized_pcm_sha256': fingerprint, 'quality': 'ok', 'license': 'CC-BY-4.0'})
            event_rows.extend({**event, 'recording_id': identity} for event in labels)
            blocks.append((identity, group, sha, audio_path, labels, coverage, duration))
        except ValueError as error:
            rejected.append({'recording_id': 'spr2022_' + stem, 'reason': str(error)})
    if not added:
        raise ValueError('No eligible source data survived audit')
    output.mkdir(parents=True)
    cache = output / 'cache'; cache.mkdir()
    for row in index.itertuples():
        os.link(base_cache / row.file, cache / row.file)
    new_index = []
    for position, (identity, group, sha, audio_path, labels, coverage, duration) in enumerate(blocks, 1):
        x, rate = sf.read(audio_path, dtype='float32', always_2d=True)
        for block in windows(x, rate, labels, config, valid_end_s=duration, coverage=False):
            block['mask'] = acoustic_mask(block, coverage, config, duration)
            if not np.any(block['mask']):
                continue
            name = f"{identity}_{block['start_sample']}.npz"
            np.savez_compressed(cache / name, **block)
            new_index.append({'file': name, 'group': group, 'recording_id': identity,
                              'split': 'train', 'source_sha256': sha})
        if position % 100 == 0 or position == len(blocks):
            print(f'Prepared source recordings {position}/{len(blocks)}', flush=True)
    combined = pd.concat([index, pd.DataFrame(new_index)], ignore_index=True)
    combined.to_csv(cache / 'index.csv', index=False)
    all_records = pd.concat([records, pd.DataFrame(added)], ignore_index=True)
    all_records.to_csv(output / 'recordings.csv', index=False)
    pd.concat([events, pd.DataFrame(event_rows)], ignore_index=True).to_csv(output / 'events.csv', index=False)
    (cache / 'config.json').write_text(json.dumps(config, indent=2))
    audit = json.loads(base_audit.read_text())
    audit.update(schema_version='lung-data-audit-multisource-v1', grouping='HF shifted dates + namespaced SPR patient IDs',
                 split_counts=all_records.split.value_counts().to_dict(),
                 training_groups=int(all_records.loc[all_records.split.isin(['train', 'validation']), 'group'].nunique()),
                 patient_disjoint_verified=False, annotation_coverage_verified=True,
                 coverage_policy='HF unchanged; SPR acoustic categories exhaustive only inside explicitly categorized events; no I/E supervision',
                 source_revision=REVISION, source_receipt_sha256=digest(source / 'receipt.json'),
                 source_recordings_added=len(added), source_windows_added=len(new_index),
                 source_patients_added=len({r['group'] for r in added}), source_event_counts=observed,
                 source_event_patient_support={key: len(value) for key, value in patient_support.items()},
                 rejected=rejected, official_test_labels_opened=False,
                 duplicate_check='HF inherited audit; SPR official test patient/blob inventory; TRAIN normalized 4-kHz PCM vs HF and SPR',
                 duplicate_check_limitations='Hash/gain-DC/resampled-PCM checks are not exhaustive perceptual or cross-source identity verification')
    (output / 'audit.json').write_text(json.dumps(audit, indent=2))
    (cache / 'provenance.json').write_text(json.dumps({'audit_sha256': digest(output / 'audit.json'),
        'config_sha256': digest(cache / 'config.json'), 'index_sha256': digest(cache / 'index.csv'),
        'recordings_sha256': digest(output / 'recordings.csv'), 'events_sha256': digest(output / 'events.csv'),
        'base_index_sha256': digest(base_cache / 'index.csv'), 'source_receipt_sha256': digest(source / 'receipt.json'),
        'adapter_version': 'sprsound-acoustic-mask-v1', 'validation_policy': 'original HF validation unchanged'}, indent=2))
    preflight(cache, output / 'audit.json')
    return audit
