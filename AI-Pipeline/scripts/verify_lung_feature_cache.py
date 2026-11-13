"""Verify complete fixed-reference cache parity and overlap invariance; never fit."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd
import _bootstrap  # noqa: F401
from auriscore.acquisition_lung import digest
from auriscore.lung_training import preflight, statistics


def verify(old_cache: Path, new_cache: Path, old_audit: Path, new_audit: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError('Fresh verification output required')
    old, old_index = preflight(old_cache, old_audit)
    new, index = preflight(new_cache, new_audit)
    if (digest(old_audit) != digest(new_audit) or old_cache.resolve() == new_cache.resolve()
            or {k: v for k, v in new.items() if k != 'lung_feature_policy'} != old
            or new.get('lung_feature_policy', {}).get('schema_version') != 'lung-fixed-logmel-v1'):
        raise ValueError('Only a versioned Lung feature change is allowed')
    pd.testing.assert_frame_equal(index, old_index)
    mean, std, weights = statistics(new_cache, index[index.split == 'train'])
    max_difference = 0.; overlap_pairs = 0; previous = None; clipped = cells = 0
    for position, row in enumerate(index.itertuples(), 1):
        with np.load(old_cache / row.file, allow_pickle=False) as a, np.load(new_cache / row.file, allow_pickle=False) as b:
            if set(a.files) != set(b.files) or a['features'].shape != b['features'].shape:
                raise ValueError('Cache payload/geometry changed')
            for key in a.files:
                if key != 'features' and not np.array_equal(a[key], b[key]):
                    raise ValueError(f'Target/timestamp/mask changed: {row.file}/{key}')
            features = b['features']; start = int(b['start_sample'])
            if not np.isfinite(features).all():
                raise ValueError('Nonfinite fixed-reference features')
            if previous is not None and previous[0] == row.recording_id:
                offset = (start-previous[1])//new['hop_length']
                if start <= previous[1] or (start-previous[1]) % new['hop_length']:
                    raise ValueError('Unexpected window ordering/grid')
                count = len(previous[2])-offset
                if count > 0:
                    difference = float(np.max(np.abs(previous[2][offset:]-features[:count])))
                    max_difference = max(max_difference, difference); overlap_pairs += 1
                    if difference > 1e-5:
                        raise ValueError(f'Identical audio feature disagreement: {row.file}: {difference}')
            previous = (row.recording_id, start, features.copy())
            known = np.any(b['mask'] > 0, axis=1)
            z = (features[known]-mean)/std
            clipped += int((np.abs(z) > 5).sum()); cells += z.size
        if position == 1 or position % 5000 == 0 or position == len(index):
            print(f'Verified {position}/{len(index)} cache windows', flush=True)
    output.mkdir(parents=True)
    np.savez(output / 'training-normalization.npz', mean=mean, std=std)
    report = {'training_started': False, 'official_test_labels_opened': False,
              'windows': len(index), 'target_mask_time_payloads_identical': True, 'split_index_identical': True,
              'old_index_sha256': digest(old_cache / 'index.csv'), 'new_index_sha256': digest(new_cache / 'index.csv'),
              'new_cache': str(new_cache), 'new_config_sha256': digest(new_cache / 'config.json'),
              'old_config_sha256': digest(old_cache / 'config.json'), 'overlap_pairs': overlap_pairs,
              'maximum_shared_frame_feature_difference': max_difference, 'overlap_tolerance': 1e-5,
              'normalization_scope': 'original supervised TRAIN only', 'minimum_std': float(std.min()),
              'supervised_feature_clip_fraction': clipped/cells if cells else None,
              'train_global_frame_positive_weights': weights.tolist()}
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('old-cache', 'new-cache', 'old-audit', 'new-audit', 'output'):
        parser.add_argument('--'+key, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.old_cache, args.new_cache, args.old_audit, args.new_audit, args.output)))
