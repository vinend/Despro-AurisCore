"""Auxiliary Lung clip objective using the development annotation semantics."""


def frame_and_clip_loss(positive_weights, clip_frames, frames, *, focus_class=None):
    """Retain strong frame BCE and add BCE over complete, known clip labels."""
    import tensorflow as tf

    classes = len(positive_weights)
    weights = tf.constant(positive_weights, tf.float32)
    slots = frames // clip_frames
    retained = slots * clip_frames

    def loss(packed, scores):
        truth, mask = packed[..., :classes], packed[..., classes:2 * classes]
        point = tf.keras.ops.binary_crossentropy(truth, scores) * (1 - truth + truth * weights)
        strong = tf.math.divide_no_nan(tf.reduce_sum(point * mask, [1, 2]),
                                       tf.reduce_sum(mask, [1, 2]))
        shape = [-1, slots, clip_frames, classes]
        known = tf.reshape(mask[:, :retained] > 0, shape)
        y = tf.reshape(truth[:, :retained] > 0, shape)
        complete = tf.reduce_all(tf.reshape(packed[:, :retained, 2 * classes] > 0,
                                            [-1, slots, clip_frames]), axis=2)
        positive = tf.reduce_any(y & known, axis=2)
        eligible = (positive | tf.reduce_all(known, axis=2)) & complete[..., None]
        pooled = tf.reduce_max(tf.reshape(scores[:, :retained], shape), axis=2)
        auxiliary = tf.keras.ops.binary_crossentropy(tf.cast(positive, tf.float32), pooled)
        if focus_class is not None:
            # Favor difficult decisions for the affected source, including misses.
            correct_score = tf.where(positive, pooled, 1 - pooled)
            auxiliary *= tf.square(1 - correct_score)
            eligible &= ((packed[:, 0, 2 * classes + 1] > 0)[:, None, None]
                         & (tf.range(classes) == focus_class)[None, None, :])
        auxiliary = tf.math.divide_no_nan(
            tf.reduce_sum(tf.where(eligible, auxiliary, 0.), [1, 2]),
            tf.reduce_sum(tf.cast(eligible, tf.float32), [1, 2]),
        )
        return strong + .5 * auxiliary

    return loss
