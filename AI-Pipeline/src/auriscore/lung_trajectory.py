"""Opt-in epoch evidence; no threshold search or changes to fitting/early stopping."""
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .acquisition_lung import digest
from .lung_deep_review import window_loss_matrix
from .lung_evaluation import frame_metrics


def select_probes(fitting: pd.DataFrame, validation: pd.DataFrame,
                  recordings: pd.DataFrame, *, count: int, seed: int) -> pd.DataFrame:
    """Freeze one window/recording, balanced by device within each fitting partition."""
    if (fitting.empty or validation.empty or type(count) is not int or not 1 <= count <= 64
            or set(fitting.group.astype(str)) & set(validation.group.astype(str))):
        raise ValueError('Nonempty disjoint grouped fitting/validation probes required')
    if recordings.recording_id.duplicated().any():
        raise ValueError('Unique source identities required')
    metadata = recordings.set_index('recording_id')
    pieces = []
    for role, rows in [('fitting', fitting), ('inner_validation', validation)]:
        if not rows.split.isin(['train', 'validation']).all():
            raise ValueError('Official test cannot enter trajectory probes')
        rows = rows.copy()
        if not set(rows.recording_id).issubset(metadata.index):
            raise ValueError('Probe recording missing from audited metadata')
        source = metadata.loc[rows.recording_id]
        if (not source.split.isin(['train', 'validation']).all()
                or not np.array_equal(source.split.to_numpy(), rows.split.to_numpy())
                or not np.array_equal(source.group.astype(str).to_numpy(), rows.group.astype(str).to_numpy())):
            raise ValueError('Invalid probe source partition/group')
        rows['device'] = source.device.to_numpy()
        rows['partition_role'] = role
        for _, group in rows.groupby('device', sort=True):
            records = group.groupby('recording_id', group_keys=False, sort=True).sample(n=1, random_state=seed)
            pieces.append(records.sample(n=min(count, len(records)), random_state=seed))
    result = pd.concat(pieces, ignore_index=True)
    if result.file.duplicated().any():
        raise ValueError('Duplicate trajectory window')
    return result


