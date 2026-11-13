"""TRAIN-only supervision planning for versioned per-window Lung objectives."""
from pathlib import Path

import numpy as np
import pandas as pd

from .lung_loss_audit import window_mass


def plan_supervision(cache: Path, rows: pd.DataFrame, indices: list[int],
                     settings: dict, *, log=None) -> tuple[pd.DataFrame, np.ndarray, dict]:
    """Freeze fitting rows and weights without reading held-out labels.

    This must run after a grouped partition is chosen. Normalization retains the
    historical original TRAIN scope and is deliberately calculated separately.
    Unknown labels never become negatives. Zero-mask windows have zero mass.
    """
    from .lung_training import load_block

    if rows.empty or not indices or len(set(indices)) != len(indices):
        raise ValueError('Nonempty fitting rows and unique class indices required')
    if 'split' in rows and not rows.split.isin(['train', 'validation']).all():
        raise ValueError('Official test cannot enter supervision planning')
    if (settings.get('positive_weighting') not in ('global_frame', 'window_mass')
            or settings.get('empty_training_windows') not in ('keep', 'drop')):
        raise ValueError('Explicit supervision weighting/filter policy required')
    positive = np.zeros(len(indices), np.float64)
    negative = positive.copy()
    keep = []
    empty = 0
    for position, name in enumerate(rows.file, 1):
        path = (Path(cache) / name).resolve()
        if path.parent != Path(cache).resolve() or path.suffix != '.npz':
            raise ValueError('Unsafe fitting cache path')
        _, y, mask = load_block(path)
        y, mask = y[:, indices], mask[:, indices]
        active = bool(mask.any())
        empty += int(not active)
        keep.append(active or settings['empty_training_windows'] == 'keep')
        if settings['positive_weighting'] == 'window_mass':
            p, n = window_mass(y, mask)
        else:
            p, n = (y * mask).sum(axis=0), ((1-y) * mask).sum(axis=0)
        positive += p
        negative += n
        if log is not None:
            log.progress('supervision_plan', position, len(rows))
    if np.any(positive <= 0) or np.any(negative <= 0):
        raise ValueError('Fitting needs positive/negative support for each selected class')
    weights = np.clip(negative / positive, .25, 20).astype(np.float32)
    selected = rows.loc[np.asarray(keep)].copy()
    if selected.empty:
        raise ValueError('No supervised fitting windows')
    report = {'settings': dict(settings), 'original_windows': len(rows),
              'empty_windows': empty, 'fitting_windows': len(selected),
              'positive_mass': positive.tolist(), 'negative_mass': negative.tolist(),
              'positive_weights': weights.tolist(), 'weight_clip': [.25, 20],
              'fitting_files': selected.file.tolist(),
              'scope': 'current_partition_fitting_rows_only'}
    return selected, weights, report
