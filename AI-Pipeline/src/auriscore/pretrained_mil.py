"""H016 uses H015 attention with an immutable fold-local acoustic encoder."""
from __future__ import annotations

import hashlib
from typing import Any

import numpy as np
import tensorflow as tf

from .mil import SiteAwareMIL, masked_softmax


def encoder_digest(encoder: tf.keras.layers.Layer) -> str:
    """Fingerprint all acoustic parameters, including BatchNorm moving state."""
    digest = hashlib.sha256()
    for weight in encoder.get_weights():
        array = np.ascontiguousarray(weight)
        digest.update(str(array.shape).encode())
        digest.update(str(array.dtype).encode())
        digest.update(array.tobytes())
    return digest.hexdigest()


@tf.keras.utils.register_keras_serializable(package="auriscore")
class FrozenSiteAwareMIL(SiteAwareMIL):
    """The H015 topology; Stage-2 acoustic encoder always uses inference mode."""

    def __init__(self, dropout: float = .30, **kwargs: Any):
        super().__init__(dropout=dropout, **kwargs)
        self.segment_encoder.trainable = False

    def call(self, inputs: tuple[tf.Tensor, tf.Tensor, tf.Tensor],
             training: bool = False, return_attention: bool = False) -> Any:
        segments, segment_recording_index, site_ids = inputs
        n_recordings = tf.shape(site_ids)[0]
        # Freeze BatchNorm moving statistics and disable encoder dropout as well.
        acoustic_segments = self.segment_encoder(segments, training=False)
        counts = tf.math.unsorted_segment_sum(
            tf.ones_like(segment_recording_index, dtype=tf.float32),
            segment_recording_index, n_recordings)
        tf.debugging.assert_positive(counts)
        acoustic_recordings = tf.math.unsorted_segment_sum(
            acoustic_segments, segment_recording_index, n_recordings) / counts[:, None]
        attention_input = tf.concat([acoustic_recordings, self.site_embedding(site_ids)], -1)
        logits = self.attention_logit(self.attention_dropout(
            self.attention_hidden(attention_input), training=training))
        weights = masked_softmax(logits, tf.ones([n_recordings], dtype=tf.bool))
        acoustic_participant = tf.reduce_sum(weights[:, None] * acoustic_recordings, axis=0)
        probability = self.classifier_probability(self.classifier_dropout(
            self.classifier_hidden(acoustic_participant[None, :]), training=training))
        probability = tf.reshape(probability, [])
        return (probability, weights) if return_attention else probability

    def get_build_config(self) -> dict[str, Any]:
        return {"segment_shape": [40, 313, 1]}

    def build_from_config(self, config: dict[str, Any]) -> None:
        self((tf.zeros((1, *config["segment_shape"])),
              tf.constant([0]), tf.constant([0])), training=False)


def from_acoustic_model(acoustic: tf.keras.Model, seed: int) -> FrozenSiteAwareMIL:
    """Copy only this fold's Stage-1 encoder, initialize the MIL head anew."""
    tf.keras.utils.set_random_seed(seed)
    model = FrozenSiteAwareMIL()
    model((tf.zeros((1, 40, 313, 1)), tf.constant([0]), tf.constant([0])), training=False)
    layers = acoustic.layers[1:-1]  # Exclude InputLayer and sigmoid classifier.
    if [type(x).__name__ for x in layers] != [
        type(x).__name__ for x in model.segment_encoder.layers]:
        raise ValueError("Stage-1 encoder topology differs from H015 compact encoder")
    for source, destination in zip(layers, model.segment_encoder.layers, strict=True):
        if [w.shape for w in source.get_weights()] != [w.shape for w in destination.get_weights()]:
            raise ValueError("Encoder weight shapes differ")
        destination.set_weights(source.get_weights())
    model.segment_encoder.trainable = False
    if model.segment_encoder.trainable_variables:
        raise ValueError("Stage-2 encoder is not fully frozen")
    return model
