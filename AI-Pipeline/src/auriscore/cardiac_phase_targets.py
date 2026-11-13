"""Official cardiac-state targets; never manufacture murmur intervals."""
from pathlib import Path
import numpy as np


def read_intervals(path: Path, duration: float) -> np.ndarray:
    """Reject malformed/overlapping intervals; retain unknown state zero."""
    rows = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError('Malformed phase row')
        a, b, c = map(float, fields)
        if not np.isfinite([a,b,c]).all() or not 0 <= a < b <= duration or c not in range(5):
            raise ValueError('Invalid phase interval')
        if rows and a < rows[-1][1]:
            raise ValueError('Overlapping/out-of-order phase intervals')
        rows.append((a,b,c))
    return np.asarray(rows, dtype=float).reshape(-1,3)


def targets(intervals: np.ndarray, start_sample: int, valid_samples: int,
            sample_rate: int = 8000) -> dict[str, np.ndarray]:
    """Align the 39 pooled bins to centered STFT frames 8*j..8*j+7.

    Centers are (8*j+3.5)*128 samples. A 200 ms receptive-field radius
    masks audio padding; a half-output-stride guard masks phase boundaries.
    Absolute timestamps preserve overlap; each window uses its own valid length.
    """
    intervals = np.asarray(intervals, dtype=float).reshape(-1,3)
    if start_sample < 0 or not 0 <= valid_samples <= 40000 or sample_rate != 8000:
        raise ValueError('Invalid frozen window')
    local = (8*np.arange(39)+3.5)*128/sample_rate
    seconds = start_sample/sample_rate + local
    radius = 1600/sample_rate
    padding = (local-radius < 0) | (local+radius >= valid_samples/sample_rate)
    labels = np.full(39,-1,dtype=np.int32)
    boundary = np.zeros(39,dtype=bool)
    for a,b,state in intervals:
        inside = (seconds >= a) & (seconds < b)
        if state:
            labels[inside] = int(state)-1
        boundary |= (np.abs(seconds-a) <= .064) | (np.abs(seconds-b) <= .064)
    unknown = labels < 0
    valid = ~(padding | boundary | unknown)
    return dict(seconds=seconds, labels=labels, valid=valid, unknown=unknown,
                boundary=boundary, padding=padding)


def merge_overlap(seconds: np.ndarray, values: np.ndarray, valid: np.ndarray) -> tuple[np.ndarray,np.ndarray]:
    """Average aligned repeated samples; retain absolute times, never join sites."""
    seconds, values, valid = np.asarray(seconds), np.asarray(values), np.asarray(valid,bool)
    if seconds.shape != valid.shape or values.shape[:seconds.ndim] != seconds.shape:
        raise ValueError('Overlap shape mismatch')
    times = np.round(seconds[valid],9)
    unique = np.unique(times)
    return unique, np.asarray([values[valid][times == t].mean(axis=0) for t in unique])
