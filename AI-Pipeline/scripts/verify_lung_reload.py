"""Read-only, hash-bound Lung inference parity probe; never fit or select thresholds."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd

from auriscore.acquisition_lung import digest
from auriscore.lung_training import load_block


def verify(cache: Path, experiment: Path, output: Path, *, device: str, deterministic: bool) -> dict:
    """Compare fresh/reloaded scores and historical saved scores on 16 frozen windows."""
    scores_path = output.with_suffix('.scores.npz')
    if output.exists() or scores_path.exists():
        raise ValueError('Fresh parity output required')
    source = json.loads((experiment / 'source.json').read_text())
    if (source.get('evaluation_role') != 'development_only'
            or source.get('index_sha256') != digest(cache / 'index.csv')):
        raise ValueError('Bound development experiment required')
    order = json.loads((experiment / 'prediction_index.json').read_text())
    if not order or any(row['fold'] != 0 for row in order):
        raise ValueError('Single-fold development parity probe required')
    index = pd.read_csv(cache / 'index.csv').set_index('file')
    files = [row['file'] for row in order]
    if len(set(files)) != len(files) or not index.loc[files].split.eq('validation').all():
        raise ValueError('Only bound held-out development windows allowed')
    positions = np.random.default_rng(42).choice(len(order), min(16, len(order)), replace=False)
    with np.load(experiment / 'fold-0/normalization.npz', allow_pickle=False) as norm:
        mean, std = norm['mean'], norm['std']
    features = []
    for i in positions:
        path = (cache / files[int(i)]).resolve()
        if path.parent != cache.resolve():
            raise ValueError('Unsafe cache path')
        features.append(np.clip((load_block(path)[0]-mean)/std, -5, 5))
    model_path = experiment / 'fold-0/model.keras'
    model_hash = digest(model_path)
    import tensorflow as tf
    if device == 'cpu':
        tf.config.set_visible_devices([], 'GPU')
    else:
        devices = tf.config.list_physical_devices('GPU')
        if not devices:
            raise RuntimeError('GPU required for GPU parity probe')
        for gpu in devices:
            tf.config.experimental.set_memory_growth(gpu, True)
    if deterministic:
        tf.keras.utils.set_random_seed(42)
        tf.config.experimental.enable_op_determinism()
        tf.config.experimental.enable_tensor_float_32_execution(False)
    with tf.device('/CPU:0' if device == 'cpu' else '/GPU:0'):
        first = tf.keras.models.load_model(model_path, compile=False)
        actual = np.concatenate([first(x[None], training=False).numpy() for x in features])
        second = tf.keras.models.load_model(model_path, compile=False)
        restored = np.concatenate([second(x[None], training=False).numpy() for x in features])
    with np.load(experiment / 'fold-0/development_predictions.npz', allow_pickle=False) as saved:
        expected = saved['scores'].reshape(len(order), *actual.shape[1:])[positions]
    thresholds = json.loads((experiment / 'fold-0/evaluation.json').read_text())['thresholds']
    report = {'training_started': False, 'official_test_labels_opened': False,
              'model_sha256': model_hash, 'model_unchanged': digest(model_path) == model_hash,
              'index_sha256': source['index_sha256'], 'tensorflow': tf.__version__,
              'device': device, 'deterministic_ops_requested': deterministic,
              'tf32_enabled': tf.config.experimental.tensor_float_32_execution_enabled(),
              'sample_positions': positions.tolist(), 'inference_batch_size': 1,
              'reload_maximum_difference': float(np.max(np.abs(actual-restored))),
              'reload_parity_passed': bool(np.allclose(actual, restored, atol=1e-4, rtol=1e-4)),
              'historical_maximum_difference': float(np.max(np.abs(actual-expected))),
              'historical_mean_absolute_difference': float(np.mean(np.abs(actual-expected))),
              'historical_parity_passed': bool(np.allclose(actual, expected, atol=1e-4, rtol=1e-4)),
              'historical_threshold_decisions_changed': int(np.count_nonzero((actual >= thresholds) != (expected >= thresholds))),
              'tolerance': {'atol': 1e-4, 'rtol': 1e-4}}
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(scores_path, positions=positions, scores=actual)
    output.write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cache', 'experiment', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'gpu'], required=True)
    parser.add_argument('--deterministic', action='store_true')
    parser.add_argument('--require-parity', action='store_true')
    args = parser.parse_args()
    result = verify(args.cache, args.experiment, args.output, device=args.device,
                    deterministic=args.deterministic)
    print(json.dumps(result))
    if args.require_parity and not (result['reload_parity_passed'] and result['historical_parity_passed'] and result['model_unchanged']):
        raise SystemExit('Strict inference parity failed; report preserved')