def trajectory_callback(folder: Path, cache: Path, fitting: pd.DataFrame,
                        validation: pd.DataFrame, recordings: pd.DataFrame,
                        mean: np.ndarray, std: np.ndarray, indices: list[int],
                        classes: list[str], weights: np.ndarray, policy: dict,
                        *, seed: int, batch_size: int, log=None) -> Any:
    """Save pre-restoration epoch weights, probes and class/source/group metrics.

    Probe thresholds are frozen diagnostic constants. This callback never
    modifies Keras logs, learning rate, optimizer variables or stopping state.
    """
    import tensorflow as tf
    from .lung_training import load_block
    settings = policy['trajectory']
    probes = select_probes(fitting, validation, recordings,
                           count=settings['recordings_per_device_partition'], seed=seed)
    destination = Path(folder) / 'trajectory'
    destination.mkdir(exist_ok=False)
    probes.to_csv(destination / 'probe-index.csv', index=False)
    x, y, m = [], [], []
    for row in probes.itertuples():
        path = (Path(cache) / row.file).resolve()
        if path.parent != Path(cache).resolve():
            raise ValueError('Unsafe trajectory cache path')
        features, truth, mask = load_block(path)
        x.append(np.clip((features-mean)/std, -5, 5)); y.append(truth[:, indices]); m.append(mask[:, indices])
    x, y, m = map(np.stack, (x, y, m))
    thresholds = settings['thresholds']
    (destination / 'protocol.json').write_text(json.dumps({
        'schema_version': 'lung-trajectory-v1', 'classes': classes, 'thresholds': thresholds,
        'thresholds_reselected': False, 'seed': seed, 'probe_index_sha256': digest(destination / 'probe-index.csv'),
        'positive_weights': np.asarray(weights).tolist(), 'checkpoint_timing': 'epoch_end_before_train_end_best_restore',
        'evaluation_unit': 'fixed_diagnostic_windows_including_overlap; not independent patients',
        'official_test_labels_opened': False, 'selection': settings}, indent=2))

    class EpochEvidence(tf.keras.callbacks.Callback):
        def on_epoch_end(self, epoch, logs=None):
            target = destination / f'epoch-{epoch+1:04d}'
            target.mkdir(exist_ok=False)
            before = int(self.model.optimizer.iterations.numpy())
            self.model.save_weights(target / 'weights.weights.h5')
            probability = np.concatenate([np.asarray(self.model(x[start:start+batch_size], training=False))
                                          for start in range(0, len(x), batch_size)])
            if not np.isfinite(probability).all():
                raise ValueError('Nonfinite trajectory scores')
            np.savez_compressed(target / 'predictions.npz', truth=y, scores=probability, mask=m)
            losses = window_loss_matrix(y, probability, m, np.asarray(weights))
            report = {'schema_version': 'lung-trajectory-v1', 'epoch': epoch+1, 'optimizer_updates': before,
                      'learning_rate': float(tf.keras.backend.get_value(self.model.optimizer.learning_rate)),
                      'thresholds_reselected': False, 'metrics': {}}
            for role, rows in probes.groupby('partition_role', sort=True):
                positions = rows.index.to_numpy()
                def describe(at):
                    result = {}
                    for j, (label, metric) in enumerate(zip(classes, frame_metrics(y[at], probability[at], m[at], thresholds))):
                        active = m[at, :, j] > 0
                        yy, pp = y[at, :, j][active], probability[at, :, j][active]
                        total = sum(metric[k] for k in ('tn', 'fp', 'fn', 'tp'))
                        q = np.clip(pp.astype(np.float64), 1e-7, 1-1e-7)
                        result[label] = {**metric, 'positive_bce': float(losses[at, j, 0].mean()),
                            'negative_bce': float(losses[at, j, 1].mean()),
                            'accuracy': (metric['tn']+metric['tp'])/total if total else None,
                            'balanced_accuracy': (metric['sensitivity']+metric['specificity'])/2
                                if metric['sensitivity'] is not None and metric['specificity'] is not None else None,
                            'raw_brier': float(np.mean((pp-yy)**2)) if len(yy) else None,
                            'mean_binary_entropy': float(np.mean(-q*np.log(q)-(1-q)*np.log1p(-q))) if len(q) else None,
                            'confident_wrong_fraction_01_99': float(np.mean(((pp > .99)&(yy == 0))|((pp < .01)&(yy == 1)))) if len(yy) else None,
                            'positive_score_quantiles_10_50_90': np.quantile(pp[yy > 0], [.1, .5, .9]).tolist() if np.any(yy > 0) else [],
                            'negative_score_quantiles_10_50_90': np.quantile(pp[yy == 0], [.1, .5, .9]).tolist() if np.any(yy == 0) else [],
                            'mean_raw_score': float(pp.mean()) if len(pp) else None,
                            'prevalence': float(yy.mean()) if len(yy) else None}
                    return result
                report['metrics'][role] = {'windows': len(positions), 'classes': describe(positions),
                    'devices': {str(k): describe(v.index.to_numpy()) for k, v in rows.groupby('device')},
                    'date_groups': {str(k): describe(v.index.to_numpy()) for k, v in rows.groupby('group')}}
            if int(self.model.optimizer.iterations.numpy()) != before:
                raise RuntimeError('Trajectory probe changed optimizer state')
            report['weights_sha256'] = digest(target / 'weights.weights.h5')
            report['predictions_sha256'] = digest(target / 'predictions.npz')
            (target / 'metrics.json').write_text(json.dumps(report, indent=2, allow_nan=False))
            (destination / 'last-epoch.json').write_text(json.dumps({'epoch': epoch+1,
                'weights': str((target / 'weights.weights.h5').relative_to(destination)),
                'optimizer_updates': before, 'restored_best': False}, indent=2))
            if log is not None:
                log.event('trajectory_saved', epoch=epoch+1, optimizer_updates=before, path=str(target))
    return EpochEvidence()
