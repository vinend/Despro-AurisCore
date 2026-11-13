"""Audit completed three-sound pipeline numerics/objective/data; never fit or tune."""
import argparse
import gc
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd
from auriscore.acquisition_lung import digest
from auriscore.lung_training import preflight, load_block
from auriscore.lung_evaluation import frame_metrics
from auriscore.lung_loss_audit import window_mass, constant_optimum, gradient_probe
from auriscore.lung_diagnostics import stratified_scores


def investigate(cache: Path, audit: Path, experiment: Path, output: Path) -> None:
    """Audit only bound development data and frozen best-checkpoint inference."""
    if output.exists():
        raise ValueError('Fresh diagnostic output required')
    config, index = preflight(cache, audit)
    source = json.loads((experiment / 'source.json').read_text())
    evaluation = json.loads((experiment / 'fold-0/evaluation.json').read_text())
    if (source.get('evaluation_role') != 'development_only'
            or json.loads((experiment / 'status.json').read_text())['status'] != 'completed'
            or source['index_sha256'] != digest(cache / 'index.csv') or source['audit_sha256'] != digest(audit)
            or source['config'] != config):
        raise ValueError('Completed development-only run bound to cache required')
    classes = evaluation['classes']; indices = [config['classes'].index(c) for c in classes]
    events = [json.loads(line) for line in (experiment / 'process.jsonl').read_text().splitlines()]
    weights = np.array([next(e for e in events if e['stage'] == 'statistics_completed')['positive_weights'][c] for c in classes])
    objective_path = experiment / 'fold-0/objective.json'
    if objective_path.exists():
        weights = np.asarray(json.loads(objective_path.read_text())['positive_weights'])
    records = pd.read_csv(audit.parent / 'recordings.csv', dtype={'group': str}).set_index('recording_id')
    normalization = np.load(experiment / 'fold-0/normalization.npz')
    mean, std = normalization['mean'], normalization['std']; normalization.close()
    output.mkdir(parents=True)
    totals = {}
    clip = {}
    for position, row in enumerate(index.itertuples(), 1):
        x, y, mask = load_block(cache / row.file)
        y, mask = y[:, indices], mask[:, indices]
        record = records.loc[row.recording_id]
        if record.split != row.split or str(record.group) != str(row.group):
            raise ValueError('Cache/source identity mismatch')
        positive = (y * mask).sum(axis=0, dtype=np.float64)
        negative = ((1-y) * mask).sum(axis=0, dtype=np.float64)
        p_mass, n_mass = window_mass(y, mask)
        for key in (row.split, row.split + '/' + str(record.device)):
            if key not in totals:
                totals[key] = {name: np.zeros(len(classes), np.float64) for name in ('positive', 'negative', 'window_positive', 'window_negative', 'positive_only_windows')}
                totals[key].update(windows=0, empty_windows=0)
            item = totals[key]
            for name, value in [('positive', positive), ('negative', negative), ('window_positive', p_mass), ('window_negative', n_mass),
                                ('positive_only_windows', ((positive > 0) & (negative == 0)).astype(float))]:
                item[name] += value
            item['windows'] += 1
            item['empty_windows'] += int(not mask.any())
        with np.load(cache / row.file, allow_pickle=False) as block:
            physical = block['times_s'] + config['n_fft'] / (2 * config['sample_rate']) <= record.valid_end_s + 1e-9
        z = (x - mean) / std
        entry = clip.setdefault(row.split + '/' + str(record.device), {'cells': 0, 'clipped_cells': 0, 'sum': 0., 'sum_squares': 0.})
        valid_z = z[physical]
        entry['cells'] += valid_z.size
        entry['clipped_cells'] += int((np.abs(valid_z) > 5).sum())
        entry['sum'] += float(valid_z.sum(dtype=np.float64)); entry['sum_squares'] += float(np.square(valid_z.astype(np.float64)).sum())
        if position % 10000 == 0 or position == len(index):
            print(f'Objective/normalization audit {position}/{len(index)}', flush=True)
    report = {'role': 'development_only', 'training_started': False, 'thresholds_reselected': False,
              'official_test_labels_opened': False, 'classes': classes, 'positive_weights': weights.tolist(),
              'index_sha256': digest(cache / 'index.csv'), 'audit_sha256': digest(audit), 'model_sha256': digest(experiment / 'fold-0/model.keras'),
              'mask_coverage': {}, 'normalization': {}, 'subsample_diagnostics': {},
              'duplicate_partition_check': 'group/source hashes disjoint; enforced by unchanged preflight'}
    for key, item in totals.items():
        prevalence = item['positive'] / (item['positive'] + item['negative'])
        report['mask_coverage'][key] = {name: value.tolist() if isinstance(value, np.ndarray) else value for name, value in item.items()}
        report['mask_coverage'][key].update(frame_prevalence=prevalence.tolist(),
            actual_window_loss_constant_optimum=constant_optimum(item['window_positive'], item['window_negative'], weights),
            frame_loss_constant_optimum=constant_optimum(item['positive'], item['negative'], weights))
    for key, item in clip.items():
        average = item['sum'] / item['cells']
        report['normalization'][key] = {'physical_feature_cells': item['cells'], 'fraction_clipped': item['clipped_cells'] / item['cells'],
            'z_mean': average, 'z_std': max(0., item['sum_squares'] / item['cells'] - average**2)**.5}
    # Fixed nuisance/source-only baseline: source rates are derived from TRAIN only.
    order = json.loads((experiment / 'prediction_index.json').read_text())
    selected = index.set_index('file').loc[[row['file'] for row in order]]
    if (any(row['fold'] != 0 for row in order) or not selected.split.eq('validation').all()
            or len(set(selected.index)) != len(selected)):
        raise ValueError('Saved predictions are not development validation')
    with np.load(experiment / 'fold-0/development_predictions.npz', allow_pickle=False) as saved:
        truth, scores, validity = saved['truth'], saved['scores'], saved['mask']
    frames = len(truth) // len(order)
    if frames * len(order) != len(truth):
        raise ValueError('Saved prediction frame/window alignment mismatch')
    report['stratified_validation'] = stratified_scores(
        truth.reshape(len(order), frames, len(classes)), scores.reshape(len(order), frames, len(classes)),
        validity.reshape(len(order), frames, len(classes)), classes, evaluation['thresholds'],
        [str(records.loc[row.recording_id, 'device']) for row in selected.itertuples()],
        selected.group.astype(str).tolist())
    saturation = []
    for i, label in enumerate(classes):
        active = validity[:, i] > 0
        saturated = (scores[:, i] <= 1e-7) | (scores[:, i] >= 1-1e-7)
        wrong = ((scores[:, i] <= 1e-7) & (truth[:, i] > 0)) | ((scores[:, i] >= 1-1e-7) & (truth[:, i] == 0))
        saturation.append({'class': label, 'valid_frames': int(active.sum()), 'saturated': int((active & saturated).sum()),
                           'wrong_saturated': int((active & wrong).sum())})
    report['best_checkpoint_probability_saturation'] = saturation
    baseline_scores = []
    for row in selected.itertuples():
        device = str(records.loc[row.recording_id, 'device'])
        item = totals['train/' + device]
        baseline_scores.append(item['positive'] / (item['positive'] + item['negative']))
    nuisance = np.repeat(np.asarray(baseline_scores, np.float32), frames, axis=0)
    nuisance_metrics = frame_metrics(truth, nuisance, validity, evaluation['thresholds'])
    report['TRAIN_device_only_baseline'] = {label: {'roc_auc': metric['roc_auc'], 'pr_auc': metric['pr_auc']}
                                           for label, metric in zip(classes, nuisance_metrics)}
    del nuisance, baseline_scores, truth, scores, validity
    gc.collect()
    import tensorflow as tf
    devices = tf.config.list_physical_devices('GPU')
    for device in devices:
        tf.config.experimental.set_memory_growth(device, True)
    report['synthetic_gradient_probe'] = gradient_probe()
    model = tf.keras.models.load_model(experiment / 'fold-0/model.keras', compile=False)
    # One deterministic random window per record, up to 64 records per device/split.
    index = index.copy()
    index['device'] = index.recording_id.map(records.device)
    for split in ('train', 'validation'):
        pieces = []
        for _, rows in index[index.split == split].groupby('device', sort=True):
            per_record = rows.groupby('recording_id', group_keys=False, sort=True).sample(n=1, random_state=42)
            pieces.append(per_record.sample(n=min(64, len(per_record)), random_state=42))
        sample = pd.concat(pieces, ignore_index=True)
        yy, pp, mm = [], [], []
        for start in range(0, len(sample), 8):
            batch, targets, masks = [], [], []
            for row in sample.iloc[start:start+8].itertuples():
                x, y, m = load_block(cache / row.file)
                batch.append(np.clip((x-mean)/std, -5, 5)); targets.append(y[:, indices]); masks.append(m[:, indices])
            probability = model(np.stack(batch), training=False).numpy()
            pp.extend(probability); yy.extend(targets); mm.extend(masks)
        truth, probability, validity = np.concatenate(yy), np.concatenate(pp), np.concatenate(mm)
        report['subsample_diagnostics'][split] = {'windows': len(sample), 'recordings': int(sample.recording_id.nunique()),
            'date_groups': int(sample.group.nunique()), 'selection': 'seed42 one random window per record, up to64 records/device',
            'unit': 'diagnostic subsample; not full population performance',
            'metrics': dict(zip(classes, frame_metrics(truth, probability, validity, evaluation['thresholds'])))}
        sample[['file', 'recording_id', 'split', 'device', 'group']].to_csv(output / f'{split}-sample.csv', index=False)
    report['model_unchanged'] = digest(experiment / 'fold-0/model.keras') == report['model_sha256']
    (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False))
    print('Investigation completed; no fitting, threshold selection or test access.', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cache', 'audit', 'experiment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    investigate(args.cache, args.audit, args.experiment, args.output)
