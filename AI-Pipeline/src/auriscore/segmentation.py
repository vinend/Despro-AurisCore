"""Deterministic complete windows; short recordings get one padded window."""
from collections.abc import Iterator
import numpy as np


def segment(audio: np.ndarray, sr: int, seconds: float = 5,
            overlap: float = 0.5) -> Iterator[tuple[int, np.ndarray, int]]:
    """Yield (start sample, window, valid samples); discard incomplete long tails."""
    if sr <= 0 or seconds <= 0 or not 0 <= overlap < 1:
        raise ValueError("Invalid segmentation parameters")
    size = round(sr * seconds)
    step = round(size * (1 - overlap))
    if size < 1 or step < 1 or audio.ndim != 1 or not audio.size:
        raise ValueError("Nonempty mono audio and positive window/hop required")
    if len(audio) < size:
        yield 0, np.pad(audio, (0, size - len(audio))), len(audio)
    else:
        for start in range(0, len(audio) - size + 1, step):
            yield start, audio[start:start + size], size
