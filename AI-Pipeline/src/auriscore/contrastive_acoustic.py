"""H022-only hard-negative supervised acoustic separation at the 64-D layer."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import tensorflow as tf

from auriscore.cnn import _example_iterator
from auriscore.spectrogram import spectrogram_shape


def hard_negative_contrastive_loss(embeddings, labels, hard_flags, temperature: float = .10):
    """Mean -log(sum exp(sim to other Absent) / sum exp(sim to all others)).

    Anchors are only fold-local mined Absent segments. The denominator includes
    declared-site Present and other Absent segments. A batch lacking either
    class of comparison contributes zero; self-pairs are always excluded.
    """
    embeddings = tf.convert_to_tensor(embeddings)
    tf.debugging.assert_equal(tf.shape(embeddings)[-1], 64)
    z = tf.math.l2_normalize(embeddings, axis=-1)
    labels = tf.reshape(tf.cast(labels, tf.float32), [-1])
    hard_flags = tf.reshape(tf.cast(hard_flags, tf.bool), [-1])
    n = tf.shape(z)[0]
    same_negative = tf.logical_and(labels[:, None] < .5, labels[None, :] < .5)
    off_diag = tf.logical_not(tf.eye(n, dtype=tf.bool))
    same_negative = tf.logical_and(same_negative, off_diag)
    positives = labels[None, :] > .5
    anchor = tf.logical_and(hard_flags, labels < .5)
    valid = tf.logical_and(anchor, tf.logical_and(
        tf.reduce_any(same_negative, axis=1), tf.reduce_any(positives, axis=1)))
    logits = tf.matmul(z, z, transpose_b=True) / temperature
    floor = tf.cast(-1e9, logits.dtype)
    numerator = tf.reduce_logsumexp(tf.where(same_negative, logits, floor), axis=1)
    denominator = tf.reduce_logsumexp(tf.where(off_diag, logits, floor), axis=1)
    per_anchor = denominator - numerator
    return tf.math.divide_no_nan(tf.reduce_sum(tf.where(valid, per_anchor, 0.0)),
                                  tf.reduce_sum(tf.cast(valid, per_anchor.dtype)))


def stage1_dataset(frame, root: Path, config: dict, training: bool,
                   multipliers: dict[str, float] | None = None,
                   hard_ids: set[str] | None = None):
    """H021 Stage-1 examples plus a hard-negative flag, using identical windows."""
    expected = set(frame.recording_id.astype(str))
    if multipliers is not None and set(multipliers) != expected:
        raise ValueError("Multipliers must cover exactly the Stage-1 partition")
    if hard_ids is not None and not hard_ids.issubset(expected):
        raise ValueError("Hard negative outside Stage-1 partition")
    hard_ids = hard_ids or set()
    if frame.loc[frame.recording_id.astype(str).isin(hard_ids), "label"].ne("Absent").any():
        raise ValueError("Present recording marked as hard negative")
    f, t = spectrogram_shape(config)
    signature = ((tf.TensorSpec((f, t, 1), tf.float32), tf.TensorSpec((), tf.bool)),
                 tf.TensorSpec((), tf.float32), tf.TensorSpec((), tf.float32))

    def generate():
        rng = np.random.default_rng(int(config["seed"]))
        examples = _example_iterator(frame, root, config, True, training, rng, multipliers)
        for row, (x, y, weight) in zip(frame.itertuples(index=False), examples, strict=True):
            yield (x, np.bool_(str(row.recording_id) in hard_ids)), y, weight

    ds = tf.data.Dataset.from_generator(generate, output_signature=signature)
    ds = ds.apply(tf.data.experimental.assert_cardinality(len(frame)))
    if training:
        ds = ds.shuffle(min(len(frame), 4096), seed=int(config["seed"]), reshuffle_each_iteration=True)
    return ds.batch(int(config.get("cnn_batch_size", 32))).prefetch(tf.data.AUTOTUNE)


@tf.keras.utils.register_keras_serializable(package="auriscore")
class ContrastiveAcousticTrainer(tf.keras.Model):
    """Same H014 CNN/BCE, with one added training-only representation term."""

    def __init__(self, acoustic_model, temperature=.10, representation_loss_weight=.10, **kwargs):
        super().__init__(**kwargs)
        self.acoustic_model = acoustic_model
        self.temperature = float(temperature)
        self.representation_loss_weight = float(representation_loss_weight)
        self.joint = tf.keras.Model(acoustic_model.input,
                                    [acoustic_model.layers[-2].output, acoustic_model.output])
        self.loss_metric = tf.keras.metrics.Mean(name="loss")
        self.representation_metric = tf.keras.metrics.Mean(name="representation_loss")
        self.accuracy_metric = tf.keras.metrics.BinaryAccuracy(name="accuracy")
        self.sensitivity_metric = tf.keras.metrics.Recall(name="sensitivity")
        self.precision_metric = tf.keras.metrics.Precision(name="precision")
        self.roc_metric = tf.keras.metrics.AUC(name="roc_auc")
        self.pr_metric = tf.keras.metrics.AUC(name="pr_auc", curve="PR")

    @property
    def metrics(self):
        return [self.loss_metric, self.representation_metric, self.accuracy_metric,
                self.sensitivity_metric, self.precision_metric, self.roc_metric, self.pr_metric]

    def call(self, inputs, training=False):
        return self.acoustic_model(inputs, training=training)

    def _update_class_metrics(self, y, probability, weights):
        for metric in (self.accuracy_metric, self.sensitivity_metric, self.precision_metric,
                       self.roc_metric, self.pr_metric):
            metric.update_state(y, probability, sample_weight=weights)

    def train_step(self, data):
        (x, hard), y, weight = data
        with tf.GradientTape() as tape:
            embedding, probability = self.joint(x, training=True)
            bce = tf.keras.losses.binary_crossentropy(y[:, None], probability)
            classification = tf.reduce_mean(bce * weight)
            representation = hard_negative_contrastive_loss(embedding, y, hard, self.temperature)
            total = classification + self.representation_loss_weight * representation
        gradients = tape.gradient(total, self.acoustic_model.trainable_variables)
        self.optimizer.apply_gradients(zip(gradients, self.acoustic_model.trainable_variables, strict=True))
        self.loss_metric.update_state(total)
        self.representation_metric.update_state(representation)
        self._update_class_metrics(y[:, None], probability, weight)
        return {metric.name: metric.result() for metric in self.metrics}

    def test_step(self, data):
        (x, _), y, weight = data
        probability = self.acoustic_model(x, training=False)
        bce = tf.keras.losses.binary_crossentropy(y[:, None], probability)
        self.loss_metric.update_state(tf.reduce_mean(bce * weight))
        self.representation_metric.update_state(0.0)
        self._update_class_metrics(y[:, None], probability, weight)
        return {metric.name: metric.result() for metric in self.metrics}

    def get_config(self):
        return {**super().get_config(),
                "acoustic_model": tf.keras.utils.serialize_keras_object(self.acoustic_model),
                "temperature": self.temperature,
                "representation_loss_weight": self.representation_loss_weight}

    @classmethod
    def from_config(cls, config):
        config["acoustic_model"] = tf.keras.utils.deserialize_keras_object(config["acoustic_model"])
        return cls(**config)
