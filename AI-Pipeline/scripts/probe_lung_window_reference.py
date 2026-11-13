"""Frozen-checkpoint paired inference on identical audio under two window dB references."""
import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
import numpy as np
import pandas as pd
from auriscore.acquisition_lung import digest
from auriscore.lung_training import load_block


def probe(cache: Path, experiment: Path, pairs_path: Path, output: Path) -> None:
    if output.exists():
        raise ValueError('Fresh paired-inference output required')
    source = json.loads((experiment / 'source.json').read_text())
    if source.get('evaluation_role') != 'development_only' or source['index_sha256'] != digest(cache / 'index.csv'):
        raise ValueError('Hash-bound development experiment required')
    pairs = pd.DataFrame(json.loads(pairs_path.read_text()))
    # Fixed first eight records per source/split from a prior seed42 sample;
    # selection is independent of model errors, class labels and offset magnitude.
    pairs = pairs.groupby(['split', 'device'], sort=True).head(8)
    if not pairs.split.isin(['train', 'validation']).all():
        raise ValueError('Official test prohibited')
    index = pd.read_csv(cache / 'index.csv').set_index('file')
    import tensorflow as tf
    devices = tf.config.list_physical_devices('GPU')
    if not devices:
        raise RuntimeError('GPU required for paired inference')
    tf.config.set_logical_device_configuration(devices[0], [tf.config.LogicalDeviceConfiguration(memory_limit=3072)])
    tf.keras.utils.set_random_seed(42)
    tf.config.experimental.enable_op_determinism()
    tf.config.experimental.enable_tensor_float_32_execution(False)
    model_path = experiment / 'fold-0/model.keras'
    model_hash = digest(model_path)
    with np.load(experiment / 'fold-0/normalization.npz', allow_pickle=False) as saved:
        mean, std = saved['mean'], saved['std']
    model = tf.keras.models.load_model(model_path, compile=False)
    classes = source['model_classes']; rows = []
    for pair in pairs.itertuples():
        for name in (pair.first_file, pair.second_file):
            if (cache / name).resolve().parent != cache.resolve() or index.loc[name, 'split'] != pair.split:
                raise ValueError('Unsafe/mispartitioned paired feature path')
        a = load_block(cache / pair.first_file)[0]; b = load_block(cache / pair.second_file)[0]
        delta = int(pair.hop_delta)
        local = np.arange(min(len(b), len(a)-delta))
        active = (local >= 35) & (local < len(b)-35) & (local+delta >= 35) & (local+delta < len(a)-35)
        local = local[active]
        if not len(local):
            raise ValueError('No fully shared receptive-field interior')
        normalized = [np.clip((x-mean)/std, -5, 5) for x in (a, b, b+pair.db_offset)]
        probability = model(np.stack(normalized), training=False).numpy()
        for j, label in enumerate(classes):
            before = np.abs(probability[0, local+delta, j]-probability[1, local, j])
            after = np.abs(probability[0, local+delta, j]-probability[2, local, j])
            rows.append({'recording_id': pair.recording_id, 'split': pair.split, 'device': pair.device,
                         'class': label, 'frames': len(local), 'db_offset': float(pair.db_offset),
                         'mean_absolute_score_difference_before': float(before.mean()),
                         'mean_absolute_score_difference_after': float(after.mean()),
                         'maximum_absolute_score_difference_before': float(before.max()),
                         'maximum_absolute_score_difference_after': float(after.max())})
    data = pd.DataFrame(rows)
    result = {'training_started': False, 'optimizer_steps': 0, 'official_test_labels_opened': False,
              'thresholds_reselected': False, 'cache_changed': False, 'model_sha256': model_hash,
              'model_unchanged': digest(model_path) == model_hash, 'pairs_sha256': digest(pairs_path),
              'paired_recordings': len(pairs), 'runtime': 'deterministic_GPU_float32',
              'selection': 'first8/source/split from frozen seed42 sample, independent of scores/labels/offset',
              'intervention': 'second cached dB feature plus measured scalar reference offset, in memory only',
              'limitation': 'mechanism probe; does not validate a new preprocessing protocol or improvement in generalization',
              'summary': {}}
    for (split, device, label), subset in data.groupby(['split', 'device', 'class']):
        before = float(subset.mean_absolute_score_difference_before.mean())
        after = float(subset.mean_absolute_score_difference_after.mean())
        result['summary']['/'.join([split, device, label])] = {'pairs': len(subset),
            'mean_absolute_difference_before': before, 'mean_absolute_difference_after': after,
            'fraction_reduction': 1-after/before if before else None}
    output.mkdir(parents=True)
    data.to_csv(output / 'pairs.csv', index=False)
    (output / 'report.json').write_text(json.dumps(result, indent=2, allow_nan=False))
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('cache', 'experiment', 'pairs', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    args = parser.parse_args()
    probe(args.cache, args.experiment, args.pairs, args.output)
