"""Auxiliary weak cycle supervision for the L023 research comparison."""
from collections import Counter
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import soundfile as sf

from .acquisition_lung import digest
from .lung_icbhi import read_cycles, train_recordings
from .lung_multisource import normalized_fingerprint
from .lung_preprocessing import extract_lung_features
from .preprocessing import preprocess


def prepare_cycles(source: Path, recordings_path: Path, config: dict):
    """Audit authorized TRAIN recordings and keep complete cycles fitting one window."""
    split = source / "official-split.txt"
    media = source / "verified-media"
    allowed = train_recordings(split.read_bytes())
    records = pd.read_csv(recordings_path)
    hashes = set(records.sha256.dropna())
    fingerprints = set(records.normalized_pcm_sha256.dropna())
    features, targets, packed_masks, sources = [], [], [], []
    counts = Counter()
    sample_rate = config["sample_rate"]
    size = round(config["window_seconds"] * sample_rate)
    fft, hop = config["n_fft"], config["hop_length"]
    for stem, group in sorted(allowed.items()):
        path = media / f"{stem}.wav"
        raw, rate = sf.read(path, dtype="float32", always_2d=True)
        sha = digest(path)
        if not len(raw) or not np.isfinite(raw).all() or np.std(raw) < 1e-6:
            counts["invalid_audio"] += 1
            continue
        fingerprint = normalized_fingerprint(raw, rate)
        if sha in hashes or fingerprint in fingerprints:
            counts["duplicate_audio"] += 1
            continue
        hashes.add(sha)
        fingerprints.add(fingerprint)
        signal = preprocess(raw, rate, config)
        cycles = read_cycles(media, stem, allowed, len(raw) / rate)
        included = 0
        for cycle in cycles:
            start, end = (round(t * sample_rate) for t in (cycle.start_seconds, cycle.end_seconds))
            audio = signal[start:end]
            if not fft <= len(audio) <= size:
                counts["cycles_outside_window_geometry"] += 1
                continue
            feature = extract_lung_features(np.pad(audio, (0, size - len(audio))), config)
            valid = np.arange(len(feature)) * hop + fft <= len(audio)
            labels = np.array([cycle.labels[0], 0, cycle.labels[2]], dtype=np.float32)
            mask = valid[:, None] * np.array([2, 0, 2], dtype=np.float32)
            features.append(feature)
            targets.append(np.broadcast_to(labels, mask.shape))
            packed_masks.append(mask)
            counts["wheeze_positive" if labels[0] else "wheeze_negative"] += 1
            counts["crackle_positive" if labels[2] else "crackle_negative"] += 1
            included += 1
        if included:
            sources.append(dict(group=group, recording_sha256=sha, normalized_pcm_sha256=fingerprint,
                                annotation_sha256=digest(media / f"{stem}.txt"), cycles=included))
    if not all(counts[key] for key in ("wheeze_positive", "wheeze_negative", "crackle_positive", "crackle_negative")):
        raise ValueError("ICBHI requires positive and negative cycles for both classes")
    return (np.asarray(features, dtype=np.float32),
            np.concatenate([targets, packed_masks], axis=-1, dtype=np.float32),
            dict(counts, split_sha256=digest(split), recordings=sources, eligible_recordings=len(allowed)))


def joint_loss(positive_weights):
    """Use exact HF frame BCE plus max-pooled BCE on known cycle labels."""
    import tensorflow as tf

    weights = tf.constant(positive_weights, tf.float32)

    def loss(packed, scores):
        truth, mask = tf.split(packed, 2, axis=-1)
        frame = tf.cast(mask == 1, tf.float32)
        point = tf.keras.ops.binary_crossentropy(truth, scores) * (1 - truth + truth * weights)
        strong_loss = tf.math.divide_no_nan(tf.reduce_sum(point * frame, [1, 2]),
                                            tf.reduce_sum(frame, [1, 2]))
        cycle = mask == 2
        known = tf.reduce_any(cycle, axis=1)
        pooled = tf.reduce_max(tf.where(cycle, scores, 0.), axis=1)
        weak = tf.keras.ops.binary_crossentropy(truth[:, 0], pooled)
        weak_loss = tf.math.divide_no_nan(tf.reduce_sum(tf.where(known, weak, 0.), axis=1),
                                          tf.reduce_sum(tf.cast(known, tf.float32), axis=1))
        return strong_loss + .8 * weak_loss

    return loss
