"""Ground-truth frame mask generator and dataset loader for Sound Event Detection (SED)."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Iterator

import numpy as np
import pandas as pd

from .dataset_abdomen import parse_annotation_file
from .spectrogram import extract_spectrogram_tensor, spectrogram_shape

LOG = logging.getLogger(__name__)


def generate_frame_mask(
    window_start_s: float,
    window_dur_s: float,
    time_frames: int,
    hop_s: float,
    events: list[dict[str, Any]],
) -> np.ndarray:
    """Generate binary target vector Y in {0, 1}^(time_frames, 1) from interval annotations."""
    mask = np.zeros((time_frames, 1), dtype=np.float32)
    active_events = [e for e in events if e.get("is_active", True)]
    if not active_events:
        return mask

    for k in range(time_frames):
        frame_start = window_start_s + k * hop_s
        frame_end = frame_start + hop_s

        for e in active_events:
            # Check overlap between frame [frame_start, frame_end] and event [e['start_sec'], e['end_sec']]
            overlap = min(frame_end, e["end_sec"]) - max(frame_start, e["start_sec"])
            if overlap > 0.0:
                mask[k, 0] = 1.0
                break

    return mask


def create_sed_dataset_iterator(
    segments_frame: pd.DataFrame,
    root: Path,
    config: dict[str, Any],
    training: bool = False,
    rng: np.random.Generator | None = None,
) -> Iterator[tuple[np.ndarray, np.ndarray]]:
    """Yield pairs of (spectrogram_tensor, frame_mask) for each audio window."""
    root = root.resolve()
    sample_rate = int(config["sample_rate"])
    hop_length = int(config["hop_length"])
    hop_s = hop_length / sample_rate
    _, time_frames = spectrogram_shape(config)

    records = segments_frame.to_dict("records")
    if training and rng is not None:
        rng.shuffle(records)

    # Cache parsed annotation files to avoid repeated disk I/O
    annotation_cache: dict[str, list[dict[str, Any]]] = {}

    for row in records:
        source_path = root / row["file_path"]
        txt_path = source_path.with_suffix(".txt")
        cache_key = str(txt_path)
        if cache_key not in annotation_cache:
            annotation_cache[cache_key] = parse_annotation_file(txt_path)
        events = annotation_cache[cache_key]

        npy_path = root / row["processed_path"]
        if not npy_path.exists():
            continue
        audio_full = np.load(npy_path, allow_pickle=False)

        start_sample = int(row["start_sample"])
        valid_samples = int(row["valid_samples"])
        window_samples = int(row["window_samples"])

        window_audio = audio_full[start_sample : start_sample + valid_samples]
        if len(window_audio) < window_samples:
            window_audio = np.pad(window_audio, (0, window_samples - len(window_audio)))

        # Extract normalized spectrogram tensor (40, 313, 1)
        tensor = extract_spectrogram_tensor(window_audio, config)[..., np.newaxis]

        # Generate frame ground truth mask (313, 1)
        win_start_s = start_sample / sample_rate
        win_dur_s = window_samples / sample_rate
        mask = generate_frame_mask(win_start_s, win_dur_s, time_frames, hop_s, events)

        yield tensor, mask
