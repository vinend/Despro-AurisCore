"""Loss-objective diagnostics; never fit models or change training policies."""
import numpy as np


def window_mass(truth: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Actual positive/negative mass after the trainer's per-window reduction."""
    if (truth.ndim != 2 or truth.shape != mask.shape or not len(truth)
            or not np.isin(truth, [0, 1]).all() or not np.isin(mask, [0, 1]).all()):
        raise ValueError('Aligned binary per-window truth and masks required')
    denominator = max(float(mask.sum()), 1.)
    return (truth * mask).sum(axis=0) / denominator, ((1 - truth) * mask).sum(axis=0) / denominator


def constant_optimum(positive: np.ndarray, negative: np.ndarray, weights: np.ndarray) -> list[float]:
    """Analytic constant scores minimizing the declared weighted BCE objective."""
    positive, negative, weights = map(lambda x: np.asarray(x, np.float64), (positive, negative, weights))
    if (positive.shape != negative.shape or positive.shape != weights.shape
            or not all(np.isfinite(x).all() for x in (positive, negative, weights))
            or np.any(positive < 0) or np.any(negative < 0) or np.any(weights <= 0)
            or np.any(positive + negative <= 0)):
        raise ValueError('Finite nonnegative support and positive matching weights required')
    return (weights * positive / (weights * positive + negative)).tolist()


def gradient_probe() -> dict:
    """Compare current clipping with public stable BCE on synthetic extreme logits."""
    import tensorflow as tf
    z = tf.Variable([[[30., -30., .5]]], dtype=tf.float32)
    y = tf.constant([[[0., 1., 1.]]])
    weights = tf.constant([[[6., 6., 6.]]])
    with tf.GradientTape(persistent=True) as tape:
        p = tf.keras.activations.sigmoid(z)
        clipped = tf.clip_by_value(p, 1e-7, 1 - 1e-7)
        legacy = tf.reduce_sum(-(y * tf.math.log(clipped) * weights + (1-y) * tf.math.log1p(-clipped)))
        stable = tf.reduce_sum(tf.keras.ops.binary_crossentropy(y, p, from_logits=False) * (1-y+y*weights))
        logits = tf.reduce_sum(tf.nn.sigmoid_cross_entropy_with_logits(labels=y, logits=z) * (1-y+y*weights))
    gradients = {name: tape.gradient(value, z).numpy().reshape(-1).tolist()
                 for name, value in [('legacy', legacy), ('keras_stable', stable), ('logits_reference', logits)]}
    del tape
    return {'logits': z.numpy().reshape(-1).tolist(), 'truth': y.numpy().reshape(-1).tolist(),
            'gradients': gradients, 'real_data_opened': False, 'optimizer_steps': 0}
