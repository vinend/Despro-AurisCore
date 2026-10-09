"""H015 participant-level site-aware multiple-instance model and train-only bags.

The model never receives participant IDs or recording-level murmur targets.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import tensorflow as tf

from .cnn import _window

SITES = ("AV", "MV", "PV", "TV", "Phc", "UNKNOWN")
SITE_TO_ID = {site.upper(): i for i, site in enumerate(SITES)}
NUMERIC = ("original_sampling_rate", "duration_sec", "start_sample",
           "valid_samples", "window_samples", "sample_rate")


def read_one_split(path: Path, split: str) -> pd.DataFrame:
    """Parse only the selected split; examine only split token in other rows."""
    if split not in {"train", "validation"}:
        raise ValueError("Only development train/validation splits are allowed")
    with path.open(encoding="utf-8", newline="") as stream:
        columns = next(csv.reader([stream.readline()]))
        index = columns.index("split")
        rows = []
        for line in stream:
            prefix = line.split(",", index + 1)
            if len(prefix) <= index:
                raise ValueError("Malformed segment row")
            if prefix[index].strip('"') != split:
                continue
            rows.append(dict(zip(columns, next(csv.reader([line])), strict=True)))
    frame = pd.DataFrame(rows, columns=columns)
    for name in NUMERIC:
        frame[name] = pd.to_numeric(frame[name])
    if frame.empty or not frame.split.eq(split).all():
        raise ValueError(f"No valid {split} rows")
    return frame


@dataclass(frozen=True)
class ParticipantBag:
    participant_id: str
    label: int
    recording_ids: tuple[str, ...]
    sites: tuple[str, ...]
    rows: tuple[dict[str, Any], ...]
    segment_recording_index: np.ndarray
    site_ids: np.ndarray

    @property
    def recording_count(self) -> int:
        return len(self.recording_ids)

    @property
    def segment_count(self) -> int:
        return len(self.rows)


def build_bags(frame: pd.DataFrame) -> list[ParticipantBag]:
    """Group original segments into participant bags with no recording targets."""
    if not frame.label.isin(["Absent", "Present"]).all():
        raise ValueError("MIL requires known binary participant labels")
    bags = []
    for participant_id, participant in frame.groupby("subject_group", sort=True):
        if participant.label.nunique() != 1 or participant.split.nunique() != 1:
            raise ValueError(f"Inconsistent participant bag: {participant_id}")
        rows, indexes, recording_ids, sites, site_ids = [], [], [], [], []
        for recording_id, rec in participant.groupby("recording_id", sort=True):
            if rec.auscultation_location.nunique() != 1:
                raise ValueError(f"Inconsistent recording site: {recording_id}")
            site = str(rec.auscultation_location.iloc[0])
            if not site or site.lower() == "nan":
                site = "UNKNOWN"
            site_index = SITE_TO_ID.get(site.upper(), SITE_TO_ID["UNKNOWN"])
            recording_ids.append(str(recording_id))
            sites.append(site)
            site_ids.append(site_index)
            local = rec.to_dict("records")
            rows.extend(local)
            indexes.extend([len(recording_ids) - 1] * len(local))
        if not rows:
            raise ValueError(f"Empty participant bag: {participant_id}")
        bags.append(ParticipantBag(
            participant_id=str(participant_id),
            label=int(participant.label.iloc[0] == "Present"),
            recording_ids=tuple(recording_ids), sites=tuple(sites),
            rows=tuple(rows),
            segment_recording_index=np.asarray(indexes, dtype=np.int32),
            site_ids=np.asarray(site_ids, dtype=np.int32),
        ))
    return bags


class BagTensorLoader:
    """Apply the frozen algorithm with fold-specific frequency statistics."""

    def __init__(self, root: Path, config: dict[str, Any]):
        self.root = root
        self.config = config

        @lru_cache(maxsize=32)
        def load(path: str) -> np.ndarray:
            return np.load(path, allow_pickle=False)
        self.load = load

    def tensors(
        self, bag: ParticipantBag, *, training: bool, seed: int | None = None
    ) -> tuple[tf.Tensor, tf.Tensor, tf.Tensor]:
        if training and seed is None:
            raise ValueError("Training augmentation requires a deterministic bag seed")
        rng = np.random.default_rng(seed) if training else None
        tensors = [
            _window(row, self.root, self.config, self.load,
                    training=training, rng=rng)
            for row in bag.rows
        ]
        return (
            tf.convert_to_tensor(np.stack(tensors).astype(np.float32)),
            tf.convert_to_tensor(bag.segment_recording_index, dtype=tf.int32),
            tf.convert_to_tensor(bag.site_ids, dtype=tf.int32),
        )


def masked_softmax(logits: tf.Tensor, mask: tf.Tensor) -> tf.Tensor:
    """Return zero mass on padding; require at least one valid recording."""
    logits = tf.reshape(tf.convert_to_tensor(logits), [-1])
    mask = tf.reshape(tf.cast(mask, tf.bool), [-1])
    tf.debugging.assert_equal(tf.shape(logits), tf.shape(mask))
    tf.debugging.assert_positive(tf.reduce_sum(tf.cast(mask, tf.int32)))
    blocked = tf.where(mask, logits, tf.constant(-1e9, dtype=logits.dtype))
    weights = tf.nn.softmax(blocked)
    weights = tf.where(mask, weights, tf.zeros_like(weights))
    return weights / tf.reduce_sum(weights)


@tf.keras.utils.register_keras_serializable(package="auriscore")
class SiteAwareMIL(tf.keras.Model):
    """One H014-topology encoder, fixed recording means, site-aware attention."""

    def __init__(self, dropout: float = .30, **kwargs: Any):
        super().__init__(**kwargs)
        self.dropout_rate = float(dropout)
        encoder_layers: list[tf.keras.layers.Layer] = []
        for filters in (16, 32, 64):
            encoder_layers.extend([
                tf.keras.layers.Conv2D(filters, 3, padding="same", use_bias=False),
                tf.keras.layers.BatchNormalization(),
                tf.keras.layers.Activation("relu"),
                tf.keras.layers.MaxPooling2D(pool_size=(2, 2)),
            ])
        encoder_layers.extend([
            tf.keras.layers.GlobalAveragePooling2D(),
            tf.keras.layers.Dropout(self.dropout_rate),
        ])
        self.segment_encoder = tf.keras.Sequential(
            encoder_layers, name="h014_topology_64d_encoder")
        self.site_embedding = tf.keras.layers.Embedding(
            input_dim=len(SITES), output_dim=8, name="site_embedding")
        self.attention_hidden = tf.keras.layers.Dense(
            32, activation="relu", name="attention_hidden")
        self.attention_dropout = tf.keras.layers.Dropout(
            self.dropout_rate, name="attention_dropout")
        self.attention_logit = tf.keras.layers.Dense(
            1, activation=None, name="attention_logit")
        self.classifier_hidden = tf.keras.layers.Dense(
            32, activation="relu", name="participant_hidden")
        self.classifier_dropout = tf.keras.layers.Dropout(
            self.dropout_rate, name="participant_dropout")
        self.classifier_probability = tf.keras.layers.Dense(
            1, activation="sigmoid", name="participant_probability")

    def call(
        self,
        inputs: tuple[tf.Tensor, tf.Tensor, tf.Tensor],
        training: bool = False,
        return_attention: bool = False,
    ) -> tf.Tensor | tuple[tf.Tensor, tf.Tensor]:
        segments, segment_recording_index, site_ids = inputs
        n_recordings = tf.shape(site_ids)[0]
        acoustic_segments = self.segment_encoder(segments, training=training)
        recording_sum = tf.math.unsorted_segment_sum(
            acoustic_segments, segment_recording_index, n_recordings)
        counts = tf.math.unsorted_segment_sum(
            tf.ones_like(segment_recording_index, dtype=tf.float32),
            segment_recording_index, n_recordings)
        tf.debugging.assert_positive(counts)
        acoustic_recordings = recording_sum / counts[:, None]
        site = self.site_embedding(site_ids)
        attention_input = tf.concat([acoustic_recordings, site], axis=-1)
        logits = self.attention_logit(
            self.attention_dropout(
                self.attention_hidden(attention_input), training=training))
        # No padded recordings are instantiated in microbatched participant bags.
        # The masked implementation still guarantees zero padding mass.
        weights = masked_softmax(logits, tf.ones([n_recordings], dtype=tf.bool))
        participant_embedding = tf.reduce_sum(
            weights[:, None] * acoustic_recordings, axis=0)
        participant_hidden = self.classifier_hidden(
            participant_embedding[None, :])
        probability = self.classifier_probability(
            self.classifier_dropout(participant_hidden, training=training))
        probability = tf.reshape(probability, [])
        if return_attention:
            return probability, weights
        return probability

    def get_config(self) -> dict[str, Any]:
        return {**super().get_config(), "dropout": self.dropout_rate}

