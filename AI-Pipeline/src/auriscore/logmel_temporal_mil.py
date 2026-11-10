"""Isolated R1-compatible temporal heads. No dataset IO or fitting entry point."""
import numpy as np
import tensorflow as tf


def build_model(checkpoint: str, seed: int) -> tf.keras.Model:
    """Copy R1 trunk, freeze BN/first two blocks; fine-tune final convolution."""
    tf.keras.utils.set_random_seed(seed)
    original = tf.keras.models.load_model(checkpoint, compile=False)
    expected = ['InputLayer'] + ['Conv2D','BatchNormalization','Activation','MaxPooling2D']*3
    if tuple(original.input.shape[1:]) != (40,313,1) or [type(x).__name__ for x in original.layers[:13]] != expected:
        raise ValueError('Incompatible R1 trunk')
    source = tf.keras.Model(original.input, original.layers[12].output)
    trunk = tf.keras.models.clone_model(source)
    trunk.set_weights(source.get_weights())
    for layer in trunk.layers:
        layer.trainable = layer is trunk.layers[9]  # final Conv2D only
    inputs = tf.keras.Input((40,313,1),name='logmel')
    features = trunk(inputs,training=False)  # BN uses recovered moving statistics
    sequence = tf.keras.layers.AveragePooling2D(pool_size=(5,1))(features)
    sequence = tf.keras.layers.Reshape((39,64),name='temporal_features')(sequence)
    hidden = tf.keras.layers.Conv1D(32,1,activation='relu',name='temporal_hidden')(sequence)
    murmur = tf.keras.layers.Dense(1,name='murmur_logits')(hidden)
    phase = tf.keras.layers.Dense(4,name='phase_logits')(hidden)
    return tf.keras.Model(inputs,dict(murmur_logits=murmur,phase_logits=phase))


def mil_probability(logits: tf.Tensor, mask: tf.Tensor) -> tf.Tensor:
    """Fixed normalized log-mean-exp logits at temperature 1, then sigmoid."""
    logits = tf.squeeze(logits,axis=-1)
    mask = tf.cast(mask,tf.bool)
    count = tf.reduce_sum(tf.cast(mask,logits.dtype),axis=-1)
    tf.debugging.assert_positive(count,message='No valid presence frames')
    pooled = tf.reduce_logsumexp(tf.where(mask,logits,tf.cast(-1e30,logits.dtype)),axis=-1)-tf.math.log(count)
    return tf.math.sigmoid(pooled)


def phase_loss(logits: tf.Tensor, labels: tf.Tensor, valid: tf.Tensor) -> tf.Tensor:
    """Mean official-phase CE; no valid target contributes exactly zero."""
    valid = tf.cast(valid,tf.bool)
    safe = tf.where(valid,labels,tf.zeros_like(labels))
    losses = tf.nn.sparse_softmax_cross_entropy_with_logits(labels=safe,logits=logits)
    return tf.math.divide_no_nan(tf.reduce_sum(tf.where(valid,losses,0.)),tf.reduce_sum(tf.cast(valid,tf.float32)))


def participant_probability(recording_probabilities: np.ndarray) -> float:
    """Equal recording mean; empty/nonfinite recordings must fail explicitly."""
    x = np.asarray(recording_probabilities,dtype=float)
    if x.ndim != 1 or not x.size or not np.isfinite(x).all() or np.any((x<0)|(x>1)):
        raise ValueError('Invalid recording probabilities')
    return float(x.mean())
